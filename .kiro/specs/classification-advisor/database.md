# Návrh databáze — Klasifikační poradce

## Účel

Datový model pro `requirements.md` a `design.md` této specifikace. Navazuje **aditivně** na `app-registry-core/database.md` sekci 9: dvě nové tabulky, jeden nový nullable sloupec, výměna jednoho `CHECK` constraintu. Žádný existující sloupec nemění význam, žádná data se nemigrují.

**Není v rozsahu:** volba ORM (převzatá z jádra — SQLAlchemy), migrační nástroj (Alembic), konkrétní SQL DDL.

---

## 1. Co přibývá

| Změna | Typ | Vazba na požadavek |
|---|---|---|
| Tabulka `classification_suggestions` | nová tabulka | R3.9 |
| Tabulka `llm_call_log` | nová tabulka | R6.1, R6.2 |
| Sloupec `classification_log.suggestion_id` | nullable FK | R3.9, R7.3 |
| Výčet `classification_log.source` o `AI`, `AI_OVERRIDDEN` | výměna `CHECK` | R3.5, R3.6 |

---

## 2. `classification_suggestions` — doporučení a jeho zdůvodnění

**K čemu je.** Uchovává jedno doporučení poradce: co navrhl, proč, z jakých odpovědí a z jakého volání vzniklo. Detail záznamu z něj ukáže, že klasifikace pochází z návrhu modelu (R3.9).

| Sloupec | Typ | Poznámka |
|---|---|---|
| `id` | bigint PK | |
| `application_id` | uuid FK → `applications` | nullable — dotazník smí běžet před vznikem záznamu |
| `suggested_classification` | text | co poradce navrhl (`MALÁ`/`STŘEDNÍ`/`VELKÁ` jako strojový kód) |
| `justification` | text | zdůvodnění v češtině (`Suggestion_Rationale`) |
| `questionnaire_version` | text | verze katalogu otázek (R2.6) |
| `questionnaire_answers` | jsonb | odpovědi a jejich skóre po dimenzích |
| `deterministic_score` | smallint | součet skóre (6–18), pro transparentnost panelu |
| `is_fallback` | boolean | `true` = návrh z deterministického fallbacku, ne z modelu (R3.4) |
| `llm_call_id` | bigint FK → `llm_call_log` | nullable — prázdné u fallbacku bez volání |
| `requested_by_user_id` | uuid FK → `users` | kdo si doporučení vyžádal |
| `created_at` | timestamptz | server default `now()` |

**Bez obsahu promptu.** Ukládají se odpovědi dotazníku (uzavřené volby a skóre) a výsledné zdůvodnění — ne prompt poslaný modelu ani volná poznámka uživatele (ta je osobní vstup, R6.2). `questionnaire_answers` nese jen výběry z uzavřené nabídky, žádný volný text.

---

## 3. `llm_call_log` — technický záznam volání

**K čemu je.** Přehled o volání modelu pro provoz a náklady (R6.1). **Nikdy obsah** (R6.2).

| Sloupec | Typ | Poznámka |
|---|---|---|
| `id` | bigint PK | |
| `occurred_at` | timestamptz | vždy UTC, server default `now()` |
| `application_id` | uuid FK → `applications` | nullable — volání bez záznamu |
| `requested_by_user_id` | uuid FK → `users` | nullable |
| `gateway_impl` | text | `OPENROUTER`, `MOCK` nebo `AI_GATEWAY` |
| `model` | text | identifikátor modelu |
| `operation` | text | `CLASSIFY` nebo `REWRITE` |
| `tokens_in` | int | nullable u mocku |
| `tokens_out` | int | nullable u mocku |
| `latency_ms` | int | |
| `status` | text | `SUCCESS`, `TIMEOUT` nebo `ERROR` |
| `error_code` | text | kód chyby, **nikdy text chyby** |
| `correlation_id` | text | spojení s aplikačním logem |

**Co tu záměrně není.** Žádný sloupec pro prompt, odpověď, poznámku dotazníku ani přepis. Absence sloupce je silnější garance než pravidlo v kódu (R6.2). Osobní údaje se sem nedostanou ani nepřímo.

---

## 4. `classification_log.suggestion_id` — vazba na doporučení

Nový **nullable** sloupec `bigint FK → classification_suggestions` s `ON DELETE SET NULL`.

- Prázdný, když klasifikaci zapsal člověk bez poradce (`source = HUMAN` bez wizardu) nebo Admin přepisem (`ADMIN_OVERRIDE`).
- Vyplněný, když zápis vznikl přijetím návrhu (`AI`, `AI_OVERRIDDEN`).

**`ON DELETE SET NULL`, ne CASCADE** (R7.3). Retence smí smazat staré doporučení, ale historie klasifikace je nemazatelná. Smazání doporučení proto jen **vynuluje odkaz**, řádek `classification_log` zůstává. Historie tak přežije úklid doporučení.

---

## 5. Výměna `CHECK` na `classification_log.source`

Jádro má `source` jako `text` s `CHECK` povolujícím `HUMAN` a `ADMIN_OVERRIDE`, formulovaným jako **rozšiřitelný výčet** (jádro `database.md` sekce 9). Migrace poradce constraint vymění za povolení čtyř hodnot: `HUMAN`, `AI`, `AI_OVERRIDDEN`, `ADMIN_OVERRIDE`.

Existující řádky nesou `HUMAN` nebo `ADMIN_OVERRIDE` → po výměně dál platné. Žádná migrace dat.

**Matice zdrojů** (převzato z `app-registry/database.md`):

| Postup uživatele | `source` | `suggestion_id` |
|---|---|---|
| Vyplní úroveň sám, bez wizardu | `HUMAN` | prázdné |
| Nechá si doporučit a přijme beze změny | `AI` | vyplněné |
| Nechá si doporučit a zvolí jinou úroveň | `AI_OVERRIDDEN` | vyplněné |
| Admin přepíše cizí záznam s důvodem | `ADMIN_OVERRIDE` | prázdné |

---

## 6. Migrace

Jedna Alembic revize navazující na hlavu jádra:

1. `create table classification_suggestions` (FK na `applications`, `users`, `llm_call_log`).
2. `create table llm_call_log` (FK na `applications`, `users`).
3. `add column classification_log.suggestion_id` (nullable, FK `ON DELETE SET NULL`).
4. `drop` starý `CHECK` na `source`, `create` nový se čtyřmi hodnotami.

`downgrade` je zrcadlově opačný. Protože je vše aditivní, `upgrade` na existující databázi jádra proběhne bez dotyku dat.

---

## 7. Retence dat poradce

| Tabulka | Hranice od | Proměnná | Kaskáda |
|---|---|---|---|
| `llm_call_log` | `occurred_at` | `RETENTION_LLM_CALL_LOG_DAYS` | `classification_suggestions.llm_call_id` → `SET NULL` |
| `classification_suggestions` | `created_at` | `RETENTION_SUGGESTION_DAYS` | `classification_log.suggestion_id` → `SET NULL` |

Obě mazání znovupoužijí rutinu z `services/retention.py`. `SET NULL` na obou vazbách zajistí, že úklid technických dat nikdy neutrhne historii klasifikace ani nespadne na cizím klíči (R7.3).
