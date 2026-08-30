"""Routa tabulkového výpisu registru `/registr` (úkol 11.2, ui.md sekce 5).

Svislý řez od parametrů URL po vykreslenou tabulku. Routa **nepočítá** ani
nefiltruje v paměti — sesbírá parametry, přeloží je na `ListFilters` a předá
je repozitáři (`list_applications`, úkol 11.1), který vše provede v databázi
a vrátí jednu stránku (R3.6). Z celkového počtu se přes `paginate()` sestaví
stav stránkování a text „Zobrazeno X–Y z N záznamů" (R3.5).

**Kdo obrazovku vidí.** Obě role čtou celý registr (R2, capability matrix),
takže guard je jen `require_login` — žádné omezení na Admina. Akce v tabulce
(Přepsat klasifikaci, Vyřadit) se roli User nevykreslují; rozhodnutí dělá
`domain/rules` přes příznak `is_admin` předaný šabloně (R2.5). Skrytí je
pohodlnost, skutečné vynucení mají guardy cílových cest (úkol 15).

**Filtr stavu a „Zobrazit i vyřazené" (R3.9, kritérium úkolu).** Pruh filtrů
má select stavu s českými popisky (prázdná volba = „Vše") a **samostatný**
přepínač „Zobrazit i vyřazené". Mapování na `ListFilters`:

- select stavu prázdný + přepínač vypnutý → `state=None`,
  `include_decommissioned=False` → výchozí výpis skryje vyřazené;
- select stavu = konkrétní stav (i „Vyřazená") → `state=<stav>` → přesně ten
  stav, výchozí skrytí se neuplatní;
- select stavu prázdný + přepínač zapnutý → `include_decommissioned=True` →
  výpis zahrne všechny stavy včetně vyřazených.

Neplatné hodnoty z URL (např. `?stav=NESMYSL`) se tiše ignorují jako „nezvoleno",
aby ručně upravený odkaz výpis neshodil.

**Jméno vlastníka.** Výpis vrací `Application`, ne osoby. Sloupec Vlastník
potřebuje zobrazované jméno, proto se pro vlastníky ze **stránky** (nejvýše
`page_size` osob) dohledá mapa `id → display_name` jedním dotazem a šabloně se
předá jako `owner_names`. Kdyby jméno chybělo, zobrazí se pomlčka.
"""

from __future__ import annotations

import uuid

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from starlette.responses import RedirectResponse

from regina.auth.csrf import CsrfProtect
from regina.auth.deps import (
    ApplicationDep,
    CurrentUser,
    CurrentUserDep,
    SessionDep,
    require_can_edit,
    require_decommission,
    require_override_classification,
)
from regina.db.models.applications import Application
from regina.db.models.classification_log import ClassificationLog
from regina.db.models.users import User
from regina.domain import questionnaire, rules
from regina.domain.enums import (
    Classification,
    ClassificationSource,
    LifecycleState,
    Role,
)
from regina.repositories import classification_log as classification_log_repo
from regina.repositories import users as users_repo
from regina.repositories.applications import ListFilters, list_applications
from regina.services import classification as classification_service
from regina.services.applications import (
    LifecycleTransitionError,
    create_application,
    decommission_application,
    reactivate_application,
    update_application,
)
from regina.web import forms
from regina.web.flash import redirect_with_flash
from regina.web.forms import (
    FormValidationError,
    parse_application_form,
    validate_uniqueness_and_refs,
)
from regina.web.pagination import paginate
from regina.web.templating import page_context

router = APIRouter(tags=["registr"])

# Velikost stránky výpisu (ui.md sekce 5 — „Zobrazeno 1–20"). Drží se zde,
# protože je to rozhodnutí obrazovky, ne repozitáře.
_PAGE_SIZE = 20


def _parse_enum(value: str | None, enum_type):
    """Přeloží strojový kód z URL na člen výčtu, nebo `None`.

    Neznámá či prázdná hodnota = „nezvoleno". Tím ručně upravený odkaz
    (`?stav=NESMYSL`) výpis neshodí, jen se filtr neuplatní.
    """
    if not value:
        return None
    try:
        return enum_type(value)
    except ValueError:
        return None


def _owner_names(session: SessionDep, applications: list[Application]) -> dict[uuid.UUID, str]:
    """Dohledá mapu `owner_user_id → display_name` pro vlastníky ze stránky.

    Jeden dotaz nad nejvýše `page_size` odlišnými identifikátory. Šablona z ní
    vezme jméno vlastníka do sloupce Vlastník; chybějící jméno = pomlčka.
    """
    owner_ids = {app.owner_user_id for app in applications}
    if not owner_ids:
        return {}
    rows = session.execute(
        select(User.id, User.display_name).where(User.id.in_(owner_ids))
    ).all()
    return {row[0]: row[1] for row in rows}


def _registry_list_context(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    *,
    q: str | None,
    utvar: str | None,
    klasifikace: str | None,
    stav: str | None,
    vse: bool,
    page: int,
) -> dict[str, object]:
    """Sestaví kontext výpisu registru — sdílený stránkou i fragmentem.

    Jedno místo, kde se z parametrů URL složí filtry, stránkování, jména
    vlastníků a předvyplnění formuláře, aby celá stránka (`GET /registr`) i
    fragment živého filtrování (`GET /registr/fragment`) vykreslovaly z **týchž**
    dat. Filtruje repozitář nad databází (R3.6); routa nic nepočítá v paměti.
    """
    settings = request.app.state.settings

    # Útvar: přijímáme jen hodnotu z konfigurovaného výčtu, jinak „nezvoleno".
    department = utvar if utvar in settings.departments else None

    # Klasifikace: `NONE` je výslovná volba „Neklasifikováno" (classification IS
    # NULL), jinak strojový kód úrovně; neznámé = nezvoleno.
    unclassified_only = klasifikace == "NONE"
    classification = None if unclassified_only else _parse_enum(klasifikace, Classification)

    state = _parse_enum(stav, LifecycleState)

    filters = ListFilters(
        query=q,
        department=department,
        classification=classification,
        unclassified_only=unclassified_only,
        state=state,
        include_decommissioned=vse,
        page=page,
        page_size=_PAGE_SIZE,
    )

    result = list_applications(session, filters)
    pagination = paginate(total=result.total, page=page, page_size=_PAGE_SIZE)
    owner_names = _owner_names(session, result.items)

    # Hodnoty pro předvyplnění filtrů zpět do formuláře (aby zůstaly po odeslání).
    selected = {
        "q": q or "",
        "utvar": department or "",
        "klasifikace": klasifikace or "",
        "stav": stav or "",
        "vse": vse,
    }

    return page_context(
        request,
        user=user,
        active_nav="registr",
        section_title="Správa registru",
        applications=result.items,
        owner_names=owner_names,
        pagination=pagination,
        departments=settings.departments,
        classifications=tuple(Classification),
        lifecycle_states=tuple(LifecycleState),
        selected=selected,
        is_admin=user.role == Role.ADMIN,
    )


@router.get("/registr", include_in_schema=False)
def registry_list(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    q: str | None = Query(default=None),
    utvar: str | None = Query(default=None),
    klasifikace: str | None = Query(default=None),
    stav: str | None = Query(default=None),
    vse: bool = Query(default=False),
    page: int = Query(default=1),
) -> HTMLResponse:
    """Vykreslí tabulkový výpis registru s filtry a stránkováním.

    Parametry z URL:
    - `q` — hledání v názvu (R3.2),
    - `utvar` — filtr útvaru (hodnota z konfigurovaného výčtu),
    - `klasifikace` — filtr klasifikace; `NONE` = jen neklasifikované (R3.8),
    - `stav` — filtr stavu (strojový kód); prázdné = „Vše" (R3.3),
    - `vse` — přepínač „Zobrazit i vyřazené" (R3.9),
    - `page` — stránka výpisu.
    """
    context = _registry_list_context(
        request,
        user,
        session,
        q=q,
        utvar=utvar,
        klasifikace=klasifikace,
        stav=stav,
        vse=vse,
        page=page,
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "registry/list.html", context)


@router.get("/registr/fragment", include_in_schema=False)
def registry_list_fragment(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    q: str | None = Query(default=None),
    utvar: str | None = Query(default=None),
    klasifikace: str | None = Query(default=None),
    stav: str | None = Query(default=None),
    vse: bool = Query(default=False),
    page: int = Query(default=1),
) -> HTMLResponse:
    """Vrátí **jen** výsledky výpisu (tabulka + stránkování) pro živé filtrování.

    Endpoint živého filtrování Registru (ui.md sekce 5, R3.2/R3.3/R3.9):
    obrazovka `/registr` sem při psaní v hledání i při změně kteréhokoli filtru
    posílá celý formulář a vrácený partial vloží do kontejneru výsledků, aniž by
    přenačetla celou stránku. Renderuje `registry/_results.html` — stejný
    partial, jaký `registry/list.html` vkládá při prvním načtení, nad **týmž**
    kontextem (`_registry_list_context`), takže se stránka i fragment nikdy
    nerozejdou.

    Chráněno stejně jako `/registr` (`require_login` přes `CurrentUserDep`);
    obě role čtou celý registr (R2). Cesta `/registr/fragment` je definována
    **před** `/registr/{id}`, aby ji dynamická cesta nezachytila jako id.
    """
    context = _registry_list_context(
        request,
        user,
        session,
        q=q,
        utvar=utvar,
        klasifikace=klasifikace,
        stav=stav,
        vse=vse,
        page=page,
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "registry/_results.html", context)


# --- Detail záznamu (úkol 15.1, ui.md sekce 7, R4) -----------------------
#
# GET `/registr/{id}` — čtení detailu jednoho záznamu. Vidí ho **kdokoli
# přihlášený** (R4, capability matrix „číst detail libovolného záznamu"), proto
# guard `require_login` přes `CurrentUserDep`; žádné omezení na roli. Neexistující
# záznam je 404 (`load_application` přes `ApplicationDep`, design.md sekce 8).
#
# Co detail zobrazuje a odkud to bere:
# - hlavní karta: název, popis, útvar, stav, klasifikace, AI model (R4.2, R4.7);
# - odpovědnost: vlastník, zástupce (je-li), technický správce — **jménem a
#   pozicí** (R4.3). Záznam drží jen identifikátory, jména/pozice dohledá
#   `users.get_by_ids`;
# - klasifikace: platná hodnota + její **zdroj a datum** z nejnovějšího řádku
#   historie (R4.4); u přepisu správcem i důvod (R4.5);
# - historie klasifikace od nejnovějšího (R4.6): každý řádek hodnota, zdroj,
#   aktér, čas — `classification_log.list_for_application`;
# - akce: tlačítka řídí příznaky z `domain/rules` (Upravit, Přepsat klasifikaci,
#   Vyřadit). Skrytí je pohodlnost (R2.5); vynucení mají guardy cílových cest
#   (úkoly 14.4/13.2/15.2). Když osoba nemá právo editovat, ukáže se indikátor
#   „Pouze pro čtení" (R4.8).


def _classification_actor_ids(history: list[ClassificationLog]) -> set[uuid.UUID]:
    """Množina identifikátorů aktérů napříč řádky historie klasifikace.

    Slouží k jednomu dohledání jmen aktérů přes `users.get_by_ids` (R2.6 —
    porovnává se identita, jména se jen zobrazují).
    """
    return {row.actor_user_id for row in history}


@router.get("/registr/{id:uuid}", include_in_schema=False)
def application_detail(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    application: ApplicationDep,
) -> HTMLResponse:
    """Vykreslí detail záznamu (ui.md sekce 7, R4.1–R4.10).

    Guard `require_login` (přes `CurrentUserDep`) pustí každou přihlášenou osobu
    — detail smí číst obě role (R4). `load_application` (přes `ApplicationDep`)
    záznam načte podle `{id}` z cesty, nebo vrátí 404.

    Sesbírá vše, co šablona potřebuje, a **žádnou** logiku nenechává na šabloně:

    1. **Odpovědná trojice se jmény a pozicemi** (R4.3). Z identifikátorů
       vlastníka, zástupce (je-li vyplněn) a technického správce dohledá řádky
       `users` (jméno + pozice). Chybějící osoba se v mapě neobjeví a šablona
       zobrazí zástupný text.
    2. **Historie klasifikace od nejnovějšího** (R4.6). Řádky logu z
       `classification_log.list_for_application`. Jména aktérů dohledá jedním
       dotazem přes `users.get_by_ids` nad množinou identit z historie i trojice.
    3. **Aktuální klasifikace se zdrojem a datem** (R4.4, R4.5). Nejnovější řádek
       historie (první v seřazeném seznamu) nese zdroj a datum posledního zápisu;
       u přepisu správcem (`ADMIN_OVERRIDE`) i důvod. Když historie neexistuje,
       klasifikace je „Neklasifikováno" bez zdroje a data.
    4. **Příznaky akcí** z `domain/rules` (R2.5). `can_edit(user, app)`,
       `can_override_classification(user)`, `can_decommission(user)` — tytéž
       funkce, které vynucují guardy cílových cest. `read_only` je opak práva
       editace, pro indikátor „Pouze pro čtení" (R4.8).
    """
    history = classification_log_repo.list_for_application(session, application.id)

    # Jedno dohledání jmen: odpovědná trojice + aktéři historie dohromady.
    person_ids: set[uuid.UUID] = _classification_actor_ids(history)
    for trio_id in (
        application.owner_user_id,
        application.deputy_user_id,
        application.tech_admin_user_id,
    ):
        if trio_id is not None:
            person_ids.add(trio_id)
    people = users_repo.get_by_ids(session, person_ids)

    owner = people.get(application.owner_user_id)
    deputy = (
        people.get(application.deputy_user_id)
        if application.deputy_user_id is not None
        else None
    )
    tech_admin = people.get(application.tech_admin_user_id)

    # Nejnovější zápis nese zdroj a datum platné klasifikace (R4.4). Je první
    # v seznamu seřazeném od nejnovějšího; None, když klasifikace nikdy nebyla.
    latest = history[0] if history else None

    # Příznaky akcí — tytéž funkce, které vynucují guardy cílových cest (R2.5).
    can_edit = rules.can_edit(user, application)
    context = page_context(
        request,
        user=user,
        active_nav="registr",
        # V horní liště je vždy „Detail aplikace", aby bylo jasné, na jaké
        # obrazovce uživatel je; konkrétní název nese breadcrumb a hlavní karta.
        section_title="Detail aplikace",
        application=application,
        owner=owner,
        deputy=deputy,
        tech_admin=tech_admin,
        history=history,
        actor_names={pid: person.display_name for pid, person in people.items()},
        latest=latest,
        can_edit=can_edit,
        can_override=rules.can_override_classification(user),
        can_decommission=rules.can_decommission(user),
        read_only=not can_edit,
        is_decommissioned=(
            application.lifecycle_state == str(LifecycleState.DECOMMISSIONED)
        ),
        admin_override_source=str(ClassificationSource.ADMIN_OVERRIDE),
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "registry/detail.html", context)


# --- Průvodce registrací nového záznamu (úkol 14.3, ui.md sekce 6) -------
#
# GET `/registr/nova` vykreslí prázdný třístupňový průvodce (Základní údaje /
# Odpovědnost / Provoz a klasifikace) bez sidebaru. POST `/registr/nova` ověří
# celou sadu polí jediným odesláním (ui.md sekce 6: „jeden formulář, jedno
# odeslání"), a při chybách vrátí průvodce s chybami u konkrétních polí a
# zachovaným vstupem. Při úspěchu založí záznam a přesměruje na jeho detail
# s potvrzením.
#
# Kdo smí zakládat: kdokoli přihlášený (R5.1) — guard je `require_login`
# (`CurrentUserDep`). POST navíc chrání CSRF token vázaný na session (úkol 6.4).


def _person_options(session: SessionDep) -> list[dict[str, str]]:
    """Sestaví volby pro selecty odpovědné trojice z adresáře (R5.5, R2.6).

    Osoby se vybírají **podle identity**, ne psaním jména: hodnota volby je
    ``id`` osoby, popisek je zobrazované jméno (a pozice, je-li vyplněná).
    Vrací jen aktivní osoby, aby se nedala přiřadit deaktivovaná identita.
    """
    options: list[dict[str, str]] = []
    for person in users_repo.list_active(session):
        label = person.display_name
        if person.job_title:
            label = f"{person.display_name} — {person.job_title}"
        options.append({"id": str(person.id), "label": label})
    return options


def _lifecycle_choices(is_admin: bool) -> tuple[LifecycleState, ...]:
    """Nabídka stavů životního cyklu pro krok 3 průvodce (ui.md sekce 6).

    Stav ``Vyřazená`` (``DECOMMISSIONED``) **není ve výběru** — vyřazení je
    dedikovaná akce vyhrazená roli Admin (R5.12, úkol 15.2) a služba ho i pro
    Admina přes formulář odmítne. Vypouští se tedy pro obě role, aby průvodce
    nenabízel volbu, kterou uložení stejně zamítne. ``is_admin`` je zde pro
    symetrii s ui.md a případné budoucí rozlišení; jádro filtruje shodně.
    """
    return tuple(
        state for state in LifecycleState if state is not LifecycleState.DECOMMISSIONED
    )


def _wizard_context(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    *,
    values: dict[str, str],
    errors: dict[str, list[str]] | None = None,
    section_title: str = "Nová aplikace",
    wizard_title: str = "Průvodce registrací aplikace",
    wizard_intro: str = "Vyplňte údaje o aplikaci ve třech krocích. Záznam vznikne po odeslání formuláře.",
    submit_label: str = "Registrovat aplikaci",
    back_label: str = "Zpět na Moje aplikace",
    form_action: str = "/registr/nova",
    cancel_href: str = "/moje",
) -> dict[str, object]:
    """Poskládá kontext průvodce: volby osob, útvarů, výčtů, vstup a chyby.

    Výčty (stav, klasifikace) i útvary přicházejí z **jednoho zdroje** —
    ``LifecycleState``/``Classification`` z ``domain.enums`` a
    ``settings.departments`` z konfigurace. Osoby z adresáře přes
    ``_person_options``. ``values`` drží dosud zadané hodnoty (předvyplnění při
    re-renderu, výchozí vlastník = přihlášená osoba u vzniku, aktuální hodnoty
    záznamu u editace), ``errors`` mapu chyb po polích (R5.3).

    **Sdílená šablona pro vznik i editaci (úkol 14.4).** Texty a cíle formuláře
    přicházejí parametry s výchozími hodnotami pro registraci, takže routa
    vzniku volá funkci beze změny. Editace (``/registr/{id}/upravit``) přepíše
    ``wizard_title``, ``submit_label``, ``form_action`` a ``cancel_href`` na
    své hodnoty a předá aktuální hodnoty záznamu ve ``values``. Logika, výčty
    ani zdroje osob se přitom nemění — mění se jen texty a předvyplnění.
    """
    settings = request.app.state.settings
    is_admin = user.role == Role.ADMIN
    return page_context(
        request,
        user=user,
        active_nav=None,  # Průvodce nemá sidebar (ui.md sekce 6).
        section_title=section_title,
        people=_person_options(session),
        departments=settings.departments,
        lifecycle_states=_lifecycle_choices(is_admin),
        classifications=tuple(Classification),
        # Otázky poradce klasifikace do AI panelu formuláře (classification-advisor R2).
        advisor_questions=questionnaire.QUESTIONS,
        values=values,
        errors=errors or {},
        fields=forms,
        wizard_title=wizard_title,
        wizard_intro=wizard_intro,
        submit_label=submit_label,
        back_label=back_label,
        form_action=form_action,
        cancel_href=cancel_href,
    )


@router.get("/registr/nova", include_in_schema=False)
def new_application_form(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
) -> HTMLResponse:
    """Vykreslí prázdný průvodce registrací (R5.1, R5.5, ui.md sekce 6).

    Vlastník je předvyplněn přihlášenou osobou (R5.5), ale ve výběru ho lze
    změnit. Selecty odpovědné trojice se plní z adresáře (osoby podle identity,
    R2.6); útvary a výčty z jediného zdroje.
    """
    values = {forms.FIELD_OWNER: str(user.id)}
    context = _wizard_context(request, user, session, values=values)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "registry/wizard.html", context)


async def _read_form(request: Request) -> dict[str, str]:
    """Přečte odeslaná formulářová pole jako mapu ``{název: hodnota}``.

    Async závislost — čtení těla požadavku je asynchronní, kdežto obsluha routy
    je synchronní (běží ve vlákně poolu, jako zbytek aplikace). Načtení formuláře
    proto probíhá zde, v závislosti, a routě se předá hotová mapa. CSRF token se
    z mapy vypouští — do validace formuláře nepatří; ověřil ho ``CsrfProtect``.
    Hodnoty jsou řetězce; prázdné nepovinné pole zůstane prázdným řetězcem a
    tvarová validace ho převede na ``None``.
    """
    data = await request.form()
    return {
        key: value
        for key, value in data.items()
        if key != "csrf_token" and isinstance(value, str)
    }


FormDataDep = Annotated[dict[str, str], Depends(_read_form)]


def _advisor_fields(raw: dict[str, str]) -> tuple[int | None, Classification | None]:
    """Přečte z formuláře odkaz na doporučení poradce a navrženou úroveň.

    Skrytá pole ``advisor_suggestion_id`` a ``advisor_suggested`` vyplní JS při
    převzetí návrhu z AI panelu (classification-advisor R3.5, R3.6). Když
    chybí, jsou prázdná nebo nesmyslná, vrací ``(None, None)`` a klasifikace se
    zapíše jako ruční (``HUMAN``) — poradce je nadstavba, ne podmínka. Nesmyslné
    hodnoty se tiše ignorují, aby ručně upravený formulář zápis neshodil; zdroj
    pak degraduje na ``HUMAN``, což je bezpečná varianta.
    """
    raw_id = raw.get("advisor_suggestion_id", "").strip()
    raw_level = raw.get("advisor_suggested", "").strip()
    if not raw_id or not raw_level:
        return None, None
    try:
        suggestion_id = int(raw_id)
        suggested = Classification(raw_level)
    except (ValueError, TypeError):
        return None, None
    return suggestion_id, suggested


@router.post(
    "/registr/nova",
    include_in_schema=False,
    dependencies=[CsrfProtect],
    response_model=None,
)
def create_application_route(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    raw: FormDataDep,
) -> HTMLResponse | RedirectResponse:
    """Založí záznam z odeslaného průvodce, nebo vrátí formulář s chybami.

    Jediné odeslání celé sady polí (ui.md sekce 6). Postup:

    1. Ověří tvar přes ``parse_application_form`` (povinná pole, výčty, útvar
       proti konfiguraci). Tvarové chyby → vrátí průvodce s chybami u
       konkrétních polí a zachovaným vstupem (R5.3).
    2. Ověří kolize proti databázi přes ``validate_uniqueness_and_refs``
       (unikátní název R5.8, existence osob R2.6). Chyby → stejný re-render.
    3. Bez chyb založí záznam přes ``create_application`` (audit i klasifikaci
       řeší služba) a přesměruje na detail ``/registr/{id}`` s potvrzením.
       Commit provede závislost ``get_session`` po úspěšném návratu.

    Formulářová data načítá async závislost ``_read_form`` a předává je sem už
    jako mapu; CSRF ověřil ``CsrfProtect`` na routě.
    """
    settings = request.app.state.settings

    try:
        form = parse_application_form(raw, settings.departments)
    except FormValidationError as error:
        return _rerender_wizard(request, user, session, raw=raw, errors=error.errors)

    ref_errors = validate_uniqueness_and_refs(session, form)
    if ref_errors:
        return _rerender_wizard(request, user, session, raw=raw, errors=ref_errors)

    advisor_suggestion_id, advisor_suggested = _advisor_fields(raw)
    application = create_application(
        session,
        user,
        form,
        advisor_suggestion_id=advisor_suggestion_id,
        advisor_suggested=advisor_suggested,
    )
    session.flush()  # Zajistí application.id pro URL detailu ještě před commitem.

    return redirect_with_flash(
        f"/registr/{application.id}",
        "Aplikace byla zaregistrována.",
    )


def _rerender_wizard(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    *,
    raw: dict[str, str],
    errors: dict[str, list[str]],
    **wizard_kwargs: object,
) -> HTMLResponse:
    """Vykreslí průvodce znovu se zachovaným vstupem a chybami po polích.

    ``wizard_kwargs`` propustí parametrizaci šablony (titulek, cíl formuláře,
    popisky) na ``_wizard_context`` beze změny — tak re-render editace zůstane
    v editačním režimu (stejný ``form_action`` a texty), ne v režimu vzniku.
    """
    context = _wizard_context(
        request, user, session, values=raw, errors=errors, **wizard_kwargs
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "registry/wizard.html", context, status_code=422
    )


# --- Editace existujícího záznamu (úkol 14.4, ui.md sekce 6, R5.10/R2.2) --
#
# GET/POST `/registr/{id}/upravit` znovupoužívají **tutéž** šablonu průvodce
# jako vznik (úkol 14.3). Rozdíl je jen v textech, cíli formuláře, předvyplnění
# aktuálními hodnotami záznamu — a v autorizaci.
#
# **Autorizace je na backendu, ne skrytím tlačítka (R2.2, kritérium úkolu).**
# Obě routy chrání závislost `require_can_edit`: ta načte záznam podle `{id}`
# (`load_application`, 404 u neexistujícího) a zavolá `rules.can_edit` — člen
# odpovědné trojice, nebo Admin (R5.10, R2.6). Uživatel, který není členem
# trojice a není Admin, dostane 403 + audit `ACCESS_DENIED` i při **přímém**
# POST bez toho, aby mu rozhraní kdy nabídlo tlačítko Upravit. Vynucení tedy
# nestojí na tom, co se vykreslí.

# Cesta detailu, kam vede Zrušit i úspěšné uložení (detail je úkol 15).
_DETAIL_PATH = "/registr/{app_id}"

# Texty a cíle šablony pro editační režim. `form_action`/`cancel_href` se
# doplní konkrétním id záznamu v routách níž.
_EDIT_TITLE = "Upravit aplikaci"
_EDIT_INTRO = "Upravte údaje o aplikaci ve třech krocích. Změny se uloží po odeslání formuláře."
_EDIT_SUBMIT_LABEL = "Uložit změny"
_EDIT_BACK_LABEL = "Zpět na detail"


def _edit_wizard_kwargs(application: Application) -> dict[str, str]:
    """Parametry šablony přepínající průvodce do editačního režimu.

    Titulek, popisky, text tlačítka a cíle (POST na tentýž záznam, Zrušit zpět
    na detail). Sdílí se mezi GET (první vykreslení) i re-renderem při chybách,
    aby editace nikdy nespadla zpět do režimu vzniku.
    """
    detail_href = _DETAIL_PATH.format(app_id=application.id)
    return {
        "section_title": _EDIT_TITLE,
        "wizard_title": _EDIT_TITLE,
        "wizard_intro": _EDIT_INTRO,
        "submit_label": _EDIT_SUBMIT_LABEL,
        "back_label": _EDIT_BACK_LABEL,
        "form_action": f"{detail_href}/upravit",
        "cancel_href": detail_href,
    }


def _application_values(application: Application) -> dict[str, str]:
    """Předvyplní formulář aktuálními hodnotami záznamu (klíče ``forms.FIELD_*``).

    Šablona čte hodnoty jako řetězce (``values.get(...)``), proto se UUID i
    výčty převádějí na ``str``; nevyplněná nepovinná pole zůstávají prázdným
    řetězcem, aby se select/textarea vykreslily bez předvolby. Klasifikace je
    strojový kód platné hodnoty (nebo prázdno = Neklasifikováno).
    """
    def _text(value: object) -> str:
        return "" if value is None else str(value)

    return {
        forms.FIELD_NAME: _text(application.name),
        forms.FIELD_DESCRIPTION: _text(application.description),
        forms.FIELD_DEPARTMENT: _text(application.department),
        forms.FIELD_OWNER: _text(application.owner_user_id),
        forms.FIELD_DEPUTY: _text(application.deputy_user_id),
        forms.FIELD_TECH_ADMIN: _text(application.tech_admin_user_id),
        forms.FIELD_LIFECYCLE_STATE: _text(application.lifecycle_state),
        forms.FIELD_AI_MODEL: _text(application.ai_model),
        forms.FIELD_CLASSIFICATION: _text(application.classification),
    }


@router.get("/registr/{id:uuid}/upravit", include_in_schema=False, response_model=None)
def edit_application_form(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    application: Annotated[Application, Depends(require_can_edit)],
) -> HTMLResponse | RedirectResponse:
    """Vykreslí průvodce předvyplněný aktuálními hodnotami záznamu (R5.10).

    Guard ``require_can_edit`` (přes ``Depends``) záznam načte podle ``{id}`` a
    vynutí právo editace **na backendu**: nepřihlášený jde na login, přihlášený
    bez práva dostane 403 + audit ``ACCESS_DENIED`` — nezávisle na tom, že mu
    rozhraní tlačítko Upravit nikdy neukázalo (R2.2).

    **Vyřazený záznam.** Běžná editace nedokáže vyřazený záznam uložit — služba
    ``update_application`` přechod do/z ``DECOMMISSIONED`` odmítá
    (``LifecycleTransitionError``, constraint-safety). Průvodce navíc stav
    ``Vyřazená`` v nabídce nemá. Editační formulář proto vyřazeným záznamům
    **nenabízíme** a místo něj ukážeme českou hlášku s odkazem na detail;
    reaktivace/vyřazení je dedikovaná akce roli Admin (úkol 15.2).
    """
    detail_href = _DETAIL_PATH.format(app_id=application.id)
    if application.lifecycle_state == str(LifecycleState.DECOMMISSIONED):
        return redirect_with_flash(
            detail_href,
            "Vyřazený záznam nelze upravit tímto formulářem. "
            "Nejprve ho vraťte z vyřazení (akce vyhrazená roli Admin).",
            type="error",
        )

    context = _wizard_context(
        request,
        user,
        session,
        values=_application_values(application),
        **_edit_wizard_kwargs(application),
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "registry/wizard.html", context)


@router.post(
    "/registr/{id:uuid}/upravit",
    include_in_schema=False,
    dependencies=[CsrfProtect],
    response_model=None,
)
def update_application_route(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    application: Annotated[Application, Depends(require_can_edit)],
    raw: FormDataDep,
) -> HTMLResponse | RedirectResponse:
    """Uloží úpravy záznamu, nebo vrátí formulář s chybami (R5.10, R2.2).

    Autorizace je vynucena **backendem**: guard ``require_can_edit`` odmítne
    přímý POST na cizí záznam od uživatele, který není členem odpovědné trojice
    a není Admin — 403 + audit ``ACCESS_DENIED``, i když v rozhraní žádné
    tlačítko Upravit nebylo (kritérium úkolu, R2.2). CSRF token ověřil
    ``CsrfProtect``.

    Postup zrcadlí vznik (úkol 14.3), jen míří na existující záznam:

    1. Tvar přes ``parse_application_form`` (povinná pole, výčty, útvar). Chyby
       → re-render průvodce v **editačním** režimu s chybami u polí a zachovaným
       vstupem (R5.3).
    2. Kolize přes ``validate_uniqueness_and_refs`` s ``exclude_id=application.id``
       — nezměněný název tak nekoliduje sám se sebou (R5.8). Chyby → stejný
       re-render.
    3. ``update_application`` zapíše změny, audit (jen názvy změněných polí) a
       klasifikaci přes jediného zapisovače. Přechod do/z ``DECOMMISSIONED``
       služba odmítá — u záznamu ve stavu ``Vyřazená`` se sem ani nedojde
       (GET přesměruje), ostatní stavy v nabídce ``DECOMMISSIONED`` nemají.
    4. Přesměrování na detail ``/registr/{id}`` s potvrzením (R13.8).
    """
    detail_href = _DETAIL_PATH.format(app_id=application.id)
    edit_kwargs = _edit_wizard_kwargs(application)
    settings = request.app.state.settings

    try:
        form = parse_application_form(raw, settings.departments)
    except FormValidationError as error:
        return _rerender_wizard(
            request, user, session, raw=raw, errors=error.errors, **edit_kwargs
        )

    ref_errors = validate_uniqueness_and_refs(
        session, form, exclude_id=application.id
    )
    if ref_errors:
        return _rerender_wizard(
            request, user, session, raw=raw, errors=ref_errors, **edit_kwargs
        )

    advisor_suggestion_id, advisor_suggested = _advisor_fields(raw)
    try:
        update_application(
            session,
            user,
            application,
            form,
            advisor_suggestion_id=advisor_suggestion_id,
            advisor_suggested=advisor_suggested,
        )
    except LifecycleTransitionError:
        # Vyřazení/návrat přes formulář je zakázané (constraint-safety, R5.12).
        # Za normálních okolností se sem nedojde (stav Vyřazená není v nabídce
        # a vyřazený záznam se needituje), ale ošetříme to jako chybu pole stavu.
        return _rerender_wizard(
            request,
            user,
            session,
            raw=raw,
            errors={
                forms.FIELD_LIFECYCLE_STATE: [
                    "Vyřazení se neprovádí přes tento formulář — použijte akci "
                    "vyřazení (vyhrazenou roli Admin)."
                ]
            },
            **edit_kwargs,
        )

    return redirect_with_flash(detail_href, "Změny byly uloženy.")


# --- Vyřazení a návrat z vyřazení (úkol 15.2, ui.md sekce 7, R5.12–R5.14) -
#
# GET/POST `/registr/{id}/vyrazeni`. Obojí je vyhrazeno roli Admin — guard
# `require_decommission` (přes `Depends`) vynutí `rules.can_decommission` **na
# backendu**: přihlášený uživatel role User dostane 403 + audit `ACCESS_DENIED`
# i při **přímém** POST bez toho, aby mu rozhraní tlačítko Vyřadit nabídlo
# (R5.12, R2.2). `load_application` (přes `Depends`) záznam načte, nebo vrátí
# 404 — guard aktéra a načtení záznamu jsou dvě samostatné závislosti.
#
# Jedna cesta, dvě akce podle stavu: aktivní záznam se vyřadí, vyřazený se
# vrátí. Detail (úkol 15.1) na tuto cestu odkazuje z obou tlačítek
# (Vyřadit / Vrátit z vyřazení). Změnu i audit provede služba v transakci
# požadavku (commit řeší závislost `get_session`).

# Guard aktéra a načtení záznamu jako samostatné závislosti — guard rozhoduje
# nad rolí (nezávisle na záznamu), `load_application` doručí cílový záznam.
AdminActorDep = Annotated[CurrentUser, Depends(require_decommission)]
OverrideActorDep = Annotated[CurrentUser, Depends(require_override_classification)]


@router.get("/registr/{id:uuid}/vyrazeni", include_in_schema=False)
def decommission_confirm(
    request: Request,
    user: AdminActorDep,
    application: ApplicationDep,
) -> HTMLResponse:
    """Vykreslí potvrzení vyřazení, nebo návratu z vyřazení (R5.12).

    Vyhrazeno roli Admin (`require_decommission`). Podle stavu záznamu ukáže
    buď potvrzení vyřazení (aktivní záznam), nebo návratu (vyřazený záznam);
    obojí míří na stejný POST, který akci určí ze stavu. Neexistující záznam
    je 404 (`load_application`).
    """
    is_decommissioned = application.lifecycle_state == str(LifecycleState.DECOMMISSIONED)
    context = page_context(
        request,
        user=user,
        active_nav="registr",
        section_title=application.name or "Vyřazení",
        application=application,
        is_decommissioned=is_decommissioned,
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "registry/vyrazeni.html", context)


@router.post(
    "/registr/{id:uuid}/vyrazeni",
    include_in_schema=False,
    dependencies=[CsrfProtect],
    response_model=None,
)
def decommission_route(
    request: Request,
    user: AdminActorDep,
    session: SessionDep,
    application: ApplicationDep,
) -> RedirectResponse:
    """Vyřadí aktivní záznam, nebo vrátí vyřazený (R5.12, R5.13, R5.14).

    Vynucení „jen Admin" leží v guardu `require_decommission`; přímý POST od
    role User skončí 403 + audit `ACCESS_DENIED` (R2.2). CSRF token ověřil
    `CsrfProtect`.

    Podle aktuálního stavu záznamu:
    - aktivní → `decommission_application` (stav `DECOMMISSIONED`,
      `decommissioned_at` = teď, `decommissioned_by` = aktér, audit
      `APP_DECOMMISSIONED`);
    - vyřazený → `reactivate_application` (návrat do provozu, vyprázdní obě
      pole, audit `APP_REACTIVATED`).

    Změna i audit běží v jedné transakci (constraint zůstává splněný); commit
    provede závislost `get_session`. Přesměruje na detail s potvrzením (R13.8).
    """
    detail_href = f"/registr/{application.id}"

    if application.lifecycle_state == str(LifecycleState.DECOMMISSIONED):
        reactivate_application(session, user, application)
        return redirect_with_flash(detail_href, "Aplikace byla vrácena z vyřazení.")

    decommission_application(session, user, application)
    return redirect_with_flash(detail_href, "Aplikace byla vyřazena.")


# --- Přepis klasifikace správcem (úkol 15.2/13.2, ui.md sekce 7, R7) ------
#
# GET/POST `/registr/{id}/prepis-klasifikace`. Vyhrazeno roli Admin — guard
# `require_override_classification` vynutí `rules.can_override_classification`
# **na backendu**: role User dostane 403 + audit `ACCESS_DENIED` i při přímém
# POST (R7.1, R7.6, R2.2). Detail (úkol 15.1) na tuto cestu odkazuje tlačítkem
# „Přepsat klasifikaci".
#
# POST validuje **neprázdný** důvod a platnou klasifikaci; při prázdném důvodu
# se formulář vrátí s českou chybou u pole (R7.2, R7.3). Vlastní zápis (log +
# `applications.classification` + audit `CLASSIFICATION_OVERRIDDEN`) provede
# `services.classification.override_classification` v jednom zapisovači.


async def _read_override_form(request: Request) -> dict[str, str]:
    """Přečte pole formuláře přepisu (`classification`, `reason`) jako mapu.

    Stejný vzor jako `_read_form`: async čtení těla v závislosti, CSRF token se
    vypouští (ověřil ho `CsrfProtect`). Hodnoty jsou řetězce.
    """
    data = await request.form()
    return {
        key: value
        for key, value in data.items()
        if key != "csrf_token" and isinstance(value, str)
    }


OverrideFormDep = Annotated[dict[str, str], Depends(_read_override_form)]


def _override_context(
    request: Request,
    user: CurrentUserDep,
    application: Application,
    *,
    values: dict[str, str],
    errors: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    """Poskládá kontext formuláře přepisu: volby klasifikace, vstup a chyby."""
    return page_context(
        request,
        user=user,
        active_nav="registr",
        section_title=application.name or "Přepis klasifikace",
        application=application,
        classifications=tuple(Classification),
        values=values,
        errors=errors or {},
    )


@router.get(
    "/registr/{id:uuid}/prepis-klasifikace",
    include_in_schema=False,
    response_model=None,
)
def override_classification_form(
    request: Request,
    user: OverrideActorDep,
    application: ApplicationDep,
) -> HTMLResponse:
    """Vykreslí formulář přepisu klasifikace (R7.1, R7.6, ui.md sekce 7).

    Vyhrazeno roli Admin (`require_override_classification`). Předvyplní
    aktuální klasifikaci záznamu (nebo první úroveň, není-li klasifikován) a
    prázdný důvod. Neexistující záznam je 404 (`load_application`).
    """
    values = {
        "classification": application.classification or "",
        "reason": "",
    }
    context = _override_context(request, user, application, values=values)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "registry/prepis_klasifikace.html", context)


@router.post(
    "/registr/{id:uuid}/prepis-klasifikace",
    include_in_schema=False,
    dependencies=[CsrfProtect],
    response_model=None,
)
def override_classification_route(
    request: Request,
    user: OverrideActorDep,
    session: SessionDep,
    application: ApplicationDep,
    raw: OverrideFormDep,
) -> HTMLResponse | RedirectResponse:
    """Přepíše klasifikaci správcem, nebo vrátí formulář s chybou (R7.2, R7.3).

    Vynucení „jen Admin" leží v guardu `require_override_classification`; přímý
    POST od role User skončí 403 + audit `ACCESS_DENIED` (R7.1, R7.6, R2.2).
    CSRF token ověřil `CsrfProtect`.

    Postup:
    1. Ověří, že klasifikace nese platnou úroveň (`Classification`); neplatná
       hodnota → re-render s chybou u pole.
    2. Ověří **neprázdný** důvod (R7.2, R7.3); prázdný nebo jen-mezerový →
       re-render s českou chybou u pole `reason`.
    3. `services.classification.override_classification` zapíše řádek historie
       se `source = ADMIN_OVERRIDE`, aktualizuje `applications.classification`
       a zapíše audit `CLASSIFICATION_OVERRIDDEN` — vše v transakci požadavku.
    4. Přesměruje na detail s potvrzením (R13.8).
    """
    errors: dict[str, list[str]] = {}

    raw_classification = raw.get("classification", "")
    new_classification = _parse_enum(raw_classification, Classification)
    if new_classification is None:
        errors["classification"] = ["Zvolte platnou klasifikaci."]

    reason = raw.get("reason", "")
    if not reason.strip():
        errors["reason"] = ["Důvod přepisu je povinný."]

    if errors:
        context = _override_context(
            request, user, application, values=raw, errors=errors
        )
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request, "registry/prepis_klasifikace.html", context, status_code=422
        )

    classification_service.override_classification(
        session, application, user, new_classification, reason
    )

    return redirect_with_flash(
        f"/registr/{application.id}",
        "Klasifikace byla přepsána.",
    )
