"""Prostředí Alembic migrací pro REGINU.

Klíčová rozhodnutí (design.md 6.4):

- **URL se nikam nezapisuje.** Připojení se čte z `DATABASE_URL` v konfiguraci,
  ne z `alembic.ini`. Migrace tak běží proti téže databázi jako aplikace a
  v `alembic.ini` nezůstává žádné tajemství (R12.4).
- **`target_metadata = Base.metadata`.** Import balíčku `regina.db.models`
  zaregistruje všechny čtyři tabulky, takže autogenerace i `alembic check`
  vidí kompletní schéma.
- **Stejná pojmenovací konvence jako modely.** `Base.metadata` už konvenci nese
  (base.py), takže autogenerace i porovnání pracují s týmiž názvy constraintů
  a indexů. Bez toho by `alembic check` hlásil falešné rozdíly.
- **`render_as_batch=False`.** Batch režim je berlička pro SQLite, které neumí
  plné `ALTER TABLE`. Cílem je PostgreSQL, kde je zbytečný a jen zamlžuje DDL.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import modelů zaregistruje tabulky do Base.metadata (nutné pro autogeneraci).
from regina.config import build_settings
from regina.db.models import Base

# Objekt konfigurace Alembic; přístup k hodnotám z alembic.ini.
config = context.config

# Logging podle alembic.ini, pokud je soubor k dispozici.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Cílové schéma pro autogeneraci a `alembic check`.
target_metadata = Base.metadata


def _database_url() -> str:
    """Připojovací řetězec z konfigurace aplikace.

    Bere se z proměnné prostředí `DATABASE_URL` (přes pydantic-settings), aby
    migrace nikdy neběžely proti jiné databázi než aplikace a aby v repozitáři
    nebyl žádný připojovací řetězec natvrdo.
    """
    settings = build_settings()
    return settings.database_url


def run_migrations_offline() -> None:
    """Migrace v „offline" režimu — jen sestaví SQL, bez připojení k databázi."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Migrace v „online" režimu — s živým připojením k databázi."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=False,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
