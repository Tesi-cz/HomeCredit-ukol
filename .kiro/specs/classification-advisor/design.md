# Design — Klasifikační poradce a AI úprava popisu

## 1. Účel a hranice

Tento dokument popisuje **jak** se implementují požadavky z `requirements.md` této specifikace. Navazuje na `app-registry-core/design.md` a jeho zásadu závislostí: vrstvy míří dovnitř (`web → services → domain`, `db` stranou), balíček `domain` nemá externí závislosti.

Poradce je připojený modul. Přidává jednu novou vrstvu (`llm/`), rozšiřuje `services`, `db`, `web` a `config`, ale **nemění** jádro: jediným zapisovačem `applications.classification` zůstává `services/classification.py`. Když poradce vypneme (chybí API klíč), registr běží dál.

**Zásady, které drží celý návrh:**

1. **Jeden vstupní bod k modelu.** Veškerá komunikace s modelem prochází `llm/`. Nikde jinde (services, web) není `httpx` volání na model ani znalost jeho protokolu.
2. **Zaměnitelnost přes konfiguraci.** Výběr implementace (OpenRouter / Mock / firemní Gateway) je čtení proměnné prostředí, ne úprava kódu.
3. **Osobní údaje ven nejdou.** Anonymizace běží vždy před voláním, rehydratace po něm. Log volání nikdy nenese obsah.
4. **Fallback místo pádu.** Chybějící klíč, timeout nebo chyba modelu degradují na deterministický výsledek (poradce) nebo na nezávaznou chybu (přepis popisu). Request nikdy nespadne kvůli modelu.

---

## 2. Přehled vrstev

| Vrstva | Nové / rozšířené | Odpovědnost |
|---|---|---|
| `config.py` | rozšíření | Proměnné poradce (base URL, model, klíč, timeout, retence). Klíč nepovinný |
| `llm/` | **nová** | `LLMClient` protokol + `OpenRouterClient` + `MockClient`; datové typy volání; výběr implementace |
| `domain/` | rozšíření | `ClassificationSource` o `AI`, `AI_OVERRIDDEN`; katalog dotazníku a deterministické skóre (čisté funkce, bez závislostí) |
| `db/` | rozšíření | Alembic revize: tabulky `classification_suggestions`, `llm_call_log`; nullable `classification_log.suggestion_id`; výměna `CHECK` na `source` |
| `services/` | rozšíření | `anonymization.py`, `advisor.py` (poradce), `description_rewrite.py`, `llm_log.py`; napojení na existující `classification.py` a `retention.py` |
| `web/` | rozšíření | Wizard flow, AI panel s doporučením, tlačítko u popisu, admin výpis logů volání |
| `prompts/` | rozšíření | Prompt pro klasifikaci a pro přepis popisu |

---

## 3. Vrstva `llm/` — abstrakce volání modelu

### 3.1 Rozhraní

Jádro abstrakce je úzký protokol (duck typing přes `typing.Protocol`, jako `domain/rules.py`). Aplikace zná jen jej, ne konkrétní transport.

```
class LLMClient(Protocol):
    def complete(self, request: LLMRequest) -> LLMResponse: ...
```

- **`LLMRequest`** — systémový a uživatelský prompt, `operation` (`CLASSIFY` / `REWRITE`), volitelné parametry (teplota, max tokenů). **Text je už anonymizovaný** — anonymizaci řeší volající služba, ne klient.
- **`LLMResponse`** — text odpovědi, `model`, `tokens_in`, `tokens_out`, `latency_ms`, `status`. **Bez uchování promptu** za hranicí volání.

Rozhraní je záměrně jednotné pro generování textu i případný budoucí přepis řeči (R1.7): kdyby přibyla operace `TRANSCRIBE`, přidá se hodnota do `operation` a implementace ji obslouží, ale podpis `complete` se nemění.

### 3.2 Implementace

| Implementace | `gateway_impl` | Kdy se použije |
|---|---|---|
| `OpenRouterClient` | `OPENROUTER` | Je nakonfigurovaný `OPENROUTER_API_KEY` |
| `MockClient` | `MOCK` | Klíč chybí, nebo `LLM_PROVIDER=mock` |

- **`OpenRouterClient`** volá OpenRouter chat completions přes `httpx` s konfigurovaným timeoutem. Base URL, model a klíč jsou z konfigurace. Timeout, chybu sítě i non-2xx převádí na `LLMResponse` se `status=TIMEOUT`/`ERROR` (nevyhazuje ven neošetřenou výjimku — o degradaci rozhoduje služba).
- **`MockClient`** je deterministický, bez sítě. Pro `CLASSIFY` vrací zdůvodnění poskládané z deterministického skóre; pro `REWRITE` vrací lehce normalizovaný vstup. Umožňuje běh a testy bez klíče a slouží jako záložní režim (R1.5).

**Firemní AI Gateway** je třetí implementace téhož protokolu, nebo `OpenRouterClient` s jinou base URL — podle toho, jestli Gateway mluví OpenAI-kompatibilním protokolem. V obou případech je to konfigurace nebo přidání souboru, ne zásah do služeb (R1.3).

### 3.3 Výběr implementace

Tovární funkce `build_llm_client(settings) -> LLMClient` vrátí podle konfigurace `OpenRouterClient`, nebo `MockClient`. Volá se jednou při startu; služby dostávají klienta přes dependency injection (jako session), takže jsou testovatelné s podstrčeným mockem.

---

## 4. Deterministické skóre a katalog dotazníku (`domain/`)

Katalog otázek i výpočet skóre patří do `domain/` — jsou to čisté funkce bez závislosti na databázi, HTTP i modelu (testovatelné samostatně).

### 4.1 Šest dimenzí

| Dimension | Otázka (zkráceně) | Rozsah bodů |
|---|---|---|
| Počet uživatelů | Kolik lidí aplikaci používá | 1–3 |
| Citlivost dat | Nejcitlivější zpracovávaná data | 1–3 |
| Byznys kritičnost | Dopad výpadku na provoz | 1–3 |
| Integrační složitost | Počet napojených systémů | 1–3 |
| Regulatorní dopad | Spadá pod regulaci (GDPR, AML, ČNB, DORA) | 1–3 |
| Míra použití AI | Jak aplikace používá AI model | 1–3 |

Každá odpověď nese celočíselnou váhu. Součet je 6–18.

### 4.2 Mapa skóre na úroveň

Prahy jsou v `domain/` jako konstanty (jediný zdroj pravdy, aby model i fallback dávaly srovnatelný základ):

| Součet | Baseline Classification |
|---|---|
| 6–9 | `MALÁ` |
| 10–13 | `STŘEDNÍ` |
| 14–18 | `VELKÁ` |

Baseline je čistý součet vah — žádné speciální pojistky, aby bylo pravidlo triviálně obhajitelné a testovatelné.

`Questionnaire_Version` je konstanta v `domain/`; ukládá se s každým `Suggestion`, aby staré doporučení zůstalo interpretovatelné po změně katalogu (R2.6).

---

## 5. Služby (`services/`)

### 5.1 `anonymization.py`

Dvě čisté funkce nad textem (R5):

- `anonymize(text) -> (masked_text, mapping)` — nahradí jména, e-maily a telefony `Placeholder_Token`y (`[[JMENO_1]]`, `[[EMAIL_1]]`, `[[TEL_1]]`). Deterministické v rámci jednoho volání: stejná hodnota → stejný token (R5.5). Detekce e-mailu a telefonu regulárním výrazem, jména z adresáře `users` (přesná shoda na `display_name`) plus konzervativní heuristika.
- `rehydrate(text, mapping) -> text` — vrátí původní hodnoty na místo tokenů (R5.2).

Volají ji obě AI služby na vstupu i výstupu (R5.3). Anonymizace je **jediné místo**, kde se text připravuje pro model; klient `llm/` dostává už maskovaný text.

### 5.2 `advisor.py` — klasifikační poradce

Orchestruje jeden běh doporučení (R3):

1. Ověří, že jsou zodpovězené všechny otázky (R2.4).
2. Spočítá `Deterministic_Score` a baseline úroveň (`domain/`).
3. Anonymizuje volitelnou poznámku (R5.3).
4. Pokud je klient dostupný, sestaví `LLMRequest` (`operation=CLASSIFY`) s anonymizovanými odpověďmi a poznámkou, zavolá `llm/`, rehydratuje zdůvodnění, zaloguje volání (`llm_log.py`).
5. Sestaví `Suggestion`: navržená úroveň, zdůvodnění, skóre po dimenzích, zdroj (`OPENROUTER`/`MOCK`), odkaz na `llm_call_log`.
6. Při timeoutu/chybě/chybějícím klíči vrátí `Suggestion` z deterministického skóre a **označí ho jako fallback** (R3.4).

`advisor.py` **nezapisuje** klasifikaci. Jen vrací `Suggestion` a ukládá ho do `classification_suggestions`. Samotný zápis do registru dělá až přijetí návrhu ve webové vrstvě přes `classification.py` (viz 5.4).

### 5.3 `description_rewrite.py` — AI úprava popisu

Orchestruje přepis popisu (R4):

1. Odmítne prázdný popis českou hláškou (R4.4).
2. Anonymizuje text (R5.2, R5.3).
3. Sestaví `LLMRequest` (`operation=REWRITE`), zavolá `llm/`, rehydratuje výsledek, zaloguje volání.
4. Vrátí přepsaný text jako **návrh** — nikam ho neukládá (R4.6).
5. Při chybě vrátí nezávaznou chybu; původní popis zůstává (R4.5).

### 5.4 Napojení na jádrového zapisovače

Zápis klasifikace zůstává v `services/classification.py`. Poradce k němu přidá tenký vstupní bod, který respektuje existující podpis a invariant:

- **Přijetí návrhu beze změny úrovně** → `write_classification(..., source=AI, suggestion_id=...)`.
- **Přijetí s jinou úrovní** → `source=AI_OVERRIDDEN`.
- **Ruční volba (návrh ignorován)** → stávající `set_classification` (`source=HUMAN`).

`write_classification` dostane **nový nepovinný parametr** `suggestion_id` (odkaz do `classification_suggestions`); jeho existující chování a audit se nemění. Audit: `AI` i `AI_OVERRIDDEN` jsou „člověk zapsal" → `CLASSIFICATION_SET` (jádro už dnes odvozuje `CLASSIFICATION_OVERRIDDEN` jen od `ADMIN_OVERRIDE`, ostatní zdroje ošetřuje jako zápis). Autorizace (člen trojice / Admin) se vynucuje na backendu stejně jako dnes (R3.10).

### 5.5 `llm_log.py` — technický log volání

Zapíše řádek `llm_call_log` po každém volání (R6.1): `gateway_impl`, `model`, `operation`, `tokens_in/out`, `latency_ms`, `status`, `error_code` (kód, nikdy text chyby), `correlation_id`. **Nikdy obsah** (R6.2). Selhání volání = řádek se `status=ERROR/TIMEOUT` a záznam do aplikačního logu jako chyba, ne pád (R6.4).

---

## 6. Datový model (`db/`)

Rozšíření je čistě aditivní (jádro `database.md` sekce 9). Detaily v `database.md` této specifikace; zde přehled:

- **`classification_suggestions`** — doporučení: `suggested_classification`, `justification`, `questionnaire_version`, `questionnaire_answers` (jsonb), `llm_call_id` (FK, nullable u fallbacku), `application_id` (nullable — dotazník smí běžet před vznikem záznamu), `requested_by_user_id`, `created_at`.
- **`llm_call_log`** — technický záznam: `occurred_at`, `gateway_impl`, `model`, `operation`, `tokens_in/out`, `latency_ms`, `status`, `error_code`, `correlation_id`, `application_id` (nullable), `requested_by_user_id`. Bez obsahu.
- **`classification_log.suggestion_id`** — nový nullable FK na `classification_suggestions`. Prázdný, když poradce neběžel. Retence smí odkaz vynulovat, ne smazat řádek historie (R7.3): FK `ON DELETE SET NULL`.
- **`CHECK` na `classification_log.source`** — rozšíření povolených hodnot o `AI`, `AI_OVERRIDDEN` (výměna constraintu, existující řádky zůstávají platné).

Existující řádky mají `suggestion_id` prázdné a `source` v `HUMAN`/`ADMIN_OVERRIDE` — po rozšíření dál platné, žádná migrace dat.

---

## 7. Webová vrstva (`web/`)

### 7.1 Wizard poradce

Vícekrokový dotazník podle prototypu (`design/mocks/prototyp.html`, sekce „Klasifikační wizard"): jedna dimenze na krok, progress, dopředu/zpět (R2.1). Poslední krok má volitelnou poznámku a tlačítko „Navrhnout klasifikaci". Odeslání zavolá `advisor.py` a zobrazí **AI panel**: navržená úroveň, zdůvodnění, rozpad skóre po dimenzích (R3.3), a označení, jde-li o fallback (R3.4).

Panel nabídne: **Přijmout** (předvyplní úroveň, zdroj `AI`), **Přijmout s úpravou** (uživatel zvolí jinou úroveň, zdroj `AI_OVERRIDDEN`), **Zvolit ručně** (zdroj `HUMAN`). Zápis se provede až uložením přes standardní formulářový tok a jde přes `classification.py`.

Wizard je dostupný z formuláře a z detailu záznamu. Napojení respektuje existující formulář — pole klasifikace zůstává, wizard ho jen umí předvyplnit.

### 7.2 AI úprava popisu

Vedle pole „popis" ve formuláři tlačítko „AI úprava" (R4.1). Kliknutím se zavolá `description_rewrite.py`; výsledek se ukáže jako návrh s tlačítky **Použít** (nahradí obsah pole) a **Zahodit** (ponechá původní). Prázdný popis tlačítko deaktivuje (R4.4). Chyba modelu = nezávazná česká hláška, pole beze změny (R4.5).

### 7.3 Admin: výpis logů volání

Roli Admin přibude výpis `llm_call_log` (model, čas, tokeny, stav) — read-only, přístupný stejně jako Audit_Log (R6.3). Bez obsahu, protože ten se neukládá.

---

## 8. Konfigurace

Nové proměnné (všechny z prostředí, R8.1). Klíč **nepovinný** — bez něj běží Mock (R1.5, R8.3):

| Proměnná | Význam | Výchozí |
|---|---|---|
| `OPENROUTER_API_KEY` | Klíč k OpenRouteru. **Doplní uživatel do `.env`** | (prázdné → Mock) |
| `LLM_PROVIDER` | `openrouter` / `mock` | `openrouter` když je klíč, jinak `mock` |
| `LLM_BASE_URL` | Base URL poskytovatele (přepnutí na AI Gateway) | `https://openrouter.ai/api/v1` |
| `LLM_MODEL` | Identifikátor modelu | `deepseek/deepseek-v4-flash` |
| `LLM_TIMEOUT_SECONDS` | Timeout volání | `30` |
| `RETENTION_LLM_CALL_LOG_DAYS` | Retence logů volání | `90` |
| `RETENTION_SUGGESTION_DAYS` | Retence doporučení | `180` |

`.env.example` dostane všechny proměnné s bezpečnými placeholdery; `OPENROUTER_API_KEY=` prázdné s komentářem, kde klíč vzít. Reálný klíč jde jen do lokálního `.env` (v `.gitignore`), nikdy do repozitáře, image ani kódu (R8.2).

Model-ID `deepseek/deepseek-v4-flash` je **výchozí hodnota v konfiguraci**, ne v kódu — přesné ID revize (např. `-0731`) si reviewer ověří v účtu OpenRouter a případně přepíše přes `.env`.

---

## 9. Retence

Znovupoužije se mechanismus z `services/retention.py` (jednorázový běh při startu + interval). Přidají se dvě kategorie (R7.1, R7.2):

| Kategorie | Hranice od | Proměnná |
|---|---|---|
| Logy volání modelu | `occurred_at` | `RETENTION_LLM_CALL_LOG_DAYS` |
| Doporučení | `created_at` | `RETENTION_SUGGESTION_DAYS` |

Smazání doporučení nesmí utrhnout historii klasifikace: `classification_log.suggestion_id` je `ON DELETE SET NULL`, takže se odkaz vynuluje a řádek historie zůstává (R7.3). Log volání neobsahuje osobní údaje, přesto se maže — držíme jen to, co je potřeba pro přehled o nákladech.

---

## 10. Chování při výpadku modelu (shrnutí)

| Situace | Poradce | Přepis popisu |
|---|---|---|
| Chybí API klíč | Mock / deterministický návrh | Mock (lehká normalizace) nebo deaktivace s hláškou |
| Timeout | Deterministický fallback, označený | Nezávazná chyba, popis beze změny |
| Chyba providera (non-2xx) | Deterministický fallback, označený | Nezávazná chyba, popis beze změny |
| Vše OK | Návrh modelu + zdůvodnění | Přepsaný text jako návrh |

Ve všech řádcích se zapíše `llm_call_log` (u „chybí klíč" jako `MOCK`), request nikdy nespadne (R1.6).

---

## 11. Prompty

`prompts/` dostane dva klíčové prompty (R8.5):

- **klasifikace** — systémový prompt s definicí šesti dimenzí, škály MALÁ/STŘEDNÍ/VELKÁ a požadavkem na české zdůvodnění; uživatelský prompt jsou anonymizované odpovědi + poznámka.
- **přepis popisu** — systémový prompt „přepiš do jasnějšího firemního znění, zachovej význam, česky".

Prompty počítají s tím, že vstup je anonymizovaný (obsahuje placeholdery), a nesmí je „opravovat" zpět na jména.

---

## 12. Testy

Cíleně na místa, kde tvrdíme něco o bezpečnosti a integritě (zadání pokrytí nehodnotí):

- **Anonymizace/rehydratace** — jméno, e-mail, telefon zmizí před voláním a vrátí se po něm; deterministické mapování.
- **Fallback** — bez klíče a při vynucené chybě klienta poradce vrátí deterministický návrh a nespadne.
- **Log bez obsahu** — `llm_call_log` řádek nikdy nenese prompt ani odpověď.
- **Zdroje zápisu** — přijetí návrhu píše `AI`, úprava úrovně `AI_OVERRIDDEN`, ruční `HUMAN`; vše přes `classification.py`, invariant drží.
- **Deterministické skóre** — prahy a regulatorní pojistka.
