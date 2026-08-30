"""Výpis auditního logu `/audit` (úkol 17.1, ui.md sekce 9, R8.4/R8.7).

Ověřuje chování routy bez živé databáze: závislosti ``require_login`` a
``get_session`` se přepíší (FastAPI ``dependency_overrides``) a repozitářní
funkce se monkeypatchnou v namespace routy, takže test nepotřebuje PostgreSQL
a přitom projde reálnou routou i šablonou.

Co se ověřuje:
- čtení auditu je vyhrazeno roli Admin — role User dostane 403 + audit
  ``ACCESS_DENIED`` i při přímém požadavku na ``/audit`` (R8.4, R2.2),
  vzorem podle ``test_edit_route_authorization.py`` (bez databáze);
- šablona vykreslí sloupce Čas, Aktér, Akce, Objekt, Popis, pruh filtrů a
  stránkování;
- čas přes ``datum_cas`` (DD.MM.YYYY HH:MM), akce jako český popisek, aktér
  ze snapshotu záznamu (R8.3), žádný strojový kód v rozhraní (R13.11).
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from regina.auth import deps as auth_deps
from regina.auth.deps import CurrentUser, require_login
from regina.db.models.audit_log import AuditLog
from regina.db.models.users import User
from regina.db.session import get_session
from regina.domain.enums import AuditAction, Role
from regina.main import create_app
from regina.repositories.audit import AuditListResult
from regina.web.routes import audit as audit_routes


# --- Pomocné tovární funkce ------------------------------------------------


def _admin_user() -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        subject="admin-subject",
        name="Dáša Správcová",
        email="admin@regina.local",
        role=Role.ADMIN,
    )


def _regular_user() -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        subject="user-subject",
        name="Jan Novák",
        email="jan.novak@regina.local",
        role=Role.USER,
    )


def _entry(*, entity_id: uuid.UUID | None = None) -> AuditLog:
    """Jeden auditní záznam se snapshotem aktéra a nad aplikací."""
    entry = AuditLog(
        actor_user_id=uuid.uuid4(),
        actor_email="anna.tvurce@regina.local",
        actor_display_name="Anna Tvůrce",
        action=str(AuditAction.APP_CREATED),
        entity_type="APPLICATION",
        entity_id=entity_id or uuid.uuid4(),
        summary="Vytvoření záznamu aplikace.",
        changed_fields=["name", "department"],
    )
    entry.id = 42
    entry.occurred_at = datetime(2024, 6, 1, 12, 30, tzinfo=timezone.utc)
    return entry


class _FakeSession:
    """Session bez databáze — audit route s ní jen prochází závislostí."""


@pytest.fixture
def make_client(settings, monkeypatch):
    """Sestaví TestClient s přepsanými závislostmi a repozitáři.

    Vrací tovární funkci ``build(user_factory, entries)``. Repozitářní funkce
    (``list_audit_entries``, ``users.list_active``) se monkeypatchnou v
    namespace routy, aby test nepotřeboval databázi.
    """

    def build(user_factory, entries: list[AuditLog]):
        app = create_app(settings)

        def _override_session():
            yield _FakeSession()

        app.dependency_overrides[require_login] = user_factory
        app.dependency_overrides[get_session] = _override_session

        monkeypatch.setattr(
            audit_routes,
            "list_audit_entries",
            lambda session, filters: AuditListResult(items=entries, total=len(entries)),
        )
        monkeypatch.setattr(
            audit_routes.users_repo,
            "list_active",
            lambda session: [],
        )

        # TestClient bez kontext manažeru → nespouští lifespan (žádný engine/seed).
        return TestClient(app)

    return build


# --- Autorizace (bez databáze, vzor test_edit_route_authorization.py) ------


@pytest.fixture
def admin_recorder(settings, monkeypatch):
    """Odchytí audit ACCESS_DENIED bez zápisu do databáze."""
    audit_calls: list[dict[str, object]] = []

    @contextlib.contextmanager
    def _fake_scope():
        yield object()

    monkeypatch.setattr(auth_deps, "session_scope", _fake_scope)

    def _record_access_denied(session, actor, *, summary, entity_type=None, entity_id=None):
        audit_calls.append({"actor": actor, "summary": summary})

    monkeypatch.setattr(auth_deps.audit_service, "access_denied", _record_access_denied)
    return audit_calls


def test_regular_user_is_rejected_with_403(make_client, admin_recorder) -> None:
    """Role User na /audit → 403, i když jí nav položku neukázal (R8.4, R2.2)."""
    client = make_client(_regular_user, [])

    response = client.get("/audit")

    assert response.status_code == 403


def test_rejected_read_writes_access_denied_audit(make_client, admin_recorder) -> None:
    """Zamítnuté čtení auditu se samo zapíše jako ACCESS_DENIED (R2.3)."""
    client = make_client(_regular_user, [])

    client.get("/audit")

    assert len(admin_recorder) == 1


# --- Vykreslení pro Admina -------------------------------------------------


def test_admin_sees_columns_filters_and_row(make_client) -> None:
    """Admin vidí sloupce, filtry a řádek se snapshotem aktéra a datem/časem."""
    entry = _entry()
    client = make_client(_admin_user, [entry])

    response = client.get("/audit")
    assert response.status_code == 200
    html = response.text

    # Sloupce (ui.md sekce 9).
    assert "Čas" in html
    assert "Aktér" in html
    assert "Akce" in html
    assert "Objekt" in html
    assert "Popis" in html

    # Filtry a stránkování.
    assert 'name="akce"' in html
    assert 'name="akter"' in html
    assert 'name="od"' in html
    assert 'name="do"' in html
    assert "Zobrazeno" in html

    # Informace o nemazatelnosti a retenci nad tabulkou.
    assert "nelze měnit ani mazat" in html

    # Čas přes datum_cas (DD.MM.YYYY HH:MM).
    assert "01.06.2024 12:30" in html

    # Aktér ze snapshotu (R8.3).
    assert "Anna Tvůrce" in html
    assert "anna.tvurce@regina.local" in html

    # Akce jako český popisek, ne strojový kód (R13.11). Strojový kód smí být
    # jen v hodnotě volby filtru (`value="APP_CREATED"`), nikdy jako viditelný
    # text — proto se ověřuje, že kód není vykreslen jako text buňky mimo option.
    assert "Vytvoření záznamu" in html
    assert ">APP_CREATED<" not in html

    # Objekt: český typ entity + odkaz na detail aplikace.
    assert "Aplikace" in html
    assert f"/registr/{entry.entity_id}" in html

    # Popis (souhrn) + názvy změněných polí (bez hodnot, R8.6).
    assert "Vytvoření záznamu aplikace." in html


def test_empty_state_when_no_entries(make_client) -> None:
    """Bez záznamů se zobrazí prázdný stav, ne prázdná tabulka."""
    client = make_client(_admin_user, [])

    html = client.get("/audit").text

    assert "Žádné auditní záznamy" in html
