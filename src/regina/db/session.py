"""Připojení k databázi a správa transakcí.

Návrh používá **synchronní** SQLAlchemy. FastAPI spouští synchronní obsluhu
požadavku ve vlákně z poolu, takže to serverem vykreslované aplikaci nijak
nevadí, a vyhneme se úskalím asynchronních sessions. Aplikace není zátěžová,
takže není za co platit složitostí.

Jedna transakce na požadavek (design.md 6.3): otevře ji závislost, commit
proběhne po úspěšném zpracování, rollback při výjimce. Služby transakci
nespravují, jen do ní zapisují.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from regina.config import Settings
from regina.db.audit_guard import install_audit_immutability_guard

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def init_engine(settings: Settings) -> Engine:
    """Vytvoří engine a fabriku sessions. Volá se jednou při startu."""
    global _engine, _session_factory

    _engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
        # Bez časového limitu by se pokus o připojení k nedostupné databázi mohl
        # zaseknout na desítky sekund. Zdravotní endpoint má odpovědět rychle,
        # i když je databáze dole.
        connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
    )
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    # Pojistka nemazatelnosti auditu (R8.5): posluchač na Session odmítne
    # UPDATE/DELETE nad audit_log mimo retenční rutinu. Registruje se tady,
    # aby žil v běžící aplikaci; je idempotentní.
    install_audit_immutability_guard()
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Engine není inicializovaný. Zavolej init_engine při startu.")
    return _engine


def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transakce s automatickým commitem, nebo rollbackem při výjimce."""
    if _session_factory is None:
        raise RuntimeError("Fabrika sessions není inicializovaná.")

    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI závislost. Jedna transakce na požadavek.

    Commit/rollback řeší ``session_scope`` v úklidu závislosti. **Pozor:** tento
    commit proběhne až *po* tom, co FastAPI odešle odpověď klientovi. U
    Post/Redirect/Get to znamená, že mutační routa **nesmí** spoléhat jen na
    tento commit — prohlížeč po ``303`` vystřelí následný ``GET`` dřív, než
    teardown proběhne, a přečetl by ještě nezacommitovaná data (viz
    ``regina.web.commit.commit_before_redirect``). Mutační routy proto po zápisu
    commitnou **explicitně** ještě před vrácením přesměrování; tento úklidový
    commit je pak už jen no-op pojistka (a commit u čtecích rout beze změn).
    """
    with session_scope() as session:
        yield session


def check_database() -> bool:
    """Ověří dostupnost databáze pro zdravotní endpoint.

    Záměrně jen triviální dotaz — endpoint má říct, jestli je služba
    připravená, nikoli prozrazovat verze nebo konfiguraci (R12.2).
    """
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
