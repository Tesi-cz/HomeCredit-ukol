"""Volání modelu přes OpenRouter (R1.2, R1.3, R1.6).

`OpenRouterClient` mluví s OpenAI-kompatibilním chat-completions rozhraním.
Base URL, model, klíč a timeout jsou z konfigurace, takže **tentýž kód** obslouží
i firemní AI Gateway, pokud mluví stejným protokolem — stačí změnit
`LLM_BASE_URL` a `LLM_MODEL` (R1.3). API klíč se čte z konfigurace, která ho
bere z prostředí; v kódu není (R1.4).

**Nikdy nevyhazuje na chybě** (R1.6, design.md 3.2). Timeout, chybu sítě
i non-2xx odpověď převádí na `LLMResponse` se `status` `TIMEOUT`/`ERROR` a
strojovým `error_code`. Nikdy neloguje ani nevrací text chyby s obsahem
požadavku. O degradaci rozhoduje volající služba.
"""

from __future__ import annotations

import time

import httpx

from regina.llm.base import LLMRequest, LLMResponse, LLMStatus
from regina.logging import get_logger

logger = get_logger("regina.llm.openrouter")


class OpenRouterClient:
    """Implementace `LLMClient` nad OpenRouter / OpenAI-kompatibilní Gateway."""

    gateway_impl = "OPENROUTER"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int,
        reasoning: str = "off",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds
        # Řízení reasoningu (classification-advisor): "off" vypne řetěz úvah
        # u reasoning modelů (rychlejší, levnější odpověď); "auto" nechá na
        # modelu (parametr se nepošle); low/medium/high nastaví úsilí.
        self._reasoning = reasoning

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Zavolá model a vrátí odpověď; chybu převede na status, nevyhazuje."""
        started = time.monotonic()
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        # Řízení reasoningu přes sjednocený parametr OpenRouteru. "off" vypne
        # řetěz úvah (ne-reasoning modely to ignorují), low/medium/high nastaví
        # úsilí; "auto" parametr nepošle a nechá rozhodnutí na modelu.
        reasoning_param = self._reasoning_payload()
        if reasoning_param is not None:
            payload["reasoning"] = reasoning_param
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
        except httpx.TimeoutException:
            return self._failure(LLMStatus.TIMEOUT, "timeout", started)
        except httpx.HTTPError:
            # Síťová chyba bez těla odpovědi. Logujeme jen událost, ne obsah.
            logger.warning(
                "Volání modelu selhalo na síťové chybě",
                extra={"event": "llm.transport_error"},
            )
            return self._failure(LLMStatus.ERROR, "transport_error", started)

        if response.status_code >= 400:
            # Non-2xx: kód HTTP je strojový příznak, tělo odpovědi nelogujeme
            # ani neukládáme (mohlo by nést útržky vstupu).
            return self._failure(
                LLMStatus.ERROR, f"http_{response.status_code}", started
            )

        return self._success(response, started)

    def _success(self, response: httpx.Response, started: float) -> LLMResponse:
        """Vytáhne text a tokeny z úspěšné odpovědi."""
        latency_ms = int((time.monotonic() - started) * 1000)
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage") or {}
            tokens_in = usage.get("prompt_tokens")
            tokens_out = usage.get("completion_tokens")
        except (ValueError, KeyError, IndexError, TypeError):
            # Neočekávaný tvar odpovědi — bereme jako chybu, ne pád.
            return LLMResponse(
                text="",
                model=self._model,
                status=LLMStatus.ERROR,
                latency_ms=latency_ms,
                error_code="bad_response_shape",
            )

        return LLMResponse(
            text=text,
            model=self._model,
            status=LLMStatus.SUCCESS,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )

    def _failure(self, status: LLMStatus, error_code: str, started: float) -> LLMResponse:
        """Sestaví neúspěšnou odpověď se strojovým kódem chyby (bez obsahu)."""
        latency_ms = int((time.monotonic() - started) * 1000)
        return LLMResponse(
            text="",
            model=self._model,
            status=status,
            latency_ms=latency_ms,
            error_code=error_code,
        )

    def _reasoning_payload(self) -> dict | None:
        """Přeloží konfiguraci reasoningu na `reasoning` blok OpenRouteru.

        - `off` → `{"enabled": false}` (vypne řetěz úvah; ne-reasoning modely
          to ignorují),
        - `low`/`medium`/`high` → `{"effort": "..."}` (nastaví úsilí),
        - `auto` → `None` (parametr se nepošle, rozhodne model).

        Neznámá hodnota (nemělo by nastat — validuje config) se chová jako
        `auto`, aby request nikdy nespadl kvůli reasoningu.
        """
        value = (self._reasoning or "auto").lower()
        if value == "off":
            return {"enabled": False}
        if value in {"low", "medium", "high"}:
            return {"effort": value}
        return None
