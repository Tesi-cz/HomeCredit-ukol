"""Služba vytvoření a editace záznamu (úkol 14.2, R5.9, R6.1).

Bez živé databáze: falešná session sbírá přidané ORM objekty a předstírá
``flush`` přidělením ``id`` novým aplikacím (v produkci to dělá databáze přes
Python default ``uuid4``). Klíčová tvrzení úkolu 14.2:

- ``create_application`` poskládá záznam, nastaví ``created_by_user_id`` a
  počáteční klasifikaci zapíše **přes** ``write_classification`` (řádek v
  ``classification_log`` + audit ``CLASSIFICATION_SET``), nikdy přiřazením
  sloupce; navíc zapíše audit ``APP_CREATED``;
- ``update_application`` zapíše ``APP_UPDATED`` s ``changed_fields`` = **jen
  názvy** skutečně změněných polí (R5.9) a klasifikaci opět směruje přes
  jediného zapisovače;
- ani jedna funkce nenastaví ``application.classification`` přiřazením;
- vyřazení (stav ``DECOMMISSIONED``) přes formulář obě funkce odmítnou
  (constraint-safety, R5.12).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from regina.db.models.applications import Application
from regina.db.models.audit_log import AuditLog
from regina.db.models.classification_log import ClassificationLog
from regina.domain.enums import (
    AuditAction,
    Classification,
    LifecycleState,
    Role,
)
from regina.services.applications import (
    LifecycleTransitionError,
    create_application,
    decommission_application,
    reactivate_application,
    update_application,
)
from regina.web.forms import ApplicationForm


class FakeSession:
    """Náhrada session — sbírá přidané objekty a předstírá flush (přidělí id).

    Služba jen ``add``uje, jednou ``flush``ne (aby dostala ``application.id``)
    a necommituje (design.md 6.3). ``flush`` proto novým ``Application`` bez id
    doplní ``uuid4``, jako by to udělal Python default v ORM.
    """

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if isinstance(obj, Application) and getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()


@dataclass(frozen=True)
class FakeActor:
    """Aktér ve tvaru ``AuditActor`` (``id``, ``email``, ``name``)."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    email: str = "tvurce@regina.local"
    name: str = "Petr Svoboda"
    role: Role = Role.USER


def _logs(session: FakeSession) -> list[ClassificationLog]:
    return [obj for obj in session.added if isinstance(obj, ClassificationLog)]


def _audits(session: FakeSession) -> list[AuditLog]:
    return [obj for obj in session.added if isinstance(obj, AuditLog)]


def _apps(session: FakeSession) -> list[Application]:
    return [obj for obj in session.added if isinstance(obj, Application)]


def _base_form(**overrides: object) -> ApplicationForm:
    """Ověřený formulář s povinnými poli; přepsatelný přes kwargs."""
    data: dict[str, object] = {
        "name": "Interní portál",
        "department": "IT",
        "owner_user_id": uuid.uuid4(),
        "tech_admin_user_id": uuid.uuid4(),
        "lifecycle_state": LifecycleState.DRAFT,
    }
    data.update(overrides)
    # model_construct obchází validaci proti konfiguraci útvarů (ta patří routě);
    # tady testujeme jen službu nad už ověřeným tvarem. Použijeme běžnou
    # konstrukci přes model_validate, aby prošly typové koerce.
    return ApplicationForm.model_validate(data)


# -- create_application ---------------------------------------------------


def test_create_sets_fields_and_creator() -> None:
    """Vznik poskládá pole a nastaví created_by na aktéra (R5.5)."""
    session = FakeSession()
    actor = FakeActor()
    owner = uuid.uuid4()
    form = _base_form(owner_user_id=owner, description="Popis", ai_model="GPT-4o")

    app = create_application(session, actor, form)

    assert app.name == "Interní portál"
    assert app.department == "IT"
    assert app.owner_user_id == owner
    assert app.description == "Popis"
    assert app.ai_model == "GPT-4o"
    assert app.lifecycle_state == "DRAFT"
    assert app.created_by_user_id == actor.id
    assert app.id is not None  # flush přidělil id


def test_create_without_classification_leaves_column_none_and_no_log() -> None:
    """Bez klasifikace se sloupec neplní a nevzniká řádek logu (R5.7)."""
    session = FakeSession()
    app = create_application(session, FakeActor(), _base_form())

    assert app.classification is None
    assert _logs(session) == []
    # Jen audit APP_CREATED, žádný CLASSIFICATION_SET.
    audits = _audits(session)
    assert len(audits) == 1
    assert audits[0].action == str(AuditAction.APP_CREATED)


def test_create_with_classification_routes_through_writer() -> None:
    """S klasifikací vznikne řádek logu a audit CLASSIFICATION_SET (R6.1, R6.2)."""
    session = FakeSession()
    form = _base_form(classification=Classification.MEDIUM)

    app = create_application(session, FakeActor(), form)

    logs = _logs(session)
    assert len(logs) == 1
    assert logs[0].classification == "MEDIUM"
    assert logs[0].previous_classification is None
    assert logs[0].source == "HUMAN"
    assert logs[0].application_id == app.id
    # Sloupec = poslední řádek logu (invariant drží write_classification).
    assert app.classification == "MEDIUM"
    # Oba audity: vznik i zápis klasifikace.
    actions = {a.action for a in _audits(session)}
    assert actions == {str(AuditAction.APP_CREATED), str(AuditAction.CLASSIFICATION_SET)}


def test_create_writes_app_created_audit_with_entity_id() -> None:
    """APP_CREATED nese entity_id nového záznamu (R5.9)."""
    session = FakeSession()
    app = create_application(session, FakeActor(), _base_form())
    created = [a for a in _audits(session) if a.action == str(AuditAction.APP_CREATED)]
    assert len(created) == 1
    assert created[0].entity_id == app.id


def test_create_rejects_decommissioned_state() -> None:
    """Vznik rovnou vyřazeného záznamu je odmítnut (constraint-safety, R5.12)."""
    session = FakeSession()
    form = _base_form(lifecycle_state=LifecycleState.DECOMMISSIONED)
    with pytest.raises(LifecycleTransitionError):
        create_application(session, FakeActor(), form)
    assert session.added == []


# -- update_application ---------------------------------------------------


def _existing_app(**overrides: object) -> Application:
    """Existující záznam s vyplněnými povinnými poli pro editaci."""
    data: dict[str, object] = {
        "id": uuid.uuid4(),
        "name": "Původní název",
        "description": None,
        "department": "IT",
        "lifecycle_state": "DRAFT",
        "owner_user_id": uuid.uuid4(),
        "deputy_user_id": None,
        "tech_admin_user_id": uuid.uuid4(),
        "ai_model": None,
        "classification": None,
        "created_by_user_id": uuid.uuid4(),
    }
    data.update(overrides)
    app = Application()
    for key, value in data.items():
        setattr(app, key, value)
    return app


def test_update_changed_fields_are_names_only() -> None:
    """APP_UPDATED nese jen názvy skutečně změněných polí (R5.9, R8.6)."""
    session = FakeSession()
    app = _existing_app(name="Původní název", department="IT")
    # Změníme název a útvar; zbytek necháme stejný.
    form = _base_form(
        name="Nový název",
        department="HR",
        owner_user_id=app.owner_user_id,
        tech_admin_user_id=app.tech_admin_user_id,
        lifecycle_state=LifecycleState.DRAFT,
    )

    update_application(session, FakeActor(), app, form)

    assert app.name == "Nový název"
    assert app.department == "HR"
    audits = _audits(session)
    assert len(audits) == 1
    assert audits[0].action == str(AuditAction.APP_UPDATED)
    # Jen názvy, žádné hodnoty; přesně změněná pole.
    assert set(audits[0].changed_fields) == {"name", "department"}


def test_update_no_changes_writes_empty_changed_fields() -> None:
    """Editace beze změny hodnot zapíše audit s prázdným seznamem názvů."""
    session = FakeSession()
    app = _existing_app()
    form = _base_form(
        name=app.name,
        department=app.department,
        owner_user_id=app.owner_user_id,
        tech_admin_user_id=app.tech_admin_user_id,
        lifecycle_state=LifecycleState.DRAFT,
    )

    update_application(session, FakeActor(), app, form)

    audits = _audits(session)
    assert len(audits) == 1
    assert audits[0].action == str(AuditAction.APP_UPDATED)
    assert audits[0].changed_fields is None  # žádná změna
    assert _logs(session) == []


def test_update_classification_routes_through_writer_not_in_changed_fields() -> None:
    """Změna klasifikace jde přes zapisovače a není v changed_fields editace."""
    session = FakeSession()
    app = _existing_app(classification=None)
    form = _base_form(
        name=app.name,
        department=app.department,
        owner_user_id=app.owner_user_id,
        tech_admin_user_id=app.tech_admin_user_id,
        lifecycle_state=LifecycleState.DRAFT,
        classification=Classification.LARGE,
    )

    update_application(session, FakeActor(), app, form)

    # Klasifikace prošla jediným zapisovačem.
    logs = _logs(session)
    assert len(logs) == 1
    assert logs[0].classification == "LARGE"
    assert app.classification == "LARGE"
    # changed_fields editace neobsahuje classification.
    updated = [a for a in _audits(session) if a.action == str(AuditAction.APP_UPDATED)]
    assert len(updated) == 1
    assert updated[0].changed_fields is None
    # Vznikl i audit CLASSIFICATION_SET.
    assert any(
        a.action == str(AuditAction.CLASSIFICATION_SET) for a in _audits(session)
    )


def test_update_same_classification_writes_no_log() -> None:
    """Stejná klasifikace jako dosud → žádný nový řádek logu ani nový audit."""
    session = FakeSession()
    app = _existing_app(classification="MEDIUM")
    form = _base_form(
        name=app.name,
        department=app.department,
        owner_user_id=app.owner_user_id,
        tech_admin_user_id=app.tech_admin_user_id,
        lifecycle_state=LifecycleState.DRAFT,
        classification=Classification.MEDIUM,
    )

    update_application(session, FakeActor(), app, form)

    assert _logs(session) == []
    assert not any(
        a.action == str(AuditAction.CLASSIFICATION_SET) for a in _audits(session)
    )


def test_update_rejects_transition_to_decommissioned() -> None:
    """Vyřazení přes formulář je odmítnuto (dedikovaná akce, R5.12)."""
    session = FakeSession()
    app = _existing_app(lifecycle_state="DRAFT")
    form = _base_form(
        name=app.name,
        department=app.department,
        owner_user_id=app.owner_user_id,
        tech_admin_user_id=app.tech_admin_user_id,
        lifecycle_state=LifecycleState.DECOMMISSIONED,
    )
    with pytest.raises(LifecycleTransitionError):
        update_application(session, FakeActor(), app, form)


def test_update_rejects_return_from_decommissioned() -> None:
    """Návrat ze stavu Vyřazená přes formulář je odmítnut (dedikovaná akce)."""
    session = FakeSession()
    app = _existing_app(lifecycle_state="DECOMMISSIONED")
    form = _base_form(
        name=app.name,
        department=app.department,
        owner_user_id=app.owner_user_id,
        tech_admin_user_id=app.tech_admin_user_id,
        lifecycle_state=LifecycleState.IN_PRODUCTION,
    )
    with pytest.raises(LifecycleTransitionError):
        update_application(session, FakeActor(), app, form)


def test_neither_function_assigns_classification_directly() -> None:
    """Sloupec classification mění výhradně write_classification.

    Nepřímé ověření: bez klasifikace ve formuláři zůstane sloupec None a
    nevznikne žádný řádek logu — služba tedy sloupec nikde přiřazením nenastaví.
    """
    session = FakeSession()
    app = _existing_app(classification=None)
    form = _base_form(
        name="Změněno",
        department=app.department,
        owner_user_id=app.owner_user_id,
        tech_admin_user_id=app.tech_admin_user_id,
        lifecycle_state=LifecycleState.DRAFT,
    )
    update_application(session, FakeActor(), app, form)
    assert app.classification is None
    assert _logs(session) == []


# -- decommission_application / reactivate_application (úkol 15.2) ---------


def test_decommission_sets_state_timestamp_and_actor_and_audits() -> None:
    """Vyřazení nastaví stav, decommissioned_at + _by a audituje (R5.13)."""
    session = FakeSession()
    actor = FakeActor()
    app = _existing_app(lifecycle_state="IN_PRODUCTION")

    decommission_application(session, actor, app)

    assert app.lifecycle_state == str(LifecycleState.DECOMMISSIONED)
    assert app.decommissioned_at is not None
    assert app.decommissioned_at.tzinfo is not None  # timezone-aware (UTC)
    assert app.decommissioned_by == actor.id
    audits = _audits(session)
    assert len(audits) == 1
    assert audits[0].action == str(AuditAction.APP_DECOMMISSIONED)
    assert audits[0].entity_id == app.id


def test_decommission_keeps_constraint_satisfied() -> None:
    """Stav DECOMMISSIONED právě tehdy, když je decommissioned_at vyplněné."""
    session = FakeSession()
    app = _existing_app(lifecycle_state="TESTING")

    decommission_application(session, FakeActor(), app)

    is_decommissioned = app.lifecycle_state == str(LifecycleState.DECOMMISSIONED)
    has_timestamp = app.decommissioned_at is not None
    assert is_decommissioned == has_timestamp  # ekvivalence z constraintu


def test_decommission_rejects_already_decommissioned() -> None:
    """Opakované vyřazení už vyřazeného záznamu je odmítnuto."""
    session = FakeSession()
    app = _existing_app(lifecycle_state="DECOMMISSIONED")
    with pytest.raises(LifecycleTransitionError):
        decommission_application(session, FakeActor(), app)
    assert session.added == []


def test_reactivate_clears_both_columns_and_audits() -> None:
    """Návrat vyprázdní decommissioned_at i _by a audituje (R5.14)."""
    session = FakeSession()
    app = _existing_app(lifecycle_state="DECOMMISSIONED")
    app.decommissioned_at = datetime.now(timezone.utc)
    app.decommissioned_by = uuid.uuid4()

    reactivate_application(session, FakeActor(), app)

    assert app.lifecycle_state == str(LifecycleState.IN_PRODUCTION)
    assert app.decommissioned_at is None
    assert app.decommissioned_by is None
    audits = _audits(session)
    assert len(audits) == 1
    assert audits[0].action == str(AuditAction.APP_REACTIVATED)


def test_reactivate_keeps_constraint_satisfied() -> None:
    """Po návratu není stav DECOMMISSIONED a decommissioned_at je prázdné."""
    session = FakeSession()
    app = _existing_app(lifecycle_state="DECOMMISSIONED")
    app.decommissioned_at = datetime.now(timezone.utc)
    app.decommissioned_by = uuid.uuid4()

    reactivate_application(session, FakeActor(), app)

    is_decommissioned = app.lifecycle_state == str(LifecycleState.DECOMMISSIONED)
    has_timestamp = app.decommissioned_at is not None
    assert is_decommissioned == has_timestamp  # obě False → ekvivalence platí


def test_reactivate_rejects_active_record() -> None:
    """Návrat u nevyřazeného záznamu je odmítnut."""
    session = FakeSession()
    app = _existing_app(lifecycle_state="IN_PRODUCTION")
    with pytest.raises(LifecycleTransitionError):
        reactivate_application(session, FakeActor(), app)
    assert session.added == []


def test_reactivate_rejects_decommissioned_target_state() -> None:
    """Cílový stav návratu nesmí být DECOMMISSIONED."""
    session = FakeSession()
    app = _existing_app(lifecycle_state="DECOMMISSIONED")
    app.decommissioned_at = datetime.now(timezone.utc)
    with pytest.raises(LifecycleTransitionError):
        reactivate_application(
            session, FakeActor(), app, LifecycleState.DECOMMISSIONED
        )
