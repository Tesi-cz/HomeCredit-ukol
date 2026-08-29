"""Export registru a auditního logu do CSV (design.md sekce 5, R10).

Export je čtecí operace vyhrazená roli Admin (R10.1, R10.2, R10.4). Vynucení
„jen Admin" **neleží zde** — je v guardu `require_export` (`auth/deps.py`),
který volají routy exportu. Tato služba jen sestaví CSV z řádků, které jí
route předá; nezná HTTP ani autorizaci.

**Filtrovaná množina, ne celý datový soubor (R10.3).** Obě funkce přijímají
tytéž filtry jako obrazovkový výpis (`ListFilters` pro registr, `AuditFilters`
pro audit) a exportují přesně to, co by uživatel viděl na obrazovce — jen bez
stránkování. Toho se dosáhne tím, že se filtry použijí se `page_size` pokrývající
celou množinu (dopočítá se z `total`), takže se sdílí přesně jedna dotazovací
cesta s výpisem a export se nikdy nerozejde s tím, co obrazovka ukazuje.

**Kódování a BOM.** CSV se kóduje v UTF-8 (R10.5). Navíc se na začátek přidává
UTF-8 BOM (`\ufeff`). Je to vědomé rozhodnutí a jediná výjimka z projektového
pravidla „žádný BOM": to pravidlo platí pro **zdrojové soubory** (`.env`, `.py`,
`.md`, …), které rozbíjí parsery. Vygenerované CSV je **data ke stažení**, ne
zdrojový soubor. Microsoft Excel — nejčastější nástroj, kterým správce CSV
otevře — bez BOM interpretuje soubor v systémovém kódování (Windows-1250) a
česká diakritika se rozbije na mojibake. S BOM Excel pozná UTF-8 a diakritiku
zobrazí správně. Ostatní nástroje (pandas, LibreOffice) BOM tolerují. BOM proto
přidáváme.

**České popisky, nikdy strojové kódy (R10.5).** Výčty (stav, klasifikace,
zdroj klasifikace, akce, typ objektu) se do CSV zapisují jako české popisky
z `domain/labels.py`, přesně jako v rozhraní (R13.11). Záznam bez klasifikace
má „Neklasifikováno". Osoby (vlastník, zástupce, technický správce, aktér) se
vypisují **zobrazovaným jménem** — identifikátory se přeloží na jména jedním
dotazem; u auditu se jméno bere ze snapshotu záznamu (`actor_display_name`),
protože osoba už nemusí v adresáři existovat (R8.3).

**Výstup pro stažení.** Obě funkce vracejí dvojici `(filename, csv_bytes)`:
český název souboru s příponou `.csv` a hotové bajty (UTF-8 s BOM), které route
zabalí do `Response`/`StreamingResponse` s `Content-Disposition: attachment`.
Bajty se staví celé do paměti — export registru i auditu má v tomto rozsahu
řádově stovky až tisíce řádků, takže streamování po řádcích nemá přínos a
jednodušší je vrátit hotový obsah.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from regina.db.models.applications import Application
from regina.db.models.audit_log import AuditLog
from regina.db.models.users import User
from regina.domain import labels
from regina.domain.enums import (
    AuditAction,
    Classification,
    LifecycleState,
)
from regina.repositories.applications import ListFilters, list_applications
from regina.repositories.audit import AuditFilters, list_audit_entries

# UTF-8 BOM. Přidává se na začátek CSV, aby Excel poznal UTF-8 a nezobrazil
# českou diakritiku jako mojibake (viz docstring modulu). Jediná výjimka
# z projektového pravidla „žádný BOM" — platí pro zdrojové soubory, ne pro
# vygenerovaná data ke stažení.
_UTF8_BOM = "\ufeff"

# Zástupný symbol pro chybějící hodnotu v buňce (osoba bez jména, prázdné pole).
_MISSING = ""

# Názvy souborů ke stažení (české, s příponou .csv).
REGISTRY_FILENAME = "registr-aplikaci.csv"
AUDIT_FILENAME = "auditni-log.csv"

# České hlavičky sloupců.
REGISTRY_HEADERS = (
    "Název",
    "Popis",
    "Útvar",
    "Vlastník",
    "Zástupce",
    "Technický správce",
    "Stav",
    "Klasifikace",
    "AI model",
)
AUDIT_HEADERS = (
    "Čas",
    "Aktér",
    "E-mail aktéra",
    "Akce",
    "Objekt",
    "Popis",
    "Změněná pole",
)

#: České popisky typu objektu auditního záznamu (`audit_log.entity_type`).
#: Zrcadlí `web/routes/audit.ENTITY_TYPE_LABELS` — entity type je `text`
#: hodnota specifická pro audit, ne člen doménového výčtu, takže popisky drží
#: mapa (ne `domain/labels.py`). Do CSV se nikdy nedostane strojový kód (R10.5).
ENTITY_TYPE_LABELS: dict[str, str] = {
    "APPLICATION": "Aplikace",
    "USER": "Uživatel",
    "SESSION": "Přihlášení",
}

# Formát časového razítka v CSV: DD.MM.YYYY HH:MM, shodně s rozhraním
# (`web/templating.datum_cas`, R13.3). Vědomé rozhodnutí exportu — jednotné
# s tím, co uživatel vidí v tabulce auditu, ne ISO.
_TIMESTAMP_FORMAT = "%d.%m.%Y %H:%M"


def _encode(rows: Iterable[Iterable[object]]) -> bytes:
    """Sestaví CSV bajty (UTF-8 s BOM) z posloupnosti řádků.

    Používá standardní modul `csv`, takže se hodnoty s čárkou, uvozovkou nebo
    koncem řádku správně uvozují (quoting). Řádky se oddělují `\\r\\n` (výchozí
    `csv`, kompatibilní s Excelem). BOM se přidává jednou na začátek.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in rows:
        writer.writerow(["" if cell is None else str(cell) for cell in row])
    return (_UTF8_BOM + buffer.getvalue()).encode("utf-8")


def _lifecycle_label(value: str | None) -> str:
    """Český popisek stavu ze strojového kódu (R10.5). Prázdný kód → prázdno."""
    if not value:
        return _MISSING
    return labels.label(LifecycleState(value))


def _classification_label(value: str | None) -> str:
    """Český popisek klasifikace včetně stavu bez klasifikace (R10.5).

    Prázdná hodnota (`None`/prázdný řetězec) → „Neklasifikováno" přes
    `labels.classification_label(None)`.
    """
    if not value:
        return labels.classification_label(None)
    return labels.classification_label(Classification(value))


def _person_names(
    session: Session, applications: list[Application]
) -> dict[uuid.UUID, str]:
    """Dohledá mapu `id → display_name` pro všechny osoby z odpovědných trojic.

    Jeden dotaz nad sjednocenou množinou vlastníků, zástupců a technických
    správců z exportované množiny. Šablona/řádek pak zobrazí jméno; chybějící
    osoba (nemělo by nastat, cizí klíče to hlídají) se přeloží na prázdno.
    Porovnává se výhradně identita, nikdy jméno (R2.6).
    """
    ids: set[uuid.UUID] = set()
    for app in applications:
        ids.add(app.owner_user_id)
        if app.deputy_user_id is not None:
            ids.add(app.deputy_user_id)
        ids.add(app.tech_admin_user_id)
    if not ids:
        return {}
    rows = session.execute(
        select(User.id, User.display_name).where(User.id.in_(ids))
    ).all()
    return {row[0]: row[1] for row in rows}


def _person_name(names: dict[uuid.UUID, str], person_id: uuid.UUID | None) -> str:
    """Vrátí zobrazované jméno osoby, nebo prázdno (chybí / bez zástupce)."""
    if person_id is None:
        return _MISSING
    return names.get(person_id, _MISSING)


def _all_applications(session: Session, filters: ListFilters | None) -> list[Application]:
    """Načte **všechny** záznamy odpovídající filtrům, bez stránkování (R10.3).

    Sdílí přesně jednu dotazovací cestu s obrazovkovým výpisem
    (`list_applications`), takže export nikdy neukáže jinou množinu než tabulka.
    Nejprve zjistí `total` přes filtry, pak načte jednu „stránku" té velikosti.
    Prázdná množina se ošetří `page_size >= 1` (repozitář to stejně ořízne).
    """
    base = filters or ListFilters()
    total = list_applications(session, base).total
    unpaged = ListFilters(
        query=base.query,
        department=base.department,
        classification=base.classification,
        unclassified_only=base.unclassified_only,
        state=base.state,
        include_decommissioned=base.include_decommissioned,
        sort_desc=base.sort_desc,
        page=1,
        page_size=max(total, 1),
        trio_member_id=base.trio_member_id,
    )
    return list_applications(session, unpaged).items


def export_registry_csv(
    session: Session, filters: ListFilters | None = None
) -> tuple[str, bytes]:
    """Export registru aplikací do CSV (R10.1, R10.3, R10.5).

    Vrací `(filename, csv_bytes)`: český název souboru a hotové bajty v UTF-8
    s BOM. Sloupce mají české hlavičky (`REGISTRY_HEADERS`); výčty (stav,
    klasifikace) se vypisují českými popisky, záznam bez klasifikace má
    „Neklasifikováno" (R10.5). Osoby odpovědné trojice se vypisují jménem
    (identifikátory přeložené jedním dotazem).

    Při aktivních `filters` se exportuje **filtrovaná** množina, ne celý
    registr (R10.3) — sdílí se dotaz s obrazovkovým výpisem, jen bez stránkování.
    """
    applications = _all_applications(session, filters)
    names = _person_names(session, applications)

    def _rows() -> Iterable[Iterable[object]]:
        yield REGISTRY_HEADERS
        for app in applications:
            yield (
                app.name,
                app.description or _MISSING,
                app.department,
                _person_name(names, app.owner_user_id),
                _person_name(names, app.deputy_user_id),
                _person_name(names, app.tech_admin_user_id),
                _lifecycle_label(app.lifecycle_state),
                _classification_label(app.classification),
                app.ai_model or _MISSING,
            )

    return REGISTRY_FILENAME, _encode(_rows())


def _all_audit_entries(
    session: Session, filters: AuditFilters | None
) -> list[AuditLog]:
    """Načte **všechny** auditní záznamy odpovídající filtrům, bez stránkování.

    Stejný vzor jako `_all_applications`: sdílí dotaz s obrazovkovým výpisem
    (`list_audit_entries`), takže export odpovídá tabulce (R10.3). Řazení od
    nejnovějšího zůstává zachované.
    """
    base = filters or AuditFilters()
    total = list_audit_entries(session, base).total
    unpaged = AuditFilters(
        action=base.action,
        actor_user_id=base.actor_user_id,
        date_from=base.date_from,
        date_to=base.date_to,
        page=1,
        page_size=max(total, 1),
    )
    return list_audit_entries(session, unpaged).items


def _timestamp(value: datetime | None) -> str:
    """Naformátuje čas do DD.MM.YYYY HH:MM (R13.3), nebo prázdno pro `None`."""
    if value is None:
        return _MISSING
    return value.strftime(_TIMESTAMP_FORMAT)


def _action_label(value: str) -> str:
    """Český popisek auditní akce ze strojového kódu (R10.5, R13.11)."""
    return labels.label(AuditAction(value))


def _object_label(entity_type: str | None, entity_id: uuid.UUID | None) -> str:
    """Sestaví český popis objektu: „Typ (id)", nebo prázdno.

    Typ objektu se překládá českým popiskem (`ENTITY_TYPE_LABELS`), nikdy
    strojovým kódem (R10.5). Identifikátor se přidá do závorky, aby šlo záznam
    dohledat; bez typu se vrací prázdno.
    """
    if not entity_type:
        return _MISSING
    label = ENTITY_TYPE_LABELS.get(entity_type, entity_type)
    if entity_id is not None:
        return f"{label} ({entity_id})"
    return label


def export_audit_csv(
    session: Session, filters: AuditFilters | None = None
) -> tuple[str, bytes]:
    """Export auditního logu do CSV (R10.2, R10.3, R10.5).

    Vrací `(filename, csv_bytes)`: český název souboru a hotové bajty v UTF-8
    s BOM. Sloupce mají české hlavičky (`AUDIT_HEADERS`); čas se formátuje
    DD.MM.YYYY HH:MM (R13.3), akce a typ objektu se vypisují českými popisky
    (R10.5). Aktér i jeho e-mail se berou ze **snapshotu** záznamu (R8.3) —
    osoba už nemusí v adresáři existovat. Změněná pole jsou jen **názvy**
    atributů (bez hodnot, R8.6), spojené čárkou.

    Při aktivních `filters` se exportuje **filtrovaná** množina, ne celý log
    (R10.3) — sdílí se dotaz s obrazovkovým výpisem, jen bez stránkování.
    """
    entries = _all_audit_entries(session, filters)

    def _rows() -> Iterable[Iterable[object]]:
        yield AUDIT_HEADERS
        for entry in entries:
            changed = ", ".join(entry.changed_fields) if entry.changed_fields else _MISSING
            yield (
                _timestamp(entry.occurred_at),
                entry.actor_display_name or _MISSING,
                entry.actor_email or _MISSING,
                _action_label(entry.action),
                _object_label(entry.entity_type, entry.entity_id),
                entry.summary or _MISSING,
                changed,
            )

    return AUDIT_FILENAME, _encode(_rows())
