"""Výběr implementace abstrakce podle konfigurace (R1.3, R1.5, design.md 3.3).

`build_llm_client` je jediné místo, které rozhoduje, jestli poběží
`OpenRouterClient`, nebo `MockClient`. Volá se jednou při startu; služby
dostávají hotového klienta přes dependency injection (jako session), takže
jsou testovatelné s podstrčeným mockem.

Rozhodnutí řídí `settings.llm_provider_effective`:

- `openrouter` → `OpenRouterClient` (vyžaduje klíč),
- `mock` → `MockClient`.

**Bez klíče se nikdy nespadne** (R1.5). Když je efektivní provider
`openrouter`, ale klíč chybí (nekonzistentní ruční konfigurace), spadne se
bezpečně na mock a zaloguje se varování — aplikace naběhne a poradce funguje.
"""

from __future__ import annotations

from regina.config import Settings
from regina.llm.base import LLMClient
from regina.llm.mock import MockClient
from regina.llm.openrouter import OpenRouterClient
from regina.logging import get_logger

logger = get_logger("regina.llm")


def build_llm_client(settings: Settings) -> LLMClient:
    """Vrátí klienta modelu podle konfigurace.

    Efektivní provider (`openrouter`/`mock`) se odvozuje v `Settings`
    (přítomnost klíče, případně explicitní `LLM_PROVIDER`). Tady se jen
    sestaví odpovídající implementace. Při `openrouter` bez klíče se
    bezpečně přepne na mock (R1.5).
    """
    provider = settings.llm_provider_effective
    api_key = (settings.openrouter_api_key or "").strip()

    if provider == "openrouter":
        if not api_key:
            logger.warning(
                "LLM_PROVIDER je openrouter, ale chybí API klíč — přepínám na "
                "mock režim. Poradce funguje, jen bez volání modelu.",
                extra={"event": "llm.missing_key_fallback_to_mock"},
            )
            return MockClient(model=settings.llm_model)

        logger.info(
            "Model poradce: OpenRouter, model %s",
            settings.llm_model,
            extra={"event": "llm.provider_selected", "gateway_impl": "OPENROUTER"},
        )
        return OpenRouterClient(
            api_key=api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    logger.info(
        "Model poradce: mock režim (bez volání sítě)",
        extra={"event": "llm.provider_selected", "gateway_impl": "MOCK"},
    )
    return MockClient(model=settings.llm_model)
