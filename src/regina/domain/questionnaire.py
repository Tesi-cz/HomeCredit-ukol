"""Katalog klasifikačního dotazníku a deterministické skóre (R2, R3.1).

Patří do `domain/`, protože je to čistá znalostní vrstva bez závislosti na
databázi, HTTP i modelu (design.md 4). Díky tomu se skóre testuje samostatně
a tentýž katalog používá wizard (otázky), poradce (skóre a baseline) i mock
(zdůvodnění z baseline).

**Šest dimenzí** (R2.2), každá jedna otázka s uzavřenou nabídkou odpovědí.
Každá odpověď nese celočíselnou váhu 1–3 (R2.3). Součet je 6–18 a mapuje se na
baseline úroveň prahy 6–9 / 10–13 / 14–18 (R3.1, design.md 4.2) — čistý součet
bez speciálních pojistek, aby bylo pravidlo triviálně obhajitelné.

Texty otázek a odpovědí jsou české přímo tady (R2.7) — je to business obsah
dotazníku, ne strojový kód výčtu (ty překládá `labels.py`). Úroveň se do
rozhraní vždy zobrazí přes `labels.classification_label`, nikdy jako kód.

`QUESTIONNAIRE_VERSION` se ukládá s každým doporučením (R2.6), aby staré
doporučení zůstalo interpretovatelné po změně katalogu.
"""

from __future__ import annotations

from dataclasses import dataclass

from regina.domain.enums import Classification

#: Verze katalogu otázek. Zvyš při jakékoli změně otázek, odpovědí nebo vah,
#: aby uložená doporučení odkazovala na katalog, podle kterého vznikla (R2.6).
QUESTIONNAIRE_VERSION = "1.0"


@dataclass(frozen=True)
class Answer:
    """Jedna možná odpověď na otázku: strojový kód, český popisek a váha."""

    code: str
    label: str
    weight: int


@dataclass(frozen=True)
class Question:
    """Jedna otázka dotazníku měřící jednu dimenzi.

    `dimension` je strojový kód dimenze (stabilní klíč do
    `questionnaire_answers`), `title` a `help_text` jsou české texty do
    rozhraní, `answers` je uzavřená nabídka.
    """

    dimension: str
    title: str
    help_text: str
    answers: tuple[Answer, ...]


#: Šest dimenzí dotazníku (R2.2). Pořadí = pořadí kroků wizardu.
QUESTIONS: tuple[Question, ...] = (
    Question(
        dimension="USERS",
        title="Kolik lidí bude aplikaci používat?",
        help_text="Odhad počtu aktivních uživatelů.",
        answers=(
            Answer("FEW", "Do 50 uživatelů", 1),
            Answer("MEDIUM", "50–500 uživatelů", 2),
            Answer("MANY", "Více než 500 uživatelů", 3),
        ),
    ),
    Question(
        dimension="DATA_SENSITIVITY",
        title="Jak citlivá data aplikace zpracovává?",
        help_text="Nejcitlivější kategorie dat, se kterou aplikace pracuje.",
        answers=(
            Answer("PUBLIC", "Veřejná nebo interní neklasifikovaná", 1),
            Answer("INTERNAL", "Interní důvěrná", 2),
            Answer("PERSONAL", "Osobní údaje nebo finanční data", 3),
        ),
    ),
    Question(
        dimension="CRITICALITY",
        title="Jak kritická je aplikace pro provoz?",
        help_text="Dopad výpadku aplikace na chod firmy.",
        answers=(
            Answer("LOW", "Nízká — podpůrný nástroj", 1),
            Answer("MEDIUM", "Střední — důležitá pro tým", 2),
            Answer("HIGH", "Vysoká — kritická pro provoz", 3),
        ),
    ),
    Question(
        dimension="INTEGRATION",
        title="Kolik externích systémů je integrováno?",
        help_text="Počet napojení na jiné systémy nebo služby.",
        answers=(
            Answer("NONE", "Žádný nebo jeden", 1),
            Answer("SOME", "Dva až pět", 2),
            Answer("MANY", "Více než pět", 3),
        ),
    ),
    Question(
        dimension="REGULATION",
        title="Spadá aplikace pod regulaci?",
        help_text="Například GDPR, AML, požadavky ČNB nebo DORA.",
        answers=(
            Answer("NONE", "Nespadá pod žádnou regulaci", 1),
            Answer("PARTIAL", "Částečně — dotýká se regulovaných procesů", 2),
            Answer("FULL", "Ano — přímo regulovaná oblast", 3),
        ),
    ),
    Question(
        dimension="AI_USE",
        title="Jak aplikace používá AI model?",
        help_text="Míra, do jaké aplikace spoléhá na AI model.",
        answers=(
            Answer("NONE", "Nepoužívá AI model", 1),
            Answer("ASSIST", "Pomocná funkce, výstup kontroluje člověk", 2),
            Answer("DECISION", "AI se podílí na rozhodování o klientech", 3),
        ),
    ),
)

#: Rychlé vyhledání otázky podle dimenze.
_QUESTIONS_BY_DIMENSION: dict[str, Question] = {q.dimension: q for q in QUESTIONS}

#: Prahy součtu vah na baseline úroveň (R3.1). Součet je vždy 6–18.
SCORE_MIN = len(QUESTIONS)  # každá dimenze aspoň 1
SCORE_MAX = len(QUESTIONS) * 3  # každá dimenze nejvýše 3


def _answer_weight(dimension: str, answer_code: str) -> int:
    """Váha zvolené odpovědi, nebo `KeyError`/`ValueError` u neznámé volby."""
    question = _QUESTIONS_BY_DIMENSION[dimension]
    for answer in question.answers:
        if answer.code == answer_code:
            return answer.weight
    raise ValueError(f"Neznámá odpověď '{answer_code}' pro dimenzi '{dimension}'.")


def missing_dimensions(answers: dict[str, str]) -> list[str]:
    """Dimenze, na které chybí odpověď (R2.4). Prázdný seznam = kompletní."""
    return [q.dimension for q in QUESTIONS if not answers.get(q.dimension)]


def score_breakdown(answers: dict[str, str]) -> dict[str, int]:
    """Váha zvolené odpovědi po dimenzích. Vyžaduje kompletní odpovědi.

    Slouží k transparentnímu rozpadu skóre v AI panelu (R3.3): uživatel vidí,
    kolik bodů přispěla která dimenze.
    """
    return {q.dimension: _answer_weight(q.dimension, answers[q.dimension]) for q in QUESTIONS}


def total_score(answers: dict[str, str]) -> int:
    """Součet vah přes všech šest dimenzí (6–18). Vyžaduje kompletní odpovědi."""
    return sum(score_breakdown(answers).values())


def baseline_classification(answers: dict[str, str]) -> Classification:
    """Baseline úroveň z čistého součtu vah (R3.1).

    Prahy (design.md 4.2): 6–9 → `MALÁ`, 10–13 → `STŘEDNÍ`, 14–18 → `VELKÁ`.
    Bez speciálních pojistek — přímý, obhajitelný a testovatelný převod.
    """
    total = total_score(answers)
    if total <= 9:
        return Classification.SMALL
    if total <= 13:
        return Classification.MEDIUM
    return Classification.LARGE
