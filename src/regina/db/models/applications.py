"""Model `applications` — jádro registru (database.md sekce 4).

Jeden řádek je jedna evidovaná interní aplikace. Patnáct sloupců rozdělených
do skupin: identifikace, odpovědnost, životní cyklus, AI, klasifikace.

Výčty `lifecycle_state` a `classification` jsou `text` s `CHECK` constraintem
jako rozšiřitelný seznam povolených hodnot, ne nativní `ENUM` (design.md 6.4).
Klasifikace je denormalizovaný sloupec držící **platnou** hodnotu; historii
drží `classification_log`. Invariant „mění se jen v jedné transakci se zápisem
do logu" hlídá služba (database.md 4), zde jde jen o strukturu.

Odpovědná trojice jsou cizí klíče na `users`, ne jména jako volný text
(database.md princip 2, R2.6). Všechny vazby na osoby (`owner_user_id`,
`deputy_user_id`, `tech_admin_user_id`, `decommissioned_by`,
`created_by_user_id`) mají `ON DELETE RESTRICT`: osobu nelze smazat, dokud je
někde uvedena jako odpovědná (database.md 10, R9.8).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from regina.db.base import Base

# Povolené hodnoty výčtů (database.md 7). Klasifikace je zpočátku prázdná,
# proto je sloupec nullable a v `CHECK` se povoluje i NULL.
LIFECYCLE_STATE_VALUES = (
    "DRAFT",
    "IN_DEVELOPMENT",
    "TESTING",
    "IN_PRODUCTION",
    "DECOMMISSIONED",
)
CLASSIFICATION_VALUES = ("SMALL", "MEDIUM", "LARGE")


def _in_list_sql(column: str, values: tuple[str, ...]) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


def _nullable_in_list_sql(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IS NULL OR {_in_list_sql(column, values)}"


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # --- Identifikace ---
    # Unikátnost názvu bez ohledu na velikost písmen řeší úkol 4.2/4.4.
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Útvar je výčet z konfigurace, validovaný v aplikaci (database.md 7).
    department: Mapped[str] = mapped_column(Text, nullable=False)

    # --- Životní cyklus ---
    lifecycle_state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="DRAFT",
    )
    # Vyplněné právě tehdy, když je stav DECOMMISSIONED — vazbu na stav
    # vynucuje `CHECK` constraint v úkolu 4.2.
    decommissioned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    decommissioned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # --- Odpovědnost ---
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    deputy_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    tech_admin_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # --- AI ---
    # AI model použitý evidovanou aplikací, ne naším registrem (database.md 4).
    ai_model: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Klasifikace (denormalizovaná platná hodnota) ---
    classification: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Metadata vzniku ---
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            _in_list_sql("lifecycle_state", LIFECYCLE_STATE_VALUES),
            name="lifecycle_state_allowed",
        ),
        CheckConstraint(
            _nullable_in_list_sql("classification", CLASSIFICATION_VALUES),
            name="classification_allowed",
        ),
        # `decommissioned_at` je vyplněné právě tehdy, když je stav
        # DECOMMISSIONED (database.md 4). Ekvivalence obou směrů: ve stavu
        # DECOMMISSIONED musí být čas vyplněný, v jiném stavu musí být prázdný.
        CheckConstraint(
            "(lifecycle_state = 'DECOMMISSIONED' AND decommissioned_at IS NOT NULL) "
            "OR (lifecycle_state <> 'DECOMMISSIONED' AND decommissioned_at IS NULL)",
            name="decommissioned_at_iff_decommissioned",
        ),
        # Unikátní název bez ohledu na velikost písmen (database.md 4 a 12, R5.8).
        # Funkcionální unikátní index nad `lower(name)` — zabrání dvojím
        # záznamům lišícím se jen velikostí písmen. (Přidáno v úkolu 4.2.)
        Index(
            "uq_applications_lower_name",
            func.lower(name),
            unique=True,
        ),
        # --- Indexy z database.md sekce 12 (přidáno v úkolu 4.4) ---
        # Částečný index na nevyřazené záznamy — nese výchozí výpis registru,
        # který filtruje `lifecycle_state <> 'DECOMMISSIONED'` (R3.9).
        Index(
            "ix_applications_active",
            "lifecycle_state",
            postgresql_where=text("lifecycle_state <> 'DECOMMISSIONED'"),
        ),
        # `decommissioned_at` — hranici počítá retenční rutina (database.md 11).
        Index("ix_applications_decommissioned_at", "decommissioned_at"),
        # `lower(name)` pro vyhledávání bez ohledu na velikost písmen (R3.2).
        # Uveden v sekci 12 samostatně vedle unikátního indexu; unikátní index
        # nad `lower(name)` by pro vyhledávání posloužil také, tento je zde
        # kvůli věrnosti sekci 12 a jasnému oddělení účelu (hledání vs. unikátnost).
        Index("ix_applications_lower_name", func.lower(name)),
        # Filtry výpisu podle útvaru, klasifikace a stavu (R3.3).
        Index("ix_applications_department", "department"),
        Index("ix_applications_classification", "classification"),
        Index("ix_applications_lifecycle_state", "lifecycle_state"),
        # Kontrola oprávnění nad odpovědnou trojicí (database.md 12).
        Index("ix_applications_owner_user_id", "owner_user_id"),
        Index("ix_applications_deputy_user_id", "deputy_user_id"),
        Index("ix_applications_tech_admin_user_id", "tech_admin_user_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - jen pro ladění
        return f"<Application id={self.id} name={self.name!r} state={self.lifecycle_state}>"
