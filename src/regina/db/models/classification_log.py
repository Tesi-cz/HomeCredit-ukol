"""Model `classification_log` — kdo zapsal klasifikaci a proč (database.md 5).

Nemazatelná historie zápisů klasifikace. Každý zápis je jeden řádek, i když
jde o pouhou opravu. Zdroj pro zobrazení historie a business logiku; `audit_log`
je oproti tomu zdroj pro dohled.

`bigint` primární klíč: logy jsou přírůstkové a nikdy nejsou v adrese, takže
monotónní číslo dává levné řazení (database.md 13).

Výčet `source` je `text` s `CHECK` constraintem formulovaným jako rozšiřitelný
seznam povolených hodnot (database.md 9, design.md 6.4). Poradce ho později
doplní o `AI` a `AI_OVERRIDDEN`, aniž by šlo o breaking change. Povinný důvod
u `ADMIN_OVERRIDE` je `CHECK` constraint v úkolu 4.2.
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
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from regina.db.base import Base

# Rozšiřitelný výčet (database.md 9). Jádro zná dvě hodnoty, poradce přidá další.
CLASSIFICATION_SOURCE_VALUES = ("HUMAN", "ADMIN_OVERRIDE")
# Klasifikace samotná používá stejné hodnoty jako `applications.classification`.
CLASSIFICATION_VALUES = ("SMALL", "MEDIUM", "LARGE")


def _in_list_sql(column: str, values: tuple[str, ...]) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


def _nullable_in_list_sql(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IS NULL OR {_in_list_sql(column, values)}"


class ClassificationLog(Base):
    __tablename__ = "classification_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # `ON DELETE CASCADE`: smaže-li retence vyřazenou aplikaci, odejde s ní
    # i její historie klasifikace — bez záznamu nemá výpovědní hodnotu
    # (database.md 10, R9.7).
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Hodnota, kterou člověk zapsal, a hodnota před změnou.
    classification: Mapped[str] = mapped_column(Text, nullable=False)
    previous_classification: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[str] = mapped_column(String(20), nullable=False)

    # Povinný pro ADMIN_OVERRIDE — vynuceno `CHECK` constraintem v úkolu 4.2.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Člověk, který klasifikaci zapsal. `ON DELETE RESTRICT`: autorství zápisu
    # musí zůstat dohledatelné (database.md 10).
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            _in_list_sql("source", CLASSIFICATION_SOURCE_VALUES),
            name="source_allowed",
        ),
        CheckConstraint(
            _in_list_sql("classification", CLASSIFICATION_VALUES),
            name="classification_allowed",
        ),
        CheckConstraint(
            _nullable_in_list_sql("previous_classification", CLASSIFICATION_VALUES),
            name="previous_classification_allowed",
        ),
        # Povinný a neprázdný důvod u přepisu správcem (database.md 5, R7.2).
        # Formulace „buď to není ADMIN_OVERRIDE, nebo je důvod neprázdný" drží
        # i při ručním opravném SQL mimo aplikaci. `trim` ošetří samé mezery.
        CheckConstraint(
            "source <> 'ADMIN_OVERRIDE' "
            "OR (reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="admin_override_requires_reason",
        ),
        # Index z database.md sekce 12 (přidáno v úkolu 4.4).
        # `(application_id, created_at DESC)` — nese zobrazení historie na
        # detailu (od nejnovějšího) i nalezení posledního zápisu pro aplikaci.
        Index(
            "ix_classification_log_application_created",
            "application_id",
            created_at.desc(),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - jen pro ladění
        return f"<ClassificationLog id={self.id} app={self.application_id} source={self.source}>"
