"""Validační modely formuláře záznamu (úkol 14.1, R5.2/5.3/5.4/5.8).

Dvě roviny validace, testované odděleně:

1. **Tvar a výčty bez databáze** — ``parse_application_form``: povinná pole,
   neplatné výčty (stav/klasifikace) a útvar mimo konfigurovaný seznam. Chyby
   musí být české a přiřazené ke konkrétnímu poli (R5.3, R13.11).
2. **Kontroly proti databázi** — ``validate_uniqueness_and_refs``: unikátní
   název bez ohledu na velikost písmen (R5.8) a existence odkazovaných osob
   (R2.6). Ověřeno proti falešné session, která vrací připravené odpovědi
   repozitářů, takže test nepotřebuje živou databázi.
"""

from __future__ import annotations

import uuid

import pytest

from regina.domain.enums import Classification, LifecycleState
from regina.web import forms

DEPARTMENTS = ("Finance", "HR", "IT Ops")
OWNER = uuid.UUID("11111111-1111-1111-1111-111111111111")
TECH = uuid.UUID("22222222-2222-2222-2222-222222222222")
DEPUTY = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _valid_raw(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        forms.FIELD_NAME: "Interní portál",
        forms.FIELD_DEPARTMENT: "Finance",
        forms.FIELD_OWNER: str(OWNER),
        forms.FIELD_TECH_ADMIN: str(TECH),
        forms.FIELD_LIFECYCLE_STATE: "DRAFT",
    }
    raw.update(overrides)
    return raw


# --- Tvarová validace: povinná pole (R5.2, R5.3) ---


def test_valid_form_parses_and_normalizes() -> None:
    form = forms.parse_application_form(
        _valid_raw(name="  Portál  ", description="   ", ai_model="GPT-4o"),
        DEPARTMENTS,
    )
    assert form.name == "Portál"  # ořezané mezery
    assert form.description is None  # jen mezery → nevyplněno
    assert form.ai_model == "GPT-4o"
    assert form.lifecycle_state is LifecycleState.DRAFT
    assert form.classification is None  # neklasifikováno (R5.7)
    assert form.deputy_user_id is None  # zástupce nepovinný


def test_missing_required_fields_report_each_field_in_czech() -> None:
    with pytest.raises(forms.FormValidationError) as exc:
        forms.parse_application_form({forms.FIELD_DEPARTMENT: "Finance"}, DEPARTMENTS)
    errors = exc.value.errors
    assert forms.FIELD_NAME in errors
    assert forms.FIELD_OWNER in errors
    assert forms.FIELD_TECH_ADMIN in errors
    assert forms.FIELD_LIFECYCLE_STATE in errors
    # Hlášky jsou české, ne strojové kódy ani angličtina (R13.11).
    assert errors[forms.FIELD_NAME] == ["Zadejte název aplikace."]


def test_blank_name_is_treated_as_missing() -> None:
    with pytest.raises(forms.FormValidationError) as exc:
        forms.parse_application_form(_valid_raw(name="   "), DEPARTMENTS)
    assert forms.FIELD_NAME in exc.value.errors


def test_deputy_is_optional() -> None:
    form = forms.parse_application_form(_valid_raw(deputy_user_id=""), DEPARTMENTS)
    assert form.deputy_user_id is None


# --- Tvarová validace: výčty na backendu (R5.4) ---


def test_invalid_lifecycle_state_is_rejected_with_czech_message() -> None:
    with pytest.raises(forms.FormValidationError) as exc:
        forms.parse_application_form(_valid_raw(lifecycle_state="BOGUS"), DEPARTMENTS)
    assert exc.value.errors[forms.FIELD_LIFECYCLE_STATE] == [
        "Neplatný stav — vyberte jednu z nabízených hodnot."
    ]


def test_invalid_classification_is_rejected() -> None:
    with pytest.raises(forms.FormValidationError) as exc:
        forms.parse_application_form(_valid_raw(classification="HUGE"), DEPARTMENTS)
    assert forms.FIELD_CLASSIFICATION in exc.value.errors


def test_department_outside_allowed_list_is_rejected() -> None:
    """Útvar mimo konfigurovaný seznam se odmítne, i kdyby prohlížeč nabízel jen platné (R5.4)."""
    with pytest.raises(forms.FormValidationError) as exc:
        forms.parse_application_form(_valid_raw(department="Neexistuje"), DEPARTMENTS)
    assert forms.FIELD_DEPARTMENT in exc.value.errors


def test_valid_enum_values_pass() -> None:
    form = forms.parse_application_form(
        _valid_raw(lifecycle_state="IN_PRODUCTION", classification="LARGE"),
        DEPARTMENTS,
    )
    assert form.lifecycle_state is LifecycleState.IN_PRODUCTION
    assert form.classification is Classification.LARGE


# --- Kontroly proti databázi: unikátnost a existence osob ---


class _FakeResult:
    def __init__(self, row: object | None) -> None:
        self._row = row

    def first(self) -> object | None:
        return self._row


class _FakeSession:
    """Falešná session: vrací připravenou odpověď podle textu dotazu.

    ``name_exists`` se dotazuje na ``applications.id`` s ``lower(name)``,
    ``active_id_exists`` na ``users.id`` s ``is_active``. Rozlišíme je podle
    zkompilovaného SQL, takže se dá řídit obě kontroly nezávisle bez databáze.
    """

    def __init__(
        self,
        *,
        name_taken: bool = False,
        active_user_ids: set[uuid.UUID] | None = None,
    ) -> None:
        self._name_taken = name_taken
        self._active = active_user_ids if active_user_ids is not None else set()

    def execute(self, stmt):  # type: ignore[no-untyped-def]
        sql = str(stmt).lower()
        if "users" in sql:
            # active_id_exists: najdi navázaný identifikátor v parametrech.
            params = stmt.compile().params
            uid = next(
                (v for v in params.values() if isinstance(v, uuid.UUID)),
                None,
            )
            row = (uid,) if uid in self._active else None
            return _FakeResult(row)
        # name_exists nad applications.
        return _FakeResult(("x",) if self._name_taken else None)


def test_unique_name_ok_when_not_taken() -> None:
    session = _FakeSession(active_user_ids={OWNER, TECH})
    form = forms.parse_application_form(_valid_raw(), DEPARTMENTS)
    errors = forms.validate_uniqueness_and_refs(session, form)
    assert errors == {}


def test_duplicate_name_is_rejected() -> None:
    """Duplicitní název (bez ohledu na velikost písmen) se odmítne (R5.8)."""
    session = _FakeSession(name_taken=True, active_user_ids={OWNER, TECH})
    form = forms.parse_application_form(_valid_raw(), DEPARTMENTS)
    errors = forms.validate_uniqueness_and_refs(session, form)
    assert errors[forms.FIELD_NAME] == ["Aplikace s tímto názvem už existuje."]


def test_missing_owner_reference_is_rejected() -> None:
    session = _FakeSession(active_user_ids={TECH})  # vlastník chybí
    form = forms.parse_application_form(_valid_raw(), DEPARTMENTS)
    errors = forms.validate_uniqueness_and_refs(session, form)
    assert forms.FIELD_OWNER in errors
    assert forms.FIELD_TECH_ADMIN not in errors


def test_missing_deputy_reference_is_rejected_only_when_present() -> None:
    # Zástupce vyplněn, ale neaktivní → chyba u zástupce.
    session = _FakeSession(active_user_ids={OWNER, TECH})
    form = forms.parse_application_form(_valid_raw(deputy_user_id=str(DEPUTY)), DEPARTMENTS)
    errors = forms.validate_uniqueness_and_refs(session, form)
    assert forms.FIELD_DEPUTY in errors

    # Zástupce nevyplněn → žádná kontrola, žádná chyba.
    session2 = _FakeSession(active_user_ids={OWNER, TECH})
    form2 = forms.parse_application_form(_valid_raw(), DEPARTMENTS)
    errors2 = forms.validate_uniqueness_and_refs(session2, form2)
    assert forms.FIELD_DEPUTY not in errors2
