"""Model `classification_suggestions` — doporučení poradce (database.md 2, R3.9).

Uchovává jedno doporučení: co poradce navrhl, proč, z jakých odpovědí a z jakého
volání vzniklo. Detail záznamu z něj ukáže, že klasifikace pochází z návrhu
modelu.

**Bez obsahu promptu.** Ukládají se odpovědi dotazníku (uzavřené volby a skóre)
a výsledné zdůvodnění — ne prompt poslaný modelu ani volná poznámka uživatele
(ta je osobní vstup, R6.2). `questionnaire_answers` nese jen výběry z uzavřené
nabídky, žádný volný text.

Vazby jsou `ON DELETE SET NULL`: doporučení přežije smazání aplikace, osoby
i technického logu — retence smí log volání smazat dřív a doporučení pak jen
ztratí odkaz, ne integritu.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from regina.db.base import Base

CLASSIFICATION_VALUES = ("SMALL", "MEDIUM", "LARGE")


def _in_list_sql(column: str, values: tuple[str, ...]) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


class ClassificationSuggestion(Base):
    __tablename__ = "classification_suggestions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Dotazník smí běžet před vznikem záznamu → nullable.
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
    )

    suggested_classification: Mapped[str] = mapped_column(Text, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    questionnaire_version: Mapped[str] = mapped_column(Text, nullable=False)
    # Jen uzavřené volby a skóre po dimenzích — žádný volný text (R6.2).
    questionnaire_answers: Mapped[dict] = mapped_column(JSONB, nullable=False)
    deterministic_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # true = návrh z deterministického fallbacku, ne z modelu (R3.4).
    is_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    # Prázdné u fallbacku bez volání modelu; jinak vazba na technický log.
    llm_call_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("llm_call_log.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            _in_list_sql("suggested_classification", CLASSIFICATION_VALUES),
            name="suggested_classification_allowed",
        ),
        # Retence maže podle `created_at` (database.md 7).
        Index("ix_classification_suggestions_created_at", "created_at"),
        Index("ix_classification_suggestions_application_id", "application_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - jen pro ladění
        return (
            f"<ClassificationSuggestion id={self.id} "
            f"level={self.suggested_classification} fallback={self.is_fallback}>"
        )
