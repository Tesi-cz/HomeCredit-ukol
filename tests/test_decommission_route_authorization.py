"""Vyřazení a přepis klasifikace jsou vyhrazené roli Admin na backendu (úkol 15.2).

Důkaz klíčového tvrzení úkolu: **přímý** ``POST`` na
``/registr/{id}/vyrazeni`` i ``/registr/{id}/prepis-klasifikace`` od
přihlášeného uživatele role User je zamítnut 403 + auditem ``ACCESS_DENIED``,
i když rozhraní roli User tlačítka nikdy nenabídne. Vynucení leží v guardech
``require_decommission`` / ``require_override_classification`` (``auth/deps.py``)
volajících ``rules.can_decommission`` / ``rules.can_override_classification`` —
ne v tom, co se vykreslí (R5.12, R7.1, R7.6, R2.2).

Stejný vzor jako ``test_edit_route_authorization.py``: ``TestClient`` nad reálně
složenou aplikací (``create_app``), ale **bez živé databáze** — ``require_login``
a ``get_session`` se přepíší, ``session_scope`` v handleru zamítnutí se přepíše
falešným, aby se dal ověřit zápis auditu bez databáze. TestClient se nepoužívá
jako kontext manažer, aby se nespouštěl lifespan.
"""

from __future__ import annotations

import contextlib
import uuid

import pytest
from fastapi.testclient import TestClient

from regina.auth import deps as auth_deps
from regina.auth.deps import CurrentUser, require_login
from regina.db.models.applications import Application
from regina.db.session import get_session
from regina.domain.enums import LifecycleState, Role
from regina.main import create_app


class _FakeSession:
    """Session vracející jeden předpřipravený záznam z ``.get``."""

    def __init__(self, application: Application) -> None:
        self._application = application

    def get(self, model: type, ident: object) -> object | None:
        if model is Application and ident == self._application.id:
            return self._application
        return None


class _RecordingAuditSession:
    def __init__(self, sink: list[object]) -> None:
        self._sink = sink


def _active_application() -> Application:
    app = Application(
        name="Aplikace k vyřazení",
        department="IT",
        lifecycle_state=str(LifecycleState.IN_PRODUCTION),
        owner_user_id=uuid.uuid4(),
        deputy_user_id=None,
        tech_admin_user_id=uuid.uuid4(),
    )
    app.id = uuid.uuid4()
    return app


def _regular_user() -> CurrentUser:
    """Přihlášený uživatel role USER (není Admin)."""
    return CurrentUser(
        id=uuid.uuid4(),
        subject="user-subject",
        name="Jan Novák",
        email="jan.novak@regina.local",
        role=Role.USER,
    )


@pytest.fixture
def app_and_recorder(settings, monkeypatch):
    """Aplikace s přepsanými závislostmi a odchytnutým auditem zamítnutí."""
    application = _active_application()
    audit_calls: list[dict[str, object]] = []

    app = create_app(settings)

    def _override_session():
        yield _FakeSession(application)

    app.dependency_overrides[require_login] = _regular_user
    app.dependency_overrides[get_session] = _override_session

    @contextlib.contextmanager
    def _fake_scope():
        yield _RecordingAuditSession(audit_calls)

    monkeypatch.setattr(auth_deps, "session_scope", _fake_scope)

    def _record_access_denied(session, actor, *, summary, entity_type=None, entity_id=None):
        audit_calls.append(
            {
                "actor": actor,
                "summary": summary,
                "entity_type": entity_type,
                "entity_id": entity_id,
            }
        )

    monkeypatch.setattr(auth_deps.audit_service, "access_denied", _record_access_denied)

    client = TestClient(app)
    return client, application, audit_calls


def test_direct_post_decommission_by_non_admin_is_403(app_and_recorder) -> None:
    """Přímý POST vyřazení od role User → 403, i bez tlačítka (R5.12, R2.2)."""
    client, application, _ = app_and_recorder
    response = client.post(f"/registr/{application.id}/vyrazeni")
    assert response.status_code == 403


def test_rejected_decommission_writes_access_denied_audit(app_and_recorder) -> None:
    """Zamítnuté vyřazení se zapisuje jako ACCESS_DENIED (R2.3)."""
    client, application, audit_calls = app_and_recorder
    client.post(f"/registr/{application.id}/vyrazeni")
    assert len(audit_calls) == 1


def test_get_decommission_confirm_by_non_admin_is_403(app_and_recorder) -> None:
    """Ani GET potvrzení vyřazení role User neprojde (backend guard)."""
    client, application, _ = app_and_recorder
    response = client.get(f"/registr/{application.id}/vyrazeni")
    assert response.status_code == 403


def test_direct_post_override_by_non_admin_is_403(app_and_recorder) -> None:
    """Přímý POST přepisu klasifikace od role User → 403 (R7.1, R7.6, R2.2)."""
    client, application, _ = app_and_recorder
    response = client.post(
        f"/registr/{application.id}/prepis-klasifikace",
        data={"classification": "LARGE", "reason": "pokus"},
    )
    assert response.status_code == 403


def test_get_override_form_by_non_admin_is_403(app_and_recorder) -> None:
    """Ani GET formuláře přepisu role User neprojde (backend guard)."""
    client, application, _ = app_and_recorder
    response = client.get(f"/registr/{application.id}/prepis-klasifikace")
    assert response.status_code == 403
