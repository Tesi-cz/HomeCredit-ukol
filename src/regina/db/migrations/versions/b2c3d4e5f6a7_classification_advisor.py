"""classification-advisor: tabulky poradce, suggestion_id, rozšíření source

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-30 12:00:00.000000

Aditivní rozšíření pro klasifikačního poradce (classification-advisor/database.md).
Žádný existující sloupec nemění význam, žádná data se nemigrují:

1. `classification_suggestions` — doporučení modelu, jeho zdůvodnění a odpovědi
   dotazníku. Bez sloupce pro obsah promptu (R6.2).
2. `llm_call_log` — technický záznam volání modelu (model, čas, tokeny, stav).
   Bez sloupce pro obsah (R6.2).
3. `classification_log.suggestion_id` — nový nullable FK na doporučení,
   `ON DELETE SET NULL` (retence nesmí utrhnout historii, R7.3).
4. Výměna `CHECK` na `classification_log.source` za čtyři povolené hodnoty:
   `HUMAN`, `AI`, `AI_OVERRIDDEN`, `ADMIN_OVERRIDE`. Existující řádky
   (`HUMAN`/`ADMIN_OVERRIDE`) zůstávají platné.

`downgrade` je zrcadlově opačný; vrací původní dvouhodnotový `CHECK`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Identifikátory revize, používá je Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Logický název CHECKu (bez prefixu). Naming convention
# `ck_%(table_name)s_%(constraint_name)s` z něj u drop i create sestaví plný
# název `ck_classification_log_source_allowed`. Proto se prefix NEuvádí ručně —
# jinak by se zdvojil.
_SOURCE_CHECK_NAME = "source_allowed"
_SOURCE_OLD = "source IN ('HUMAN', 'ADMIN_OVERRIDE')"
_SOURCE_NEW = "source IN ('HUMAN', 'AI', 'AI_OVERRIDDEN', 'ADMIN_OVERRIDE')"


def upgrade() -> None:
    # 1) llm_call_log jako první — classification_suggestions na něj odkazuje.
    op.create_table(
        "llm_call_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=True),
        sa.Column("requested_by_user_id", sa.UUID(), nullable=True),
        sa.Column("gateway_impl", sa.String(length=20), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "gateway_impl IN ('OPENROUTER', 'MOCK', 'AI_GATEWAY')",
            name=op.f("ck_llm_call_log_gateway_impl_allowed"),
        ),
        sa.CheckConstraint(
            "operation IN ('CLASSIFY', 'REWRITE', 'TRANSCRIBE')",
            name=op.f("ck_llm_call_log_operation_allowed"),
        ),
        sa.CheckConstraint(
            "status IN ('SUCCESS', 'TIMEOUT', 'ERROR')",
            name=op.f("ck_llm_call_log_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"],
            name=op.f("fk_llm_call_log_application_id_applications"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"],
            name=op.f("fk_llm_call_log_requested_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_call_log")),
    )
    op.create_index("ix_llm_call_log_occurred_at", "llm_call_log", ["occurred_at"])

    # 2) classification_suggestions — odkazuje na llm_call_log, applications, users.
    op.create_table(
        "classification_suggestions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=True),
        sa.Column("suggested_classification", sa.Text(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("questionnaire_version", sa.Text(), nullable=False),
        sa.Column("questionnaire_answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("deterministic_score", sa.SmallInteger(), nullable=False),
        sa.Column("is_fallback", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("llm_call_id", sa.BigInteger(), nullable=True),
        sa.Column("requested_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "suggested_classification IN ('SMALL', 'MEDIUM', 'LARGE')",
            name=op.f("ck_classification_suggestions_suggested_classification_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"],
            name=op.f("fk_classification_suggestions_application_id_applications"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["llm_call_id"], ["llm_call_log.id"],
            name=op.f("fk_classification_suggestions_llm_call_id_llm_call_log"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"],
            name=op.f("fk_classification_suggestions_requested_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_classification_suggestions")),
    )
    op.create_index(
        "ix_classification_suggestions_created_at", "classification_suggestions", ["created_at"]
    )
    op.create_index(
        "ix_classification_suggestions_application_id",
        "classification_suggestions",
        ["application_id"],
    )

    # 3) Nový nullable FK na classification_log.
    op.add_column(
        "classification_log",
        sa.Column("suggestion_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_classification_log_suggestion_id_classification_suggestions"),
        "classification_log",
        "classification_suggestions",
        ["suggestion_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 4) Výměna CHECK na source za čtyři povolené hodnoty. Drop i create předávají
    # logický název bez prefixu; naming convention z něj sestaví plný název.
    op.drop_constraint(_SOURCE_CHECK_NAME, "classification_log", type_="check")
    op.create_check_constraint(_SOURCE_CHECK_NAME, "classification_log", _SOURCE_NEW)


def downgrade() -> None:
    # Zrcadlově opačně. Pozor: downgrade selže, pokud v datech jsou hodnoty
    # AI / AI_OVERRIDDEN — to je záměr, aby se neztratila informace tichým
    # porušením původního CHECKu.
    op.drop_constraint(_SOURCE_CHECK_NAME, "classification_log", type_="check")
    op.create_check_constraint(_SOURCE_CHECK_NAME, "classification_log", _SOURCE_OLD)

    op.drop_constraint(
        op.f("fk_classification_log_suggestion_id_classification_suggestions"),
        "classification_log",
        type_="foreignkey",
    )
    op.drop_column("classification_log", "suggestion_id")

    op.drop_index(
        "ix_classification_suggestions_application_id", table_name="classification_suggestions"
    )
    op.drop_index(
        "ix_classification_suggestions_created_at", table_name="classification_suggestions"
    )
    op.drop_table("classification_suggestions")

    op.drop_index("ix_llm_call_log_occurred_at", table_name="llm_call_log")
    op.drop_table("llm_call_log")
