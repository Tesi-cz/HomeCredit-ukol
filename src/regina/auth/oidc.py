"""OIDC klient nezávislý na poskytovateli identity.

Celý modul stojí na jednom principu: **v kódu není žádná URL poskytovatele**.
Z konfigurace přichází jediná adresa — `OIDC_ISSUER`. Všechny ostatní
endpointy (authorization, token, jwks) se čtou z discovery dokumentu
poskytovatele (`.well-known/openid-configuration`), viz design.md sekce 4.4.

Díky tomu je záměna lokálního Dexu za Microsoft Entra ID výhradně změnou
konfigurace, ne přepisem kódu *(R1.5)*:

- adresu určuje `OIDC_ISSUER`,
- názvy claimů pro e-mail, jméno a roli určují `OIDC_EMAIL_CLAIM`,
  `OIDC_NAME_CLAIM`, `OIDC_ROLE_CLAIM` a `OIDC_ADMIN_ROLE_VALUE`.

Entra pojmenovává claim s rolemi jinak než Dex; kdyby byl název zadrátovaný
v kódu, byla by výměna přepis. Proto se čtou z nastavení.

Modul záměrně **neřeší HTTP routy ani session** — to je úkol 6.2. Zde je jen
klient, který routy volají: sestavení přesměrování na přihlášení, výměna kódu
za tokeny a ověření ID tokenu (podpis, issuer, audience, expirace) s odvozením
jména, e-mailu a role.

Access ani refresh token se nikam neukládají *(design.md 4.2)*. Nepotřebujeme
mluvit s žádným API poskytovatele — jakmile z ID tokenu odvodíme identitu,
tokeny zahazujeme.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx
from authlib.integrations.httpx_client import OAuth2Client
from authlib.jose import JsonWebToken
from authlib.jose.errors import JoseError

from regina.config import Settings
from regina.domain.enums import Role
from regina.logging import get_logger

logger = get_logger(__name__)

# Podporované podpisové algoritmy ID tokenu. Uzavřený seznam je bezpečnostní
# opatření: brání útoku záměnou algoritmu (např. na `none`). Poskytovatelé
# OIDC běžně podepisují RSA nebo EC klíči.
_ALLOWED_ID_TOKEN_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]

# Discovery dokument a JWKS se mění zřídka. Držíme je v paměti po tuto dobu,
# ať se každé přihlášení neroztahuje o dvě volání na poskytovatele.
_DISCOVERY_TTL_SECONDS = 300


class OidcError(RuntimeError):
    """Selhání při komunikaci s poskytovatelem identity nebo ověření tokenu."""


@dataclass(frozen=True)
class AuthenticatedIdentity:
    """Identita odvozená z ověřeného ID tokenu.

    Obsahuje jen to, co potřebuje párování osoby a session *(design.md 4.2)*:
    subject, jméno, e-mail a roli. Žádné tokeny.
    """

    subject: str
    name: str
    email: str
    role: Role
    raw_role_claim: tuple[str, ...]


class OidcClient:
    """Klient nad Authlib, nezávislý na konkrétním poskytovateli.

    Instance se skládá jednou při startu aplikace z `Settings`. Je vláknově
    bezpečná: cache discovery dokumentu a JWKS je chráněná zámkem, takže ji
    může sdílet celá aplikace.
    """

    def __init__(self, settings: Settings, *, http_timeout_seconds: float = 10.0) -> None:
        self._issuer = settings.oidc_issuer
        self._discovery_url = settings.oidc_discovery_url
        self._client_id = settings.oidc_client_id
        self._client_secret = settings.oidc_client_secret
        self._redirect_uri = settings.oidc_redirect_uri
        self._scope = " ".join(settings.oidc_scope_list)

        self._email_claim = settings.oidc_email_claim
        self._name_claim = settings.oidc_name_claim
        self._role_claim = settings.oidc_role_claim
        self._admin_role_value = settings.oidc_admin_role_value

        self._http_timeout_seconds = http_timeout_seconds
        self._jwt = JsonWebToken(_ALLOWED_ID_TOKEN_ALGORITHMS)

        # Cache discovery dokumentu a JWKS. Naplní se líně při prvním použití.
        self._lock = threading.Lock()
        self._metadata: dict[str, Any] | None = None
        self._jwks: dict[str, Any] | None = None
        self._metadata_loaded_at = 0.0

    # -- Veřejné API, které volá úkol 6.2 --------------------------------

    def create_authorization_redirect(
        self, *, state: str, nonce: str
    ) -> str:
        """Sestaví URL pro přesměrování na přihlašovací obrazovku poskytovatele.

        Authorization endpoint pochází výhradně z discovery dokumentu, nikdy
        z kódu. `state` chrání proti CSRF na callbacku, `nonce` váže ID token
        na tento konkrétní přihlašovací pokus.

        Routa 6.2 si `state` a `nonce` uloží do dočasného stavu (podepsaná
        cookie) a při návratu je ověří.
        """
        metadata = self._get_metadata()
        authorization_endpoint = self._require_endpoint(metadata, "authorization_endpoint")

        with self._new_oauth_client() as oauth:
            url, _ = oauth.create_authorization_url(
                authorization_endpoint,
                state=state,
                nonce=nonce,
            )
        return url

    def fetch_identity(
        self, *, authorization_response_url: str, state: str, nonce: str
    ) -> AuthenticatedIdentity:
        """Vymění autorizační kód za tokeny a vrátí ověřenou identitu.

        Kroky odpovídají design.md sekce 4.2:

        1. výměna kódu za tokeny na token endpointu z discovery,
        2. ověření ID tokenu — podpis proti JWKS, issuer, audience, expirace
           a shoda `nonce`,
        3. odvození jména, e-mailu a role z konfigurovatelných claimů.

        Access ani refresh token se nevrací — po odvození identity je
        zahazujeme.

        `authorization_response_url` je celá návratová URL callbacku včetně
        `code` a `state`. `state` a `nonce` jsou hodnoty uložené při zahájení
        přihlášení.
        """
        metadata = self._get_metadata()
        token_endpoint = self._require_endpoint(metadata, "token_endpoint")

        try:
            with self._new_oauth_client(state=state) as oauth:
                token = oauth.fetch_token(
                    token_endpoint,
                    authorization_response=authorization_response_url,
                )
        except httpx.HTTPError as error:
            raise OidcError("Výměna autorizačního kódu za token selhala.") from error
        except Exception as error:  # noqa: BLE001 — Authlib hlásí různé typy
            raise OidcError("Výměna autorizačního kódu za token selhala.") from error

        id_token = token.get("id_token")
        if not id_token:
            raise OidcError("Odpověď poskytovatele neobsahuje ID token.")

        claims = self._validate_id_token(id_token, nonce=nonce, metadata=metadata)
        return self._derive_identity(claims)

    # -- Ověření ID tokenu -----------------------------------------------

    def _validate_id_token(
        self, id_token: str, *, nonce: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """Ověří podpis, issuer, audience, expiraci a nonce ID tokenu."""
        jwks = self._get_jwks(metadata)

        claims_options = {
            "iss": {"essential": True, "value": self._issuer},
            "aud": {"essential": True, "value": self._client_id},
            "exp": {"essential": True},
        }

        try:
            claims = self._jwt.decode(
                id_token,
                key=jwks,
                claims_options=claims_options,
            )
            # Ověří expiraci (`exp`), `iss` a `aud` proti očekávaným hodnotám.
            # Podpis se ověřuje už v `decode` proti JWKS.
            claims.validate()
        except JoseError as error:
            raise OidcError("ID token neprošel ověřením.") from error

        # `nonce` váže ID token na tento konkrétní přihlašovací pokus a brání
        # jeho přehrání. Ověřujeme ho explicitně: musí přesně odpovídat hodnotě
        # vygenerované při zahájení přihlášení.
        if claims.get("nonce") != nonce:
            raise OidcError("ID token neprošel ověřením: nonce nesouhlasí.")

        return dict(claims)

    def _derive_identity(self, claims: dict[str, Any]) -> AuthenticatedIdentity:
        """Z claimů odvodí subject, jméno, e-mail a roli.

        Názvy claimů pro e-mail, jméno a roli jsou konfigurovatelné, takže
        se poskytovatel mění bez zásahu do kódu *(R1.4, R1.5)*.
        """
        subject = claims.get("sub")
        if not subject:
            raise OidcError("ID token neobsahuje subject (claim `sub`).")

        email = claims.get(self._email_claim) or ""
        name = claims.get(self._name_claim) or email or subject

        role_values = self._extract_role_values(claims.get(self._role_claim))
        role = (
            Role.ADMIN
            if self._admin_role_value in role_values
            else Role.USER
        )

        return AuthenticatedIdentity(
            subject=str(subject),
            name=str(name),
            email=str(email),
            role=role,
            raw_role_claim=role_values,
        )

    @staticmethod
    def _extract_role_values(raw: Any) -> tuple[str, ...]:
        """Normalizuje claim s rolemi na n-tici řetězců.

        Poskytovatelé posílají role různě: Dex jako pole ve `groups`, Entra
        jako pole ve `roles`, jiní jako jeden řetězec. Snášíme obě podoby.
        """
        if raw is None:
            return ()
        if isinstance(raw, str):
            return (raw,)
        if isinstance(raw, (list, tuple)):
            return tuple(str(item) for item in raw)
        return (str(raw),)

    # -- Discovery a JWKS s cache ----------------------------------------

    def _get_metadata(self) -> dict[str, Any]:
        """Vrátí discovery dokument poskytovatele, s krátkou cache."""
        with self._lock:
            fresh = (
                self._metadata is not None
                and (time.monotonic() - self._metadata_loaded_at) < _DISCOVERY_TTL_SECONDS
            )
            if fresh:
                return self._metadata  # type: ignore[return-value]

            metadata = self._load_discovery_document()
            self._validate_issuer(metadata)
            self._metadata = metadata
            self._jwks = None  # JWKS znovu podle nového jwks_uri
            self._metadata_loaded_at = time.monotonic()
            return metadata

    def _get_jwks(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Vrátí sadu veřejných klíčů poskytovatele, s cache."""
        with self._lock:
            if self._jwks is not None:
                return self._jwks
            jwks_uri = self._require_endpoint(metadata, "jwks_uri")
            self._jwks = self._load_json(jwks_uri, "JWKS")
            return self._jwks

    def _load_discovery_document(self) -> dict[str, Any]:
        return self._load_json(self._discovery_url, "discovery dokument")

    def _load_json(self, url: str, what: str) -> dict[str, Any]:
        try:
            response = httpx.get(url, timeout=self._http_timeout_seconds)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as error:
            raise OidcError(
                f"Nepodařilo se načíst {what} od poskytovatele identity."
            ) from error

    def _validate_issuer(self, metadata: dict[str, Any]) -> None:
        """Ověří, že issuer v discovery odpovídá konfiguraci.

        Rozpor by znamenal, že by ID tokeny neprošly kontrolou `iss`. Chytit
        to při načtení discovery je srozumitelnější než záhadné selhání
        ověření tokenu.
        """
        declared = metadata.get("issuer")
        if declared is not None and declared.rstrip("/") != self._issuer:
            raise OidcError(
                "Issuer v discovery dokumentu neodpovídá konfiguraci "
                "OIDC_ISSUER."
            )

    @staticmethod
    def _require_endpoint(metadata: dict[str, Any], key: str) -> str:
        value = metadata.get(key)
        if not value:
            raise OidcError(
                f"Discovery dokument poskytovatele neobsahuje `{key}`."
            )
        return str(value)

    # -- Pomocné ----------------------------------------------------------

    def _new_oauth_client(self, *, state: str | None = None) -> OAuth2Client:
        """Sestaví Authlib OAuth2 klient s parametry z konfigurace.

        Klient nedrží žádnou URL — endpointy se předávají explicitně z discovery
        v místě volání.
        """
        return OAuth2Client(
            client_id=self._client_id,
            client_secret=self._client_secret,
            scope=self._scope,
            redirect_uri=self._redirect_uri,
            state=state,
            code_challenge_method=None,
            timeout=self._http_timeout_seconds,
        )


def build_oidc_client(settings: Settings) -> OidcClient:
    """Sestaví klient pro běh aplikace.

    Samostatná fabrika kvůli složení v `main.py` a kvůli testovatelnosti:
    test si vytvoří klient nad vlastním `Settings` mířícím na testovací
    discovery.
    """
    logger.info(
        "oidc_client_ready",
        extra={"issuer_configured": bool(settings.oidc_issuer)},
    )
    return OidcClient(settings)
