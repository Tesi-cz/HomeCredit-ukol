"""Ochrana formulářů tokenem CSRF vázaným na session (design.md sekce 7).

**Proč vůbec.** Session cookie je `SameSite=Lax` (`auth/session.py`), což už
samo odfiltruje většinu cross-site odeslání formulářů. CSRF token je vrstva
navíc (defense-in-depth), jak design.md sekce 7 výslovně žádá: „Každý `POST`
nese CSRF token vázaný na session." `SameSite=Lax` **neoslabujeme** — token na
něj jen navazuje.

**Jak je token vázaný na session.** Nedržíme žádný server-side stav. Token je
`itsdangerous`-podepsaná hodnota odvozená z **identity session cookie**
(subjektu z podepsané session). Podpisovým klíčem je `SESSION_SECRET`, se
samostatným „salt", aby se CSRF token nedal zaměnit za session ani za dočasný
stav OIDC. Kdo nezná tajemství, token nevyrobí; a token platný pro jednu
session neprojde u jiné, protože do podpisu vstupuje subjekt té session.

**Kde se používá.**

1. Šablony (sekce 8) si vyžádají aktuální token přes `get_csrf_token(request)`
   a vloží ho do formuláře jako skryté pole `<input type="hidden"
   name="csrf_token" value="…">`. Token se zpřístupní i v kontextu šablon.
2. Každý stavotvorný `POST` prochází závislostí `csrf_protect`, která odeslaný
   token porovná s hodnotou očekávanou pro danou session. Neshoda nebo chybějící
   token → `CsrfError` → globální handler vrátí stránku 403 bez stack trace
   (design.md sekce 8). Validace je na **jednom místě**, stejně jako zamítnutí
   autorizace v úkolu 6.3.

Anonymní `POST` (např. odhlášení bez platné session) token nemá k čemu vázat;
`csrf_protect` takový požadavek propustí, protože bez přihlášené identity není
co chránit — a chráněné routy stejně spadnou dřív na `require_login`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, Request
from itsdangerous import BadSignature, URLSafeSerializer
from starlette.responses import Response

from regina.auth.session import read_session
from regina.config import Settings
from regina.logging import get_logger

_logger = get_logger("regina.auth")

# Samostatný „salt" odlišuje CSRF token od session cookie a od dočasného stavu
# OIDC (`auth/session.py`), i když všechny tři podepisuje stejné tajemství.
# Bez toho by šla jedna hodnota podstrčit místo druhé.
_CSRF_SALT = "regina.csrf"

# Název skrytého pole ve formuláři i klíč v kontextu šablon. Šablony (sekce 8)
# vloží `<input type="hidden" name="csrf_token" value="{{ csrf_token }}">`.
CSRF_FIELD_NAME = "csrf_token"

# HTTP metody, které stav nemění a token proto nevyžadují (bezpečné metody dle
# RFC 9110). Chráníme jen stavotvorné požadavky.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class CsrfError(Exception):
    """Chybějící nebo neplatný CSRF token u stavotvorného požadavku.

    Handler ji promění na stránku 403 bez detailů (design.md sekce 8). Nese jen
    krátký důvod do logu; nikdy neobsahuje samotný token.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _serializer(settings: Settings) -> URLSafeSerializer:
    return URLSafeSerializer(settings.session_secret, salt=_CSRF_SALT)


def _session_identity(request: Request, settings: Settings) -> str | None:
    """Vrátí subjekt přihlášené session, nebo `None` u anonymního požadavku.

    Token se váže na tuto hodnotu: token vydaný pro jednu přihlášenou osobu
    neprojde u jiné a znovupoužití napříč sessionami tak nedává výhodu.
    """
    session_user = read_session(request, settings)
    if session_user is None:
        return None
    return session_user.subject


def issue_csrf_token(request: Request, settings: Settings) -> str:
    """Vytvoří CSRF token vázaný na aktuální session.

    Podepíše subjekt session samostatným saltem. Pro anonymní požadavek (bez
    platné session) vrátí prázdný řetězec — není co vázat a chráněné formuláře
    se stejně vykreslují až přihlášenému uživateli.
    """
    subject = _session_identity(request, settings)
    if subject is None:
        return ""
    return _serializer(settings).dumps({"sub": subject})


def get_csrf_token(request: Request) -> str:
    """Pohodlný přístup pro šablony (sekce 8).

    Šablona zavolá `get_csrf_token(request)` a výsledek vloží do skrytého pole.
    Token pro daný požadavek se počítá jednou a cachuje na `request.state`, aby
    se opakované volání v jedné šabloně nepodepisovalo znovu.
    """
    cached = getattr(request.state, "csrf_token", None)
    if cached is not None:
        return cached
    settings: Settings = request.app.state.settings
    token = issue_csrf_token(request, settings)
    request.state.csrf_token = token
    return token


def _token_matches(request: Request, settings: Settings, submitted: str) -> bool:
    """Ověří, že odeslaný token patří k aktuální session.

    Rozváže podpis (chytí padělek i cizí salt) a porovná subjekt uvnitř tokenu
    se subjektem aktuální session (chytí token z jiné session).
    """
    if not submitted:
        return False

    try:
        payload = _serializer(settings).loads(submitted)
    except BadSignature:
        return False

    if not isinstance(payload, dict):
        return False

    expected_subject = _session_identity(request, settings)
    if expected_subject is None:
        return False

    return payload.get("sub") == expected_subject


async def csrf_protect(request: Request) -> None:
    """FastAPI závislost: ověří CSRF token u každého stavotvorného požadavku.

    Bezpečné metody (`GET`, `HEAD`, …) propustí bez kontroly. U `POST` a dalších
    stavotvorných metod přečte token z formulářového pole `csrf_token` a ověří
    ho proti session. Neshoda nebo chybějící token → `CsrfError`, kterou
    globální handler promění na 403. Validace tak leží na jednom místě
    (mirror úkolu 6.3), routy o CSRF nic vědět nemusí — jen připojí tuto
    závislost.

    Anonymní požadavek (bez platné session) se propustí: token nemá k čemu vázat
    a chráněné routy spadnou dřív na `require_login`.
    """
    if request.method in _SAFE_METHODS:
        return

    # Anonymní požadavek nemá session, ke které by se token vázal.
    settings: Settings = request.app.state.settings
    if _session_identity(request, settings) is None:
        return

    form = await request.form()
    submitted = form.get(CSRF_FIELD_NAME)
    submitted_token = submitted if isinstance(submitted, str) else ""

    if not _token_matches(request, settings, submitted_token):
        raise CsrfError("Chybějící nebo neplatný CSRF token.")


CsrfProtect = Depends(csrf_protect)
CsrfGuardDep = Annotated[None, Depends(csrf_protect)]


# -- Globální handler ----------------------------------------------------
#
# Handler je zde, u validace, stejně jako handlery autorizace bydlí u guardů
# v `auth/deps.py`. `main.create_app` ho jen zaregistruje přes
# `register_csrf_handler`.


def _handle_csrf_error(request: Request, exc: CsrfError) -> Response:
    """Neplatný CSRF token → stránka 403, zalogováno jednou, bez tokenu v logu.

    Vrací tutéž stylovanou stránku 403 jako zamítnutá autorizace — obě selhání
    vypadají pro uživatele stejně a sdílí jednu šablonu (úkol 8.4). Renderer je
    v `auth/deps.py`, protože 403 tam už bydlí; import je lokální, aby při
    načítání modulu nevznikla vazba na `deps`.
    """
    from regina.auth.deps import render_forbidden

    _logger.warning(
        "csrf_rejected",
        extra={
            "event": "auth.csrf_rejected",
            "method": request.method,
            "path": request.url.path,
        },
    )
    return render_forbidden(request)


def register_csrf_handler(app: FastAPI) -> None:
    """Zaregistruje handler `CsrfError` na aplikaci (volá `main.create_app`)."""
    app.add_exception_handler(CsrfError, _handle_csrf_error)
