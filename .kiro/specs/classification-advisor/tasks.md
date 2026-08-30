# Implementation Plan

Klasifikační poradce a AI úprava popisu

## Overview

Aditivní nadstavba nad jádrem (`app-registry-core`). Přidává vrstvu `llm/`, rozšiřuje `domain`, `db`, `services`, `web` a `config`. Jádro se nemění: jediným zapisovačem `applications.classification` zůstává `services/classification.py`, který dostane jen nepovinný parametr `suggestion_id`.

**Pořadí je záměrné.** Nejdřív konfigurace a abstrakce (bez nich nic nevolá model), pak doména (čisté funkce skóre — testovatelné hned), pak databáze, pak služby jako svislé řezy, teprve nakonec obrazovky. Anonymizace je před první službou, která volá model, protože žádné volání nesmí jít ven bez ní.

**Průběžné pravidlo.** Po každém úseku musí `docker compose up` naběhnout a `/health` odpovídat. Aplikace musí nabíhat **i bez** `OPENROUTER_API_KEY` (mock režim). Rozbitý stav se nepředává dál.

**Klíč doplní uživatel.** Žádný úkol nezapisuje reálný API klíč. Klíč jde jen do lokálního `.env` (v `.gitignore`); `.env.example` nese prázdný placeholder.

Úkoly označené `*` jsou testy. Pokrytí se nehodnotí; testy 6.x a 3.x jsou důkazy bezpečnostních tvrzení (anonymizace, log bez obsahu, fallback) — doporučuji je neškrtat.

## Tasks

- [ ] 1. Konfigurace a abstrakce modelu
  - [ ] 1.1 Rozšířit `config.py` o proměnné poradce: `OPENROUTER_API_KEY` (nepovinné), `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL` (default `deepseek/deepseek-v4-flash`), `LLM_TIMEOUT_SECONDS`, `RETENTION_LLM_CALL_LOG_DAYS`, `RETENTION_SUGGESTION_DAYS`
    - Chybějící klíč **nesmí** shodit start; jen přepne default `LLM_PROVIDER` na `mock`
    - _Requirements: 1.4, 1.5, 8.1, 8.3_

  - [ ] 1.2 Doplnit `.env.example` o všechny proměnné poradce s bezpečnými placeholdery; `OPENROUTER_API_KEY=` prázdné s komentářem, kde klíč vzít a že patří jen do `.env`
    - Ověřit, že `.env` je v `.gitignore` a žádný klíč není v repu
    - _Requirements: 8.2, 8.4_

  - [ ] 1.3 Vytvořit balíček `llm/`: datové typy `LLMRequest`, `LLMResponse` a protokol `LLMClient` (`complete(request) -> response`)
    - Rozhraní jednotné pro `CLASSIFY` i `REWRITE` a připravené na budoucí `TRANSCRIBE` bez změny podpisu
    - _Requirements: 1.1, 1.7_

  - [ ] 1.4 Napsat `MockClient`: deterministický, bez sítě; `CLASSIFY` vrací zdůvodnění ze skóre, `REWRITE` normalizovaný vstup
    - _Requirements: 1.2, 1.5_

  - [ ] 1.5 Napsat `OpenRouterClient` přes `httpx` s timeoutem; base URL, model, klíč z konfigurace; timeout a non-2xx převádí na `LLMResponse` se `status=TIMEOUT`/`ERROR`, nevyhazuje ven
    - Přidat `httpx` do `requirements.txt` s připnutou verzí (pokud tam ještě není)
    - _Requirements: 1.2, 1.3, 1.6_

  - [ ] 1.6 Napsat továrnu `build_llm_client(settings)`: podle konfigurace vrátí `OpenRouterClient`, nebo `MockClient`; napojit do DI vedle session
    - _Requirements: 1.3, 1.5_

- [ ] 2. Doména — dotazník a deterministické skóre
  - [ ] 2.1 Přidat do `domain/enums.py` hodnoty `Classification_Source.AI` a `AI_OVERRIDDEN`; doplnit popisky v `domain/labels.py`
    - _Requirements: 3.5, 3.6_

  - [ ] 2.2 Vytvořit katalog dotazníku v `domain/`: šest dimenzí, otázky, uzavřené odpovědi s vahami, `Questionnaire_Version` jako konstanta; české popisky přes `labels.py`
    - _Requirements: 2.2, 2.3, 2.6, 2.7_

  - [ ] 2.3 Napsat čistou funkci skóre: součet vah → baseline úroveň (prahy 6–9 / 10–13 / 14–18), bez speciálních pojistek
    - _Requirements: 3.1_

  - [ ] 2.4* Testy skóre: prahy na hranicích bez modelu
    - _Requirements: 3.1_

- [ ] 3. Anonymizace
  - [ ] 3.1 Napsat `services/anonymization.py`: `anonymize(text) -> (masked, mapping)` a `rehydrate(text, mapping)`; e-mail a telefon regexem, jména z adresáře `users` + konzervativní heuristika; deterministické mapování v rámci volání
    - _Requirements: 5.1, 5.2, 5.5_

  - [ ] 3.2* Test anonymizace: jméno, e-mail, telefon zmizí z maskovaného textu a vrátí se rehydratací; stejná hodnota → stejný token
    - _Requirements: 5.1, 5.2, 5.5_

- [ ] 4. Databáze — dvě tabulky, vazba, výměna CHECK
  - [ ] 4.1 Přidat ORM modely `classification_suggestions` a `llm_call_log` (`db/models/`) podle `database.md` sekce 2 a 3; `llm_call_log` **bez** sloupce pro obsah
    - _Requirements: 3.9, 6.1, 6.2_

  - [ ] 4.2 Přidat nullable `classification_log.suggestion_id` (FK `ON DELETE SET NULL`)
    - _Requirements: 3.9, 7.3_

  - [ ] 4.3 Napsat Alembic revizi navazující na hlavu jádra: dvě tabulky, nový sloupec, výměna `CHECK` na `source` za čtyři hodnoty (`HUMAN`, `AI`, `AI_OVERRIDDEN`, `ADMIN_OVERRIDE`); `downgrade` zrcadlově
    - Ověřit `upgrade`/`downgrade` na kopii databáze jádra bez dotyku dat
    - _Requirements: 3.5, 3.6, 7.3_

- [ ] 5. Služby — log volání, poradce, přepis popisu
  - [ ] 5.1 Napsat `services/llm_log.py`: zapíše řádek `llm_call_log` po každém volání (`gateway_impl`, `model`, `operation`, tokeny, `latency_ms`, `status`, `error_code`, `correlation_id`); nikdy obsah
    - _Requirements: 6.1, 6.2, 6.4_

  - [ ] 5.2 Napsat `services/advisor.py`: ověří kompletnost odpovědí, spočítá skóre, anonymizuje poznámku, zavolá `llm/` (je-li klient), rehydratuje zdůvodnění, zaloguje volání, uloží `classification_suggestions`; při chybě/timeoutu/bez klíče vrátí fallback označený `is_fallback`
    - Nezapisuje klasifikaci — jen vrací `Suggestion`
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ] 5.3 Rozšířit `services/classification.py`: `write_classification` dostane nepovinný `suggestion_id`; přidat vstupní body pro přijetí návrhu (`source=AI`) a přijetí s úpravou (`source=AI_OVERRIDDEN`)
    - Existující chování, invariant a audit se nemění; `AI`/`AI_OVERRIDDEN` se audituje jako `CLASSIFICATION_SET`
    - _Requirements: 3.5, 3.6, 3.7, 3.8_

  - [ ] 5.4 Napsat `services/description_rewrite.py`: odmítne prázdný popis, anonymizuje, zavolá `llm/` (`REWRITE`), rehydratuje, zaloguje; vrátí návrh (neukládá); chyba = nezávazná hláška
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ] 5.5* Testy zdrojů a fallbacku: přijetí návrhu píše `AI`, úprava `AI_OVERRIDDEN`, ruční `HUMAN` — vše přes `classification.py`; bez klíče poradce vrátí fallback a nespadne
    - _Requirements: 3.4, 3.5, 3.6, 3.7_

  - [ ] 5.6* Test logu bez obsahu: řádek `llm_call_log` nikdy nenese prompt ani odpověď
    - _Requirements: 6.2_

- [ ] 6. Web — wizard, AI panel, tlačítko u popisu, admin výpis
  - [ ] 6.1 Přidat routu a šablony wizardu podle prototypu: krok na dimenzi, progress, dopředu/zpět, volitelná poznámka, tlačítko „Navrhnout klasifikaci"
    - Vše česky přes `labels.py`; kompletnost odpovědí vynucena před vyžádáním návrhu
    - _Requirements: 2.1, 2.4, 2.5, 2.7_

  - [ ] 6.2 AI panel s doporučením: navržená úroveň, zdůvodnění, rozpad skóre po dimenzích, označení fallbacku; akce Přijmout / Přijmout s úpravou / Zvolit ručně
    - Zápis až přes standardní formulářový tok a `classification.py`; autorizace (člen trojice / Admin) na backendu
    - _Requirements: 3.3, 3.4, 3.5, 3.6, 3.7, 3.10_

  - [ ] 6.3 Tlačítko „AI úprava" u pole popis: zavolá přepis, výsledek jako návrh s Použít / Zahodit; prázdný popis tlačítko deaktivuje; chyba = česká nezávazná hláška, pole beze změny
    - _Requirements: 4.1, 4.3, 4.4, 4.5_

  - [ ] 6.4 Admin výpis `llm_call_log` (model, čas, tokeny, stav), read-only, přístup jako Audit_Log
    - _Requirements: 6.3_

- [ ] 7. Retence a prompty
  - [ ] 7.1 Rozšířit `services/retention.py` o dvě kategorie: `llm_call_log` (od `occurred_at`) a `classification_suggestions` (od `created_at`); `SET NULL` na obou vazbách chrání historii
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ] 7.2 Přidat do `prompts/` prompt pro klasifikaci (šest dimenzí, škála, české zdůvodnění, počítá s anonymizovaným vstupem) a pro přepis popisu
    - _Requirements: 8.5_

  - [ ] 7.3 Doplnit README: výchozí model a verze, retenční lhůty poradce, důvod neimplementace MFA (řeší IdP), vědomý dluh; Master Prompt
    - _Requirements: 7.1, 8.4, 8.5_

- [ ] 8. Kontrolní bod — poradce běží
  - `docker compose up` naběhne **bez** `OPENROUTER_API_KEY` a poradce funguje v mock režimu.
  - Po doplnění klíče do `.env` vrací poradce návrh od DeepSeeku se zdůvodněním; přepis popisu funguje.
  - `llm_call_log` se plní, neobsahuje obsah; přijetí návrhu zapisuje `AI`/`AI_OVERRIDDEN` přes `classification.py`.
