"""Webové závislosti navázané na `app.state` (classification-advisor).

Drží tenké FastAPI závislosti pro objekty složené jednou při startu a uložené
na `app.state` — dnes klient jazykového modelu. Je to stejný vzor jako u OIDC
klienta: routa nezná konkrétní implementaci, jen protokol `LLMClient`, takže
se v testu snadno podstrčí mock.

Záměrně mimo `auth/deps.py`: ten drží identitu a autorizaci a nesmí záviset na
balíčku `llm`. Webové napojení modelu proto bydlí tady.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from regina.llm.base import LLMClient


def get_llm_client(request: Request) -> LLMClient:
    """Vrátí sdíleného klienta modelu z `app.state` (napojen v `main.create_app`)."""
    return request.app.state.llm_client


LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]
