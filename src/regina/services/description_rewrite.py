"""AI úprava popisu (classification-advisor R4, design.md 5.3).

Přepíše zadaný popis záznamu do kultivovanějšího znění pomocí modelu. Vrací
**návrh** — nikam ho neukládá (R4.6); uložení proběhne až uložením formuláře.

**Osobní údaje ven nejdou** (R4.2, R5.3): text se před odesláním anonymizuje
a po návratu rehydratuje.

**Chyba je nezávazná** (R4.5, R1.6): při timeoutu/chybě modelu se vrátí
neúspěšný výsledek s českou hláškou; původní popis zůstává nedotčený, request
nespadne. Prázdný popis se odmítne ještě před voláním (R4.4).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from regina.llm.base import LLMClient, LLMRequest, Operation
from regina.services import llm_log
from regina.services.anonymization import anonymize, rehydrate

#: Systémový prompt pro přepis popisu. Zrcadlí se do `prompts/` (úkol 7).
REWRITE_SYSTEM_PROMPT = (
    "Přepiš popis interní firemní aplikace do jasnějšího a kultivovanějšího "
    "českého znění. Zachovej význam i všechny faktické údaje, neměň smysl, "
    "nepřidávej nové informace. Vstup může obsahovat zástupné symboly typu "
    "[[JMENO_1]] — ponech je beze změny. Vrať jen upravený popis bez úvodu a "
    "bez nadpisů."
)


@dataclass(frozen=True)
class RewriteResult:
    """Výsledek přepisu popisu pro webovou vrstvu.

    Při úspěchu nese ``text`` s návrhem; při neúspěchu ``ok=False`` a českou
    ``error_message`` k nezávaznému zobrazení. Návrh se nikam neukládá (R4.6).
    """

    ok: bool
    text: str = ""
    error_message: str = ""


def rewrite_description(
    session: Session,
    client: LLMClient,
    *,
    description: str,
    known_names: list[str] | None = None,
    application_id: uuid.UUID | None = None,
    requested_by_user_id: uuid.UUID | None = None,
    correlation_id: str | None = None,
) -> RewriteResult:
    """Vrátí návrh přepsaného popisu, nebo nezávaznou chybu (R4).

    Prázdný popis odmítne bez volání modelu (R4.4). Jinak text anonymizuje,
    zavolá model přes abstrakci, zaloguje volání a při úspěchu vrátí
    rehydratovaný návrh. Při chybě vrátí ``ok=False`` s českou hláškou; popis
    se nemění (R4.5). Necommituje.
    """
    if not description or not description.strip():
        return RewriteResult(
            ok=False,
            error_message="Popis je prázdný — není co upravovat.",
        )

    masked, mapping = anonymize(description, known_names=known_names)
    request = LLMRequest(
        operation=Operation.REWRITE,
        system_prompt=REWRITE_SYSTEM_PROMPT,
        user_prompt=masked,
    )
    response = client.complete(request)

    llm_log.record_call(
        session,
        response,
        gateway_impl=client.gateway_impl,
        operation=Operation.REWRITE,
        application_id=application_id,
        requested_by_user_id=requested_by_user_id,
        correlation_id=correlation_id,
    )

    if response.ok and response.text.strip():
        return RewriteResult(ok=True, text=rehydrate(response.text.strip(), mapping))

    return RewriteResult(
        ok=False,
        error_message="Úpravu popisu se teď nepodařilo získat. Zkus to prosím znovu.",
    )
