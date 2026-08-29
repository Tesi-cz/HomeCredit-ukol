# Implementation Plan

REGINA — jádro evidence interních aplikací

## Overview

Postupná stavba serverem vykreslované aplikace: FastAPI, Jinja2, SQLAlchemy 2.0, Alembic, PostgreSQL, Dex jako poskytovatel identity. Vše běží přes `docker compose up`.

**Pořadí je záměrné.** Nejdřív běžící skořápka a nasazení, aby existovalo místo, kam přidávat. Pak doména a autorizace, protože na nich stojí každá obrazovka. Teprve pak obrazovky, každá jako svislý řez od routy po šablonu.

**Průběžné pravidlo.** Po každém dokončeném úseku musí `docker compose up` naběhnout a aplikace odpovídat na `/health`. Rozbitý stav se nepředává dál.

Úkoly označené `*` jsou testy. Testovací pokrytí se nehodnotí, ale úkol 6.3 je výjimka — je to důkaz bezpečnostního tvrzení a doporučuji ho neškrtat.

## Tasks

- [x] 1. Skořápka projektu a konfigurace
  - [x] 1.1 Vytvořit strukturu balíčků podle `design.md` sekce 3: `src/regina/` s podbalíčky `domain`, `db`, `repositories`, `services`, `auth`, `web`, plus `tests/` a `prompts/`
    - Prázdné `__init__.py` v každém balíčku
    - _Requirements: 12.1_

  - [x] 1.2 Napsat `config.py` pomocí `pydantic-settings`: `DATABASE_URL`, `SESSION_SECRET`, `SESSION_COOKIE_SECURE`, všechny `OIDC_*`, `DEPARTMENTS`, `RETENTION_*`, `LOG_LEVEL`, `SEED_ON_START`
    - Chybějící povinná hodnota musí shodit start s jasnou zprávou, ne se projevit později
    - Ověřeno 10 testy v `tests/test_config.py`
    - _Requirements: 1.6, 12.4_

  - [x] 1.3 Napsat `logging.py`: strukturované logování na standardní výstup, úroveň z konfigurace, korelační identifikátor požadavku
    - Zakázat logování hesel, tokenů, obsahu session, jmen a e-mailů
    - Access log uvicornu ztišen, protože obsahuje query string s vyhledávaným výrazem
    - _Requirements: 12.3, 12.10_

  - [x] 1.4 Napsat `main.py`: factory aplikace, registrace middleware, log startu, endpoint `GET /health` s kontrolou dostupnosti databáze
    - Health endpoint bez autentizace, neprozrazuje verze ani konfiguraci
    - Aplikace se nevytváří při importu; uvicorn ji spouští jako fabriku
    - _Requirements: 12.2, 12.3_

  - [x] 1.5 Vytvořit `requirements.txt` s přesně připnutými verzemi všech závislostí
    - Verze ověřené proti PyPI, instalace potvrzená ve venv
    - _Requirements: 12.7_

  - [x] 1.6 Dořešit zaseknutí testů zdravotního endpointu
    - Doplněn `connect_timeout` do engine, výchozí 5 s; v testech 1 s
    - Odhalilo to druhou chybu: testy validace konfigurace tiše procházely přes lokální `.env`, takže neověřovaly nic. Přidán `build_settings(env_file=None)`
    - _Requirements: 12.2_

- [x] 2. Nasazení a běhové prostředí
  - [x] 2.1 Napsat vícestupňový `Dockerfile`: node stupeň přeloží Tailwind do jednoho CSS, python stupeň nainstaluje připnuté závislosti a zkopíruje přeložené CSS
    - Aplikace neběží jako root, `.dockerignore` drží tajemství mimo build kontext
    - Fonty se kopírují z `brand-assets/fonts/`, žádný odkaz na CDN
    - _Requirements: 12.4, 13.9_

  - [x] 2.2 Napsat `docker-compose.yaml` se službami `db`, `dex`, `app`
    - `db` s pojmenovaným volume, healthcheckem a **bez publikovaného portu**
    - `app` s `depends_on: condition: service_healthy` na obě služby
    - Chybějící proměnná shodí `docker compose` s českou zprávou přes `${VAR:?…}`
    - _Requirements: 12.1_

  - [x] 2.3 Napsat `deploy/dex/config.yaml`: statické syntetické účty, klient pro REGINU
    - Tajemství klienta se čte z prostředí přes `secretEnv`, není v souboru
    - **Zjištěno:** issuer musí být tatáž adresa pro prohlížeč i pro aplikační kontejner. Řeší to `host.docker.internal` — Docker Desktop ho zapisuje do hosts na hostiteli a zároveň ho rozlišuje uvnitř kontejnerů. Ověřeno z obou stran, viz úkol 3
    - **Zjištěno:** Dex u statických účtů nevydává claim se skupinami, takže roli Admin přiděluje seed a lokální správa rolí. Čtení claimu je přesto implementované kvůli záměně za Entra ID (R11.6)
    - _Requirements: 1.1, 12.11_

  - [x] 2.4 Napsat `.env.example` se všemi proměnnými, vysvětlením a bez skutečných hodnot; ověřit, že `.env` je ignorovaný
    - _Requirements: 12.5, 12.6_

- [x] 3. Kontrolní bod — aplikace naběhne
  - **Splněno.** `docker compose up` zvedá tři služby, všechny `healthy`.
  - `GET /health` vrací `200` a `{"status":"ok","database":"up"}`.
  - Discovery dokument Dexu je dostupný z hostitele i z aplikačního kontejneru se shodným issuerem.
  - Logy jsou strukturovaný JSON, korelační identifikátor je v odpovědi i v logu.
  - Databáze zatím nemá schéma, to je záměr — přijde v úkolu 4.
  - _Requirements: 12.1, 12.2_

- [x] 4. Databázové schéma
  - [x] 4.1 Napsat modely SQLAlchemy podle `database.md`: `users`, `applications`, `classification_log`, `audit_log`
    - Výčty jako `text` s `CHECK` constraintem formulovaným jako rozšiřitelný seznam povolených hodnot, ne nativní `ENUM`
    - _Requirements: 5.4_

  - [x] 4.2 Doplnit constrainty vynucené databází: povinný důvod u `source = ADMIN_OVERRIDE`, `decommissioned_at` vyplněné právě tehdy když stav je `DECOMMISSIONED`, unikátní `lower(name)`, unikátní `lower(email)`
    - _Requirements: 5.8, 7.2, 7.3_

  - [x] 4.3 Doplnit chování cizích klíčů: kaskáda u `classification_log.application_id`, `RESTRICT` u vazeb na osoby, `audit_log.entity_id` **bez** cizího klíče
    - _Requirements: 9.7, 9.8_

  - [x] 4.4 Vytvořit indexy podle `database.md` sekce 12, včetně částečného indexu na nevyřazené záznamy
    - _Requirements: 3.2, 3.3, 3.9_

  - [x] 4.5 Nastavit Alembic a vytvořit úvodní revizi; migrace se aplikují automaticky při startu kontejneru před spuštěním serveru
    - Bez ručního migračního kroku
    - _Requirements: 12.8_

- [x] 5. Doména
  - [x] 5.1 Napsat `domain/enums.py`: strojové kódy pro roli, zdroj role, stav životního cyklu, klasifikaci, zdroj klasifikace, typ auditní akce
    - Přesně podle tabulky v `database.md` sekce 7
    - _Requirements: 5.4_

  - [x] 5.2 Napsat `domain/labels.py`: mapování strojových kódů na české popisky, včetně popisků z tabulky v R13
    - Žádný český text v databázi, žádný anglický popisek v rozhraní
    - _Requirements: 13.1, 13.11_

  - [x] 5.3 Napsat `domain/rules.py` jako čisté funkce bez závislostí: `can_edit`, `can_set_classification`, `can_override_classification`, `can_decommission`, `can_read_audit`, `can_export`, `can_manage_roles`
    - `can_edit` porovnává identifikátory osob, nikdy jména
    - _Requirements: 2.1, 2.2, 2.6_

  - [ ]* 5.4 Napsat testy pravidel proti capability matrix z R2, bez databáze a bez HTTP
    - Pro každý řádek matrix jeden test povolení a jeden zamítnutí
    - _Requirements: 2.1, 2.2_

- [x] 6. Identita, session a autorizační guardy
  - [x] 6.1 Napsat `auth/oidc.py`: klient nad Authlib, endpointy výhradně z discovery dokumentu, konfigurovatelné názvy claimů pro e-mail, jméno a roli
    - Žádná URL poskytovatele v kódu
    - _Requirements: 1.1, 1.4, 1.5_

  - [x] 6.2 Napsat `auth/session.py` a routy `GET /login`, `GET /auth/callback`, `POST /odhlaseni`
    - Ověření podpisu, issuera, audience a expirace ID tokenu
    - Párování osoby podle `oidc_subject`, jinak podle e-mailu s doplněním subjektu, jinak nový řádek s rolí `USER`
    - Session cookie `HttpOnly`, `SameSite=Lax`, `Secure` z konfigurace; bez access a refresh tokenů
    - Audit `SIGN_IN` a `SIGN_OUT`
    - _Requirements: 1.2, 1.3, 1.4, 1.8, 1.9, 11.7_

  - [x] 6.3 Napsat `auth/deps.py`: FastAPI závislosti volající funkce z `domain/rules.py`, plus výjimka `AuthorizationError` a globální handler, který zapíše audit `ACCESS_DENIED` a vrátí stránku 403
    - Odepření se loguje na jediném místě, ne v každé routě
    - _Requirements: 2.2, 2.3, 8.1_

  - [x] 6.4 Zavést ochranu formulářů tokenem CSRF vázaným na session pro každý `POST`
    - _Requirements: 2.2_

  - [ ]* 6.5 Napsat testy autorizace přes HTTP: přímý `POST` na cizí záznam je zamítnut, i když v rozhraní tlačítko není
    - Toto je důkaz tvrzení „autorizace je na backendu, ne skrytím prvku"
    - _Requirements: 2.2, 2.3, 2.5_

- [x] 7. Kontrolní bod — přihlášení funguje
  - Přihlášení přes Dex projde, session drží, odhlášení funguje, obojí je v auditní tabulce. Chráněná cesta bez přihlášení přesměruje na login.
  - _Requirements: 1.1, 1.3, 1.8_

- [ ] 8. Základ rozhraní
  - [ ] 8.1 Nastavit Tailwind: `package.json`, `tailwind.config.js` s barvami, typografií a rozestupy z mocků a z `.kiro/steering/brand-guidelines.md`
    - _Requirements: 13.4_

  - [x] 8.2 Zkopírovat do statických zdrojů woff2 fonty z `brand-assets/fonts/` a podsoubor ikonového fontu; odstranit veškeré odkazy na CDN
    - Rozhraní se musí vykreslit správně bez připojení k internetu
    - _Requirements: 13.9_

  - [ ] 8.3 Napsat základní šablonu: tmavý sidebar s názvem REGINA a podtitulem „REGistr INterních Aplikací", navigace Moje aplikace / Registr / Uživatelé / Auditní logy, primární akce Nová aplikace, blok přihlášené osoby s iniciálami a odhlášením, horní lišta s názvem sekce a hledáním, patička
    - Položky Uživatelé a Auditní logy se roli User nevykreslují, ale cesty jsou chráněné na backendu
    - Šablona volá **tytéž** funkce z `domain/rules.py` jako guardy
    - _Requirements: 2.5, 13.5, 13.6, 13.7_

  - [x] 8.4 Napsat komponenty šablon: badge stavu, badge klasifikace včetně varianty „Neklasifikováno", badge role, prázdný stav, stránkování, hlášení o výsledku akce, stránky 403 a 404
    - Chybové stránky nesmí ukazovat stack trace ani konfiguraci
    - _Requirements: 3.8, 13.3, 13.8_

  - [x] 8.5 Nastavit `lang="cs"`, formát datumu DD.MM.YYYY a responzivní chování od 1024 px s balením sidebaru
    - _Requirements: 13.2, 13.3, 13.10_

- [x] 9. Syntetická data
  - [x] 9.1 Napsat `seed.py`: přibližně dvacet osob s českými jmény a pozicemi, jedna ve roli Admin odpovídající demo účtu v Dexu
    - _Requirements: 12.9, 12.11_

  - [x] 9.2 Doplnit přibližně třicet záznamů aplikací přes všechny útvary, stavy a klasifikace, včetně několika neklasifikovaných a několika vyřazených; u části doplnit historii klasifikace včetně přepisu správcem s důvodem
    - Naplnění musí být idempotentní — opakovaný start data nezduplikuje
    - Žádné skutečné jméno, e-mail ani telefon
    - _Requirements: 12.9, 12.11_

- [x] 10. Auditní služba
  - [x] 10.1 Napsat `services/audit.py` s jednou funkcí pro zápis záznamu; ukládá snapshot jména a e-mailu aktéra a v `changed_fields` **jen názvy** změněných atributů
    - Zápis probíhá ve stejné transakci jako změna, aby nemohla vzniknout změna bez auditu ani naopak
    - Žádná IP adresa, žádný user agent
    - _Requirements: 8.1, 8.2, 8.3, 8.6_

  - [x] 10.2 Zavést pravidlo, že aplikace nikdy nevydá `UPDATE` ani `DELETE` nad auditní tabulkou; jedinou výjimkou je retenční rutina
    - _Requirements: 8.5_

- [x] 11. Registr — tabulkový výpis
  - [x] 11.1 Napsat repozitář a dotaz pro výpis: vyhledávání podle názvu bez ohledu na velikost písmen, filtry útvar / klasifikace / stav, řazení podle názvu, stránkování s celkovým počtem
    - Vše provádí databáze, odpověď obsahuje jen požadovanou stránku
    - Řazení podle **povoleného seznamu sloupců**, nikdy podle názvu z parametru URL
    - Výchozí filtr vylučuje vyřazené záznamy
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.9_

  - [x] 11.2 Napsat routu a šablonu `/registr` podle `ui.md` sekce 5: zebra striping, sticky hlavička, pruh filtrů, text „Zobrazeno 1–20 z 128 záznamů"
    - Sloupce: Název, Vlastník, Útvar, Klasifikace, AI model, Stav, Akce
    - Akce Přepsat klasifikaci a Vyřadit pouze roli Admin
    - Výčtové hodnoty vykreslené jako české popisky, nikdy jako strojové kódy
    - _Requirements: 3.1, 3.7, 3.8_

- [x] 12. Moje aplikace — karty
  - [x] 12.1 Doplnit dotaz na záznamy, kde je přihlášená osoba členem odpovědné trojice
    - _Requirements: 3.10_

  - [x] 12.2 Napsat routu a šablonu `/moje` podle `ui.md` sekce 4: hero s vyhledáváním a tlačítkem Registrovat novou aplikaci, mřížka karet 3/2/1 sloupce
    - Karta: ikona, badge stavu, badge klasifikace, název, zkrácený popis, datum poslední úpravy, odkaz Detail
    - Prázdný stav s vysvětlením a výzvou k registraci
    - Nastavit `/moje` jako cíl po přihlášení a přesměrovat na ni z `/`
    - _Requirements: 3.10, 3.11, 3.12_

- [x] 13. Zápis klasifikace
  - [x] 13.1 Napsat `services/classification.py` s funkcí `write_classification` jako **jediným** místem, které smí měnit `applications.classification`
    - V jedné transakci vloží řádek do `classification_log` s předchozí hodnotou a nastaví sloupec na záznamu
    - Zapisuje audit
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 13.2 Doplnit přepis správcem se `source = ADMIN_OVERRIDE` a povinným důvodem; odmítnout prázdný důvod a odmítnout požadavek od roli User
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.6, 7.7_

  - [ ]* 13.3 Napsat testy invariantu: po každém zápisu odpovídá `applications.classification` poslednímu řádku logu; přepis bez důvodu odmítne aplikace i databáze
    - _Requirements: 6.2, 7.2, 7.3_

- [x] 14. Registrace a editace záznamu
  - [x] 14.1 Napsat validační modely pro vstup formuláře: povinná pole název, vlastník, technický správce, útvar, stav; kontrola výčtů na backendu; kontrola duplicity názvu
    - _Requirements: 5.2, 5.3, 5.4, 5.8_

  - [x] 14.2 Napsat `services/applications.py`: vytvoření a editace záznamu s auditním zápisem a názvy změněných atributů
    - Vlastník předvyplněn tvůrcem, lze změnit před uložením
    - Klasifikaci zapsat přes `write_classification`, nikdy přímo
    - _Requirements: 5.1, 5.5, 5.6, 5.7, 5.9, 5.10_

  - [x] 14.3 Napsat šablonu průvodce podle `ui.md` sekce 6: tři kroky Základní údaje / Odpovědnost / Provoz a klasifikace, ukazatel průběhu z mocku, bez sidebaru
    - Kroky se přepínají v prohlížeči, záznam vzniká **jediným** odesláním na konci
    - V kroku 3 nechat pravý sloupec prázdný jako vyhrazené místo pro budoucí AI panel
    - Osoby se vybírají z adresáře, ne psaním jména
    - Stav Vyřazená není ve výběru pro roli User
    - Chyby validace u konkrétních polí, ne jako jedna hláška
    - _Requirements: 5.3, 5.5, 5.6, 5.12_

  - [x] 14.4 Napsat obrazovku editace nad stejnou šablonou, chráněnou `can_edit`
    - _Requirements: 5.10_

- [x] 15. Detail záznamu
  - [x] 15.1 Napsat routu a šablonu `/registr/{id}` podle `ui.md` sekce 7: drobenka, hlavní karta, odpovědnost s pozicemi, klasifikace se zdrojem a datem, historie klasifikace od nejnovějšího, AI model
    - Indikátor „Pouze pro čtení" a skryté akce, když osoba nemá právo editovat
    - U přepisu správcem zobrazit důvod
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10_

  - [x] 15.2 Doplnit akci vyřazení: nastaví stav, `decommissioned_at` a `decommissioned_by`; návrat ze stavu oba sloupce vyprázdní; obojí jen roli Admin
    - _Requirements: 5.11, 5.12, 5.13, 5.14_

- [x] 16. Kontrolní bod — evidence je použitelná
  - Uživatel se přihlásí, vidí své aplikace, založí novou, upraví ji, nastaví klasifikaci. Správce vidí celý registr, přepíše klasifikaci s důvodem, vyřadí záznam. Uživatel se na cizí záznam dostane jen pro čtení a přímý `POST` mu neprojde.
  - _Requirements: 2.2, 3.10, 5.1, 6.1, 7.1_

- [x] 17. Auditní logy a správa uživatelů
  - [x] 17.1 Napsat routu a šablonu `/audit` podle `ui.md` sekce 9: sloupce Čas, Aktér, Akce, Objekt, Popis, filtry podle akce, aktéra a času, stránkování
    - Nad tabulkou informace, že záznamy nelze měnit ani mazat a podléhají retenci
    - _Requirements: 8.4, 8.7_

  - [x] 17.2 Napsat `services/users.py` a obrazovku `/uzivatele` podle `ui.md` sekce 8: jméno, e-mail, pozice, role, zdroj role, přepnutí role
    - Správce si nemůže odebrat vlastní roli; v systému musí zůstat alespoň jeden správce
    - Obrazovka nezakládá ani nemaže identity, což je na ní uvedeno textem
    - Změna role zapisuje audit
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

- [x] 18. Export CSV
  - [x] 18.1 Napsat `services/export.py`: export registru a auditního logu, kódování UTF-8, výčty jako české popisky
    - Při aktivních filtrech se exportuje filtrovaná množina, ne celý datový soubor
    - Chráněno `can_export`, roli User zamítnuto
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 19. Retence
  - [x] 19.1 Napsat `services/retention.py`: asynchronní úloha spuštěná při startu, běžící v konfigurovatelném intervalu, bez ručního kroku
    - Hranice pro záznamy se počítá z `decommissioned_at`, nikdy z času poslední úpravy
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 19.2 Doplnit logování každého běhu: kategorie, hranice, počet smazaných řádků
    - _Requirements: 9.5_

  - [ ]* 19.3 Napsat testy retence: záznam za hranicí se maže, jeho historie klasifikace odchází kaskádou, jeho auditní záznamy zůstávají
    - _Requirements: 9.6, 9.7_

- [x] 20. Dokumentace
  - [x] 20.1 Napsat `README.md`: popis, spuštění na jeden příkaz, demo účty s upozorněním na lokální určení, použitý model a Master Prompt, klasifikace samotné REGINY se zdůvodněním
    - _Requirements: 12.1_

  - [x] 20.2 Doplnit do README retenční lhůty s odůvodněním a vysvětlení, proč se neimplementuje MFA
    - _Requirements: 1.7, 9.6_

  - [x] 20.3 Doplnit do README záměnu poskytovatele identity za Microsoft Entra ID jako tabulku proměnných, bez zásahu do kódu
    - _Requirements: 1.5_

  - [x] 20.4 Doplnit do README sekci vědomého dluhu z `requirements.md`, včetně odloženého našeptávače a jeho zdůvodnění
    - _Requirements: 12.1_

  - [x] 20.5 Naplnit `prompts/` klíčovými prompty a uložit schválené mocky do `design/mocks/`
    - _Requirements: 12.1_

- [x] 21. Závěrečné ověření
  - [x] 21.1 Ověřit čistý start: smazat volumes, zkopírovat `.env.example` do `.env`, spustit `docker compose up` a projít celý tok bez jediného ručního kroku
    - _Requirements: 12.1, 12.8, 12.9_

  - [x] 21.2 Ověřit běh bez internetu: odpojit síť a zkontrolovat, že se rozhraní vykreslí správně včetně fontů a ikon
    - _Requirements: 13.9_

  - [x] 21.3 Projít repozitář na tajemství: žádné hodnoty v kódu, v image ani v historii; `.env` ignorovaný; závislosti připnuté
    - _Requirements: 12.4, 12.5, 12.6, 12.7_

  - [x] 21.4 Projít rozhraní na anglické popisky a na strojové kódy prosakující místo českých popisků
    - _Requirements: 13.1, 13.11_
