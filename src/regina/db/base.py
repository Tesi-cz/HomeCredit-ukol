"""Deklarativní základ pro SQLAlchemy modely.

Typovaný styl SQLAlchemy 2.0 (design.md sekce 2 a 6.4). Všechny modely dědí
z `Base`, aby sdílely jedno `MetaData` — na něm stojí `create_all` v testech
i autogenerace Alembic revize (úkol 4.5).

Pojmenovací konvence pro constrainty a indexy je nastavená explicitně. Bez ní
generuje databáze náhodná jména a Alembic revize se pak špatně čtou a špatně
migrují. S konvencí má každý constraint předvídatelný název, což je nutné mimo
jiné pro rozšíření `CHECK` constraintu výčtu, které plánuje `database.md`
sekce 9 (výměna constraintu místo `ALTER TYPE`).
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Deterministická jména constraintů a indexů (design.md 6.4, database.md 9).
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Společný předek všech ORM modelů."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
