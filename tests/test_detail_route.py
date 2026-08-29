"""Detail záznamu `/registr/{id}` (úkol 15.1, ui.md sekce 7, R4).

Ověřuje chování routy bez živé databáze: závislosti ``require_login`` a
``get_session`` se přepíší (FastAPI ``dependency_overrides``) a repozitářní
funkce (``users.get_by_ids``, ``classification_log.list_for_application``) se
monkeypatchnou v namespace routy, takže test nepotřebuje PostgreSQL a přitom
projde reálnou routou i šablonou.

Co se ověřuje:
- detail vyžaduje přihlášení (nepřihlášený → přesměrování na ``/login``);
- neexistující ``{id}`` je 404 (``load_application``);
- šablona vykreslí drobenku, hlavní kartu, odpovědnost **s pozicemi**,
  klasifikaci se zdrojem a datem, historii **od nejnovějšího** a AI model;
- tlačítka akcí se řídí příznaky z ``domain/rules`` — Admin je vidí, člen
  trojice bez role Admin vidí jen Upravit, cizí uživatel žádné (R2.5, R4.8).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from regina.auth.deps import CurrentUser, require_login
from regina.db.models.applications import Application
from regina.db.models.classification_log import ClassificationLog
from regina.db.models.users import User
from regina.db.session import get_session
from regina.domain.enums import Classification, ClassificationSource, LifecycleState, Role
from regina.main import create_app
from regina.web.routes import registry as registry_routes


# --- Pomocné tovární funkce ------------------------------------------------

_OWNER_ID = uuid.uuid4()
_DEPUTY_ID = uuid.uuid4()
_TECH_ID = uuid.uuid4()
_ADMIN_ID = uuid.uuid4()


def _application(*, classified: bool = True) -> Application:
    app = Application(
        name="Interní portál",
        description="Popis interního portálu.",
        department="IT",
        lifecycle_state=str(LifecycleState.IN_PRODUCTION),
        owner_user_id=_OWNER_ID,
        deputy_user_id=_DEPUTY_ID,
        tech_admin_user_id=_TECH_ID,
        ai_model="GPT-4o" if classified else None,
        classification=str(Classification.MEDIUM) if classified else None,
    )
    app.id = uuid.uuid4()
    return app


def _people() -> dict[uuid.UUID, User]:
    def _u(uid: uuid.UUID, name: str, title: str) -> User:
        u = User(email=f"{name}@regina.local", display_name=name, job_title=title)
        u.id = uid
        return u

    return {
        _OWNER_ID: _u(_OWNER_ID, "Anna Vlastníková", "Produktová vlastnice"),
        _DEPUTY_ID: _u(_DEPUTY_ID, "Bořek Zástupce", "Analytik"),
        _TECH_ID: _u(_TECH_ID, "Cyril Správný", "Technický lead"),
        _ADMIN_ID: _u(_ADMIN_ID, "Dáša Správcová", "Administrátorka"),
    }


def _history(app_id: uuid.UUID) -> list[ClassificationLog]:
    """Dva zápisy: starší HUMAN, novější ADMIN_OVERRIDE — od nejnovějšího."""
    older = ClassificationLog(
        application_id=app_id,
        classification=str(Classification.SMALL),
        previous_classification=None,
        source=str(ClassificationSource.HUMAN),
        reason=None,
        actor_user_id=_OWNER_ID,
    )
    older.id = 1
    older.created_at = datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc)

    newer = ClassificationLog(
        application_id=app_id,
        classification=str(Classification.MEDIUM),
        previous_classification=str(Classification.SMALL),
        source=str(ClassificationSource.ADMIN_OVERRIDE),
        reason="Vyšší dopad než původně uvedeno.",
        actor_user_id=_ADMIN_ID,
    )
    newer.id = 2
    newer.created_at = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)

    # Repozitář vrací od nejnovějšího; napodobíme to i tady.
    return [newer, older]


class _FakeSession:
    def __init__(self, application: Application | None) -> None:
        self._application = application

    def get(self, model: type, ident: object):
        if (
            model is Application
            and self._application is not None
            and ident == self._application.id
        ):
            return self._application
        return None


def _admin_user() -> CurrentUser:
    return CurrentUser(
        id=_ADMIN_ID,
        subject="admin-subject",
        name="Dáša Správcová",
        email="admin@regina.local",
        role=Role.ADMIN,
    )


def _owner_user() -> CurrentUser:
    return CurrentUser(
        id=_OWNER_ID,
        subject="owner-subject",
        name="Anna Vlastníková",
        email="owner@regina.local",
        role=Role.USER,
    )


def _foreign_user() -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        subject="foreign-subject",
        name="Cizí Osoba",
        email="foreign@regina.local",
        role=Role.USER,
    )


@pytest.fixture
def make_client(settings, monkeypatch):
    """Sestaví TestClient s přepsanými závislostmi a repozitáři.

    Vrací tovární funkci ``build(user, application)``. Repozitářní funkce se
    monkeypatchnou v namespace routy, aby test nepotřeboval databázi.
    """
    people = _people()

    def build(user_factory, application: Application | None):
        app = create_app(settings)

        def _override_session():
            yield _FakeSession(application)

        app.dependency_overrides[require_login] = user_factory
        app.dependency_overrides[get_session] = _override_session

        if application is not None:
            monkeypatch.setattr(
                registry_routes.classification_log_repo,
                "list_for_application",
                lambda session, app_id: _history(app_id),
            )
        monkeypatch.setattr(
            registry_routes.users_repo,
            "get_by_ids",
            lambda session, ids: {pid: people[pid] for pid in ids if pid in people},
        )

        # TestClient bez kontext manažeru → nespouští lifespan (žádný engine/seed).
        return TestClient(app)

    return build


# --- Testy -----------------------------------------------------------------


def test_detail_requires_login(make_client):
    """Nepřihlášený požadavek na detail → přesměrování na /login (R1.3)."""
    application = _application()

    def _login_required():
        from regina.auth.deps import LoginRequired

        raise LoginRequired()

    client = make_client(_login_required, application)
    response = client.get(f"/registr/{application.id}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_detail_missing_id_is_404(make_client):
    """Neexistující záznam vrací 404 (load_application)."""
    client = make_client(_admin_user, None)
    response = client.get(f"/registr/{uuid.uuid4()}")

    assert response.status_code == 404


def test_detail_renders_all_blocks_for_admin(make_client):
    """Detail vykreslí drobenku, kartu, odpovědnost s pozicemi, klasifikaci,
    historii od nejnovějšího a AI model (R4.1–R4.7)."""
    application = _application()
    client = make_client(_admin_user, application)

    response = client.get(f"/registr/{application.id}")
    assert response.status_code == 200
    html = response.text

    # Drobenka (R4.1, R4.10).
    assert "Registr" in html
    assert 'href="/registr"' in html
    assert application.name in html

    # Odpovědnost se jmény a pozicemi (R4.3).
    assert "Anna Vlastníková" in html
    assert "Produktová vlastnice" in html
    assert "Bořek Zástupce" in html  # zástupce je vyplněn
    assert "Cyril Správný" in html
    assert "Technický lead" in html

    # AI model (R4.7).
    assert "GPT-4o" in html

    # Klasifikace se zdrojem a datem posledního zápisu (R4.4). Nejnovější je
    # ADMIN_OVERRIDE → český popisek „Přepis správce" a jeho datum 01.06.2024.
    assert "Přepis správce" in html
    assert "01.06.2024" in html
    # Důvod přepisu (R4.5).
    assert "Vyšší dopad než původně uvedeno." in html

    # Historie obsahuje i starší zápis (Člověk) a jeho aktéra.
    assert "Člověk" in html

    # České popisky klasifikace, ne strojové kódy (R13.11).
    assert "STŘEDNÍ" in html
    assert "MEDIUM" not in html


def test_history_ordered_newest_first(make_client):
    """Nejnovější zápis se v HTML objeví před starším (R4.6)."""
    application = _application()
    client = make_client(_admin_user, application)

    html = client.get(f"/registr/{application.id}").text

    # Datum novějšího zápisu je v dokumentu dříve než datum staršího.
    assert html.index("01.06.2024") < html.index("01.01.2024")


def test_admin_sees_all_action_buttons(make_client):
    """Admin vidí Upravit, Přepsat klasifikaci i Vyřadit (R2.5)."""
    application = _application()
    client = make_client(_admin_user, application)

    html = client.get(f"/registr/{application.id}").text

    assert f"/registr/{application.id}/upravit" in html
    assert f"/registr/{application.id}/prepis-klasifikace" in html
    assert f"/registr/{application.id}/vyrazeni" in html
    assert "Pouze pro čtení" not in html


def test_trio_member_sees_only_edit(make_client):
    """Člen trojice (role User) vidí Upravit, ne přepis ani vyřazení (R2.5)."""
    application = _application()
    client = make_client(_owner_user, application)

    html = client.get(f"/registr/{application.id}").text

    assert f"/registr/{application.id}/upravit" in html
    assert "prepis-klasifikace" not in html
    assert "vyrazeni" not in html


def test_foreign_user_sees_read_only_and_no_actions(make_client):
    """Cizí uživatel: indikátor „Pouze pro čtení" a žádná akce (R4.8)."""
    application = _application()
    client = make_client(_foreign_user, application)

    html = client.get(f"/registr/{application.id}").text

    assert "Pouze pro čtení" in html
    assert "/upravit" not in html
    assert "prepis-klasifikace" not in html
    assert "vyrazeni" not in html
