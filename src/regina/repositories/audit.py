"""Repozitář auditního logu — dotaz pro výpis `/audit` (design.md 6.1, R8).

Auditní obrazovka (úkol 17.1, ui.md sekce 9) zobrazuje záznamy **od nejnovějšího**
se sloupci Čas, Aktér, Akce, Objekt, Popis a s filtry podle akce, aktéra a
časového rozsahu (R8.7), stránkovaně. Tento repozitář drží jediný dotaz, který
tuto množinu načte — filtrování, řazení i stránkování provádí **databáze**, ne
aplikace v paměti; odpověď obsahuje jen požadovanou stránku plus celkový počet
odpovídající filtrům (pro text „Zobrazeno X–Y z N záznamů").

Klíčová rozhodnutí dotazu:

- **Řazení od nejnovějšího** (ui.md sekce 9): `occurred_at DESC`, sekundárně
  `id DESC` (log má monotónní `bigint` klíč), aby bylo pořadí stabilní i u
  záznamů se shodným razítkem. Využívá index `ix_audit_log_occurred_at`.
- **Filtr akce** (R8.7): přesná shoda `action` proti strojovému kódu
  `AuditAction`. Neplatná hodnota z URL se řeší ve vrstvě routy (přeloží se na
  „nezvoleno"), sem přichází buď platný člen výčtu, nebo `None`.
- **Filtr aktéra** (R8.7): shoda `actor_user_id`. Aktér se vybírá z **rozbalovací
  nabídky známých osob** (route ji plní z adresáře), takže filtr míří na
  identitu, ne na text snapshotu. Zobrazované jméno aktéra v tabulce se přesto
  bere ze **snapshotu** (`actor_display_name`/`actor_email`), ne joinem — osoba
  už nemusí v adresáři existovat (R8.3). Záznamy bez aktéra (`actor_user_id IS
  NULL`, např. neúspěšné přihlášení) se při zvoleném aktérovi přirozeně
  nevyberou (rovnost v SQL neplatí pro NULL).
- **Časový rozsah** (R8.7): `occurred_at >= od` a `occurred_at < do + 1 den`.
  Meze jsou **kalendářní dny** (uživatel zadává datum, ne čas); horní mez je
  proto exkluzivní půlnoc následujícího dne, aby do rozsahu spadl celý zvolený
  koncový den. Kterákoli mez smí chybět (otevřený interval).
- **Stránkování** (R8.7): `LIMIT`/`OFFSET`; celkový počet přes `COUNT` nad
  **stejnými filtry, ale před stránkováním**, takže „z N" sedí na filtry.

Repozitář vrací čisté řádky `audit_log`. Zobrazované jméno aktéra i české
popisky výčtů skládá až šablona přes `labels.py` — audit drží strojové kódy
(R13.11). Objekt (typ entity + id) se rovněž vykresluje až v šabloně.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from regina.db.models.audit_log import AuditLog
from regina.domain.enums import AuditAction


@dataclass(frozen=True)
class AuditFilters:
    """Parametry výpisu auditního logu, jak je route sesbírá z URL (R8.7).

    Všechna pole jsou volitelná a výchozí hodnoty dávají „výchozí výpis":
    bez filtru akce, bez filtru aktéra, otevřený časový interval, první stránka.

    - `action`: přesná shoda typu akce (`AuditAction`). `None` = bez filtru.
    - `actor_user_id`: shoda identity aktéra (`actor_user_id`). `None` = bez
      filtru. Záznamy bez aktéra se při zvoleném aktérovi nevyberou (NULL).
    - `date_from` / `date_to`: kalendářní dny časového rozsahu (včetně obou
      dnů). Kterákoli mez smí být `None` (otevřený interval).
    - `page` / `page_size`: stránkování (od 1; ořez do platného rozsahu).
    """

    action: AuditAction | None = None
    actor_user_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class AuditListResult:
    """Výsledek výpisu: jedna stránka záznamů plus celkový počet přes filtry.

    `total` je počet záznamů odpovídajících filtrům **napříč všemi stránkami**
    (před `LIMIT`/`OFFSET`), takže route z něj sestaví „Zobrazeno X–Y z N".
    `items` je jen požadovaná stránka, seřazená od nejnovějšího.
    """

    items: list[AuditLog] = field(default_factory=list)
    total: int = 0


def _start_of_day(day: date) -> datetime:
    """Půlnoc daného dne v UTC — dolní mez časového rozsahu (inkluzivní).

    `occurred_at` je uložený s časovou zónou (`DateTime(timezone=True)`), proto
    se i mez skládá jako aware `datetime` v UTC, aby porovnání nemíchalo naivní
    a aware hodnoty.
    """
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def _apply_filters(stmt: Select, filters: AuditFilters) -> Select:
    """Přidá na dotaz `WHERE` klauzule společné pro výpis i pro počítání.

    Sdílí je stránkovací dotaz i `COUNT`, aby celkový počet vždy odpovídal
    přesně té množině, kterou uživatel vidí (jen bez `LIMIT`/`OFFSET`).
    """
    if filters.action is not None:
        stmt = stmt.where(AuditLog.action == filters.action.value)

    if filters.actor_user_id is not None:
        stmt = stmt.where(AuditLog.actor_user_id == filters.actor_user_id)

    if filters.date_from is not None:
        stmt = stmt.where(AuditLog.occurred_at >= _start_of_day(filters.date_from))

    if filters.date_to is not None:
        # Horní mez exkluzivní půlnoc následujícího dne, aby do rozsahu spadl
        # celý zvolený koncový den (uživatel zadává datum, ne čas).
        upper = _start_of_day(filters.date_to + timedelta(days=1))
        stmt = stmt.where(AuditLog.occurred_at < upper)

    return stmt


def list_audit_entries(
    session: Session, filters: AuditFilters | None = None
) -> AuditListResult:
    """Vrátí jednu stránku auditního výpisu a celkový počet přes filtry (R8.7).

    Vše dělá databáze; do paměti se načítá jen požadovaná stránka. Řazení je
    napevno `occurred_at DESC, id DESC` (od nejnovějšího, stabilní), nikdy podle
    hodnoty z URL. Celkový počet se počítá přes stejné filtry, ale bez řazení a
    stránkování, takže „z N" sedí na filtry.

    Stránkování se defenzivně ořeže: `page` nejméně 1, `page_size` nejméně 1.
    Přepočet neplatné stránky mimo rozsah řeší `web/pagination.paginate()` v
    route; zde jde jen o platný `OFFSET`.
    """
    filters = filters or AuditFilters()

    page = filters.page if filters.page >= 1 else 1
    page_size = filters.page_size if filters.page_size >= 1 else 1

    count_stmt = _apply_filters(select(func.count()).select_from(AuditLog), filters)
    total = int(session.execute(count_stmt).scalar_one())

    page_stmt = _apply_filters(select(AuditLog), filters)
    page_stmt = (
        page_stmt.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    items = list(session.execute(page_stmt).scalars().all())

    return AuditListResult(items=items, total=total)
