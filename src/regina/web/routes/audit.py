"""Routa výpisu auditního logu `/audit` (úkol 17.1, ui.md sekce 9, R8.4/R8.7).

Svislý řez od parametrů URL po vykreslenou tabulku. Routa **nepočítá** ani
nefiltruje v paměti — sesbírá parametry, přeloží je na `AuditFilters` a předá
repozitáři (`list_audit_entries`), který vše provede v databázi a vrátí jednu
stránku plus celkový počet. Z celkového počtu se přes `paginate()` sestaví
stav stránkování a text „Zobrazeno X–Y z N záznamů".

**Kdo obrazovku vidí — jen Admin (R8.4).** Guard `require_read_audit` vynutí
`rules.can_read_audit` **na backendu**: přihlášený uživatel role User dostane
403 + audit `ACCESS_DENIED`, i když mu sidebar položku „Auditní logy" nikdy
neukázal (nav ji roli User skrývá, R2.5). Skrytí je pohodlnost, vynucení leží
zde.

**Filtry (R8.7):**

- akce — select typů akce s českými popisky (prázdná volba = „Vše"); neplatný
  strojový kód z URL se tiše ignoruje jako „nezvoleno",
- aktér — **rozbalovací nabídka známých osob** (adresář), hodnota je `id`
  osoby, filtr míří na `actor_user_id`. Zobrazované jméno aktéra v tabulce se
  přesto bere ze **snapshotu** záznamu (`actor_display_name`/`actor_email`),
  ne joinem — osoba už nemusí v adresáři existovat (R8.3),
- časový rozsah — dvě datová pole od/do (standardní `date` input, zobrazení
  DD.MM.YYYY dělá filtr `datum`); kterákoli mez smí chybět.

Filtry se odesílají metodou GET, takže zůstanou v query stringu a stránkování
je přes `page_url` zachová.

**České popisky, žádné strojové kódy (R13.11).** Akce se vykreslují přes
`labels.label(AuditAction)`. Typ objektu (APPLICATION/USER/SESSION) není člen
doménového výčtu — je to `text` hodnota specifická pro audit — proto jeho
české popisky drží mapa `ENTITY_TYPE_LABELS` zde a předává se šabloně.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from regina.auth.deps import CurrentUser, SessionDep, require_read_audit
from regina.domain.enums import AuditAction
from regina.services.audit import ENTITY_APPLICATION
from regina.repositories import users as users_repo
from regina.repositories.audit import AuditFilters, list_audit_entries
from regina.web.pagination import paginate
from regina.web.templating import page_context

router = APIRouter(tags=["audit"])

# Velikost stránky výpisu (ui.md sekce 9, shodně s registrem). Rozhodnutí
# obrazovky, ne repozitáře.
_PAGE_SIZE = 20

# Guard aktéra vyhrazený roli Admin (R8.4). Vrací přihlášeného aktéra.
AuditReaderDep = Annotated[CurrentUser, Depends(require_read_audit)]

#: České popisky typu objektu auditního záznamu (`audit_log.entity_type`).
#: Entity type je `text` hodnota specifická pro audit, ne člen doménového
#: výčtu, proto popisky drží tato mapa (ne `domain/labels.py`). Do rozhraní se
#: nikdy nedostane strojový kód (R13.11).
ENTITY_TYPE_LABELS: dict[str, str] = {
    "APPLICATION": "Aplikace",
    "USER": "Uživatel",
    "SESSION": "Přihlášení",
}


def _parse_action(value: str | None) -> AuditAction | None:
    """Přeloží strojový kód akce z URL na člen `AuditAction`, nebo `None`.

    Neznámá či prázdná hodnota = „nezvoleno", aby ručně upravený odkaz
    (`?akce=NESMYSL`) výpis neshodil, jen se filtr neuplatní.
    """
    if not value:
        return None
    try:
        return AuditAction(value)
    except ValueError:
        return None


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    """Přeloží identifikátor aktéra z URL na `UUID`, nebo `None` při nesmyslu."""
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _parse_date(value: str | None) -> date | None:
    """Přeloží datum z URL (ISO `YYYY-MM-DD` z `date` inputu) na `date`.

    Prázdná nebo neplatná hodnota = mez nezvolena (otevřený interval), aby
    ručně upravený odkaz výpis neshodil.
    """
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _actor_options(session: SessionDep) -> list[dict[str, str]]:
    """Sestaví volby aktérů pro filtr z adresáře osob (R8.7).

    Aktér se vybírá **podle identity**: hodnota volby je `id` osoby, popisek je
    zobrazované jméno. Nabízí jen aktivní osoby z adresáře. Filtr tak míří na
    `actor_user_id`; zobrazení jména v tabulce se přesto bere ze snapshotu
    záznamu (R8.3), protože aktér už v adresáři být nemusí.
    """
    return [
        {"id": str(person.id), "label": person.display_name}
        for person in users_repo.list_active(session)
    ]


def _audit_list_context(
    request: Request,
    user: AuditReaderDep,
    session: SessionDep,
    *,
    akce: str | None,
    akter: str | None,
    od: str | None,
    do: str | None,
    page: int,
) -> dict[str, object]:
    """Sestaví kontext výpisu auditu — sdílený stránkou i fragmentem.

    Jedno místo, kde se z parametrů URL složí filtry, stránkování, volby aktérů
    a předvyplnění formuláře, aby celá stránka (`GET /audit`) i fragment živého
    filtrování (`GET /audit/fragment`) vykreslovaly z **týchž** dat. Filtruje
    repozitář nad databází (R3.6/R8.7); routa nic nepočítá v paměti.
    """
    action = _parse_action(akce)
    actor_id = _parse_uuid(akter)
    date_from = _parse_date(od)
    date_to = _parse_date(do)

    filters = AuditFilters(
        action=action,
        actor_user_id=actor_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=_PAGE_SIZE,
    )

    result = list_audit_entries(session, filters)
    pagination = paginate(total=result.total, page=page, page_size=_PAGE_SIZE)

    # Hodnoty pro předvyplnění filtrů zpět do formuláře (aby zůstaly po odeslání).
    selected = {
        "akce": akce or "",
        "akter": akter or "",
        "od": od or "",
        "do": do or "",
    }

    return page_context(
        request,
        user=user,
        active_nav="audit",
        section_title="Auditní logy",
        entries=result.items,
        pagination=pagination,
        actions=tuple(AuditAction),
        actors=_actor_options(session),
        entity_type_labels=ENTITY_TYPE_LABELS,
        application_entity_type=ENTITY_APPLICATION,
        selected=selected,
    )


@router.get("/audit", include_in_schema=False)
def audit_list(
    request: Request,
    user: AuditReaderDep,
    session: SessionDep,
    akce: str | None = Query(default=None),
    akter: str | None = Query(default=None),
    od: str | None = Query(default=None),
    do: str | None = Query(default=None),
    page: int = Query(default=1),
) -> HTMLResponse:
    """Vykreslí výpis auditního logu s filtry a stránkováním (R8.4, R8.7).

    Vyhrazeno roli Admin (`require_read_audit`); role User skončí 403 + audit
    `ACCESS_DENIED` (R8.4, R2.2). Parametry z URL:
    - `akce` — filtr typu akce (strojový kód `AuditAction`); prázdné = „Vše",
    - `akter` — filtr aktéra (`id` osoby); prázdné = všichni,
    - `od` / `do` — časový rozsah (kalendářní dny, ISO datum),
    - `page` — stránka výpisu.
    """
    context = _audit_list_context(
        request, user, session, akce=akce, akter=akter, od=od, do=do, page=page
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "audit/list.html", context)


@router.get("/audit/fragment", include_in_schema=False)
def audit_list_fragment(
    request: Request,
    user: AuditReaderDep,
    session: SessionDep,
    akce: str | None = Query(default=None),
    akter: str | None = Query(default=None),
    od: str | None = Query(default=None),
    do: str | None = Query(default=None),
    page: int = Query(default=1),
) -> HTMLResponse:
    """Vrátí **jen** výsledky výpisu (tabulka + stránkování) pro živé filtrování.

    Endpoint živého filtrování auditu (ui.md sekce 9, R8.7): obrazovka `/audit`
    sem při změně kteréhokoli filtru posílá celý formulář a vrácený partial vloží
    do kontejneru výsledků, aniž by přenačetla celou stránku. Renderuje
    `audit/_results.html` — stejný partial, jaký `audit/list.html` vkládá při
    prvním načtení, nad **týmž** kontextem (`_audit_list_context`), takže se
    stránka i fragment nikdy nerozejdou.

    Vyhrazeno roli Admin stejně jako `/audit` (`require_read_audit`); role User
    skončí 403 + audit `ACCESS_DENIED` — fragment tedy neobejde autorizaci.
    """
    context = _audit_list_context(
        request, user, session, akce=akce, akter=akter, od=od, do=do, page=page
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "audit/_results.html", context)
