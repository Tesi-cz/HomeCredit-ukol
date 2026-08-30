"""Testy zdravotního endpointu.

Ověřují, že endpoint je dostupný bez přihlášení, že rozlišuje nedostupnou
databázi a že neprozrazuje konfiguraci.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from regina.config import Settings
from regina.main import create_app


def test_health_reports_degraded_when_database_is_unreachable(settings: Settings) -> None:
    """Bez databáze musí endpoint odpovědět, ale přiznat degradaci."""
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "down"}


def test_health_needs_no_authentication(settings: Settings) -> None:
    """Endpoint nesmí přesměrovávat na přihlášení (R12.2)."""
    with TestClient(create_app(settings)) as client:
        response = client.get("/health", follow_redirects=False)

    assert response.status_code != 302
    assert response.status_code != 307


def test_health_does_not_leak_configuration(settings: Settings) -> None:
    """Odpověď nesmí obsahovat connection string, tajemství ani issuer."""
    with TestClient(create_app(settings)) as client:
        body = client.get("/health").text

    assert "postgresql" not in body
    assert settings.session_secret not in body
    assert settings.oidc_client_secret not in body
    assert settings.oidc_issuer not in body


def test_response_carries_correlation_id(settings: Settings) -> None:
    """Každá odpověď nese korelační identifikátor pro dohledání v logu."""
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")

    assert response.headers.get("X-Correlation-Id")


def test_supplied_correlation_id_is_preserved(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/health", headers={"X-Correlation-Id": "abc123"})

    assert response.headers["X-Correlation-Id"] == "abc123"
