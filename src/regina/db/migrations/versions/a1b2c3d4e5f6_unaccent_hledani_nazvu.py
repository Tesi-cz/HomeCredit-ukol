"""Hledání názvu bez ohledu na diakritiku (unaccent).

Revision ID: a1b2c3d4e5f6
Revises: 30916da03a23
Create Date: 2026-08-29 10:00:00.000000

Účel: aby „pre" v hledání našlo i „pře", „prě", „před" apod. — tedy shodu
názvu **bez ohledu na diakritiku** vedle už existující necitlivosti na velikost
písmen (R3.2). Filtruje databáze, ne aplikace v paměti (R3.6).

Jak:

- **`CREATE EXTENSION unaccent`** — dodá funkci `unaccent(text)`, která odstraní
  diakritiku (`pře` → `pre`). Rozšíření je součástí `contrib` balíku PostgreSQL,
  v oficiálním image `postgres` je k dispozici bez doinstalování.
- **`f_unaccent(text)` jako `IMMUTABLE` obal.** Vestavěná `unaccent()` je jen
  `STABLE` (závisí na aktuálním slovníku), a `STABLE` funkci nelze použít ve
  funkcionálním indexu. Standardní řešení je tenký `IMMUTABLE` wrapper, který
  slovník uzamkne na `unaccent` a stane se indexovatelným. Zafixovaný
  `search_path` je bezpečnostní pojistka wrapperu.
- **Funkcionální index** `ix_applications_unaccent_lower_name` nad
  `f_unaccent(lower(name))`, aby hledání `f_unaccent(lower(name)) LIKE ...`
  mohlo index využít stejně jako dřív `lower(name)`.

Downgrade je symetrický: zahodí index, obal i rozšíření. `unaccent` se
odstraňuje jen pokud ho nedrží jiný objekt (`DROP EXTENSION` bez `CASCADE`).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# Identifikátory revize, používá je Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "30916da03a23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Rozšíření dodávající unaccent(text). Součást contrib balíku, v oficiálním
    # postgres image je bez doinstalování.
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # IMMUTABLE obal nad STABLE unaccent(), aby šel použít ve funkcionálním
    # indexu. Slovník je uzamčen napevno na 'unaccent'; pevný search_path je
    # bezpečnostní pojistka (funkce se nespoléhá na volajícího).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION f_unaccent(text)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE
        PARALLEL SAFE
        STRICT
        SET search_path = pg_catalog, public
        AS $func$
            SELECT public.unaccent('public.unaccent', $1)
        $func$
        """
    )

    # Funkcionální index pro hledání bez diakritiky i velikosti písmen (R3.2).
    op.execute(
        "CREATE INDEX ix_applications_unaccent_lower_name "
        "ON applications (f_unaccent(lower(name)))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_applications_unaccent_lower_name")
    op.execute("DROP FUNCTION IF EXISTS f_unaccent(text)")
    # Bez CASCADE: rozšíření se odstraní, jen pokud na něm nic nezávisí.
    op.execute("DROP EXTENSION IF EXISTS unaccent")
