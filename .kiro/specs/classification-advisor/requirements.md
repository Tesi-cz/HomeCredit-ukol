# Requirements Document

Klasifikační poradce a AI úprava popisu — navazující specifikace

## Introduction

Tato specifikace doplňuje jádro evidence (`app-registry-core`) o **jazykový model**. Přidává dvě funkce, které sdílejí stejnou abstrakční vrstvu pro volání modelu, stejnou anonymizaci osobních údajů a stejný technický log volání:

1. **Klasifikační poradce** — vícekrokový dotazník (wizard). Uživatel odpoví na sadu otázek o aplikaci; systém z odpovědí navrhne Classification (`MALÁ` / `STŘEDNÍ` / `VELKÁ`) a **zdůvodní ji** lidsky čitelným textem. Uživatel návrh přijme beze změny, přijme s úpravou úrovně, nebo ho ignoruje a zvolí ručně.
2. **AI úprava popisu** — tlačítko u pole „popis" ve formuláři záznamu. Systém přepíše zadaný popis do kultivovanějšího, jasnějšího znění; uživatel výsledek přijme nebo zahodí.

Obě funkce volají model **výhradně přes vlastní abstrakční vrstvu**, nikdy přímo z aplikačního nebo webového kódu. Abstrakce je zaměnitelná za firemní AI Gateway pouhou změnou konfigurace. Osobní údaje se před odesláním modelu anonymizují a po zpracování vracejí zpět. O každém volání se ukládá technický záznam (model, čas, tokeny) **bez obsahu promptu i odpovědi**.

Tato specifikace **nemění** invariant jádra: jediným zapisovačem `applications.classification` zůstává `services/classification.py`. Poradce k němu jen přidává nové zdroje zápisu (`AI`, `AI_OVERRIDDEN`) a nepovinnou vazbu na uložené doporučení.

## Vztah k ostatním specifikacím

| Specifikace | Role |
|---|---|
| `app-registry-core` | Jádro evidence. Klasifikaci zadává člověk, model nevystupuje. Navrženo tak, aby ho tato specifikace doplnila **aditivně** (viz jeho `database.md` sekce 9) |
| `app-registry` | Archiv návrhových úvah. Sekce 1 jeho `database.md` obsahuje původní model poradce (tabulky, matice zdrojů), ze kterého tato specifikace vychází |
| `classification-advisor` | **Tento dokument.** Doplňuje jazykový model: poradce, AI úpravu popisu, abstrakční vrstvu, anonymizaci, log volání a jeho retenci |

**Aditivnost je závazná.** Žádný existující sloupec nemění význam, žádná data se nemigrují, jádro funguje i s vypnutým poradcem. Když není nakonfigurovaný přístup k modelu, registr běží dál a klasifikaci i popis lze zadat ručně — funkce poradce se jen slušně vypnou nebo přepnou na deterministický záložní režim.

## Rozsah tohoto dokumentu

Popisuje **co** poradce dělá a **jaká pravidla platí**. Neobsahuje volbu konkrétního frameworku, HTTP kontrakty ani strukturu souborů — to řeší `design.md`. Datový model doplňuje `database.md` této specifikace (navazuje na sekci 9 jádra).

## Glossary

### Poradce a dotazník

- **Advisor**: Souhrnný název pro funkci klasifikačního poradce — dotazník, vyžádání doporučení modelu a jeho zobrazení
- **Questionnaire**: Uspořádaná sada otázek (Question), na které uživatel odpovídá ve wizardu. Má verzi (Questionnaire_Version), aby uložené doporučení odkazovalo na katalog, podle kterého vzniklo
- **Question**: Jedna otázka dotazníku s uzavřenou nabídkou odpovědí. Patří do jedné Dimension
- **Dimension**: Osa hodnocení, kterou otázka měří. Šest dimenzí: počet uživatelů, citlivost dat, byznys kritičnost, integrační složitost, regulatorní dopad, míra použití AI
- **Deterministic_Score**: Číselné skóre spočítané z odpovědí bez modelu. Slouží jako záložní návrh a jako obhajitelná kostra, se kterou se porovnává návrh modelu
- **Suggestion**: Doporučená Classification s textovým zdůvodněním, vzniklá z odpovědí dotazníku. Nese svůj zdroj (model, nebo deterministický fallback), skóre po dimenzích a odkaz na volání modelu, pokud proběhlo
- **Suggestion_Rationale**: Lidsky čitelné zdůvodnění doporučené úrovně v češtině

### Jazykový model a jeho volání

- **LLM_Provider**: Poskytovatel jazykového modelu za abstrakční vrstvou. Pro odevzdání OpenRouter s modelem DeepSeek; zaměnitelný za firemní AI Gateway změnou konfigurace. Pro běh bez klíče lokální Mock_Provider
- **LLM_Abstraction**: Vnitřní rozhraní, přes které aplikace volá model. Aplikační a webový kód nezná konkrétního poskytovatele ani jeho HTTP protokol
- **Mock_Provider**: Deterministická implementace LLM_Abstraction bez sítě. Umožňuje běh a testy bez API klíče a slouží jako záložní režim
- **LLM_Call_Log**: Technický záznam jednoho volání modelu. Obsahuje jméno modelu, čas, počty tokenů a výsledek (úspěch/chyba). Neobsahuje obsah promptu ani odpovědi
- **Description_Rewrite**: Funkce, která přepíše zadaný popis záznamu do kultivovanějšího znění pomocí modelu

### Ochrana osobních údajů

- **Anonymization**: Nahrazení osobních údajů (jméno, e-mail, telefon) zástupnými symboly v textu **před** odesláním modelu
- **Rehydration**: Vrácení původních hodnot na místo zástupných symbolů v textu **po** zpracování modelem
- **Placeholder_Token**: Zástupný symbol, kterým Anonymization nahrazuje osobní údaj (např. `[[JMENO_1]]`)

### Zdroje klasifikace (rozšíření jádra)

- **Classification_Source `AI`**: Uživatel přijal doporučení modelu beze změny úrovně
- **Classification_Source `AI_OVERRIDDEN`**: Uživatel doporučení modelu viděl, ale zvolil jinou úroveň

---

## Requirements

### Requirement 1: Abstrakční vrstva pro volání modelu

**User Story:** As a security and platform reviewer, I want every model call to go through one internal abstraction, so that swapping the public provider for the company AI Gateway is a configuration change, not a code rewrite.

#### Acceptance Criteria

1. THE System SHALL route every language-model call through a single internal LLM_Abstraction; application, service, and web code SHALL NOT call any public model API directly.
2. THE System SHALL provide at least two implementations of the LLM_Abstraction: an LLM_Provider backed by OpenRouter and a Mock_Provider that requires no network access.
3. THE System SHALL allow replacement of the LLM_Provider — including a company AI Gateway — through configuration values only (base URL, model identifier, API key, timeout), with no change to application source code.
4. THE System SHALL read the model API key exclusively from an environment variable and SHALL NOT contain any API key in source code, container image, or repository.
5. IF no model API key is configured, THEN THE System SHALL start normally and fall back to the Mock_Provider or the Deterministic_Score, so that the registry runs and classification and description can still be entered manually.
6. WHEN a model call exceeds the configured timeout or fails, THE System SHALL degrade gracefully to the deterministic fallback (for the Advisor) or report a non-blocking error (for Description_Rewrite), never crash the request.
7. THE System SHALL keep the LLM_Abstraction interface identical regardless of whether the underlying transport is speech-to-text or text generation, so that a future speech feature reuses the same abstraction.

### Requirement 2: Klasifikační dotazník (wizard)

**User Story:** As a record owner, I want to answer a short guided questionnaire, so that the system can propose a size classification I would struggle to judge on my own.

#### Acceptance Criteria

1. THE System SHALL present the Questionnaire as a multi-step wizard, one Dimension per step, with visible progress and forward/back navigation.
2. THE Questionnaire SHALL cover exactly six Dimensions: number of users, data sensitivity, business criticality, integration complexity, regulatory impact, and degree of AI use.
3. EACH Question SHALL offer a closed set of answer options, each carrying a numeric weight contributing to the Deterministic_Score.
4. THE System SHALL require an answer to every Question before a Suggestion can be requested.
5. THE System SHALL allow the user to optionally add a free-text note describing the application, used only to enrich the model's rationale.
6. THE Questionnaire SHALL carry a Questionnaire_Version, stored with every Suggestion, so that a Suggestion remains interpretable after the catalogue changes.
7. THE System SHALL render every question, option, Dimension name, and Classification level as its Czech label, never as a machine code.

### Requirement 3: Doporučení klasifikace a jeho zdůvodnění

**User Story:** As a record owner, I want the system to propose a level and explain why, so that I can accept a defensible classification or consciously override it.

#### Acceptance Criteria

1. WHEN the user requests a Suggestion with all Questions answered, THE System SHALL compute a Deterministic_Score across the six Dimensions and derive a baseline Classification from it.
2. WHERE a model call is available, THE System SHALL request a Suggestion from the model through the LLM_Abstraction, providing the anonymized answers and optional note, and SHALL obtain a proposed Classification and a Czech Suggestion_Rationale.
3. THE System SHALL present the Suggestion showing the proposed Classification, the Suggestion_Rationale, and the per-Dimension contribution, so that the proposal is transparent, not a black box.
4. IF the model call is unavailable or fails, THEN THE System SHALL present the Deterministic_Score result with a generated rationale and SHALL indicate that the proposal is the deterministic fallback.
5. WHEN the user accepts the Suggestion without changing the level, THE System SHALL write the Classification with Classification_Source `AI`.
6. WHEN the user accepts the Suggestion but selects a different level, THE System SHALL write the Classification with Classification_Source `AI_OVERRIDDEN`.
7. WHEN the user ignores the Suggestion and sets a level manually, THE System SHALL write the Classification with Classification_Source `HUMAN`, exactly as the core does today.
8. THE System SHALL write the Classification exclusively through the core single-writer in `services/classification.py`, preserving its transactional invariant and audit behavior.
9. THE System SHALL store the Suggestion and link it from the Classification_Log entry it produced, so that the detail view can show that a classification originated from a model proposal.
10. THE System SHALL evaluate the authorization to write the Classification on the backend, identically to the core (Stewardship_Trio member or Role_Admin), regardless of the Advisor path taken.

### Requirement 4: AI úprava popisu

**User Story:** As a record owner, I want a button that rewrites my rough description into clearer wording, so that registry entries read consistently without me laboring over phrasing.

#### Acceptance Criteria

1. THE System SHALL provide a control next to the description field that requests a Description_Rewrite of the current description text through the LLM_Abstraction.
2. WHEN the user requests a Description_Rewrite, THE System SHALL anonymize personal data in the text before sending it to the model and rehydrate it in the returned text.
3. THE System SHALL present the rewritten text as a proposal the user can accept (replacing the field) or discard (keeping the original), never overwriting the field automatically.
4. IF the description field is empty, THEN THE System SHALL disable or reject the Description_Rewrite request with a Czech explanatory message.
5. IF the model call is unavailable or fails, THEN THE System SHALL report a non-blocking Czech error and leave the original description untouched.
6. THE System SHALL NOT persist the rewritten text until the user saves the record through the normal form flow.

### Requirement 5: Anonymizace osobních údajů

**User Story:** As a data-protection reviewer, I want personal data masked before it leaves for the model, so that names, e-mails, and phone numbers never appear in an outbound model request.

#### Acceptance Criteria

1. BEFORE sending any text to the model, THE System SHALL replace personal data — names, e-mail addresses, and phone numbers — with Placeholder_Tokens.
2. AFTER receiving the model's response, THE System SHALL restore the original values in place of their Placeholder_Tokens (Rehydration).
3. THE System SHALL apply Anonymization to both the Advisor free-text note and the Description_Rewrite input.
4. THE System SHALL work exclusively with synthetic data in seeds and examples.
5. THE Anonymization SHALL be deterministic within a single request, so that the same personal value maps to the same Placeholder_Token and rehydrates unambiguously.

### Requirement 6: Log volání modelu

**User Story:** As an operator, I want a technical log of model calls without their content, so that I can see usage and cost without ever storing prompts or personal data.

#### Acceptance Criteria

1. WHEN a model call completes (success or failure), THE System SHALL record an LLM_Call_Log entry with the model identifier, timestamp, token counts, and outcome.
2. THE LLM_Call_Log SHALL NOT contain the prompt content, the response content, the questionnaire free-text note, or any transcript.
3. THE System SHALL make the LLM_Call_Log readable only to Role_Admin, consistently with Audit_Log access in the core.
4. THE System SHALL log application start, sign-in and sign-out, and errors, consistently with the core; a failed model call SHALL be recorded as an error, not a crash.

### Requirement 7: Retence dat poradce

**User Story:** As a data-protection reviewer, I want advisor data to expire on a defined schedule, so that we keep only what we need for as long as we need it.

#### Acceptance Criteria

1. THE System SHALL define, in the README, the retention period for LLM_Call_Log entries and for stored Suggestions, and SHALL enforce it in code.
2. THE System SHALL delete LLM_Call_Log entries older than their configured retention period automatically, reusing the core retention mechanism.
3. WHERE a Suggestion is linked from a Classification_Log entry, THE System SHALL preserve the Classification_Log entry even after the Suggestion is purged, by clearing the optional link rather than deleting history.
4. THE System SHALL read all retention periods from configuration.

### Requirement 8: Konfigurace a provoz

**User Story:** As a reviewer, I want the advisor to run from `docker compose up` with no manual steps, so that I can evaluate it on the first try.

#### Acceptance Criteria

1. THE System SHALL read all advisor configuration — provider base URL, model identifier, API key, timeout, retention periods — from environment variables.
2. THE repository SHALL contain a `.env.example` documenting every advisor variable with safe placeholder values and SHALL NOT contain a real API key anywhere.
3. WHEN the application starts without an API key, THE System SHALL start successfully and operate in the Mock_Provider / deterministic mode.
4. THE README SHALL state the default model name and version, the reason MFA is not implemented (delegated to the Identity_Provider), and what is conscious debt.
5. THE repository SHALL contain the key prompts under `prompts/`, including the Master Prompt.

---

## Mimo rozsah této specifikace

| Prvek | Důvod |
|---|---|
| Přepis řeči (speech-to-text) | Varianta A ho nepotřebuje. Abstrakce je ale navržená tak, aby ho přijala beze změny rozhraní (R1.7) |
| Streamování odpovědi modelu do UI po částech | Návrh i přepis popisu vrací jeden výsledek; streamování je zbytečná složitost pro tento rozsah |
| Doladění (fine-tuning) vlastního modelu | Používá se hostovaný model přes poskytovatele; ladění není v rozsahu úkolu |
| Vícejazyčné zdůvodnění | Rozhraní je české; zdůvodnění vzniká v češtině (R2.7, R3.2) |
| Ukládání obsahu promptů kvůli auditu kvality | Přímý rozpor s R6.2. Kvalitu řeší prompty ve `prompts/`, ne logování obsahu |
