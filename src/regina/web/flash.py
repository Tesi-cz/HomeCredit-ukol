"""Hlášení o výsledku akce (toast) přes query parametr (R13.8, ui.md sekce 3).

**Proč query parametr.** Po úspěšném `POST` (např. uložení záznamu) se dělá
přesměrování `303` na cílovou obrazovku — vzor Post/Redirect/Get, aby
znovunačtení stránky formulář neodeslalo podruhé. Zpráva o výsledku ale musí
přežít přesměrování. Bez server-side stavu (žádná session flash tabulka, žádná
databáze) je nejjednodušší a bezstavové řešení předat ji v query stringu cíle:

    return redirect_with_flash("/registr/{id}", "Záznam byl uložen.")
    # → 303 na /registr/{id}?flash=Z%C3%A1znam%20byl%20ulo%C5%BEen.&flash_type=success

Cílová routa nemusí nic číst — `page_context(...)` z query parametrů poskládá
`flash` do kontextu a komponenta `components/flash.html` ho vykreslí, pokud je
přítomen. Zpráva je jednorázová v tom smyslu, že po dalším přechodu bez
parametru zmizí.

**Varianty.** `success` (hotovo), `error` (varovani), `info` (info) — jméno
varianty určuje ikonu a barvu v komponentě. Neznámá hodnota spadne na `info`,
aby nevalidní parametr z URL rozhraní nerozbil.

Text je vždy český a předává ho volající routa; tento modul žádné popisky
nedrží.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from fastapi import Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

# Názvy query parametrů nesoucích zprávu a její typ. Drženy tady, aby je
# `page_context` (čtení) i `redirect_with_flash` (zápis) používaly shodně.
FLASH_MESSAGE_PARAM = "flash"
FLASH_TYPE_PARAM = "flash_type"

# Povolené varianty. Neznámý typ z URL se mapuje na „info", aby zůstal validní.
_ALLOWED_TYPES = frozenset({"success", "error", "info"})
_DEFAULT_TYPE = "info"


@dataclass(frozen=True)
class FlashMessage:
    """Jedno hlášení o výsledku akce k vykreslení v komponentě flash.

    `text` je český popis (od routy), `type` je jedna z povolených variant
    (`success`/`error`/`info`), která určuje ikonu a barvu.
    """

    text: str
    type: str


def flash_from_request(request: Request) -> FlashMessage | None:
    """Poskládá `FlashMessage` z query parametrů požadavku, nebo vrátí `None`.

    Volá se z `page_context`, takže obrazovky dostanou hlášení automaticky.
    Prázdný nebo chybějící `flash` znamená „žádné hlášení". Neznámý `flash_type`
    se sveze na `info`.
    """
    text = request.query_params.get(FLASH_MESSAGE_PARAM)
    if not text:
        return None
    raw_type = request.query_params.get(FLASH_TYPE_PARAM, _DEFAULT_TYPE)
    flash_type = raw_type if raw_type in _ALLOWED_TYPES else _DEFAULT_TYPE
    return FlashMessage(text=text, type=flash_type)


def redirect_with_flash(
    location: str,
    message: str,
    *,
    type: str = "success",
    status_code: int = 303,
) -> RedirectResponse:
    """Přesměruje na `location` a připojí hlášení jako query parametry.

    Vzor Post/Redirect/Get: routa po úspěšné akci vrátí tento response. Cílová
    obrazovka hlášení vykreslí přes `page_context` a komponentu flash. Výchozí
    `303 See Other` zajistí, že po `POST` následuje `GET` cíle.
    """
    flash_type = type if type in _ALLOWED_TYPES else _DEFAULT_TYPE
    separator = "&" if "?" in location else "?"
    query = urlencode({FLASH_MESSAGE_PARAM: message, FLASH_TYPE_PARAM: flash_type})
    return RedirectResponse(f"{location}{separator}{query}", status_code=status_code)


def redirect_after_write(
    session: Session,
    location: str,
    message: str,
    *,
    type: str = "success",
    status_code: int = 303,
) -> RedirectResponse:
    """Commitne transakci **a teprve pak** vrátí přesměrování s hlášením.

    **Proč commit tady, ne až v úklidu závislosti.** Transakci požadavku sice
    commituje ``get_session`` (přes ``session_scope``), jenže ten commit běží až
    *po* odeslání odpovědi klientovi. U Post/Redirect/Get to vytváří race:
    prohlížeč dostane ``303`` a okamžitě — často po jiném keep-alive spojení —
    vystřelí následný ``GET`` cíle. Ten otevře **novou** session a přečte
    ``applications.classification`` (a další) dřív, než se commit původního
    ``POST`` stihne zapsat. Výsledek: cílová obrazovka ukáže *předchozí* hodnotu
    (klasifikace, stav, role…), dokud uživatel nedá F5 — přesně příznak z chyby.

    Řešení je zapsat transakci **synchronně v obsluze**, ještě než odejde
    přesměrování. Mutační routy proto po zápisu volají tuto funkci místo
    ``redirect_with_flash``: nejdřív ``session.commit()``, pak se sestaví
    ``RedirectResponse``. Následný ``GET`` už tak vždy vidí commitnutá data.
    Úklidový commit v ``get_session`` pak nad prázdnou transakcí neudělá nic
    (no-op), takže se nic nezapíše dvakrát.

    Podpis je jinak shodný s ``redirect_with_flash`` — jen navíc přebírá
    ``session`` k commitu. Používá se všude, kde po úspěšné **změně dat**
    následuje přesměrování (vznik, editace, klasifikace, vyřazení, role).
    """
    session.commit()
    return redirect_with_flash(
        location, message, type=type, status_code=status_code
    )
