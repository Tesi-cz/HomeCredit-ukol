"""Obrazovka „Moje aplikace" `/moje` a fragment živého hledání `/moje/fragment`.

Ověřuje chování rout bez živé databáze: závislost ``require_login`` a
``get_session`` se přepíší (FastAPI ``dependency_overrides``) a repozitářní
funkce (``list_my_applications``, ``_owner_names``) se monkeypatchnou v namespace
routy, takže test nepotřebuje PostgreSQL a přitom projde reálnou routou i
šablonou.

Co se ověřuje:
- ``/moje`` vyžaduje přihlášení (nepřihlášený → přesměrování na ``/login``);
- celá stránka nese hero blok s hledáním, wiring živého hledání
  (``data-live-search``, cíl fragmentu) a skript ``live-search.js``;
- fragment ``/moje/fragment`` vykreslí **jen** partial výsledků (mřížka karet),
  bez sidebaru a hero bloku — je určený k vložení do kontejneru výsledků;
- fragment i stránka renderují nad týmiž daty (stejné názvy záznamů);
- prázdný výsledek hledání ve fragmentu ukáže hlášku „nic nenalezeno", ne
  skutečný prázdný stav.
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
from regina.web.routes import mine as mine_routes


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


def _user() -> CurrentUser:
    return CurrentUser(
        id=_USER_ID,
        subject="user-subject",
        name="Eva Uživatelka",
        email="eva@regina.local",
        role=Role.USER,
    )


class _FakeSession:
    """Prázdná session — repozitář se monkeypatchuje, session se nepoužije."""


@pytest.fixture
def make_client(settings, monkeypatch):
    """Sestaví TestClient s přepsanými závislostmi a repozitářem výpisu.

    Vrací tovární funkci ``build(user_factory, items)``. ``list_my_applications``
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
            mine_routes,
            "list_my_applications",
            lambda session, user_id, filters: ListResult(items=items, total=len(items)),
        )
        monkeypatch.setattr(
            mine_routes,
            "_owner_names",
            lambda session, apps: {_OWNER_ID: "Eva Uživatelka"},
        )

        return TestClient(app)

    return build


def test_mine_requires_login(make_client):
    """Nepřihlášený požadavek na /moje → přesměrování na /login (R1.3)."""

    def _login_required():
        from regina.auth.deps import LoginRequired

        raise LoginRequired()

    client = make_client(_login_required, [])
    response = client.get("/moje", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_mine_page_has_live_search_wiring(make_client):
    """Celá stránka nese hero s hledáním, wiring živého hledání a skript."""
    client = make_client(_user, [_application("Interní portál")])

    html = client.get("/moje").text

    # Hero blok a záznam.
    assert "Moje aplikace" in html
    assert "Interní portál" in html
    # Wiring živého hledání: formulář, cíl fragmentu, kontejner a skript.
    assert "data-live-search" in html
    assert 'data-fragment-url="/moje/fragment"' in html
    assert 'id="vysledky-moje"' in html
    assert "live-search.js" in html


def test_fragment_renders_only_results(make_client):
    """Fragment vykreslí jen partial výsledků — bez sidebaru a hero bloku."""
    client = make_client(_user, [_application("Interní portál")])

    html = client.get("/moje/fragment?q=int").text

    # Záznam se vykreslí.
    assert "Interní portál" in html
    # Ale ne rámec stránky: žádný sidebar, hero ani skript živého hledání.
    assert "<aside" not in html
    assert "data-live-search" not in html
    assert "live-search.js" not in html


def test_fragment_requires_login(make_client):
    """Fragment je chráněný stejně jako stránka (R3.10) — nepřihlášený na /login."""

    def _login_required():
        from regina.auth.deps import LoginRequired

        raise LoginRequired()

    client = make_client(_login_required, [])
    response = client.get("/moje/fragment", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_fragment_empty_search_shows_no_results_message(make_client):
    """Prázdný výsledek s hledáním = hláška filtru, ne skutečný prázdný stav."""
    client = make_client(_user, [])

    html = client.get("/moje/fragment?q=nexistuje").text

    assert "Žádná aplikace neodpovídá hledání" in html
    # Ne skutečný prázdný stav „nespravujete žádnou aplikaci".
    assert "Zatím nespravujete žádnou aplikaci" not in html
