"""Obrazovka správy uživatelů `/uzivatele` (úkol 17.2, ui.md sekce 8, R11).

Svislý řez od cesty po vykreslenou tabulku a přepnutí role. Vyhrazeno roli
Admin — guard `require_manage_roles` vynutí `rules.can_manage_roles` **na
backendu** (R11.2): přihlášený uživatel role User dostane 403 + audit
`ACCESS_DENIED`, i když mu sidebar položku „Uživatelé" nikdy neukázal (nav ji
roli User skrývá, R2.5). Skrytí je pohodlnost, vynucení leží zde.

**GET `/uzivatele`** vypíše osoby známé aplikaci (celý adresář přes
`users.list_all`) se sloupci Jméno, E-mail, Pozice, Role (badge, český popisek),
Zdroj role (český popisek přes `labels.label`) a Akce (R11.1). Každý řádek nese
formulář `POST` přepínající roli mezi Uživatel a Správce (R11.2) s CSRF tokenem.

**POST `/uzivatele/{id}/role`** načte dotčenou osobu a zavolá
`services.users.set_role`, který změní roli, nastaví zdroj role na lokální
(R11.6) a zapíše audit `ROLE_CHANGED` (R11.4) — vše v transakci požadavku
(commit řeší `get_session`). Pojistku posledního správce (R11.5) vynucuje
služba: při pokusu odebrat poslední adminská práva vyhodí `LastAdminError` a
routa přesměruje zpět s českým chybovým hlášením. Vynucení autorizace i pojistky
je na backendu — přímý POST od role User skončí 403 + `ACCESS_DENIED` i bez
tlačítka v rozhraní (R2.2, R11.2).

**Obrazovka nezakládá ani nemaže identity (R11.3)** — to zůstává na
poskytovateli identity a je na obrazovce uvedeno textem (ui.md sekce 8).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from starlette.responses import RedirectResponse

from regina.auth.csrf import CsrfProtect
from regina.auth.deps import CurrentUser, SessionDep, require_manage_roles
from regina.domain.enums import Role, RoleSource
from regina.repositories import users as users_repo
from regina.services.users import LastAdminError, set_role
from regina.web.flash import redirect_with_flash
from regina.web.templating import page_context

router = APIRouter(tags=["uzivatele"])

# Guard aktéra vyhrazený roli Admin (R11.2). Vrací přihlášeného aktéra.
RoleManagerDep = Annotated[CurrentUser, Depends(require_manage_roles)]

# Cesta, kam vede úspěch i chyba přepnutí role (Post/Redirect/Get).
_LIST_PATH = "/uzivatele"


@router.get("/uzivatele", include_in_schema=False)
def users_list(
    request: Request,
    user: RoleManagerDep,
    session: SessionDep,
) -> HTMLResponse:
    """Vykreslí seznam osob se správou rolí (R11.1, R11.2, ui.md sekce 8).

    Vyhrazeno roli Admin (`require_manage_roles`); role User skončí 403 + audit
    `ACCESS_DENIED` (R11.2, R2.2). Vypíše celý adresář (`users.list_all`) se
    sloupci Jméno / E-mail / Pozice / Role / Zdroj role / Akce. Přepínač role
    u vlastního účtu se nevykresluje jako aktivní tlačítko — vlastní roli si
    správce odebrat nemůže (R11.5, ui.md sekce 8); skutečnou pojistku ale
    vynucuje služba na backendu, ne toto skrytí.

    Pro každou osobu se dopočítá, na jakou roli by ji přepnutí přepnulo
    (Uživatel ↔ Správce) a její český popisek, aby šablona nemusela obsahovat
    žádnou logiku výčtů (R13.11).
    """
    people = users_repo.list_all(session)

    # Pro každý řádek předpočítáme cílovou roli přepnutí a příznak „je to
    # aktuální aktér" — obojí patří sem, ne do šablony.
    rows = []
    for person in people:
        current = Role(person.role)
        target = Role.USER if current == Role.ADMIN else Role.ADMIN
        rows.append(
            {
                "person": person,
                "role": current,
                "role_source": RoleSource(person.role_source),
                "target_role": target,
                "is_self": person.id == user.id,
            }
        )

    context = page_context(
        request,
        user=user,
        active_nav="uzivatele",
        section_title="Uživatelé",
        rows=rows,
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "users/list.html", context)


@router.post(
    "/uzivatele/{id}/role",
    include_in_schema=False,
    dependencies=[CsrfProtect],
    response_model=None,
)
async def change_user_role(
    request: Request,
    user: RoleManagerDep,
    session: SessionDep,
    id: uuid.UUID,
) -> RedirectResponse:
    """Přepne roli osoby, nebo vrátí chybu pojistky (R11.2, R11.4, R11.5).

    Autorizace je vynucena **backendem**: guard `require_manage_roles` odmítne
    přímý POST od role User — 403 + audit `ACCESS_DENIED`, i když v rozhraní
    žádné tlačítko nebylo (R2.2, R11.2). CSRF token ověřil `CsrfProtect`.

    Postup:

    1. Načte dotčenou osobu podle `{id}`; neexistující → přesměrování zpět s
       chybou (obrazovka identity nezakládá ani nemaže, R11.3).
    2. Přečte cílovou roli z formulářového pole `role` (strojový kód). Neplatná
       hodnota → chyba zpět.
    3. Zavolá `services.users.set_role`, který změní roli, nastaví zdroj role
       na lokální (R11.6) a zapíše audit `ROLE_CHANGED` (R11.4) v transakci
       požadavku. Pojistka posledního správce (R11.5) vyhodí `LastAdminError`
       → přesměrování zpět s českým chybovým hlášením.
    4. Úspěch → přesměrování na `/uzivatele` s potvrzením (R13.8).
    """
    target = users_repo.get_by_id(session, id)
    if target is None:
        return redirect_with_flash(
            _LIST_PATH,
            "Osoba nebyla nalezena.",
            type="error",
        )

    form = await request.form()
    raw_role = form.get("role")
    try:
        new_role = Role(raw_role) if isinstance(raw_role, str) else None
    except ValueError:
        new_role = None
    if new_role is None:
        return redirect_with_flash(
            _LIST_PATH,
            "Neplatná role.",
            type="error",
        )

    try:
        set_role(session, user, target, new_role)
    except LastAdminError:
        return redirect_with_flash(
            _LIST_PATH,
            "V systému musí zůstat alespoň jeden správce. "
            "Poslední adminská práva nelze odebrat.",
            type="error",
        )

    return redirect_with_flash(_LIST_PATH, "Role byla změněna.")
