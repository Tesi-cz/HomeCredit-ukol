"""Deterministické skóre dotazníku (classification-advisor R3.1, úkol 2.4).

Čistá doménová logika bez databáze i modelu. Ověřuje se:

- součet vah přes šest dimenzí je v rozsahu 6–18,
- prahy baseline úrovně na hranicích (9/10 a 13/14),
- rozpad skóre po dimenzích odpovídá zvoleným odpovědím,
- neúplné odpovědi se rozpoznají (R2.4).
"""

from __future__ import annotations

import pytest

from regina.domain.enums import Classification
from regina.domain.questionnaire import (
    QUESTIONS,
    SCORE_MAX,
    SCORE_MIN,
    baseline_classification,
    missing_dimensions,
    score_breakdown,
    total_score,
)


def _answers_for_weight(weight_code_index: int) -> dict[str, str]:
    """Sestaví odpovědi, kde každá dimenze zvolí odpověď daného pořadí (0-2)."""
    return {q.dimension: q.answers[weight_code_index].code for q in QUESTIONS}


def test_rozsah_souctu_je_6_az_18() -> None:
    assert SCORE_MIN == 6
    assert SCORE_MAX == 18
    assert total_score(_answers_for_weight(0)) == 6
    assert total_score(_answers_for_weight(2)) == 18


def test_prahy_baseline_na_hranicich() -> None:
    # Součet 6 (samé nejnižší) → MALÁ.
    assert baseline_classification(_answers_for_weight(0)) is Classification.SMALL
    # Součet 18 (samé nejvyšší) → VELKÁ.
    assert baseline_classification(_answers_for_weight(2)) is Classification.LARGE


def _answers_with_total(total: int) -> dict[str, str]:
    """Sestaví kompletní odpovědi s přesně požadovaným součtem vah (6–18).

    Každá dimenze začíná na váze 1 (základ 6). Rozdíl nad minimum rozdělíme
    přidáváním po jednom bodu do jednotlivých dimenzí, nikdy nad váhu 3.
    """
    assert SCORE_MIN <= total <= SCORE_MAX
    weights = [1] * len(QUESTIONS)
    extra = total - SCORE_MIN
    i = 0
    while extra > 0:
        if weights[i] < 3:
            weights[i] += 1
            extra -= 1
        else:
            i += 1
    answers: dict[str, str] = {}
    for question, weight in zip(QUESTIONS, weights):
        answers[question.dimension] = next(a.code for a in question.answers if a.weight == weight)
    return answers


@pytest.mark.parametrize(
    "total,expected",
    [
        (9, Classification.SMALL),
        (10, Classification.MEDIUM),
        (13, Classification.MEDIUM),
        (14, Classification.LARGE),
    ],
)
def test_prahy_presne_na_zlomu(total: int, expected: Classification) -> None:
    """Sestaví odpovědi s přesným součtem a ověří práh na zlomu."""
    answers = _answers_with_total(total)
    assert total_score(answers) == total
    assert baseline_classification(answers) is expected


def test_rozpad_skore_po_dimenzich() -> None:
    answers = _answers_for_weight(1)  # samé prostřední (váha 2)
    breakdown = score_breakdown(answers)
    assert set(breakdown) == {q.dimension for q in QUESTIONS}
    assert all(value == 2 for value in breakdown.values())


def test_neuplne_odpovedi_se_rozpoznaji() -> None:
    answers = _answers_for_weight(0)
    first_dim = QUESTIONS[0].dimension
    del answers[first_dim]
    assert missing_dimensions(answers) == [first_dim]
