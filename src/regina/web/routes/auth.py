"""Routy přihlášení a odhlášení (design.md 4.2, sekce 7).

Tři veřejné/přihlášené cesty tvoří celý přihlašovací tok:

- `GET /login` — vygeneruje `state` a `nonce`, uloží je do krátkodobé
  podepsané cookie a přesměruje na přihlašovací obrazovku poskytovatele
  (URL pochází z discovery, ne z kódu).
- `GET /auth/callback` — vymění kód za tokeny, ověří ID token, spáruje osobu,
  založí session a přesměruje na `/moje`.
- `POST /odhlaseni` — zneplatní session a přesměruje na `/login`.

Párování osoby (design.md 4.2 krok 6) je v `_match_person`: podle
`oidc_subject`, jinak podle e-mailu s doplněním subjektu, jinak nový řádek
s rolí `USER`. Tím lze osobu zapsat do odpovědné trojice dřív, než se poprvé
přihlásí (R11.7).

Autentizační guardy pro chráněné cesty a handler 403 jsou úkol 6.3, CSRF je
úkol 6.4 — zde se neimplementují. Routy jsou ale strukturované tak, aby se
daly doplnit: `/odhlaseni` je `POST`, session se čte přes `read_session`.

Logování (design.md 11, R12.10): přihlášení i odhlášení se loguje s
**identifikátorem osoby**, nikdy s e-mailem ani jménem. Čitelná identita
zůstává v auditní tabulce chráněné rolí.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from regina.auth.csrf import CsrfProtect
from regina.auth.oidc import AuthenticatedIdentity, OidcClient, OidcError
from regina.auth.session import (
    OidcState,
    SessionUser,
    clear_oidc_state,
    clear_session,
    create_session_cookie,
    read_oidc_state,
    read_session,
    stash_oidc_state,
)
from regina.config import Settings
from regina.db.models.users import User
from regina.db.session import session_scope
from regina.domain.enums import Role, RoleSource
from regina.logging import get_logger
from regina.repositories import users as users_repo
from regina.services import audit as audit_service

logger = get_logger("regina.auth")

router = APIRouter(tags=["auth"])

# Cíl po přihlášení a stránka pro nepřihlášené (design.md sekce 7).
_LANDING_PATH = "/moje"
_LOGIN_PATH = "/login"
# Chybu přihlášení hlásíme přesměrováním s neutrálním příznakem, ne stack tracem
# (design.md sekce 8): chybové stránky nikdy neukazují detaily.
_LOGIN_ERROR_PATH = "/login?chyba=prihlaseni"


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _oidc_client(request: Request) -> OidcClient:
    return request.app.state.oidc_client


@router.get("/login", include_in_schema=False)
def login(request: Request) -> RedirectResponse:
    """Zahájí přihlašovací tok.

    Vygeneruje náhodný `state` (ochrana callbacku proti CSRF) a `nonce`
    (vazba ID tokenu na tento pokus), uloží je do krátkodobé podepsané cookie
    a přesměruje na authorization endpoint poskytovatele.
    """
    settings = _settings(request)
    client = _oidc_client(request)

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)

    try:
        authorization_url = client.create_authorization_redirect(state=state, nonce=nonce)
    except OidcError:
        logger.warning("login_redirect_failed", extra={"event": "auth.login.failed"})
        return RedirectResponse(_LOGIN_ERROR_PATH, status_code=303)

    response = RedirectResponse(authorization_url, status_code=303)
    stash_oidc_state(response, settings, OidcState(state=state, nonce=nonce))
    return response


@router.get("/auth/callback", include_in_schema=False)
def auth_callback(request: Request) -> RedirectResponse:
    """Dokončí přihlášení: ověří token, spáruje osobu, založí session.

    Kroky odpovídají design.md 4.2 (5–8). `state` a `nonce` se čtou z dočasné
    cookie a předávají do ověření; nesouhlas nebo chybějící stav vede na
    chybovou stránku bez detailů.
    """
    settings = _settings(request)
    client = _oidc_client(request)

    stored_state = read_oidc_state(request, settings)
    if stored_state is None:
        logger.warning("callback_missing_state", extra={"event": "auth.callback.no_state"})
        return _redirect_login_error(settings)

    try:
        identity = client.fetch_identity(
            authorization_response_url=str(request.url),
            state=stored_state.state,
            nonce=stored_state.nonce,
        )
    except OidcError:
        # Bez stack trace a bez detailů poskytovatele (design.md sekce 8).
        logger.warning("callback_identity_failed", extra={"event": "auth.callback.failed"})
        return _redirect_login_error(settings)

    # Párování osoby a audit SIGN_IN běží v jedné transakci (design.md 5.2).
    with session_scope() as session:
        user = _match_person(session, identity)
        session_user = SessionUser(
            subject=identity.subject,
            name=user.display_name,
            email=user.email,
            role=Role(user.role),
        )
        audit_service.sign_in(session, user)
        # Identifikátor osoby do logu, nikdy e-mail ani jméno (R12.10).
        logger.info(
            "sign_in",
            extra={"event": "auth.sign_in", "user_id": str(user.id)},
        )

    response = RedirectResponse(_LANDING_PATH, status_code=303)
    create_session_cookie(response, settings, session_user)
    clear_oidc_state(response, settings)
    return response


@router.post("/odhlaseni", include_in_schema=False, dependencies=[CsrfProtect])
def logout(request: Request) -> RedirectResponse:
    """Odhlášení: zneplatní session a zapíše audit `SIGN_OUT` (R1.8).

    Odhlášení u poskytovatele se neprovádí — je to oddělená odpovědnost
    a v README je uvedené jako vědomé omezení (design.md 4.2).

    Formulář odhlášení nese CSRF token (úkol 6.4): závislost `CsrfProtect`
    ověří skryté pole `csrf_token` proti session. Šablona (sekce 8) pole
    doplní přes `get_csrf_token(request)`.
    """
    settings = _settings(request)
    session_user = read_session(request, settings)

    if session_user is not None:
        with session_scope() as session:
            user = users_repo.get_by_oidc_subject(session, session_user.subject)
            audit_service.sign_out(session, user)
            logger.info(
                "sign_out",
                extra={
                    "event": "auth.sign_out",
                    "user_id": str(user.id) if user is not None else None,
                },
            )

    response = RedirectResponse(_LOGIN_PATH, status_code=303)
    clear_session(response, settings)
    return response


def _redirect_login_error(settings: Settings) -> RedirectResponse:
    response = RedirectResponse(_LOGIN_ERROR_PATH, status_code=303)
    # I při chybě uklidíme dočasný stav, ať v prohlížeči nezůstává viset.
    clear_oidc_state(response, settings)
    return response


def _match_person(session: Session, identity: AuthenticatedIdentity) -> User:
    """Spáruje ověřenou identitu s řádkem v `users` (design.md 4.2 krok 6).

    1. Podle `oidc_subject` — po prvním přihlášení trvalá identita osoby.
    2. Jinak podle e-mailu z claimu; při shodě se `oidc_subject` doplní. Tím
       se osoba zapsaná do odpovědné trojice před prvním přihlášením (R11.7)
       spáruje se svou identitou z IdP.
    3. Jinak vznikne nový řádek s rolí `USER` (R2.4).

    Vždy se aktualizuje `last_login_at`. Role se zde **nepřepisuje** podle
    claimu — správu rolí řeší úkol 17.2; lokální role má u mock poskytovatele
    přednost (R11.6). U nově založené osoby je výchozí role `USER`.
    """
    now = datetime.now(timezone.utc)

    user = users_repo.get_by_oidc_subject(session, identity.subject)
    if user is not None:
        user.last_login_at = now
        return user

    user = users_repo.get_by_email(session, identity.email)
    if user is not None:
        # Doplníme subjekt k dosud nepřihlášené osobě z adresáře (R11.7).
        user.oidc_subject = identity.subject
        if not user.display_name and identity.name:
            user.display_name = identity.name
        user.last_login_at = now
        return user

    user = User(
        oidc_subject=identity.subject,
        email=identity.email,
        display_name=identity.name or identity.email or identity.subject,
        role=Role.USER,
        role_source=RoleSource.LOCAL,
        last_login_at=now,
    )
    session.add(user)
    # Flush přidělí primární klíč, aby ho mohl použít auditní zápis SIGN_IN.
    session.flush()
    return user
