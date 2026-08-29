"""Složení aplikace REGINA.

Zde se aplikace jen skládá: nastaví se logování, konfigurace, databázové
připojení a zaregistruje middleware a routy. Business logika sem nepatří.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import PlainTextResponse

from regina.auth.csrf import register_csrf_handler
from regina.auth.deps import register_auth_handlers
from regina.auth.oidc import build_oidc_client
from regina.config import Settings, load_settings
from regina.db import session as db_session
from regina.logging import (
    configure_logging,
    get_logger,
    new_correlation_id,
    set_correlation_id,
)
from regina.seed import run_seed
from regina.services.retention import run_retention_loop
from regina.web.routes.audit import router as audit_router
from regina.web.routes.auth import router as auth_router
from regina.web.routes.export import router as export_router
from regina.web.routes.mine import router as mine_router
from regina.web.routes.registry import router as registry_router
from regina.web.routes.users import router as users_router
from regina.web.templating import build_templates

# Statické zdroje leží vedle webového balíčku. Cesta se počítá z umístění
# souboru, aby fungovala nezávisle na pracovním adresáři (uvicorn i testy).
_STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"

logger = get_logger("regina")

CORRELATION_HEADER = "X-Correlation-Id"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings

    db_session.init_engine(settings)

    logger.info(
        "Aplikace startuje",
        extra={
            "event": "app.startup",
            "app_name": settings.app_name,
            "oidc_issuer": settings.oidc_issuer,
            "departments": len(settings.departments),
            "retention_enabled": settings.retention_enabled,
        },
    )

    # Naplnění syntetickými daty (úkol 9.1, R12.9). Běží po inicializaci enginu
    # a je řízené SEED_ON_START. Schéma je v tu chvíli hotové — migrace pouští
    # entrypoint kontejneru před spuštěním serveru (design.md 6.4, 13).
    # Idempotentní, takže opakovaný start data nezduplikuje.
    run_seed(settings)

    # Retenční úloha na pozadí (úkol 19.1, R9.3): spustí se hned při startu a
    # pak běží v konfigurovatelném intervalu, bez plánovače navíc a bez ručního
    # kroku. Startuje jen když je retence povolená (RETENTION_ENABLED); jinak
    # úlohu vůbec nezakládáme. Uložíme si ji, abychom ji při vypnutí čistě
    # zrušili (blok finally).
    retention_task: asyncio.Task[None] | None = None
    if settings.retention_enabled:
        retention_task = asyncio.create_task(run_retention_loop(settings))
        logger.info(
            "Retenční úloha spuštěna",
            extra={
                "event": "retention.started",
                "interval_hours": settings.retention_interval_hours,
            },
        )

    try:
        yield
    finally:
        if retention_task is not None:
            retention_task.cancel()
            # Počkáme, až úloha na zrušení zareaguje; CancelledError spolkneme,
            # protože zrušení při vypnutí je očekávané, ne chyba.
            with contextlib.suppress(asyncio.CancelledError):
                await retention_task
        db_session.dispose_engine()
        logger.info("Aplikace se zastavuje", extra={"event": "app.shutdown"})


def _register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlation_and_access_log(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Přidá korelační identifikátor a zaloguje výsledek požadavku.

        Loguje se cesta **bez** query stringu — ten nese vyhledávaný výraz
        zadaný uživatelem a do aplikačního logu nepatří (R12.10).
        """
        correlation_id = request.headers.get(CORRELATION_HEADER) or new_correlation_id()
        set_correlation_id(correlation_id)
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Neošetřená chyba při zpracování požadavku",
                extra={
                    "event": "request.failed",
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            raise
        finally:
            set_correlation_id(None)

        response.headers[CORRELATION_HEADER] = correlation_id
        logger.info(
            "Požadavek zpracován",
            extra={
                "event": "request.completed",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return response


def _register_web(app: FastAPI) -> None:
    """Připojí šablony a statické zdroje (úkol 8.3).

    Jinja2 se skládá jednou při startu a ukládá na `app.state.templates`, aby
    routy sdílely stejnou konfiguraci s globálními funkcemi (`get_csrf_token`,
    `initials`). Statické zdroje (přeložené CSS, self-hostované fonty a ikonový
    sprite) se servírují z `/static`, takže se rozhraní vykreslí i bez připojení
    k internetu (R13.9). Adresář musí existovat — v image ho plní build stupeň
    Tailwindu a kopie fontů.
    """
    app.state.templates = build_templates()
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


def _render_not_found(request: Request) -> Response:
    """Vykreslí stylovanou stránku 404 (design.md sekce 8, úkol 8.4).

    Minimální kontext — šablona `errors/404.html` dědí z `errors/error_layout`,
    který nepotřebuje přihlášenou osobu ani navigaci, takže se vykreslí i u
    nepřihlášeného požadavku. Bez stack trace a bez konfigurace.
    """
    templates = request.app.state.templates
    context = {
        "request": request,
        "app_name": request.app.state.settings.app_name,
    }
    return templates.TemplateResponse(
        request, "errors/404.html", context, status_code=404
    )


def _register_error_pages(app: FastAPI) -> None:
    """Zaregistruje stylovanou stránku 404 (úkol 8.4).

    Handler `AuthorizationError`/`CsrfError` (403) i `LoginRequired`
    (přesměrování) registrují moduly `auth`. Zde se dořeší 404: ať přijde z
    `load_application` (neexistující záznam, design.md sekce 8) nebo z neznámé
    cesty, vykreslí se stylovaná stránka. Ostatní stavy `HTTPException` se
    předají výchozímu handleru Starlette, aby se chování nestandardně neměnilo.
    """

    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> Response:
        if exc.status_code == 404:
            return _render_not_found(request)
        # Ostatní stavy (401, 405, …) předá výchozímu chování Starlette:
        # prostý text s odpovídajícím kódem a hlavičkami.
        return PlainTextResponse(
            exc.detail, status_code=exc.status_code, headers=exc.headers
        )

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)


def _register_routes(app: FastAPI) -> None:
    @app.get("/health", include_in_schema=False)
    def health() -> JSONResponse:
        """Zdravotní endpoint, dostupný bez přihlášení (R12.2).

        Neprozrazuje verze ani konfiguraci. Vrací pouze, zda je služba
        připravená obsluhovat požadavky.
        """
        database_ready = db_session.check_database()
        payload = {
            "status": "ok" if database_ready else "degraded",
            "database": "up" if database_ready else "down",
        }
        return JSONResponse(payload, status_code=200 if database_ready else 503)

    # Routy přihlášení a odhlášení (úkol 6.2). Chráněné obrazovky přijdou
    # v dalších úkolech; guardy a handler 403 jsou úkol 6.3.
    app.include_router(auth_router)
    # Tabulkový výpis registru `/registr` (úkol 11.2). Chráněný přihlášením;
    # obě role čtou celý registr (R2, capability matrix).
    app.include_router(registry_router)
    # Obrazovka „Moje aplikace" `/moje` (úkol 12.2), vstupní obrazovka po
    # přihlášení, a landing `GET /` → přesměrování na `/moje` (design.md 7).
    app.include_router(mine_router)
    # Výpis auditního logu `/audit` (úkol 17.1). Chráněný `require_read_audit`
    # — čte jen role Admin (R8.4).
    app.include_router(audit_router)
    # Správa uživatelů `/uzivatele` (úkol 17.2). Chráněná `require_manage_roles`
    # — spravovat role smí jen role Admin (R11.2).
    app.include_router(users_router)
    # Export CSV `/export/registr` a `/export/audit` (úkol 18.1). Chráněný
    # `require_export` — exportovat smí jen role Admin (R10.1, R10.2, R10.4).
    app.include_router(export_router)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Fabrika aplikace."""
    resolved = settings or load_settings()
    configure_logging(resolved.log_level)

    app = FastAPI(
        title=resolved.app_name,
        description=resolved.app_subtitle,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=_lifespan,
    )
    app.state.settings = resolved
    # OIDC klient se skládá jednou při startu z konfigurace; routy ho čtou
    # z `app.state`. Je vláknově bezpečný, takže ho může sdílet celá aplikace.
    app.state.oidc_client = build_oidc_client(resolved)

    _register_middleware(app)
    _register_web(app)
    _register_routes(app)
    # Guardy z auth/deps.py vyhazují LoginRequired a AuthorizationError; jejich
    # globální handlery (přesměrování na /login, resp. audit ACCESS_DENIED + 403)
    # se registrují zde, aby odepření žilo na jednom místě (design.md 4.3).
    register_auth_handlers(app)
    # CSRF ochrana formulářů (úkol 6.4): závislost `csrf_protect` na routách
    # vyhazuje CsrfError, jejíž handler vrací 403. Registruje se tady vedle
    # ostatních autorizačních handlerů, aby validace žila na jednom místě.
    register_csrf_handler(app)
    # Stylovaná stránka 404 (úkol 8.4). 403 a přesměrování na /login registrují
    # handlery výše; zde se dořeší nenalezené záznamy i neznámé cesty.
    _register_error_pages(app)

    return app


# Aplikace se záměrně nevytváří při importu modulu. Uvicorn ji spouští jako
# fabriku (`--factory regina.main:create_app`), takže import modulu nevyžaduje
# úplnou konfiguraci a testy si mohou vytvořit instanci s vlastním nastavením.
