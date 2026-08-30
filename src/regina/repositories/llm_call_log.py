"""Repozitář logu volání modelu — výpis pro Admina (classification-advisor R6.3).

Admin obrazovka zobrazuje technické záznamy volání modelu od nejnovějšího:
implementace, model, operace, tokeny, latence, stav, čas. **Bez obsahu** — ten
se neukládá (R6.2), takže výpis ani nemá co citlivého zobrazit.

Jediný dotaz: stránkovaně, řazeno `occurred_at DESC, id DESC` (od nejnovějšího,
stabilní i při shodném razítku), přes index `ix_llm_call_log_occurred_at`.
Filtrování ani řazení podle URL se v tomto rozsahu nedělá — výpis je prostý
přehled. Celkový počet se počítá zvlášť pro text „Zobrazeno X–Y z N".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from regina.db.models.llm_call_log import LLMCallLog


@dataclass(frozen=True)
class LLMCallLogResult:
    """Jedna stránka záznamů plus celkový počet (pro „Zobrazeno X–Y z N")."""

    items: list[LLMCallLog] = field(default_factory=list)
    total: int = 0


def list_calls(session: Session, *, page: int = 1, page_size: int = 20) -> LLMCallLogResult:
    """Vrátí jednu stránku výpisu volání modelu a celkový počet.

    Vše dělá databáze; do paměti jen požadovaná stránka. `page`/`page_size` se
    defenzivně ořežou na nejméně 1 (přepočet mimo rozsah řeší `paginate` v routě).
    """
    page = page if page >= 1 else 1
    page_size = page_size if page_size >= 1 else 1

    total = int(session.execute(select(func.count()).select_from(LLMCallLog)).scalar_one())

    stmt = (
        select(LLMCallLog)
        .order_by(LLMCallLog.occurred_at.desc(), LLMCallLog.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    items = list(session.execute(stmt).scalars().all())

    return LLMCallLogResult(items=items, total=total)
