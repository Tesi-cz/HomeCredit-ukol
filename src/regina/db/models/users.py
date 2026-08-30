"""Model `users` — adresář osob a lokální role (database.md sekce 3).

Databáze nikdy nedrží ověřovací materiál: žádné heslo, hash ani token
(database.md princip 1, R1.2). Tabulka eviduje osoby kvůli autorizaci
(porovnání identit u odpovědné trojice) a kvůli přiřazení osoby, která se
dosud nepřihlásila.

Výčty `role` a `role_source` jsou `text` s `CHECK` constraintem formulovaným
jako rozšiřitelný seznam povolených hodnot, ne nativní `ENUM` (design.md 6.4).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from regina.db.base import Base

# Povolené hodnoty výčtů. Seznam je záměrně otevřený rozšíření (database.md 7);
# constraint níže se formuluje jako „hodnota je v seznamu", ne jako vyloučení.
ROLE_VALUES = ("USER", "ADMIN")
ROLE_SOURCE_VALUES = ("LOCAL", "IDP")


def _in_list_sql(column: str, values: tuple[str, ...]) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # `oidc_subject` je zpočátku prázdný a doplní se při prvním přihlášení
    # (database.md 3). Unikátnost řeší úkol 4.2/4.4; tady jen struktura sloupce.
    oidc_subject: Mapped[str | None] = mapped_column(Text, nullable=True)

    # E-mail je spojovací klíč mezi adresářem osob a poskytovatelem identity.
    email: Mapped[str] = mapped_column(Text, nullable=False)

    display_name: Mapped[str] = mapped_column(Text, nullable=False)

    # Pracovní pozice napájí zobrazení u odpovědné trojice na detailu (R4.3).
    job_title: Mapped[str | None] = mapped_column(Text, nullable=True)

    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="USER",
    )
    role_source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="LOCAL",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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
        CheckConstraint(_in_list_sql("role", ROLE_VALUES), name="role_allowed"),
        CheckConstraint(
            _in_list_sql("role_source", ROLE_SOURCE_VALUES),
            name="role_source_allowed",
        ),
        # Unikátní e-mail bez ohledu na velikost písmen (database.md 12).
        # E-mail je spojovací klíč mezi adresářem osob a poskytovatelem
        # identity; funkcionální unikátní index nad `lower(email)` zamezí
        # dvojímu párování téže osoby. (Přidáno v úkolu 4.2.)
        Index(
            "uq_users_lower_email",
            func.lower(email),
            unique=True,
        ),
        # Unikátní `oidc_subject` (database.md 12, přidáno v úkolu 4.4).
        # Sub claim z IdP je po prvním přihlášení trvalá identita osoby a musí
        # být jednoznačný. Sloupec je nullable (prázdný do prvního přihlášení),
        # a proto částečný unikátní index nad neprázdnými hodnotami — víc osob
        # smí mít `oidc_subject` NULL, ale žádné dvě nesmí sdílet stejný subjekt.
        Index(
            "uq_users_oidc_subject",
            "oidc_subject",
            unique=True,
            postgresql_where=text("oidc_subject IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - jen pro ladění
        return f"<User id={self.id} role={self.role}>"
