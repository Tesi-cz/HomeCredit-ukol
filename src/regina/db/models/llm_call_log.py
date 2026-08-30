"""Model `llm_call_log` — technický záznam volání modelu (database.md 3, R6).

Přehled o volání modelu pro provoz a náklady. **Nikdy obsah** — žádný sloupec
pro prompt, odpověď, poznámku dotazníku ani přepis (R6.2). Absence sloupce je
silnější garance než pravidlo v kódu: osobní údaje se sem nedostanou ani
nedopatřením. `error_code` nese jen strojový kód chyby, nikdy její text.

`bigint` primární klíč jako ostatní přírůstkové logy (database.md 13).
Vazby na `applications` a `users` jsou `ON DELETE SET NULL`: technický log
přežije smazání aplikace i osoby, jen se odkaz vynuluje — na rozdíl od jádra
nedrží log žádnou tvrdou vazbu, kterou by bylo nutné chránit.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from regina.db.base import Base

# Rozšiřitelné výčty jako CHECK (design.md 6.4). Jádro implementací:
# OPENROUTER (reálné volání), MOCK (bez sítě), AI_GATEWAY (firemní brána).
GATEWAY_IMPL_VALUES = ("OPENROUTER", "MOCK", "AI_GATEWAY")
LLM_OPERATION_VALUES = ("CLASSIFY", "REWRITE", "TRANSCRIBE")
LLM_STATUS_VALUES = ("SUCCESS", "TIMEOUT", "ERROR")


def _in_list_sql(column: str, values: tuple[str, ...]) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


class LLMCallLog(Base):
    __tablename__ = "llm_call_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Volání bez záznamu (dotazník před vznikem aplikace) → nullable.
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    gateway_impl: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)

    # Tokeny mock nezná → nullable.
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # Strojový kód chyby, NIKDY text chyby (R6.2).
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            _in_list_sql("gateway_impl", GATEWAY_IMPL_VALUES),
            name="gateway_impl_allowed",
        ),
        CheckConstraint(
            _in_list_sql("operation", LLM_OPERATION_VALUES),
            name="operation_allowed",
        ),
        CheckConstraint(
            _in_list_sql("status", LLM_STATUS_VALUES),
            name="status_allowed",
        ),
        # Retence maže podle `occurred_at` (database.md 7).
        Index("ix_llm_call_log_occurred_at", "occurred_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - jen pro ladění
        return f"<LLMCallLog id={self.id} impl={self.gateway_impl} status={self.status}>"
