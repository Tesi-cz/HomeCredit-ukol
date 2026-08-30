"""Abstrakční vrstva pro volání jazykového modelu (classification-advisor R1).

Toto je **jediné** místo v aplikaci, které smí mluvit s jazykovým modelem.
Služby a webová vrstva znají pouze protokol `LLMClient` a datové typy
`LLMRequest`/`LLMResponse` — nikdy konkrétního poskytovatele ani jeho HTTP
protokol (R1.1). Díky tomu je výměna OpenRouteru za firemní AI Gateway změnou
konfigurace, ne přepisem kódu (R1.3).

Vrstva má nejméně dvě implementace (R1.2):

- `OpenRouterClient` — reálné volání přes OpenRouter (a jakoukoli
  OpenAI-kompatibilní Gateway změnou base URL),
- `MockClient` — deterministická náhrada bez sítě pro běh a testy bez klíče
  a jako záložní režim (R1.5).

Výběr provádí `build_llm_client(settings)` podle konfigurace.
"""

from __future__ import annotations

from regina.llm.base import LLMClient, LLMRequest, LLMResponse, LLMStatus, Operation
from regina.llm.factory import build_llm_client
from regina.llm.mock import MockClient
from regina.llm.openrouter import OpenRouterClient

__all__ = [
    "LLMClient",
    "LLMRequest",
    "LLMResponse",
    "LLMStatus",
    "Operation",
    "MockClient",
    "OpenRouterClient",
    "build_llm_client",
]
