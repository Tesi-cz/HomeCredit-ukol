from __future__ import annotations

import pytest

from regina.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Nastavení pro testy. Databáze ukazuje na neexistující hostitele záměrně —
    testy, které databázi potřebují, si ji obstarají samy."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url="postgresql+psycopg://regina:secret@127.0.0.1:1/regina",
        # Krátký limit, aby testy nečekaly na provozní pětisekundový timeout.
        database_connect_timeout_seconds=1,
        session_secret="t" * 32,
        oidc_issuer="http://dex:5556/dex",
        oidc_client_id="regina",
        oidc_client_secret="client-secret",
        seed_on_start=False,
        retention_enabled=False,
    )
