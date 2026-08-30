"""Výpis Registru `/registr` a fragment živého filtrování `/registr/fragment`.

Ověřuje chování rout bez živé databáze: závislost ``require_login`` a
``get_session`` se přepíší (FastAPI ``dependency_overrides``) a repozitářní
funkce (``list_applications``, ``_owner_names``) se monkeypatchnou v namespace
routy, takže test nepotřebuje PostgreSQL a přitom projde reálnou routou i
šablonou.

Co se ověřuje:
- ``/registr`` vyžaduje přihlášení (nepřihlášený → přesměrování na ``/login``);
- celá stránka nese pruh filtrů, wiring živého filtrování
  (``data-live-search``, cíl fragmentu) a skript ``live-search.js``;
- fragment ``/registr/fragment`` vykreslí **jen** partial výsledků (tabulka),
  bez sidebaru, pruhu filtrů a skriptu — je určený k vložení do kontejneru;
- fragment i stránka renderují nad týmiž daty (stejné názvy záznamů);
- fragment je chráněný přihlášením stejně jako stránka.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from regina.auth.deps import CurrentUser, require_login
from regina.db.models.applications import Application
from regina.db.session import get_session
from regina.domain.enums import Classification, LifecycleState, Role
from regina.main import create_app
from regina.repositories.applications import ListResult
from regina.web.routes import registry as registry_routes


_USER_ID = uuid.uuid4()
_OWNER_ID = uuid.uuid4()


def _application(name: str) -> Application:
    app = Application(
        name=name,
        description="Popis aplikace.",
        department="IT",
        lifecycle_state=str(LifecycleState.IN_PRODUCTION),
        owner_user_id=_OWNER_ID,
        deputy_user_id=None,
        tech_admin_user_id=_OWNER_ID,
        ai_model=None,
        classification=str(Classification.SMALL),
    )
    app.id = uuid.uuid4()
    app.updated_at = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    return app


def _admin_user() -> CurrentUser:
    return CurrentUser(
        id=_USER_ID,
        subject="admin-subject",
        name="Dáša Správcová",
        email="admin@regina.local",
        role=Role.ADMIN,
    )


class _FakeSession:
    """Prázdná session — repozitář se monkeypatchuje, session se nepoužije."""


@pytest.fixture
def make_client(settings, monkeypatch):
    """Sestaví TestClient s přepsanými závislostmi a repozitářem výpisu.

    Vrací tovární funkci ``build(user_factory, items)``. ``list_applications``
    i ``_owner_names`` se monkeypatchnou v namespace routy, aby test nepotřeboval
    databázi.
    """

    def build(user_factory, items: list[Application]):
        app = create_app(settings)

        def _override_session():
            yield _FakeSession()

        app.dependency_overrides[require_login] = user_factory
        app.dependency_overrides[get_session] = _override_session

        monkeypatch.setattr(
            registry_routes,
            "list_applications",
            lambda session, filters: ListResult(items=items, total=len(items)),
        )
        monkeypatch.setattr(
            registry_routes,
            "_owner_names",
            lambda session, apps: {_OWNER_ID: "Eva Uživatelka"},
        )

        return TestClient(app)

    return build


def test_registry_requires_login(make_client):
    """Nepřihlášený požadavek na /registr → přesměrování na /login (R1.3)."""

    def _login_required():
        from regina.auth.deps import LoginRequired

        raise LoginRequired()

    client = make_client(_login_required, [])
    response = client.get("/registr", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_registry_page_has_live_filter_wiring(make_client):
    """Celá stránka nese pruh filtrů, wiring živého filtrování a skript."""
    client = make_client(_admin_user, [_application("Detekce podvodů")])

    html = client.get("/registr").text

    assert "Detekce podvodů" in html
    # Wiring živého filtrování: formulář, cíl fragmentu, kontejner a skript.
    assert "data-live-search" in html
    assert 'data-fragment-url="/registr/fragment"' in html
    assert 'id="vysledky-registr"' in html
    assert "live-search.js" in html
    # Přepínač vyřazených (name="vse") zůstává na stránce v pruhu filtrů.
    assert 'name="vse"' in html
    # Export CSV je pro Admina součástí pruhu filtrů.
    assert "Export CSV" in html
    assert "/export/registr" in html


def test_registry_fragment_renders_only_results(make_client):
    """Fragment vykreslí jen partial výsledků — bez sidebaru, filtrů a skriptu."""
    client = make_client(_admin_user, [_application("Detekce podvodů")])

    html = client.get("/registr/fragment?q=det").text

    # Záznam se vykreslí (tabulka).
    assert "Detekce podvodů" in html
    # Ale ne rámec stránky ani pruh filtrů.
    assert "<aside" not in html
    assert "data-live-search" not in html
    assert "live-search.js" not in html
    # Pruh filtrů (přepínač vyřazených) není součástí fragmentu výsledků.
    assert 'name="vse"' not in html


def test_registry_fragment_requires_login(make_client):
    """Fragment je chráněný stejně jako stránka — nepřihlášený na /login."""

    def _login_required():
        from regina.auth.deps import LoginRequired

        raise LoginRequired()

    client = make_client(_login_required, [])
    response = client.get("/registr/fragment", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
