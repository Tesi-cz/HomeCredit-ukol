"""Autorizace editace na backendu, ne skrytím tlačítka (úkol 14.4, R2.2/R5.10).

Důkaz klíčového tvrzení úkolu: **přímý** ``POST`` na
``/registr/{id}/upravit`` nad cizím záznamem je zamítnut i tehdy, když
rozhraní uživateli nikdy nenabídlo tlačítko Upravit. Vynucení leží v guardu
``require_can_edit`` (``auth/deps.py``) volajícím ``rules.can_edit`` — ne v
tom, co se vykreslí.

Test běží přes ``TestClient`` nad reálně složenou aplikací (``create_app``),
ale **bez živé databáze**: závislosti ``require_login`` a ``get_session`` se
přepíší (FastAPI ``dependency_overrides``), takže guard dostane falešného
aktéra a falešnou session vracející cílový záznam. Audit ``ACCESS_DENIED`` se
zapisuje ve vlastní transakci přes ``session_scope`` — tu handler v
``auth/deps.py`` přepíšeme falešnou, aby test nepotřeboval databázi a přitom
ověřil, že se audit o zamítnutí opravdu zapisuje (R2.3).

TestClient se **nepoužívá jako kontext manažer**, aby se nespouštěl lifespan
(inicializace enginu a seed) — routing a guardy živou databázi nepotřebují.
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
    """Session vracející jeden předpřipravený záznam z ``.get``.

    Guard ``load_application`` volá ``session.get(Application, id)``; jiné
    metody nejsou v tomto testu potřeba.
    """

    def __init__(self, application: Application) -> None:
        self._application = application

    def get(self, model: type, ident: object) -> object | None:
        if model is Application and ident == self._application.id:
            return self._application
        return None


class _RecordingAuditSession:
    """Zaznamená volání auditu bez zápisu do databáze."""

    def __init__(self, sink: list[tuple[object, ...]]) -> None:
        self._sink = sink


def _foreign_application() -> Application:
    """Záznam, jehož odpovědná trojice **neobsahuje** testovacího aktéra."""
    app = Application(
        name="Cizí aplikace",
        department="IT",
        lifecycle_state=str(LifecycleState.IN_PRODUCTION),
        owner_user_id=uuid.uuid4(),
        deputy_user_id=None,
        tech_admin_user_id=uuid.uuid4(),
    )
    app.id = uuid.uuid4()
    return app


def _non_member_user() -> CurrentUser:
    """Přihlášený uživatel role USER, který není členem trojice záznamu."""
    return CurrentUser(
        id=uuid.uuid4(),
        subject="user-subject",
        name="Jan Novák",
        email="jan.novak@regina.local",
        role=Role.USER,
    )


@pytest.fixture
def app_and_recorder(settings, monkeypatch):
    """Sestaví aplikaci s přepsanými závislostmi a odchytnutým auditem.

    Vrací trojici (client, application, audit_calls). ``audit_calls`` se plní
    při každém zápisu ``access_denied``, takže test ověří i to, že se audit
    zamítnutí opravdu zapisuje (R2.3).
    """
    application = _foreign_application()
    audit_calls: list[dict[str, object]] = []

    app = create_app(settings)

    def _override_session():
        yield _FakeSession(application)

    app.dependency_overrides[require_login] = _non_member_user
    app.dependency_overrides[get_session] = _override_session

    # Handler zamítnutí zapisuje audit ve vlastní transakci přes session_scope.
    # Přepíšeme ji falešnou, aby test nepotřeboval databázi.
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


def test_direct_post_to_foreign_record_is_rejected_with_403(app_and_recorder) -> None:
    """Přímý POST na cizí záznam → 403, i bez tlačítka v rozhraní (R2.2)."""
    client, application, audit_calls = app_and_recorder

    response = client.post(
        f"/registr/{application.id}/upravit",
        data={"name": "Pokus o změnu"},
    )

    assert response.status_code == 403


def test_rejected_post_writes_access_denied_audit(app_and_recorder) -> None:
    """Zamítnutí se zapisuje do auditu jako ACCESS_DENIED nad záznamem (R2.3)."""
    client, application, audit_calls = app_and_recorder

    client.post(f"/registr/{application.id}/upravit", data={"name": "Pokus"})

    assert len(audit_calls) == 1
    entry = audit_calls[0]
    assert entry["entity_type"] == "APPLICATION"
    assert entry["entity_id"] == application.id


def test_get_edit_form_for_foreign_record_is_rejected(app_and_recorder) -> None:
    """Ani GET editačního formuláře cizího záznamu neprojde (backend guard)."""
    client, application, _ = app_and_recorder

    response = client.get(f"/registr/{application.id}/upravit")

    assert response.status_code == 403
