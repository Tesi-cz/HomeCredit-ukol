"""Autentizační a autorizační závislosti FastAPI (design.md 4.3, sekce 7).

Tady se autorizace **vynucuje**. Rozhodnutí ale nevzniká zde — leží v čistých
funkcích v `domain/rules.py`. Tento modul je jen most: z požadavku odvodí
aktuálního aktéra, zavolá pravidlo a při zamítnutí vyhodí `AuthorizationError`.
Tytéž funkce z `domain/rules.py` volá později i šablona při rozhodování, zda
vykreslit tlačítko (design.md 4.3 „jedno pravidlo, dvě použití"). Logika se
proto nikde neduplikuje.

**Aktér.** Session cookie nese jen subjekt, jméno, e-mail a roli — nikdy
identifikátor z databáze (`auth/session.py`). Autorizace nad záznamy i auditní
zápis však identitu z databáze potřebují: `can_edit` porovnává `actor.id` proti
odpovědné trojici (R2.6) a audit ukládá `actor_user_id`. `require_login` proto
session dohledá na řádek `users` podle `oidc_subject` a vrátí `CurrentUser`,
který slouží jako aktér pro pravidla (`.id`, `.role`) i pro audit
(`.id`, `.email`, `.name`).

**Nepřihlášený požadavek.** Když session chybí nebo neplatí, `require_login`
vyhodí `LoginRequired`, jejíž handler přesměruje na `/login` (R1.3). Vůči
uživateli je to zahájení přihlášení, ne chyba.

**Zamítnutí se loguje na jednom místě.** Guard jen vyhodí `AuthorizationError`
s popisem pokusu. Globální handler registrovaný v `main.create_app` zapíše
audit `ACCESS_DENIED` (R2.3), zaloguje odepření **jedenkrát** (ne v každé
routě, design.md 4.3) a vrátí stránku 403 bez stack trace a bez konfigurace
(design.md sekce 8).

Rozdělení guardů odpovídá tabulce cest v design.md sekci 7:

- guardy jen nad aktérem — `require_override_classification`,
  `require_decommission`, `require_read_audit`, `require_export`,
  `require_manage_roles`;
- guardy vázané na konkrétní záznam — `require_can_edit`,
  `require_can_set_classification` — potřebují cílovou aplikaci načtenou podle
  `{id}` z cesty, proto ji dohledají a předají pravidlu spolu s aktérem.

CSRF je úkol 6.4 a zde se neřeší.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Request
from sqlalchemy.orm import Session
from starlette.responses import HTMLResponse, RedirectResponse, Response

from regina.auth.session import read_session
from regina.config import Settings
from regina.db.models.applications import Application
from regina.db.session import get_session, session_scope
from regina.domain import rules
from regina.domain.enums import Role
from regina.logging import get_logger
from regina.repositories import users as users_repo
from regina.services import audit as audit_service

_logger = get_logger("regina.auth")


@dataclass(frozen=True)
class CurrentUser:
    """Přihlášená osoba doplněná o identitu z databáze.

    Spojuje session (subjekt, role) s řádkem `users` (databázový `id`, jméno,
    e-mail). Použitelná přímo jako:

    - aktér pravidel v `domain/rules.py` — má `id` a `role`;
    - aktér auditního zápisu v `services/audit.py` — má `id`, `email`, `name`.

    `name` schválně kopíruje `users.display_name`, aby odpovídalo strukturálnímu
    typu `AuditActor` (ten čte `actor.name`).
    """

    id: uuid.UUID
    subject: str
    name: str
    email: str
    role: Role


class LoginRequired(Exception):
    """Nepřihlášený požadavek na chráněnou cestu (R1.3).

    Není to chyba — handler ji překlopí na přesměrování na `/login`, čímž se
    zahájí přihlašovací tok.
    """


class AuthorizationError(Exception):
    """Přihlášený aktér nemá právo na požadovanou operaci (R2.3).

    Nese dost kontextu pro auditní zápis `ACCESS_DENIED`: kdo se o co pokusil.
    `actor` může být `None` jen teoreticky (guard běží až za `require_login`),
    drží se ale kvůli robustnosti handleru. `entity_type`/`entity_id` popisují
    cíl pokusu, `summary` je krátký český popis do auditu (design.md sekce 8).
    """

    def __init__(
        self,
        *,
        actor: CurrentUser | None,
        summary: str,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
    ) -> None:
        super().__init__(summary)
        self.actor = actor
        self.summary = summary
        self.entity_type = entity_type
        self.entity_id = entity_id


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def require_login(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> CurrentUser:
    """Vrátí aktuálního aktéra, nebo zahájí přihlášení.

    Přečte a ověří session cookie (`read_session`) a dohledá k ní řádek
    `users` podle `oidc_subject`. Chybějící session, neplatný podpis nebo
    nedohledatelná osoba vedou na `LoginRequired` → přesměrování na `/login`
    (R1.3). Osoba musí v `users` existovat: řádek zakládá callback při prvním
    přihlášení (`web/routes/auth.py`), takže platná session bez řádku by byla
    nekonzistence, na kterou je správné reagovat novým přihlášením.
    """
    settings = _settings(request)
    session_user = read_session(request, settings)
    if session_user is None:
        raise LoginRequired()

    # Dohledání osoby podle subjektu z IdP (auth/session.py, database.md 3).
    user = users_repo.get_by_oidc_subject(session, session_user.subject)
    if user is None:
        raise LoginRequired()

    return CurrentUser(
        id=user.id,
        subject=session_user.subject,
        name=user.display_name,
        email=user.email,
        role=Role(user.role),
    )


CurrentUserDep = Annotated[CurrentUser, Depends(require_login)]
SessionDep = Annotated[Session, Depends(get_session)]


# -- Guardy nad aktérem (nezávislé na konkrétním záznamu) ----------------


def require_override_classification(actor: CurrentUserDep) -> CurrentUser:
    """Guard cesty přepisu klasifikace — vyhrazeno roli Admin (R7.1, R7.6)."""
    if not rules.can_override_classification(actor):
        raise AuthorizationError(
            actor=actor,
            summary="Pokus o přepis klasifikace bez oprávnění.",
        )
    return actor


def require_decommission(actor: CurrentUserDep) -> CurrentUser:
    """Guard vyřazení záznamu — vyhrazeno roli Admin (R5.12)."""
    if not rules.can_decommission(actor):
        raise AuthorizationError(
            actor=actor,
            summary="Pokus o vyřazení záznamu bez oprávnění.",
        )
    return actor


def require_read_audit(actor: CurrentUserDep) -> CurrentUser:
    """Guard čtení auditního logu — vyhrazeno roli Admin (R8.4)."""
    if not rules.can_read_audit(actor):
        raise AuthorizationError(
            actor=actor,
            summary="Pokus o čtení auditního logu bez oprávnění.",
        )
    return actor


def require_export(actor: CurrentUserDep) -> CurrentUser:
    """Guard exportu CSV — vyhrazeno roli Admin (R10.1, R10.2, R10.4)."""
    if not rules.can_export(actor):
        raise AuthorizationError(
            actor=actor,
            summary="Pokus o export CSV bez oprávnění.",
        )
    return actor


def require_manage_roles(actor: CurrentUserDep) -> CurrentUser:
    """Guard správy rolí — vyhrazeno roli Admin (R11.2)."""
    if not rules.can_manage_roles(actor):
        raise AuthorizationError(
            actor=actor,
            summary="Pokus o správu rolí bez oprávnění.",
        )
    return actor


# -- Guardy vázané na konkrétní záznam -----------------------------------


def load_application(
    session: SessionDep,
    app_id: Annotated[uuid.UUID, Path(alias="id")],
) -> Application:
    """Načte aplikaci podle `{id}` z cesty, nebo vyhodí 404.

    Autorizace nad záznamem (`can_edit`, `can_set_classification`) potřebuje
    cílovou aplikaci s odpovědnou trojicí. Neexistující záznam je 404
    (design.md sekce 8), ne 403 — o oprávnění nemá smysl rozhodovat nad tím,
    co neexistuje.
    """
    app = session.get(Application, app_id)
    if app is None:
        raise HTTPException(status_code=404)
    return app


ApplicationDep = Annotated[Application, Depends(load_application)]


def require_can_edit(actor: CurrentUserDep, app: ApplicationDep) -> Application:
    """Guard editace záznamu — člen odpovědné trojice, nebo Admin (R5.10).

    Rozhodnutí dělá `rules.can_edit`, které porovnává `actor.id` proti trojici
    (R2.6). Vrací načtený záznam, aby ho routa nemusela načítat podruhé.
    """
    if not rules.can_edit(actor, app):
        raise AuthorizationError(
            actor=actor,
            summary="Pokus o editaci cizího záznamu bez oprávnění.",
            entity_type="APPLICATION",
            entity_id=app.id,
        )
    return app


def require_can_set_classification(
    actor: CurrentUserDep, app: ApplicationDep
) -> Application:
    """Guard zápisu klasifikace — člen odpovědné trojice, nebo Admin.

    Zápis klasifikace *vlastního* záznamu (R6). Přepis *cizího* záznamu je
    samostatná schopnost `require_override_classification` (R7).
    """
    if not rules.can_set_classification(actor, app):
        raise AuthorizationError(
            actor=actor,
            summary="Pokus o zápis klasifikace bez oprávnění.",
            entity_type="APPLICATION",
            entity_id=app.id,
        )
    return app


# -- Globální handlery výjimek (registruje main.create_app) --------------
#
# Handlery jsou zde, ne v `main.py`, aby vynucení i jeho následky (audit,
# log, 403) bydlely u pravidel, která je vyvolávají. `main.create_app` je jen
# zaregistruje na aplikaci — viz `register_auth_handlers`.

_LOGIN_PATH = "/login"


def render_forbidden(request: Request) -> HTMLResponse:
    """Vykreslí stylovanou stránku 403 (design.md sekce 8, úkol 8.4).

    Sdílený vstupní bod pro oba zdroje 403 — zamítnutou autorizaci
    (`AuthorizationError`) i selhání ověření formuláře (`CsrfError` v
    `auth/csrf.py`), aby obě vypadaly stejně. Renderuje se přes
    `app.state.templates` s **minimálním** kontextem: šablona `errors/403.html`
    dědí z `errors/error_layout.html`, který nepotřebuje přihlášenou osobu ani
    navigaci, takže stránka nespadne ani u nepřihlášeného požadavku. Ukazuje se
    jen kód, český popis a odkaz zpět — žádný stack trace ani konfigurace.
    """
    templates = request.app.state.templates
    context = {
        "request": request,
        "app_name": request.app.state.settings.app_name,
    }
    return templates.TemplateResponse(
        request, "errors/403.html", context, status_code=403
    )


def _handle_login_required(request: Request, exc: LoginRequired) -> Response:
    """Nepřihlášený požadavek → přesměrování na `/login` (R1.3).

    Přesměrování `303 See Other`, aby i po `POST` následoval `GET /login`.
    """
    return RedirectResponse(_LOGIN_PATH, status_code=303)


def _handle_authorization_error(request: Request, exc: AuthorizationError) -> Response:
    """Zamítnutí na jednom místě: audit `ACCESS_DENIED`, log, stránka 403.

    Sem stéká každý zamítnutý pokus ze všech guardů. Audit se zapisuje **zde**
    (R2.3) a odepření se loguje **jedenkrát** (design.md 4.3), takže routy o
    tom nic vědět nemusí. Audit běží ve vlastní transakci (`session_scope`),
    aby se zapsal i tehdy, když se transakce požadavku odrolovala.
    """
    with session_scope() as session:
        audit_service.access_denied(
            session,
            exc.actor,
            summary=exc.summary,
            entity_type=exc.entity_type,
            entity_id=exc.entity_id,
        )

    # Identifikátor osoby do logu, nikdy e-mail ani jméno (R12.10).
    _logger.warning(
        "access_denied",
        extra={
            "event": "auth.access_denied",
            "user_id": str(exc.actor.id) if exc.actor is not None else None,
            "entity_type": exc.entity_type,
            "entity_id": str(exc.entity_id) if exc.entity_id is not None else None,
        },
    )

    # 403 bez stack trace a bez konfigurace (design.md sekce 8), stylovaná
    # šablona (úkol 8.4).
    return render_forbidden(request)


def register_auth_handlers(app: FastAPI) -> None:
    """Zaregistruje handlery `LoginRequired` a `AuthorizationError` na aplikaci.

    Volá `main.create_app`. Drží vynucení autorizace na jednom místě: guardy
    vyhazují výjimky, tyto handlery je proměňují na přesměrování, respektive na
    audit + log + stránku 403.
    """
    app.add_exception_handler(LoginRequired, _handle_login_required)
    app.add_exception_handler(AuthorizationError, _handle_authorization_error)
