"""Strukturované logování na standardní výstup.

Sběr logů si řeší prostředí, aplikace jen píše na stdout.

Co se **nikdy** neloguje (R12.10): hesla, tokeny, obsah session cookie, jména
a e-maily osob, celé řádky databáze. Přihlášení se loguje s identifikátorem
osoby, ne s e-mailem — čitelná identita patří do auditní tabulky chráněné rolí,
ne do aplikačního logu, který může skončit kdekoli.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# Atributy, které LogRecord nese vždy. Vše ostatní je považováno za doplňkový
# kontext a serializuje se do výstupu.
_STANDARD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
        # Uvicorn přidává obarvenou variantu zprávy s ANSI sekvencemi. Do
        # strukturovaného logu nepatří — je to duplikát s řídicími znaky.
        "color_message",
    }
)


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:16]


def set_correlation_id(value: str | None) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


class JsonFormatter(logging.Formatter):
    """Formátuje záznam jako jeden řádek JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        correlation_id = get_correlation_id()
        if correlation_id:
            payload["correlation_id"] = correlation_id

        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Nastaví jediný handler na stdout s JSON formátem."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn si přináší vlastní handlery; přesměrujeme je na náš root.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True

    # Access log uvicornu obsahuje celé URL včetně query parametrů. Ty mohou
    # nést vyhledávaný výraz, který uživatel zadal. Ponecháváme ho na WARNING,
    # protože požadavky logujeme vlastním middleware bez query stringu.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
