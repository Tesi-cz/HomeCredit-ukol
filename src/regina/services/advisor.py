"""Klasifikační poradce (classification-advisor R3, design.md 5.2).

Orchestruje jeden běh doporučení: z odpovědí dotazníku spočítá deterministické
skóre, případně vyžádá zdůvodnění od modelu a uloží ``classification_suggestions``.

**Nezapisuje klasifikaci.** Vrací a ukládá jen ``Suggestion``. Samotný zápis do
registru dělá až přijetí návrhu ve webové vrstvě přes
``services/classification.set_classification_from_suggestion`` (design.md 5.2).

**Fallback místo pádu** (R3.4, R1.6). Když klient chybí, vrátí chybu nebo
timeout, poradce se opře o deterministické skóre a doporučení označí jako
fallback (``is_fallback=True``). Request nikdy nespadne kvůli modelu.

**Osobní údaje ven nejdou.** Volitelná poznámka se před odesláním modelu
anonymizuje a zdůvodnění se po návratu rehydratuje (R5.3). Do
``classification_suggestions`` se ukládají jen odpovědi (uzavřené volby a skóre)
a zdůvodnění — poznámka ani prompt se neukládají (R6.2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from regina.db.models.classification_suggestion import ClassificationSuggestion
from regina.domain import questionnaire
from regina.domain.enums import Classification
from regina.domain.labels import classification_label
from regina.llm.base import LLMClient, LLMRequest, Operation
from regina.services import llm_log
from regina.services.anonymization import anonymize, rehydrate

#: Systémový prompt pro klasifikaci. V úkolu 7 se zrcadlí do `prompts/`; zde je
#: zdroj pravdy pro běh. Počítá s anonymizovaným vstupem (placeholdery) a NESMÍ
#: je „opravovat" zpět na jména.
CLASSIFY_SYSTEM_PROMPT = (
    "Jsi asistent pro klasifikaci interních firemních aplikací ve finanční "
    "instituci. Na základě odpovědí dotazníku doporučíš velikostní klasifikaci "
    "MALÁ, STŘEDNÍ, nebo VELKÁ a stručně ji zdůvodníš česky (2–4 věty). "
    "Vstup může obsahovat zástupné symboly typu [[JMENO_1]] nebo [[EMAIL_1]] — "
    "ponech je beze změny, nedoplňuj za ně konkrétní údaje. Odpovíš čistým "
    "zdůvodněním bez nadpisů."
)


@dataclass(frozen=True)
class Suggestion:
    """Výsledek jednoho běhu poradce pro zobrazení v AI panelu (R3.3).

    Nese navrženou úroveň, zdůvodnění, rozpad skóre po dimenzích, příznak
    fallbacku a identifikátor uloženého ``classification_suggestions`` řádku
    (pro navázání při přijetí návrhu, R3.9).
    """

    suggestion_id: int
    classification: Classification
    rationale: str
    score_breakdown: dict[str, int]
    total_score: int
    is_fallback: bool


def _fallback_rationale(level: Classification, total: int) -> str:
    """České zdůvodnění poskládané z deterministického skóre (R3.4)."""
    return (
        f"Doporučení vzniklo z bodového hodnocení dotazníku (skóre {total} "
        f"z {questionnaire.SCORE_MAX}). Odpovídá úrovni "
        f"{classification_label(level)}. Návrh je záložní (bez jazykového "
        f"modelu)."
    )


def request_suggestion(
    session: Session,
    client: LLMClient,
    *,
    answers: dict[str, str],
    note: str | None = None,
    known_names: list[str] | None = None,
    application_id: uuid.UUID | None = None,
    requested_by_user_id: uuid.UUID | None = None,
    correlation_id: str | None = None,
) -> Suggestion:
    """Vyžádá doporučení klasifikace z odpovědí dotazníku (R3.1–R3.4, R3.9).

    Postup (design.md 5.2):

    1. Ověří kompletnost odpovědí (R2.4) — jinak ``ValueError``.
    2. Spočítá deterministické skóre a baseline úroveň (R3.1).
    3. Je-li k dispozici model, sestaví anonymizovaný prompt, zavolá ho přes
       abstrakci, rehydratuje zdůvodnění a zaloguje volání (R3.2, R5, R6).
    4. Při chybě/timeoutu/prázdné odpovědi se opře o deterministický fallback
       a označí ho (R3.4).
    5. Uloží ``classification_suggestions`` a vrátí ``Suggestion``.

    Necommituje — o transakci se stará volající (design.md 6.3).
    """
    missing = questionnaire.missing_dimensions(answers)
    if missing:
        raise ValueError(f"Chybí odpověď na dimenze: {', '.join(missing)} (R2.4).")

    breakdown = questionnaire.score_breakdown(answers)
    total = questionnaire.total_score(answers)
    baseline = questionnaire.baseline_classification(answers)

    rationale = _fallback_rationale(baseline, total)
    classification = baseline
    is_fallback = True
    llm_call_id: int | None = None

    # Volání modelu. Když selže nebo vrátí prázdný text, zůstává deterministický
    # fallback. Anonymizace poznámky proběhne vždy před odesláním (R5.3).
    masked_note, mapping = anonymize(note or "", known_names=known_names)
    user_prompt = _build_user_prompt(breakdown, total, baseline, masked_note)
    request = LLMRequest(
        operation=Operation.CLASSIFY,
        system_prompt=CLASSIFY_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    response = client.complete(request)

    call = llm_log.record_call(
        session,
        response,
        gateway_impl=client.gateway_impl,
        operation=Operation.CLASSIFY,
        application_id=application_id,
        requested_by_user_id=requested_by_user_id,
        correlation_id=correlation_id,
    )
    session.flush()  # potřebujeme llm_call_id pro vazbu z doporučení
    llm_call_id = call.id

    if response.ok and response.text.strip():
        rationale = rehydrate(response.text.strip(), mapping)
        is_fallback = False
        # Úroveň drží baseline (deterministická, obhajitelná kostra); model
        # dodává zdůvodnění. Případné čtení úrovně z textu modelu je vědomě
        # mimo rozsah — baseline je stabilnější a testovatelná.

    suggestion = ClassificationSuggestion(
        application_id=application_id,
        suggested_classification=str(classification),
        justification=rationale,
        questionnaire_version=questionnaire.QUESTIONNAIRE_VERSION,
        questionnaire_answers=dict(answers),
        deterministic_score=total,
        is_fallback=is_fallback,
        llm_call_id=llm_call_id,
        requested_by_user_id=requested_by_user_id,
    )
    session.add(suggestion)
    session.flush()  # potřebujeme id pro Suggestion a pozdější vazbu z logu

    return Suggestion(
        suggestion_id=suggestion.id,
        classification=classification,
        rationale=rationale,
        score_breakdown=breakdown,
        total_score=total,
        is_fallback=is_fallback,
    )


def _build_user_prompt(
    breakdown: dict[str, int],
    total: int,
    baseline: Classification,
    masked_note: str,
) -> str:
    """Sestaví anonymizovaný uživatelský prompt z odpovědí a skóre.

    Používá popisky otázek a zvolených odpovědí (české texty z katalogu), skóre
    po dimenzích a deterministickou baseline jako vodítko. Poznámka je už
    anonymizovaná (placeholdery).
    """
    lines = ["Odpovědi dotazníku a jejich bodové hodnocení:"]
    for question in questionnaire.QUESTIONS:
        weight = breakdown[question.dimension]
        lines.append(f"- {question.title} → {weight} b.")
    lines.append(f"Celkové skóre: {total} z {questionnaire.SCORE_MAX}.")
    lines.append(f"Bodové doporučení: {classification_label(baseline)}.")
    if masked_note.strip():
        lines.append(f"Poznámka zadavatele: {masked_note.strip()}")
    lines.append(
        "Doporuč úroveň (MALÁ/STŘEDNÍ/VELKÁ) a zdůvodni ji česky ve 2–4 větách."
    )
    return "\n".join(lines)
