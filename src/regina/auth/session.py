"""Podepsaná session cookie a dočasný stav OIDC (design.md 4.2, sekce 2).

Bez tabulky sessions. Stav přihlášení nese **podepsaná cookie** (`itsdangerous`),
takže se nikam neukládá a server ji jen ověří podpisem. Klíčem je
`SESSION_SECRET` z konfigurace.

**Co session obsahuje** (design.md 4.2): pouze `subject`, `jméno`, `e-mail`
a `roli`. Žádný access ani refresh token — nepotřebujeme mluvit s žádným API
poskytovatele, takže je po odvození identity zahazujeme.

**Příznaky cookie**: `HttpOnly` (JS ji nepřečte), `SameSite=Lax` (brání CSRF
z cizích stránek u navigačních požadavků), `Secure` řízené konfigurací
(`SESSION_COOKIE_SECURE` — `false` pro lokální HTTP, `true` v provozu),
`Max-Age` z `SESSION_MAX_AGE_SECONDS`.

Modul spravuje i **krátkodobý podepsaný stav** mezi `GET /login` a
`GET /auth/callback`: nese `state` a `nonce`, které chrání callback proti CSRF
a přehrání ID tokenu. Používá stejný podpisový klíč, ale oddělený „salt", aby
se obě cookie nedaly zaměnit.
"""

from __future__ import annotations

from dataclasses import dataclass

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.requests import Request
from starlette.responses import Response

from regina.config import Settings
from regina.domain.enums import Role

# Oddělené „salt" hodnoty pro dvě různé cookie podepsané stejným tajemstvím.
# Bez nich by šla platná session cookie podstrčit místo stavu přihlášení a
# naopak. Salt je součástí odvození podpisu, takže podpis jedné neověří druhou.
_SESSION_SALT = "regina.session"
_OIDC_STATE_SALT = "regina.oidc-state"

# Dočasný stav přihlášení žije jen mezi přesměrováním na poskytovatele a
# návratem na callback. Deset minut je pohodlná rezerva na přihlašovací
# obrazovku a přitom krátké okno pro případné zneužití.
_OIDC_STATE_MAX_AGE_SECONDS = 10 * 60
_OIDC_STATE_COOKIE_NAME = "regina_oidc_state"


@dataclass(frozen=True)
class SessionUser:
    """Přihlášená osoba načtená z session cookie.

    Drží jen to, co je v cookie: subjekt z IdP, jméno, e-mail a roli. Nemá
    identifikátor z databáze — ten dohledávají vrstvy, které pracují se
    záznamy. `role` je `Role`, takže se dá rovnou předat autorizačním
    pravidlům v `domain/rules.py` (ta porovnávají proti `Role.ADMIN`).
    """

    subject: str
    name: str
    email: str
    role: Role


@dataclass(frozen=True)
class OidcState:
    """Krátkodobý stav mezi `/login` a `/auth/callback`.

    `state` chrání callback proti CSRF, `nonce` váže ID token na tento
    konkrétní přihlašovací pokus.
    """

    state: str
    nonce: str


def _session_serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt=_SESSION_SALT)


def _state_serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt=_OIDC_STATE_SALT)


# -- Session cookie ------------------------------------------------------


def create_session_cookie(
    response: Response, settings: Settings, session_user: SessionUser
) -> None:
    """Zapíše podepsanou session cookie do odpovědi.

    Ukládá pouze subjekt, jméno, e-mail a roli — žádné tokeny (design.md 4.2).
    Příznaky: `HttpOnly`, `SameSite=Lax`, `Secure` z konfigurace, `Max-Age`
    z konfigurace.
    """
    payload = {
        "sub": session_user.subject,
        "name": session_user.name,
        "email": session_user.email,
        "role": str(session_user.role),
    }
    token = _session_serializer(settings).dumps(payload)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


def read_session(request: Request, settings: Settings) -> SessionUser | None:
    """Přečte a ověří session cookie. Vrací `None`, když chybí nebo neplatí.

    Neplatnost (chybějící cookie, poškozený podpis, vypršelá platnost, neznámá
    role) se vždy překlopí na `None` — volající s tím zachází jako s
    nepřihlášeným požadavkem a přesměruje na `/login`. Chybu nevyhazujeme, aby
    zastaralá cookie nezpůsobila 500.
    """
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None

    try:
        payload = _session_serializer(settings).loads(
            token, max_age=settings.session_max_age_seconds
        )
    except (BadSignature, SignatureExpired):
        return None

    if not isinstance(payload, dict):
        return None

    subject = payload.get("sub")
    raw_role = payload.get("role")
    if not subject or raw_role not in (Role.USER, Role.ADMIN):
        return None

    return SessionUser(
        subject=str(subject),
        name=str(payload.get("name") or ""),
        email=str(payload.get("email") or ""),
        role=Role(raw_role),
    )


def clear_session(response: Response, settings: Settings) -> None:
    """Smaže session cookie z prohlížeče (odhlášení)."""
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


# -- Dočasný stav OIDC mezi /login a /auth/callback ----------------------


def stash_oidc_state(response: Response, settings: Settings, state: OidcState) -> None:
    """Uloží `state` a `nonce` do krátkodobé podepsané cookie.

    Cookie je `HttpOnly`, `SameSite=Lax`, `Secure` z konfigurace a žije jen
    krátce (`_OIDC_STATE_MAX_AGE_SECONDS`). Callback ji přečte a hned smaže.
    """
    token = _state_serializer(settings).dumps({"state": state.state, "nonce": state.nonce})
    response.set_cookie(
        key=_OIDC_STATE_COOKIE_NAME,
        value=token,
        max_age=_OIDC_STATE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


def read_oidc_state(request: Request, settings: Settings) -> OidcState | None:
    """Přečte a ověří dočasný stav OIDC. Vrací `None`, když chybí nebo neplatí."""
    token = request.cookies.get(_OIDC_STATE_COOKIE_NAME)
    if not token:
        return None

    try:
        payload = _state_serializer(settings).loads(
            token, max_age=_OIDC_STATE_MAX_AGE_SECONDS
        )
    except (BadSignature, SignatureExpired):
        return None

    if not isinstance(payload, dict):
        return None

    state = payload.get("state")
    nonce = payload.get("nonce")
    if not state or not nonce:
        return None

    return OidcState(state=str(state), nonce=str(nonce))


def clear_oidc_state(response: Response, settings: Settings) -> None:
    """Smaže dočasnou stavovou cookie po dokončení callbacku."""
    response.delete_cookie(
        key=_OIDC_STATE_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )
