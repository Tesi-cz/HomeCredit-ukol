"""Routa obrazovky „Moje aplikace" `/moje` (úkol 12.2, ui.md sekce 4).

Vstupní obrazovka po přihlášení. Zobrazuje záznamy, kde je přihlášená osoba
členem odpovědné trojice — tedy ty, které smí editovat (R3.10). Je to svislý
řez od parametrů URL po vykreslenou mřížku karet, postavený stejně jako výpis
registru (`web/routes/registry.py`, úkol 11.2): routa **nefiltruje** ani
nepočítá v paměti, jen sesbírá parametry, přeloží je na `ListFilters` a předá
je repozitáři.

**Rozdíl proti registru.** Místo `list_applications` volá
`list_my_applications(session, user.id, filters)` (úkol 12.1), která výpis zúží
na trojici podle **identity** přihlášené osoby — nikdy podle jména (R4.2).
Autoritativní je `user.id` z guardu `require_login`; případný `trio_member_id`
ve `filters` repozitář ignoruje, takže routa nemůže omylem zobrazit cizí
záznamy.

**Kdo obrazovku vidí.** Kdokoli přihlášený (`require_login`); žádné omezení na
roli. Prázdný stav (uživatel není v žádné trojici, R3.12) i prázdný výsledek
hledání řeší šablona.

**Jméno vlastníka.** Výpis vrací `Application`, ne osoby. Karta ukazuje jméno
vlastníka, proto se pro vlastníky ze **stránky** dohledá mapa `id → display_name`
jedním dotazem a šabloně se předá jako `owner_names`; chybějící jméno = pomlčka.
Sdílí se helper s registrem přes `web/routes/registry._owner_names`.

**Landing `/` → `/moje`.** Kořen aplikace přesměrovává na tuto obrazovku
(design.md sekce 7). Přesměrování je zde jako routa `GET /`, aby landing bydlel
u obrazovky, na kterou míří; registruje ho `main._register_routes`.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from regina.auth.deps import CurrentUserDep, SessionDep
from regina.repositories.applications import ListFilters, list_my_applications
from regina.web.pagination import paginate
from regina.web.routes.registry import _owner_names
from regina.web.templating import page_context

router = APIRouter(tags=["moje"])

# Velikost stránky mřížky karet. Násobek tří, aby poslední řada na desktopu
# (tři sloupce) vycházela plná. Drží se zde, protože je to rozhodnutí
# obrazovky, ne repozitáře.
_PAGE_SIZE = 12


@router.get("/", include_in_schema=False)
def landing() -> RedirectResponse:
    """Landing kořene aplikace → přesměrování na `/moje` (design.md sekce 7).

    `303 See Other`, aby po případném `POST` následoval čistý `GET /moje`.
    Samotné `/moje` je chráněné přihlášením; nepřihlášený uživatel se odtud
    dostane na `/login` přes guard, ne zde.
    """
    return RedirectResponse("/moje", status_code=303)


@router.get("/moje", include_in_schema=False)
def my_applications(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    q: str | None = Query(default=None),
    page: int = Query(default=1),
) -> HTMLResponse:
    """Vykreslí mřížku karet záznamů přihlášené osoby (ui.md sekce 4).

    Parametry z URL:
    - `q` — hledání v názvu (bez ohledu na velikost písmen, R3.2),
    - `page` — stránka výpisu.

    Výpis se omezí na odpovědnou trojici přihlášené osoby (R3.10) v repozitáři;
    routa jen sestaví filtry, stránkování a jména vlastníků pro karty.
    """
    filters = ListFilters(query=q, page=page, page_size=_PAGE_SIZE)

    result = list_my_applications(session, user.id, filters)
    pagination = paginate(total=result.total, page=page, page_size=_PAGE_SIZE)
    owner_names = _owner_names(session, result.items)

    # Rozlišení „uživatel nemá žádný záznam" vs. „hledání nic nenašlo": prázdný
    # výsledek bez hledání je skutečný prázdný stav (R3.12), s hledáním jde jen
    # o prázdný výsledek filtru. Šablona podle toho volí text.
    has_search = bool(q and q.strip())

    context = page_context(
        request,
        user=user,
        active_nav="moje",
        section_title="Moje aplikace",
        applications=result.items,
        owner_names=owner_names,
        pagination=pagination,
        selected={"q": q or ""},
        has_search=has_search,
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "mine/list.html", context)
