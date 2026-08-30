"""Datové typy a protokol abstrakce volání modelu (R1.1, R1.7).

Rozhraní je **záměrně úzké a jednotné** pro generování textu (`CLASSIFY`,
`REWRITE`) i pro budoucí přepis řeči (`TRANSCRIBE`): jediná metoda `complete`
přijme `LLMRequest` a vrátí `LLMResponse`. Kdyby přibyla operace přepisu řeči,
přidá se jen hodnota do `Operation` — podpis se nemění (R1.7). To je celý smysl
abstrakce: zaměnitelnost bez zásahu do volajícího kódu.

**Text je už anonymizovaný.** Klient dostává text zbavený osobních údajů;
anonymizaci a rehydrataci řeší volající služba (`services/anonymization.py`),
ne klient (design.md 5.1). Tím je zaručeno, že žádná implementace klienta
nemůže poslat ven osobní údaj.

**Klient nevyhazuje na chybě.** Timeout ani chyba poskytovatele se nepropagují
jako výjimka; klient je převede na `LLMResponse` se `status` `TIMEOUT`/`ERROR`.
O degradaci (fallback poradce, nezávazná chyba u přepisu popisu) rozhoduje
služba, ne klient (R1.6, design.md 3.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class Operation(StrEnum):
    """Typ operace volání modelu.

    `CLASSIFY` a `REWRITE` používá poradce a přepis popisu. `TRANSCRIBE` je
    vyhrazené budoucímu přepisu řeči — je tu proto, aby bylo doložené, že
    rozhraní počítá s jeho doplněním bez změny podpisu (R1.7).
    """

    CLASSIFY = "CLASSIFY"
    REWRITE = "REWRITE"
    TRANSCRIBE = "TRANSCRIBE"


class LLMStatus(StrEnum):
    """Výsledek volání modelu — zapisuje se do `llm_call_log.status`."""

    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


@dataclass(frozen=True)
class LLMRequest:
    """Požadavek na model. Text je už anonymizovaný (design.md 5.1).

    Atributy:
        operation: typ operace (`CLASSIFY` / `REWRITE` / `TRANSCRIBE`).
        system_prompt: systémová instrukce (role, styl, jazyk odpovědi).
        user_prompt: uživatelský vstup — anonymizovaný.
        temperature: míra kreativity; u klasifikace nízká kvůli stabilitě.
        max_tokens: strop délky odpovědi.
    """

    operation: Operation
    system_prompt: str
    user_prompt: str
    temperature: float = 0.2
    max_tokens: int = 4096


@dataclass(frozen=True)
class LLMResponse:
    """Odpověď modelu plus technická metadata pro `llm_call_log`.

    `text` je odpověď modelu (u chyby prázdný řetězec). Metadata (`model`,
    tokeny, `latency_ms`, `status`, `error_code`) jdou do technického logu —
    **bez obsahu** promptu i odpovědi (R6.2). `error_code` nese jen strojový
    kód chyby, nikdy její text.
    """

    text: str
    model: str
    status: LLMStatus
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int = 0
    error_code: str | None = None

    @property
    def ok(self) -> bool:
        """True, když volání skončilo úspěchem a lze použít `text`."""
        return self.status is LLMStatus.SUCCESS


@runtime_checkable
class LLMClient(Protocol):
    """Protokol každé implementace abstrakce (R1.1).

    Jediná metoda `complete` je jednotná pro všechny operace. Implementace
    (`OpenRouterClient`, `MockClient`, budoucí Gateway) se navzájem zaměňují
    beze změny volajícího kódu. Vrací vždy `LLMResponse` — na chybě nevyhazuje
    výjimku, jen nastaví `status` (design.md 3.2).
    """

    #: Strojový kód implementace pro `llm_call_log.gateway_impl`
    #: (`OPENROUTER`, `MOCK`, případně `AI_GATEWAY`).
    gateway_impl: str

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Provede jedno volání modelu a vrátí odpověď s metadaty."""
        ...
