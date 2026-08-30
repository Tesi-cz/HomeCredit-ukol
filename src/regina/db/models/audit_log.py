"""Model `audit_log` — kdo co udělal (database.md sekce 6).

Chronologický přírůstkový záznam akcí. Aplikace nad touto tabulkou nikdy
nevydá `UPDATE` ani `DELETE`, jedinou výjimkou je retenční rutina (R8.5) —
to je pravidlo aplikace, ne struktury.

`bigint` primární klíč ze stejného důvodu jako u `classification_log`
(database.md 13).

Klíčová rozhodnutí zapsaná ve struktuře:
- Snapshot aktéra (`actor_email`, `actor_display_name`) zůstává čitelný i po
  smazání osoby (R8.3).
- `entity_id` je **bez** cizího klíče — audit musí přežít zmizení objektu,
  o kterém vypovídá (database.md 6 a 10, R9.7).
- `changed_fields` obsahuje jen **názvy** změněných atributů, ne hodnoty,
  aby se do auditu nedostaly osobní údaje (R8.6, R12.10).
- Žádná IP adresa ani user agent (R8.6).

Výčty `action` a `entity_type` jsou `text` s `CHECK` constraintem jako
rozšiřitelný seznam povolených hodnot (design.md 6.4). Poradce doplní další
akce, aniž by šlo o breaking change (database.md 9).
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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from regina.db.base import Base

# Rozšiřitelné výčty (database.md 7 a 9).
AUDIT_ACTION_VALUES = (
    "SIGN_IN",
    "SIGN_OUT",
    "APP_CREATED",
    "APP_UPDATED",
    "APP_DECOMMISSIONED",
    "APP_REACTIVATED",
    "CLASSIFICATION_SET",
    "CLASSIFICATION_OVERRIDDEN",
    "ROLE_CHANGED",
    "ACCESS_DENIED",
)
AUDIT_ENTITY_TYPE_VALUES = ("APPLICATION", "USER", "SESSION")


def _in_list_sql(column: str, values: tuple[str, ...]) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


def _nullable_in_list_sql(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IS NULL OR {_in_list_sql(column, values)}"


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Prázdné u neúspěšného přihlášení. Bez `ON DELETE` klauzule: database.md 10
    # tuto vazbu mezi vynucená chování cizích klíčů neuvádí, a osobu s auditními
    # záznamy chrání před smazáním už `ON DELETE RESTRICT` na odpovědné trojici.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    # Snapshot aktéra pro čitelnost i po smazání osoby (R8.3).
    actor_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_display_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    action: Mapped[str] = mapped_column(String(32), nullable=False)

    entity_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Volná reference bez cizího klíče — audit přežije zmizení objektu (R9.7).
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Krátký popis v češtině.
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    # Jen názvy změněných atributů, nikdy hodnoty (R8.6, R12.10).
    changed_fields: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            _in_list_sql("action", AUDIT_ACTION_VALUES),
            name="action_allowed",
        ),
        CheckConstraint(
            _nullable_in_list_sql("entity_type", AUDIT_ENTITY_TYPE_VALUES),
            name="entity_type_allowed",
        ),
        # --- Indexy z database.md sekce 12 (přidáno v úkolu 4.4) ---
        # Filtry výpisu auditního logu (R8.7). Výpis řadí chronologicky sestupně,
        # proto `occurred_at DESC`.
        Index("ix_audit_log_occurred_at", occurred_at.desc()),
        # Dohledání akcí nad konkrétním objektem — volná reference bez FK.
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_actor_user_id", "actor_user_id"),
        Index("ix_audit_log_action", "action"),
    )

    def __repr__(self) -> str:  # pragma: no cover - jen pro ladění
        return f"<AuditLog id={self.id} action={self.action}>"
