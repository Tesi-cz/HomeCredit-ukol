# Requirements Document

Registr interních aplikací — provozovatelná verze

> **NAHRAZENO.** Tato specifikace byla rozdělena na dvě implementační specifikace:
>
> - **`app-registry-core`** — jádro evidence, implementuje se první
> - **`classification-advisor`** — dotazník, doporučení modelu, abstrakční vrstva, anonymizace a log volání
>
> Dokument zůstává jako **archiv návrhových úvah**. Obsahuje zdůvodnění rozhodnutí a záznam toho, jak se návrh vyvíjel — zejména `database.md` sekce 12, která popisuje, proč zmizel schvalovací proces klasifikace, hranice důvěry a fallback větev. Tyto úvahy jsou podkladem pro README.
>
> **Závazná pravidla jsou v implementačních specifikacích, ne zde.** Při rozporu platí ony.

## Introduction

Provozovatelná verze interního registru aplikací pro Home Credit. Navazuje na spec `mvp-static-prototype`, kde byl ověřen vizuál a UX flow na statických mockách. Tento dokument definuje **business pravidla a funkční požadavky** reálné aplikace: přihlášení přes OIDC, dvě role s odlišnými právy vynucenými na backendu, AI návrh klasifikace za vlastní abstrakční vrstvou, perzistence záznamů, auditní záznamy a retenční politika.

Funkční rozsah je odvozen ze tří HTML mocků, které nahrazují dřívější prototyp:

1. **Detail aplikace (pohled uživatele)** — bento layout, breadcrumbs, indikátor View Only Mode, karta Security & Privacy, blok Technical Specifications
2. **Správa registru (pohled admina)** — datová tabulka s filtry, multi-select, override klasifikace, bulk akce, export CSV, stránkování
3. **Auditní logy LLM volání** — technický záznam inference bez obsahu promptu, filtry, export CSV, stránkování

## Hlavní funkce a bonus

Hlavní funkcí aplikace je **evidence interních aplikací**. Ta musí fungovat samostatně, bez jediného volání jazykového modelu: uživatel zakládá záznamy, spravuje odpovědné osoby, stav i klasifikaci ručně.

**Classification_Advisor je připojený modul.** Doporučí klasifikaci podle odpovědí v dotazníku a zdůvodní ji, ale platnou klasifikaci nikdy nezapisuje — to dělá vždy člověk. Když poradce není nakonfigurovaný nebo je nedostupný, registr je plně použitelný.

Toto dělení je vynucené i datovým modelem, viz `database.md` sekce 1.

## Rozsah tohoto dokumentu

Tento dokument popisuje **CO** systém dělá a **jaká pravidla platí**. Vědomě neobsahuje:

- datový model a schéma databáze
- volbu konkrétních technologií, frameworků a knihoven
- API kontrakty a endpointy
- strukturu repozitáře a build/deploy pipeline

Vše výše uvedené patří do `design.md`, který vznikne po schválení tohoto dokumentu.

## Glossary

### Domain entities

- **Application_Record**: Záznam v registru reprezentující jednu interně vytvořenou aplikaci
- **Application_Registry**: Kolekce všech Application_Record, nad kterou probíhá vyhledávání, filtrování a stránkování
- **Stewardship_Trio**: Trojice odpovědných osob u každého záznamu — Vlastník (business owner), Zástupce (deputy), Technický správce (technical lead)
- **Department**: Organizační útvar, ke kterému záznam patří (např. Finance, HR, IT Ops, Risk). Slouží jako filtr a agregační dimenze
- **Lifecycle_State**: Stav životního cyklu aplikace: `Návrh` → `Ve vývoji` → `Testování` → `Produkce` → `Vyřazená`
- **Data_Class**: Citlivost dat zpracovávaných aplikací: `Veřejná`, `Interní důvěrná`, `Osobní údaje a finanční data`. Odpovídá jedné z otázek klasifikačního dotazníku a je zobrazena na kartě Security & Privacy
- **Technical_Metadata**: Volitelná technická charakteristika záznamu — hostingové prostředí, použité frameworky, cíl dostupnosti (SLA)

### Klasifikace

- **Classification**: Platná úroveň záznamu: `MALÁ`, `STŘEDNÍ`, `VELKÁ`. Zapisuje ji vždy člověk
- **Classification_Questionnaire**: Sada otázek (4), na které uživatel odpovídá; vstup pro Classification_Advisor
- **Classification_Advisor**: Připojený modul, který na základě odpovědí doporučí úroveň a zdůvodní ji. Volitelný — registr funguje i bez něj
- **Classification_Suggestion**: Doporučení vytvořené Classification_Advisor. Obsahuje úroveň, textové zdůvodnění a AI_Confidence. Není platnou klasifikací, dokud ji člověk nezapíše
- **AI_Confidence**: Míra důvěry doporučení v rozsahu 0–100 %. Zobrazuje se jako ikona s tooltipem. U mock implementace může být prázdná
- **Classification_Source**: Způsob, jakým platná Classification vznikla: `HUMAN` (člověk zadal bez doporučení), `AI` (přijal doporučení bez úpravy), `AI_OVERRIDDEN` (doporučení viděl a zvolil jinou úroveň), `ADMIN_OVERRIDE` (Role_Admin zasáhla do cizího záznamu s povinným důvodem)
- **Classification_Log**: Nemazatelná historie zápisů Classification. Každý zápis nese Classification_Source, předchozí hodnotu a aktéra
- **Classification_Override**: Změna Classification provedená rolí Admin na záznamu, kde není členem Stewardship_Trio. Vždy s povinným důvodem

### Identita a oprávnění

- **Identity_Provider**: Externí OIDC/OAuth2 poskytovatel identity. Pro lokální běh mock, v produkci Microsoft Entra ID
- **Role_User**: Role s právem číst celý registr a spravovat pouze záznamy, u kterých je členem Stewardship_Trio
- **Role_Admin**: Role s právem spravovat všechny záznamy, přepisovat klasifikaci, spravovat role a číst auditní záznamy
- **View_Only_Mode**: Stav detailu záznamu, kdy přihlášený uživatel nemá právo záznam editovat. Je vizuálně indikován a zároveň vynucen na backendu

### AI a audit

- **LLM_Gateway**: Vlastní abstrakční vrstva pro volání jazykových modelů. Jediné místo v kódu, které zná konkrétního poskytovatele
- **LLM_Call_Log**: Technický záznam jednoho volání modelu: čas, model, tokeny vstup/výstup, latence, výsledný stav. Neobsahuje obsah promptu ani odpovědi
- **Audit_Log**: Záznam business akcí uživatelů: přihlášení, odhlášení, vytvoření, editace, override klasifikace, archivace
- **Anonymization**: Nahrazení osobních údajů (jméno, e-mail, telefon) zástupnými symboly před odesláním do LLM_Gateway a jejich obnovení po zpracování
- **Retention_Policy**: Pravidlo určující, jak dlouho se která kategorie dat uchovává a kdy se automaticky maže

---

## Requirements

### Requirement 1: Autentizace přes externího poskytovatele identity

**User Story:** As an employee, I want to sign in with my company identity, so that I do not manage another password and the application never stores my credentials.

#### Acceptance Criteria

1. THE System SHALL authenticate all users exclusively through an OIDC/OAuth2 Identity_Provider using the Authorization Code flow.
2. THE System SHALL NOT store user passwords, password hashes, or any credential material.
3. WHEN an unauthenticated request targets any resource other than the health endpoint or the login route, THE System SHALL reject it and initiate the Identity_Provider login flow.
4. WHEN authentication succeeds, THE System SHALL derive the user's display name, e-mail, and role assignment from the identity token claims.
5. THE System SHALL allow replacement of the Identity_Provider with Microsoft Entra ID through configuration values only (issuer URL, client id, client secret, scopes, claim names), with no change to application source code.
6. THE System SHALL read all Identity_Provider configuration and secrets from environment variables.
7. THE System SHALL NOT implement multi-factor authentication, since MFA is a responsibility of the Identity_Provider.
8. WHEN a user signs out, THE System SHALL invalidate the local session and record an Audit_Log entry.
9. THE System SHALL display the authenticated user's name and e-mail in the sidebar profile block.

### Requirement 2: Role a oprávnění vynucená na backendu

**User Story:** As a security reviewer, I want authorization enforced on the server for every operation, so that hiding a button in the UI is never the only protection.

#### Acceptance Criteria

1. THE System SHALL support exactly two roles: Role_User and Role_Admin.
2. THE System SHALL evaluate authorization on the backend for every state-changing operation and every read of Admin-only data, independently of what the UI renders.
3. WHEN a user without the required role attempts a restricted operation, THE System SHALL deny the operation with an authorization error and record an Audit_Log entry.
4. THE System SHALL derive the effective role from Identity_Provider claims; IF no role claim is present, THEN THE System SHALL assign Role_User as the default.
5. THE System SHALL hide UI controls the current role cannot use, as a usability measure layered on top of backend enforcement, never as a replacement for it.

**Capability matrix** (normative — každý řádek je vynucen na backendu):

| Schopnost | Role_User | Role_Admin |
|---|---|---|
| Číst seznam registru (všechny záznamy) | ano | ano |
| Číst detail libovolného záznamu | ano | ano |
| Vytvořit nový záznam | ano | ano |
| Editovat záznam, kde je členem Stewardship_Trio | ano | ano |
| Editovat záznam, kde není členem Stewardship_Trio | ne | ano |
| Spustit Classification_Questionnaire | ano | ano |
| Potvrdit AI návrh klasifikace u vlastního záznamu | ano | ano |
| Provést Classification_Override | ne | ano |
| Provést bulk Classification_Override | ne | ano |
| Archivovat záznam | ne | ano |
| Číst LLM_Call_Log | ne | ano |
| Číst Audit_Log | ne | ano |
| Exportovat CSV | ne | ano |
| Spravovat přiřazení rolí | ne | ano |

### Requirement 3: Seznam registru

**User Story:** As an employee, I want to search, filter, and page through the registry, so that I can locate a specific application among hundreds of records.

#### Acceptance Criteria

1. THE Application_Registry list SHALL display for each record: název, Vlastník, Department, Classification with AI_Confidence indicator, AI model, and Lifecycle_State as a colored badge.
2. THE System SHALL provide full-text search over the record name.
3. THE System SHALL provide independent filters for Department, Classification, and Lifecycle_State, applicable in combination.
4. THE System SHALL provide sorting by record name.
5. THE System SHALL paginate the list and display the current range and total count (e.g. "Zobrazeno 1–20 z 128").
6. THE System SHALL apply search, filtering, sorting, and pagination on the backend, so that the response contains only the requested page.
7. WHEN a user selects a record, THE System SHALL navigate to its detail view.
8. WHERE the Classification_Source indicates a Classification_Suggestion was involved, THE System SHALL display an AI indicator whose tooltip shows the Classification_Source and, WHERE present, the AI_Confidence value.
9. THE System SHALL exclude archived records from the default list view and make them reachable through an explicit filter.

### Requirement 4: Detail aplikace

**User Story:** As an employee, I want one page that shows everything known about an application, so that I understand who owns it, how it is classified, and how it handles data.

#### Acceptance Criteria

1. THE detail view SHALL display breadcrumbs in the form "Registr › {název záznamu}".
2. THE detail view SHALL display the record name, Lifecycle_State badge, Classification badge, and description.
3. THE detail view SHALL display the full Stewardship_Trio with each person's name and job title.
4. THE detail view SHALL display a Security & Privacy block containing the Anonymization status, the Data_Class, and the date of the most recent Classification_Log entry.
5. THE detail view SHALL display a Technical_Metadata block containing hosting environment, frameworks, and availability target, and SHALL omit individual items that are not filled in.
6. THE detail view SHALL display the Classification together with its Classification_Source, and WHERE a Classification_Suggestion is linked, also its justification and AI_Confidence.
6a. WHERE the Classification_Source is `AI_OVERRIDDEN` or `ADMIN_OVERRIDE`, THE detail view SHALL display both the written Classification and the differing suggested level, so that the divergence is visible.
7. WHEN the current user has no edit right for the record, THE detail view SHALL display a View_Only_Mode indicator and SHALL NOT render edit actions.
8. WHEN the current user has an edit right for the record, THE detail view SHALL offer an edit action.
9. THE detail view SHALL provide a link back to the registry list.

### Requirement 5: Vytvoření a editace záznamu

**User Story:** As an application owner, I want to register my application and keep its record current, so that the registry reflects reality.

#### Acceptance Criteria

1. THE System SHALL accept the following attributes on a record: název, Vlastník, Zástupce, Technický správce, Department, Lifecycle_State, AI model, popis, **Classification**, Data_Class, and Technical_Metadata.
2. THE System SHALL treat as mandatory: název, Vlastník, Technický správce, Department, and Lifecycle_State.
3. WHEN a mandatory attribute is missing or empty, THE System SHALL reject the operation and report which attributes are missing.
4. THE System SHALL validate on the backend that Lifecycle_State is one of the defined values and Data_Class is one of the defined values.
5. WHEN a record is created, THE System SHALL set its creator as Vlastník by default, and SHALL allow the creator to change it before saving.
6. THE System SHALL allow a user to set the Classification directly on the record form without consulting the Classification_Advisor, and SHALL record such a write with Classification_Source `HUMAN`.
7. WHEN a record is created without a Classification, THE System SHALL persist it with Classification unset and SHALL present it in the registry list as neklasifikovaná.
8. THE System SHALL NOT require the Classification_Advisor to be available or configured in order to create, edit, or classify a record.
9. WHEN a record is created or modified, THE System SHALL record an Audit_Log entry identifying the actor, the record, and the changed attributes.
10. THE System SHALL reject an edit request from a user who is neither a member of the record's Stewardship_Trio nor Role_Admin.
11. THE System SHALL NOT allow physical deletion of records by any role; removal from active use SHALL be modeled as archivace by Role_Admin.

### Requirement 6: Klasifikační dotazník a doporučení

**User Story:** As an application owner, I want the option to have a classification recommended and explained, so that I do not have to interpret the classification policy myself when I am unsure.

#### Acceptance Criteria

1. THE Classification_Questionnaire SHALL consist of four questions covering: expected number of users, sensitivity of processed data, business criticality, and integration complexity.
2. THE System SHALL present one question at a time with a progress indicator and SHALL allow navigation back to a previous question without losing already given answers.
3. THE System SHALL make the questionnaire optional; a user SHALL be able to classify a record without ever opening it.
4. WHEN all questions are answered, THE System SHALL request a Classification_Suggestion from the LLM_Gateway.
5. THE Classification_Suggestion SHALL contain a Classification level and a textual justification in Czech, and MAY contain an AI_Confidence value.
6. WHEN a Classification_Suggestion is produced, THE System SHALL persist the questionnaire answers, the questionnaire version, the suggested level, the justification, and the AI_Confidence, independently of whether the user later uses the suggestion.
7. IF the LLM_Gateway call fails, times out, or returns a response that cannot be parsed, THEN THE System SHALL report the failure to the user and SHALL offer manual classification, and SHALL NOT block record creation or editing.
8. THE System SHALL derive a proposed Data_Class from the answer to the data sensitivity question and SHALL treat it as a pre-filled value the user can change.
9. THE System SHALL send only questionnaire answers to the LLM_Gateway and SHALL NOT send the Stewardship_Trio names, e-mails, or phone numbers in raw form.
10. THE System SHALL treat every Classification_Suggestion as a recommendation only; a Classification_Suggestion SHALL NEVER become the record's Classification without a human write.

### Requirement 7: Zápis klasifikace člověkem

**User Story:** As an application owner, I want to be the one who writes the classification, so that a model's opinion is never recorded as fact on my behalf.

#### Acceptance Criteria

1. THE System SHALL write the Classification only as a result of an explicit human action.
2. EACH write of the Classification SHALL be recorded in the Classification_Log with its Classification_Source, the previous value, the acting user, and a timestamp.
3. WHEN a user sets the Classification without a Classification_Suggestion, THE System SHALL record Classification_Source `HUMAN`.
4. WHEN a user accepts a Classification_Suggestion unchanged, THE System SHALL record Classification_Source `AI` and SHALL link the log entry to that suggestion.
5. WHEN a user has been shown a Classification_Suggestion and writes a different level, THE System SHALL record Classification_Source `AI_OVERRIDDEN` and SHALL link the log entry to that suggestion.
6. THE System SHALL display the Classification_Suggestion together with its justification and, WHERE present, its AI_Confidence, before the user writes the Classification.
7. WHERE the AI_Confidence is low or absent, THE System SHALL present the suggestion with a visible caution and SHALL NOT pre-select it as the answer.
8. THE System SHALL allow the questionnaire to be re-run on an existing record, and WHEN it is re-run, THE System SHALL retain the current Classification until the user writes a new one.
9. THE System SHALL reject a Classification_Source value that is inconsistent with the presence or absence of a linked Classification_Suggestion.
10. THE System SHALL visually distinguish records without a Classification in the registry list.

### Requirement 8: Admin override klasifikace

**User Story:** As an admin, I want to override a classification with a stated reason, so that policy exceptions are possible and traceable.

#### Acceptance Criteria

1. THE System SHALL allow Role_Admin to set the Classification of any record to any valid level, including records where Role_Admin is not a member of the Stewardship_Trio.
2. THE System SHALL require a non-empty textual reason for every Classification_Override.
3. WHEN a Classification_Override is submitted without a reason, THE System SHALL reject it.
4. WHEN a Classification_Override is applied, THE System SHALL record it in the Classification_Log with Classification_Source `ADMIN_OVERRIDE`, the reason, and the previous value.
5. THE System SHALL retain any earlier Classification_Suggestion and its justification unchanged, so that the model's recommendation and the administrative decision can be compared.
6. THE System SHALL display the reason for the most recent Classification_Override on the record detail.
7. THE System SHALL reject any Classification_Override request from Role_User, regardless of how the request was constructed.
8. WHERE bulk override remains in scope, THE System SHALL allow Role_Admin to select multiple records and apply one override to all of them, SHALL keep the action disabled when no record is selected, and SHALL record a separate Classification_Log and Audit_Log entry for each affected record.

### Requirement 9: Abstrakční vrstva pro volání LLM

**User Story:** As a platform owner, I want every model call to pass through one internal interface, so that switching to the company AI Gateway is a configuration change.

#### Acceptance Criteria

1. THE System SHALL route all language model calls through the LLM_Gateway.
2. THE System SHALL NOT call any public AI provider API directly from application, domain, or UI code.
3. THE System SHALL support at least two interchangeable LLM_Gateway implementations: one real provider and one deterministic mock usable without network access or an API key.
3a. THE mock implementation SHALL derive the Classification_Suggestion from a rule-based score over the questionnaire answers, so that the deterministic path exists as a gateway implementation rather than as a separate fallback branch in calling code.
4. THE System SHALL select the active LLM_Gateway implementation through an environment variable.
5. THE System SHALL read the model API key exclusively from an environment variable and SHALL NOT contain it in source code, container images, or the repository.
6. WHEN no API key is configured, THE System SHALL start successfully and SHALL use the mock implementation.
7. THE LLM_Gateway interface SHALL expose provider-neutral operations, so that adding the company AI Gateway requires a new implementation of the interface and configuration only, without changes to calling code.
8. THE System SHALL apply a configurable timeout to every LLM_Gateway call.

### Requirement 10: Log volání modelu

**User Story:** As an admin, I want a technical record of every model inference without any prompt content, so that I can audit cost and reliability without creating a privacy risk.

#### Acceptance Criteria

1. WHEN an LLM_Gateway call completes, THE System SHALL record an LLM_Call_Log entry containing: timestamp in UTC, related Application_Record, model identifier, input token count, output token count, latency in milliseconds, and result status.
2. THE LLM_Call_Log SHALL NOT contain the prompt text, the model response text, or any transcript.
3. THE System SHALL record an LLM_Call_Log entry for failed and timed-out calls as well, with the corresponding status.
4. THE System SHALL restrict reading of the LLM_Call_Log to Role_Admin.
5. THE LLM_Call_Log view SHALL provide filters for Application_Record, model, and time range.
6. THE LLM_Call_Log view SHALL paginate results and display the current range and total count.
7. THE LLM_Call_Log view SHALL state explicitly that prompt and response content is intentionally not stored.

### Requirement 11: Anonymizace osobních údajů

**User Story:** As a data protection reviewer, I want personal data replaced before it leaves the application, so that no identifiable information reaches an external model.

#### Acceptance Criteria

1. WHEN text containing personal data is prepared for an LLM_Gateway call, THE System SHALL replace every detected name, e-mail address, and phone number with a placeholder token.
2. THE System SHALL maintain the mapping between placeholder tokens and original values only for the duration of the request processing.
3. WHEN the LLM_Gateway response is received, THE System SHALL restore the original values in place of the placeholder tokens before the result is presented or persisted.
4. THE System SHALL guarantee that anonymization followed by restoration returns the original text unchanged.
5. THE System SHALL NOT persist the placeholder mapping.
6. THE System SHALL operate exclusively on synthetic data in all seeded and example content.

### Requirement 12: Aplikační audit log

**User Story:** As an admin, I want a chronological record of who did what, so that changes to the registry are traceable.

#### Acceptance Criteria

1. THE System SHALL record an Audit_Log entry for: sign-in, sign-out, record creation, record modification, Classification confirmation, Classification_Override, archivace, and denied authorization attempts.
2. EACH Audit_Log entry SHALL contain: timestamp, acting user identity, action type, affected record where applicable, and a short description.
3. THE System SHALL restrict reading of the Audit_Log to Role_Admin.
4. THE System SHALL NOT allow modification or deletion of Audit_Log entries through the application.
5. THE Audit_Log SHALL NOT contain prompt content, model responses, or credential material.

### Requirement 13: Retenční politika

**User Story:** As a data protection reviewer, I want retention periods defined and actually implemented, so that data is not kept indefinitely by accident.

#### Acceptance Criteria

1. THE System SHALL define a retention period for LLM_Call_Log entries, for Audit_Log entries, and for archived Application_Record entries.
2. THE System SHALL make each retention period configurable through an environment variable with a documented default.
3. THE System SHALL run an automated routine that deletes data exceeding its retention period, without any manual step.
4. WHEN the retention routine deletes data, THE System SHALL log the operation with the affected category and the number of removed entries.
5. THE System SHALL document all retention periods and their rationale in the README.
6. THE System SHALL apply retention to Audit_Log deletion as an automated, log-only operation, so that Requirement 12.4 is not violated by manual intervention.

### Requirement 14: Export CSV

**User Story:** As an admin, I want to export registry and log data, so that I can analyze it outside the application.

#### Acceptance Criteria

1. THE System SHALL allow Role_Admin to export the Application_Registry as CSV.
2. THE System SHALL allow Role_Admin to export the LLM_Call_Log as CSV.
3. WHEN filters are active, THE System SHALL export the filtered result set, not the entire dataset.
4. THE System SHALL reject export requests from Role_User.
5. THE exported CSV SHALL NOT contain prompt content or model responses.

### Requirement 15: Správa uživatelů a rolí

**User Story:** As an admin, I want to see who has access and adjust their application role, so that permissions stay aligned with responsibilities.

#### Acceptance Criteria

1. THE System SHALL display to Role_Admin a list of users known to the application, showing display name, e-mail, and current role.
2. THE System SHALL allow Role_Admin to change a user's application role between Role_User and Role_Admin.
3. THE System SHALL NOT create, edit, or delete identities; identity lifecycle remains the responsibility of the Identity_Provider.
4. WHEN a role assignment changes, THE System SHALL record an Audit_Log entry.
5. THE System SHALL prevent Role_Admin from removing their own Admin role, so that at least one administrator always remains.
6. WHERE the Identity_Provider supplies a role claim, THE System SHALL treat the claim as the source of truth and SHALL present local role management as an override applicable only while the mock provider is in use.

### Requirement 16: Provozní požadavky

**User Story:** As a reviewer, I want to start the whole application with one command, so that I can evaluate it without following a setup checklist.

#### Acceptance Criteria

1. THE System SHALL start completely through a single `docker compose up` invocation, with no manual steps beyond copying `.env.example` to `.env`.
2. THE System SHALL expose a health endpoint reachable without authentication that reports service readiness.
3. THE System SHALL log application startup, unhandled errors, sign-in events, and sign-out events.
4. THE System SHALL NOT contain secrets in source code, in the container image, or in the repository.
5. THE repository SHALL contain `.env.example` with every required variable documented and no real values.
6. THE repository `.gitignore` SHALL exclude `.env` and other local secret files.
7. THE System SHALL pin every dependency to an exact version.
8. THE System SHALL seed the database with synthetic Application_Record data on first start, so that the registry is not empty on evaluation.
9. THE System SHALL NOT log personal data, secrets, prompt content, or model responses.

### Requirement 17: Uživatelské rozhraní a jazyk

**User Story:** As a Czech-speaking employee, I want the interface in Czech and consistent with Home Credit visual identity, so that it feels like an internal company tool.

#### Acceptance Criteria

1. THE System SHALL render all labels, headings, buttons, form fields, placeholders, status values, and messages in Czech.
2. THE System SHALL set the HTML `lang` attribute to `cs`.
3. THE System SHALL display dates in Czech format (DD.MM.YYYY), except in the LLM_Call_Log where UTC timestamps are displayed with time.
4. THE System SHALL follow the visual identity defined in `.kiro/steering/brand-guidelines.md`.
5. THE System SHALL provide a persistent sidebar with navigation to Registr, Přehled, Uživatelé, Auditní logy, and a primary action for creating a new record.
6. THE System SHALL hide the Uživatelé and Auditní logy navigation items from Role_User.
7. THE System SHALL provide a top bar containing the section title and a registry search field.
8. THE System SHALL confirm completed actions with a visible notification.
9. THE System SHALL remain usable at viewport widths from 1024px upward and SHALL collapse the sidebar below that width.

---

## Mimo rozsah a vědomý dluh

Následující prvky jsou v mockách přítomné nebo se přirozeně nabízejí, ale vědomě je neimplementujeme. Důvody patří do README jako deklarovaný dluh.

| Prvek | Rozhodnutí | Důvod |
|---|---|---|
| MFA | neimplementovat | Patří do Identity_Provider. Implementace v aplikaci by duplikovala odpovědnost a oslabila bezpečnostní model |
| Reálný Entra ID tenant | neimplementovat | Vyžaduje firemní tenant. Nahrazeno mockem s totožným OIDC rozhraním, výměna je změna konfigurace |
| Notifikace (zvonek v top baru) | neimplementovat | Vyžaduje notifikační kanál a stavovou správu přečtení, bez přínosu pro hodnocené oblasti |
| Nápověda (ikona v top baru) | neimplementovat | Statický obsah bez business logiky |
| Sekce Nastavení | neimplementovat | Konfigurace je řešena proměnnými prostředí, ne UI |
| Avatary uživatelů | neimplementovat | Vyžaduje úložiště obrázků nebo napojení na profilovou fotku v IdP. Nahrazeno iniciálami |
| Správa taxonomie Department | neimplementovat | Department je uzavřený výčet v konfiguraci, ne editovatelný registr |
| Monitoring plnění SLA | neimplementovat | Availability target je deklarativní metadata, ne měřená hodnota |
| Verzování historie záznamu | neimplementovat | Audit_Log zaznamenává, co se změnilo. Plný time-travel diff je nad rozsah |
| Samostatná AI kategorie domény | neimplementovat | Mock obsahoval sloupec „AI Class." s doménovou kategorií. Sloučeno do Classification s AI_Confidence indikátorem, aby existovala jedna autoritativní klasifikace místo dvou |
| Fyzické mazání záznamů | neimplementovat | Registr je evidence. Odstranění je modelováno archivací, aby zůstala historie |
| Schvalovací proces klasifikace | neimplementovat | Klasifikaci zapisuje vždy člověk, takže není co schvalovat. Odpadá stavový automat i konfigurovatelná hranice důvěry |
| Samostatná fallback větev při výpadku modelu | neimplementovat | Bodový scorer je mock implementací LLM_Gateway. Deterministická cesta tak existuje jako záměnná implementace, ne jako druhá větev v kódu |

## Otevřené otázky k rozhodnutí v design fázi

1. Konkrétní retenční lhůty pro LLM_Call_Log, Audit_Log a archivované záznamy
2. Rozsah detekce PII při anonymizaci (regex vs. slovník jmen) a jak se řeší false negatives
3. Zda archivace a Lifecycle_State `Vyřazená` jsou oddělené věci, jak navrhuje `database.md`
4. Zda zůstává blok Technical_Metadata a Data_Class, nebo padá jako první při krácení rozsahu
5. Zda zůstává hromadný přepis klasifikace (R8.8)
6. Jazyk rozhraní: mocky jsou anglicky, R17 vyžaduje češtinu

Vyřešeno restrukturalizací na Classification_Advisor, viz `database.md` sekce 12:

- ~~Výchozí hodnota Confidence_Threshold~~ — hranice zrušena, doporučení se nikdy neaplikuje automaticky
- ~~Zda Deterministic_Fallback smí potvrdit Role_User~~ — fallback zrušen, bodový scorer je mock implementace LLM_Gateway
