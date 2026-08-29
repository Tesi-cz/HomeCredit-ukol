# Requirements Document

Registr interních aplikací — jádro evidence

## Introduction

Provozovatelná aplikace pro evidenci interně vytvořených aplikací v Home Credit. Přihlášení přes OIDC, dvě role s odlišnými právy vynucenými na backendu, perzistence záznamů, auditní stopa a retenční politika.

Tato specifikace pokrývá **hlavní funkci: evidenci aplikací**. Klasifikaci zadává člověk. Jazykový model v tomto rozsahu nevystupuje vůbec — v kódu není žádné volání modelu, žádná abstrakční vrstva pro něj a žádný log jeho volání.

Vizuální podoba a UX flow vycházejí ze schválených mocků: seznam registru s filtry a stránkováním, detail záznamu s indikátorem View Only Mode, správa registru pro roli Admin, výpis auditních záznamů.

## Vztah k ostatním specifikacím

| Specifikace | Role |
|---|---|
| `mvp-static-prototype` | Statický vizuální prototyp. Dokončeno, slouží jako vizuální reference |
| `app-registry` | **Nahrazeno.** Ponecháno jako archiv návrhových úvah a zdůvodnění rozhodnutí |
| `app-registry-core` | **Tento dokument.** Jádro evidence, implementuje se první |
| `classification-advisor` | Navazující specifikace. Doplní dotazník, doporučení modelu, abstrakční vrstvu, anonymizaci a log volání |

**Poradce není volitelný pro odevzdání.** Zadání ho vyžaduje. Rozdělení do dvou specifikací je pořadí práce, ne krácení rozsahu. Jádro je navržené tak, aby ho poradce doplnil čistě aditivně — viz `database.md` sekce 9.

## Rozsah tohoto dokumentu

Popisuje **co** systém dělá a **jaká pravidla platí**. Vědomě neobsahuje volbu frameworků, API kontrakty ani strukturu repozitáře. Datový model je v `database.md`.

## Glossary

### Domain entities

- **Application_Record**: Záznam v registru reprezentující jednu interně vytvořenou aplikaci
- **Application_Registry**: Kolekce všech Application_Record, nad kterou probíhá vyhledávání, filtrování a stránkování
- **Stewardship_Trio**: Trojice odpovědných osob u každého záznamu — Vlastník, Zástupce, Technický správce
- **Department**: Organizační útvar, ke kterému záznam patří. Uzavřený výčet v konfiguraci, ne editovatelný registr
- **Lifecycle_State**: Stav životního cyklu aplikace: `Návrh` → `Ve vývoji` → `Testování` → `Produkce` → `Vyřazená`
- **Decommissioning**: Přechod do stavu `Vyřazená`. Vyhrazeno roli Admin. Zaznamenává se okamžik přechodu, protože od něj se počítá retenční lhůta záznamu

### Klasifikace

- **Classification**: Platná úroveň záznamu: `MALÁ`, `STŘEDNÍ`, `VELKÁ`. Zapisuje ji vždy člověk
- **Classification_Source**: Způsob, jakým platná Classification vznikla. V tomto rozsahu `HUMAN` (zadal člověk odpovědný za záznam) nebo `ADMIN_OVERRIDE` (Role_Admin zasáhla do cizího záznamu s povinným důvodem)
- **Classification_Log**: Nemazatelná historie zápisů Classification. Každý zápis nese Classification_Source, předchozí hodnotu a aktéra
- **Classification_Override**: Změna Classification provedená rolí Admin na záznamu, kde není členem Stewardship_Trio. Vždy s povinným důvodem

### Identita a oprávnění

- **Identity_Provider**: Externí OIDC/OAuth2 poskytovatel identity. Pro lokální běh mock, v produkci Microsoft Entra ID
- **Role_User**: Právo číst celý registr a spravovat pouze záznamy, u kterých je členem Stewardship_Trio
- **Role_Admin**: Právo spravovat všechny záznamy, měnit klasifikaci cizích záznamů, vyřazovat záznamy, spravovat role a číst auditní záznamy
- **View_Only_Mode**: Stav detailu, kdy přihlášený uživatel nemá právo záznam editovat. Vizuálně indikován a zároveň vynucen na backendu

### Audit a retence

- **Audit_Log**: Záznam akcí uživatelů: přihlášení, odhlášení, vytvoření, editace, zápis a přepis klasifikace, vyřazení, změna role, zamítnutý pokus
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
5. THE System SHALL allow replacement of the Identity_Provider with Microsoft Entra ID through configuration values only — issuer URL, client id, client secret, scopes, claim names — with no change to application source code.
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
6. THE System SHALL determine edit rights for a record by comparing the authenticated user's identity against the record's Stewardship_Trio, never by comparing displayed names.

**Capability matrix** (normative — každý řádek je vynucen na backendu):

| Schopnost | Role_User | Role_Admin |
|---|---|---|
| Číst seznam registru (všechny záznamy) | ano | ano |
| Číst detail libovolného záznamu | ano | ano |
| Vytvořit nový záznam | ano | ano |
| Editovat záznam, kde je členem Stewardship_Trio | ano | ano |
| Editovat záznam, kde není členem Stewardship_Trio | ne | ano |
| Nastavit Classification u záznamu, kde je členem Stewardship_Trio | ano | ano |
| Změnit Classification u cizího záznamu | ne | ano |
| Měnit Lifecycle_State mimo stav `Vyřazená` | ano (u svého záznamu) | ano |
| Nastavit Lifecycle_State na `Vyřazená` | ne | ano |
| Číst Audit_Log | ne | ano |
| Exportovat CSV | ne | ano |
| Spravovat přiřazení rolí | ne | ano |

### Requirement 3: Seznam registru

**User Story:** As an employee, I want to search, filter, and page through the registry, so that I can locate a specific application among hundreds of records.

#### Acceptance Criteria

1. THE Application_Registry list SHALL display for each record: název, Vlastník, Department, Classification, AI model, and Lifecycle_State as a colored badge.
1a. THE System SHALL render every enumerated value in the list as its Czech label, never as its stored machine code.
2. THE System SHALL provide full-text search over the record name.
3. THE System SHALL provide independent filters for Department, Classification, and Lifecycle_State, applicable in combination.
4. THE System SHALL provide sorting by record name.
5. THE System SHALL paginate the list and display the current range and total count.
6. THE System SHALL apply search, filtering, sorting, and pagination on the backend, so that the response contains only the requested page.
7. WHEN a user selects a record, THE System SHALL navigate to its detail view.
8. THE System SHALL visually distinguish records that have no Classification.
9. THE System SHALL exclude records in Lifecycle_State `Vyřazená` from the default list view and SHALL make them reachable through the Lifecycle_State filter.
10. THE System SHALL provide a separate view listing only records where the authenticated user is a member of the Stewardship_Trio, rendered as a card grid, and SHALL use it as the landing view after sign-in.
11. EACH card SHALL display the record name, Lifecycle_State, Classification, a shortened description, and the date of the last modification.
12. WHEN the authenticated user is a member of no Stewardship_Trio, THE System SHALL display an explanatory empty state with a call to register a new record.

### Requirement 4: Detail aplikace

**User Story:** As an employee, I want one page that shows everything known about an application, so that I understand who owns it, how it is classified, and how it handles data.

#### Acceptance Criteria

1. THE detail view SHALL display breadcrumbs in the form "Registr › {název záznamu}".
2. THE detail view SHALL display the record name, Lifecycle_State badge, Classification badge, and description.
3. THE detail view SHALL display the full Stewardship_Trio with each person's name and job title.
4. THE detail view SHALL display the Classification together with its Classification_Source and the date it was written.
5. WHERE the most recent Classification_Log entry is a Classification_Override, THE detail view SHALL display its reason.
6. THE detail view SHALL display the Classification_Log history, ordered from newest to oldest, showing for each entry the value, the Classification_Source, the actor, and the timestamp.
7. THE detail view SHALL display the AI model used by the recorded application, or state that none is used.
8. WHEN the current user has no edit right for the record, THE detail view SHALL display a View_Only_Mode indicator and SHALL NOT render edit actions.
9. WHEN the current user has an edit right for the record, THE detail view SHALL offer an edit action.
10. THE detail view SHALL provide a link back to the registry list.

### Requirement 5: Vytvoření a editace záznamu

**User Story:** As an application owner, I want to register my application and keep its record current, so that the registry reflects reality.

#### Acceptance Criteria

1. THE System SHALL accept the following attributes on a record: název, Vlastník, Zástupce, Technický správce, Department, Lifecycle_State, AI model, popis, and Classification.
2. THE System SHALL treat as mandatory: název, Vlastník, Technický správce, Department, and Lifecycle_State.
3. WHEN a mandatory attribute is missing or empty, THE System SHALL reject the operation and report which attributes are missing.
4. THE System SHALL validate on the backend that Lifecycle_State, Classification, and Department each hold one of their defined values.
5. WHEN a record is created, THE System SHALL set its creator as Vlastník by default, and SHALL allow the creator to change it before saving.
6. THE System SHALL allow the Classification to be set directly on the record form.
7. WHEN a record is created without a Classification, THE System SHALL persist it and present it in the registry list as neklasifikovaná.
8. THE System SHALL reject the record name IF another record with the same name, ignoring letter case, already exists.
9. WHEN a record is created or modified, THE System SHALL record an Audit_Log entry identifying the actor, the record, and the names of the changed attributes.
10. THE System SHALL reject an edit request from a user who is neither a member of the record's Stewardship_Trio nor Role_Admin.
11. THE System SHALL NOT allow physical deletion of records by any role; removal from active use SHALL be modeled as the Lifecycle_State `Vyřazená`.
12. THE System SHALL allow only Role_Admin to set the Lifecycle_State to `Vyřazená`, and SHALL reject such a request from Role_User even when the user is a member of the Stewardship_Trio.
13. WHEN a record enters Lifecycle_State `Vyřazená`, THE System SHALL store the timestamp of that transition, retain the record in the database, exclude it from the default list, and record an Audit_Log entry.
14. WHEN a record leaves Lifecycle_State `Vyřazená`, THE System SHALL clear the stored decommissioning timestamp, so that the retention period restarts only upon a new decommissioning.

### Requirement 6: Zápis klasifikace

**User Story:** As an application owner, I want to record the classification of my application, so that the registry states how significant it is.

#### Acceptance Criteria

1. THE System SHALL write the Classification only as a result of an explicit human action.
2. EACH write of the Classification SHALL be recorded in the Classification_Log with its Classification_Source, the previous value, the acting user, and a timestamp.
3. WHEN a member of the Stewardship_Trio sets the Classification, THE System SHALL record Classification_Source `HUMAN`.
4. THE System SHALL allow the Classification to be changed later, and SHALL append a new Classification_Log entry for every change rather than modifying an existing one.
5. THE System SHALL keep the Classification_Log immutable; no operation exposed by the application SHALL update or delete an existing entry.
6. THE System SHALL display the Classification_Log history on the record detail, ordered from newest to oldest.
7. THE System SHALL keep the Classification independent of the Lifecycle_State; changing one SHALL NOT change the other.

### Requirement 7: Přepis klasifikace správcem

**User Story:** As an admin, I want to correct a classification on any record with a stated reason, so that policy exceptions are possible and traceable.

#### Acceptance Criteria

1. THE System SHALL allow Role_Admin to set the Classification of any record to any valid level, including records where Role_Admin is not a member of the Stewardship_Trio.
2. THE System SHALL require a non-empty textual reason for every Classification_Override.
3. WHEN a Classification_Override is submitted without a reason, THE System SHALL reject it.
4. WHEN a Classification_Override is applied, THE System SHALL record it in the Classification_Log with Classification_Source `ADMIN_OVERRIDE`, the reason, and the previous value.
5. THE System SHALL display the reason for the most recent Classification_Override on the record detail.
6. THE System SHALL reject any Classification_Override request from Role_User, regardless of how the request was constructed.
7. WHEN a Classification_Override is applied, THE System SHALL record an Audit_Log entry in addition to the Classification_Log entry.

### Requirement 8: Auditní log

**User Story:** As an admin, I want a chronological record of who did what, so that changes to the registry are traceable.

#### Acceptance Criteria

1. THE System SHALL record an Audit_Log entry for: sign-in, sign-out, record creation, record modification, Classification write, Classification_Override, Decommissioning, return from Decommissioning, role change, and denied authorization attempts.
2. EACH Audit_Log entry SHALL contain: timestamp, acting user identity, action type, affected record where applicable, and a short description in Czech.
3. THE System SHALL store the acting user's e-mail and display name as a copy taken at the time of the action, so that the entry remains readable if the person is later removed from the directory.
4. THE System SHALL restrict reading of the Audit_Log to Role_Admin.
5. THE System SHALL NOT allow modification or deletion of Audit_Log entries through the application; the retention routine is the only exception.
6. THE System SHALL NOT record IP addresses, user agents, or credential material in the Audit_Log.
7. THE Audit_Log view SHALL provide filters for action type, actor, and time range, and SHALL paginate results.

### Requirement 9: Retenční politika

**User Story:** As a data protection reviewer, I want retention periods defined and actually implemented, so that personal data is not kept indefinitely by accident.

#### Acceptance Criteria

1. THE System SHALL define a retention period for Audit_Log entries and for Application_Record entries in Lifecycle_State `Vyřazená`.
2. THE System SHALL make each retention period configurable through an environment variable with a documented default.
3. THE System SHALL run an automated routine that deletes data exceeding its retention period, without any manual step.
4. THE System SHALL compute the retention cutoff for a record from its decommissioning timestamp, never from its last modification time, so that editing a decommissioned record does not extend its retention.
5. WHEN the retention routine deletes data, THE System SHALL log the affected category, the cutoff timestamp, and the number of removed entries.
6. THE System SHALL document all retention periods and their rationale in the README.
7. WHEN a decommissioned Application_Record is deleted by retention, THE System SHALL delete its Classification_Log entries and SHALL retain its Audit_Log entries.
8. THE System SHALL NOT delete a person from the directory while that person is referenced as a member of any Stewardship_Trio.

### Requirement 10: Export CSV

**User Story:** As an admin, I want to export registry and audit data, so that I can analyze it outside the application.

#### Acceptance Criteria

1. THE System SHALL allow Role_Admin to export the Application_Registry as CSV.
2. THE System SHALL allow Role_Admin to export the Audit_Log as CSV.
3. WHEN filters are active, THE System SHALL export the filtered result set, not the entire dataset.
4. THE System SHALL reject export requests from Role_User.
5. THE exported CSV SHALL use UTF-8 encoding and SHALL render enumerated values as their Czech labels.

### Requirement 11: Správa uživatelů a rolí

**User Story:** As an admin, I want to see who has access and adjust their application role, so that permissions stay aligned with responsibilities.

#### Acceptance Criteria

1. THE System SHALL display to Role_Admin a list of persons known to the application, showing display name, e-mail, job title, and current role.
2. THE System SHALL allow Role_Admin to change a person's application role between Role_User and Role_Admin.
3. THE System SHALL NOT create, edit, or delete identities; identity lifecycle remains the responsibility of the Identity_Provider.
4. WHEN a role assignment changes, THE System SHALL record an Audit_Log entry.
5. THE System SHALL prevent Role_Admin from removing their own Admin role, so that at least one administrator always remains.
6. WHERE the Identity_Provider supplies a role claim, THE System SHALL treat the claim as the source of truth and SHALL present local role management as an override applicable only while the mock provider is in use.
7. THE System SHALL allow a person to be recorded in a Stewardship_Trio before that person has ever signed in.

### Requirement 12: Provozní požadavky

**User Story:** As a reviewer, I want to start the whole application with one command, so that I can evaluate it without following a setup checklist.

#### Acceptance Criteria

1. THE System SHALL start completely through a single `docker compose up` invocation, with no manual steps beyond copying `.env.example` to `.env`.
2. THE System SHALL expose a health endpoint reachable without authentication that reports service readiness.
3. THE System SHALL log application startup, unhandled errors, sign-in events, and sign-out events.
4. THE System SHALL NOT contain secrets in source code, in the container image, or in the repository.
5. THE repository SHALL contain `.env.example` with every required variable documented and no real values.
6. THE repository `.gitignore` SHALL exclude `.env` and other local secret files.
7. THE System SHALL pin every dependency to an exact version.
8. THE System SHALL apply the database schema automatically on start, with no manual migration step.
9. THE System SHALL seed the database with synthetic Application_Record and person data on first start, so that the registry is not empty on evaluation.
10. THE System SHALL NOT log personal data or secrets.
11. THE System SHALL operate exclusively on synthetic data in all seeded and example content.

### Requirement 13: Uživatelské rozhraní a jazyk

**User Story:** As a Czech-speaking employee, I want the interface in Czech and consistent with Home Credit visual identity, so that it feels like an internal company tool.

#### Acceptance Criteria

1. THE System SHALL render all labels, headings, buttons, form fields, placeholders, enumerated values, and messages in Czech.
2. THE System SHALL set the HTML `lang` attribute to `cs`.
3. THE System SHALL display dates in Czech format (DD.MM.YYYY).
4. THE System SHALL follow the visual identity defined in `.kiro/steering/brand-guidelines.md`.
5. THE System SHALL provide a persistent sidebar with navigation to Moje aplikace, Registr, Uživatelé, Auditní logy, and a primary action for creating a new record.
6. THE System SHALL hide the Uživatelé and Auditní logy navigation items from Role_User.
6a. THE System SHALL present itself under the product name REGINA with the subtitle "REGistr INterních Aplikací".
7. THE System SHALL provide a top bar containing the section title and a registry search field.
8. THE System SHALL confirm completed actions with a visible notification.
9. THE System SHALL serve fonts and stylesheets from the application itself, so that the interface renders correctly without internet access.
10. THE System SHALL remain usable at viewport widths from 1024px upward and SHALL collapse the sidebar below that width.
11. THE System SHALL NOT display any English label in the user interface.

**Závazné české popisky.** Mocky jsou anglicky. Tato tabulka je normativní překlad, aby se do rozhraní angličtina nevrátila.

| V mocku | V aplikaci |
|---|---|
| App Registry | Registr aplikací |
| Registry | Registr |
| Users | Uživatelé |
| Audit Logs | Auditní logy |
| New Application | Nová aplikace |
| Search registry… | Hledat v registru… |
| Filter | Filtrovat |
| Export CSV | Exportovat CSV |
| View Only Mode | Pouze pro čtení |
| Business Owner | Vlastník |
| Deputy | Zástupce |
| Technical Lead | Technický správce |
| Department | Útvar |
| Status | Stav |
| Classification | Klasifikace |
| Override | Přepsat klasifikaci |
| Showing 1 to 20 of 128 entries | Zobrazeno 1–20 z 128 záznamů |
| Previous / Next | Předchozí / Další |
| Registry Management | Správa registru |

---

## Mimo rozsah této specifikace

### Odloženo do `classification-advisor`

Tyto věci zadání vyžaduje, ale patří do navazující specifikace.

| Prvek | Kam patří |
|---|---|
| Klasifikační dotazník | `classification-advisor` |
| Doporučení klasifikace modelem a jeho zdůvodnění | `classification-advisor` |
| Abstrakční vrstva pro volání modelu | `classification-advisor` |
| Log volání modelu s modelem, časem a tokeny | `classification-advisor` |
| Anonymizace osobních údajů před zpracováním | `classification-advisor` |
| Retence logů volání modelu | `classification-advisor` |
| Hodnoty `AI` a `AI_OVERRIDDEN` v Classification_Source | `classification-advisor` |

### Vědomý dluh

| Prvek | Rozhodnutí | Důvod |
|---|---|---|
| MFA | neimplementovat | Patří do Identity_Provider. Implementace v aplikaci by duplikovala odpovědnost a oslabila bezpečnostní model |
| Reálný Entra ID tenant | neimplementovat | Vyžaduje firemní tenant. Nahrazeno mockem s totožným OIDC rozhraním, výměna je změna konfigurace |
| Notifikace a nápověda v horní liště | neimplementovat | Vyžaduje notifikační kanál a stavovou správu přečtení, bez přínosu pro hodnocené oblasti |
| Sekce Nastavení | neimplementovat | Konfigurace je řešena proměnnými prostředí, ne rozhraním |
| Avatary uživatelů | neimplementovat | Vyžaduje úložiště obrázků nebo napojení na profilovou fotku v IdP. Nahrazeno iniciálami |
| Správa taxonomie útvarů | neimplementovat | Department je uzavřený výčet v konfiguraci, ne editovatelný registr |
| Monitoring plnění SLA | neimplementovat | Cíl dostupnosti se v jádře ani neeviduje. Bez měření by to byla jen deklarace |
| Hromadné operace nad výběrem záznamů | neimplementovat | Jednotlivý přepis roli Admin plně demonstruje. Hromadná varianta přidává práci bez nové vlastnosti |
| Citlivost dat (`Data_Class`) | odloženo | Karta Security & Privacy z mocku. Zadání ji nežádá. Přidání je jeden sloupec a jedno pole ve formuláři, lze doplnit kdykoli |
| Technická metadata (hosting, frameworky, cíl dostupnosti) | odloženo | Blok Technical Specifications z mocku. Zadání ho nežádá a bez měření je to jen deklarace |
| Archivace odděleně od stavu `Vyřazená` | neimplementovat | Dva koncepty pro jednu věc. Vyřazení je konec životního cyklu i spouštěč retence. Vyhrazeno roli Admin, aby uživatel nemohl sám nastartovat mazání svého záznamu |
| Verzování historie záznamu | neimplementovat | Audit_Log říká, co se změnilo, Classification_Log drží plnou historii klasifikace. Kompletní time-travel je nad rozsah |
| Fyzické mazání záznamů | neimplementovat | Registr je evidence. Odstranění je vyřazení, aby zůstala historie. Fyzicky maže jen retenční rutina |

---

## Rozhodnuto

| Otázka | Rozhodnutí | Důvod |
|---|---|---|
| Databáze | **PostgreSQL** jako samostatná služba v compose, port nepublikovaný | Registr je víceuživatelský a auditovaný; SQLite má jeden writer na celou databázi a auditní log je zápisově nejaktivnější tabulka. SQLite navíc vynucuje cizí klíče jen po nastavení `PRAGMA foreign_keys` na každém spojení a nemá typ pro čas s časovou zónou. Riziko selhání při startu se řeší healthcheckem a nepublikováním portu |
| Jazyk rozhraní | **Čeština**, bez výjimky | Interní česká aplikace. Závazný překlad je v R13 |
| Volitelná metadata | **Odloženo** | Pocházejí z mocku, ne ze zadání. Lze přidat později bez zásahu do modelu |
| Archivace | **Zrušena**, zůstává jen stav `Vyřazená` | Dva koncepty pro jednu věc. Vyřazení je vyhrazeno roli Admin a od jeho okamžiku běží retenční lhůta |

## Otevřené otázky

1. **Retenční lhůty.** Návrh: auditní záznamy 365 dní, vyřazené záznamy 730 dní.
2. **Výchozí filtr stavu.** Vyřazené záznamy jsou z výchozího výpisu skryté. Otázka je, zda má být ve filtru volba „Všechny včetně vyřazených", nebo jen samostatná volba „Vyřazená".
