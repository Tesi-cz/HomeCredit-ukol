"""Poradce, zdroje zápisu a log volání (classification-advisor, úkoly 5.5, 5.6).

Bezpečnostní a integritní tvrzení bez živé databáze:

- bez klíče (MockClient) poradce vrátí deterministický fallback a nespadne (R3.4),
- při vynucené chybě klienta rovněž fallback,
- přijetí návrhu beze změny úrovně píše ``AI``, s jinou úrovní ``AI_OVERRIDDEN``,
  ruční zápis ``HUMAN`` — vše přes ``classification.py`` (R3.5–R3.8),
- řádek ``llm_call_log`` nikdy nenese obsah promptu ani odpovědi (R6.2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from regina.db.models.classification_log import ClassificationLog
from regina.db.models.classification_suggestion import ClassificationSuggestion
from regina.db.models.llm_call_log import LLMCallLog
from regina.domain.enums import Classification
from regina.domain.questionnaire import QUESTIONS
from regina.llm.base import LLMRequest, LLMResponse, LLMStatus
from regina.llm.mock import MockClient
from regina.services import advisor
from regina.services.classification import set_classification_from_suggestion


class FakeSession:
    """Náhrada session: sbírá přidané objekty a při flush přiřadí id."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self._next_id = 1

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        # Přiřadí id objektům, které ho ještě nemají (napodobí autoincrement).
        for obj in self.added:
            if getattr(obj, "id", None) is None and hasattr(obj, "id"):
                try:
                    obj.id = self._next_id
                    self._next_id += 1
                except Exception:
                    pass


@dataclass(frozen=True)
class FakeActor:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    email: str = "clen@regina.local"
    name: str = "Jan Novák"


class FailingClient:
    """Klient, který vždy vrátí chybu — pro ověření fallbacku (R3.4)."""

    gateway_impl = "OPENROUTER"

    def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text="",
            model="deepseek/deepseek-v4-flash",
            status=LLMStatus.ERROR,
            error_code="http_500",
        )


def _complete_answers() -> dict[str, str]:
    # Každá dimenze nejnižší volba → skóre 6 → baseline MALÁ.
    return {q.dimension: q.answers[0].code for q in QUESTIONS}


def _suggestions(session: FakeSession) -> list[ClassificationSuggestion]:
    return [o for o in session.added if isinstance(o, ClassificationSuggestion)]


def _calls(session: FakeSession) -> list[LLMCallLog]:
    return [o for o in session.added if isinstance(o, LLMCallLog)]


def test_mock_klient_vrati_fallback_a_nespadne() -> None:
    session = FakeSession()
    result = advisor.request_suggestion(
        session,
        MockClient(model="mock"),
        answers=_complete_answers(),
    )
    # Mock pro CLASSIFY vrací prázdný text → deterministický fallback.
    assert result.is_fallback is True
    assert result.classification is Classification.SMALL
    assert result.total_score == 6
    # Uložilo se doporučení i řádek volání.
    assert len(_suggestions(session)) == 1
    assert len(_calls(session)) == 1


def test_chyba_klienta_vede_na_fallback() -> None:
    session = FakeSession()
    result = advisor.request_suggestion(
        session,
        FailingClient(),
        answers=_complete_answers(),
    )
    assert result.is_fallback is True
    assert _calls(session)[0].status == "ERROR"


def test_llm_call_log_nenese_obsah() -> None:
    """Řádek llm_call_log nemá žádný atribut s obsahem promptu/odpovědi (R6.2)."""
    session = FakeSession()
    advisor.request_suggestion(session, MockClient(), answers=_complete_answers())
    call = _calls(session)[0]
    # Model logu nesmí mít sloupce pro obsah.
    forbidden = {"prompt", "response", "content", "text", "note", "transcript"}
    columns = set(LLMCallLog.__table__.columns.keys())
    assert forbidden.isdisjoint(columns)
    # A instanci nelze naplnit obsahem (žádný takový atribut se neukládá).
    assert not hasattr(call, "prompt")


def test_prijeti_navrhu_beze_zmeny_pise_AI() -> None:
    session = FakeSession()
    app = _FakeApp()
    actor = FakeActor()
    entry = set_classification_from_suggestion(
        session,
        app,
        actor,
        chosen_classification=Classification.SMALL,
        suggested_classification=Classification.SMALL,
        suggestion_id=42,
    )
    assert entry.source == "AI"
    assert entry.suggestion_id == 42
    assert app.classification == "SMALL"


def test_prijeti_navrhu_s_upravou_pise_AI_OVERRIDDEN() -> None:
    session = FakeSession()
    app = _FakeApp()
    actor = FakeActor()
    entry = set_classification_from_suggestion(
        session,
        app,
        actor,
        chosen_classification=Classification.LARGE,
        suggested_classification=Classification.SMALL,
        suggestion_id=7,
    )
    assert entry.source == "AI_OVERRIDDEN"
    assert entry.suggestion_id == 7
    assert app.classification == "LARGE"


@dataclass
class _FakeApp:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    classification: str | None = None
