"""Deterministická implementace abstrakce bez sítě (R1.2, R1.5).

`MockClient` umožňuje běh a testy **bez API klíče** a slouží jako záložní
režim. Nevolá žádnou síť, je deterministický a nikdy nevyhazuje výjimku.

Nesnaží se předstírat model. Pro `REWRITE` vrátí lehce normalizovaný vstup
(sjednocení mezer, kapitalizace první věty), pro `CLASSIFY` vrátí prázdný text
— poradce si v mock režimu poskládá zdůvodnění z deterministického skóre sám
(design.md 5.2), takže tady žádné „falešné uvažování" negenerujeme.

Tokeny nastavuje na `None` (mock je nezná); `llm_call_log` je zapíše jako
prázdné (database.md 3).
"""

from __future__ import annotations

import re

from regina.llm.base import LLMRequest, LLMResponse, LLMStatus, Operation


class MockClient:
    """Bezsíťová deterministická náhrada `LLMClient` (R1.5)."""

    gateway_impl = "MOCK"

    def __init__(self, model: str = "mock") -> None:
        # Model se drží kvůli logu; „mock" je čitelný příznak v `llm_call_log`.
        self._model = model

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Vrátí deterministickou odpověď bez volání sítě.

        `REWRITE` normalizuje vstupní text; `CLASSIFY` (a cokoli dalšího) vrací
        prázdný text — zdůvodnění poskládá poradce z deterministického skóre.
        Status je vždy `SUCCESS`; mock nemá jak selhat.
        """
        if request.operation is Operation.REWRITE:
            text = self._normalize(request.user_prompt)
        else:
            text = ""

        return LLMResponse(
            text=text,
            model=self._model,
            status=LLMStatus.SUCCESS,
            tokens_in=None,
            tokens_out=None,
            latency_ms=0,
        )

    @staticmethod
    def _normalize(text: str) -> str:
        """Sjednotí mezery a začne velkým písmenem — náznak „úpravy" bez modelu."""
        collapsed = re.sub(r"\s+", " ", text).strip()
        if not collapsed:
            return collapsed
        return collapsed[0].upper() + collapsed[1:]
