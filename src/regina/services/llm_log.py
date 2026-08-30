"""Zápis technického logu volání modelu (classification-advisor R6).

Jediné místo, které skládá řádek `llm_call_log`. Zapisuje se po **každém**
volání modelu — úspěšném i neúspěšném (R6.1) — ve stejné transakci volajícího
(bez commitu, jako `audit.record`, design.md 6.3).

**Nikdy obsah** (R6.2). Funkce záměrně nepřijímá prompt, odpověď ani poznámku:
bere jen `LLMResponse` (metadata) a technický kontext (kdo, čeho se týkalo).
Není kudy protlačit obsah do logu — argument pro něj neexistuje.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from regina.db.models.llm_call_log import LLMCallLog
from regina.llm.base import LLMResponse, Operation


def record_call(
    session: Session,
    response: LLMResponse,
    *,
    gateway_impl: str,
    operation: Operation,
    application_id: uuid.UUID | None = None,
    requested_by_user_id: uuid.UUID | None = None,
    correlation_id: str | None = None,
) -> LLMCallLog:
    """Zapíše jeden řádek `llm_call_log` do probíhající transakce.

    Bere metadata z `LLMResponse` (model, tokeny, latence, status, kód chyby)
    a technický kontext. **Žádný obsah** promptu ani odpovědi — ten se sem
    nemá jak dostat (R6.2). Necommituje; o transakci se stará volající.

    Vrací vytvořený řádek pro navázání v testech a ve volající službě
    (`classification_suggestions.llm_call_id`).
    """
    entry = LLMCallLog(
        application_id=application_id,
        requested_by_user_id=requested_by_user_id,
        gateway_impl=gateway_impl,
        model=response.model,
        operation=str(operation),
        tokens_in=response.tokens_in,
        tokens_out=response.tokens_out,
        latency_ms=response.latency_ms,
        status=str(response.status),
        error_code=response.error_code,
        correlation_id=correlation_id,
    )
    session.add(entry)
    return entry
