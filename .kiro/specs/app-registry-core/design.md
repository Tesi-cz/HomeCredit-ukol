# Design Document

REGINA — jádro evidence interních aplikací

## Účel dokumentu

Technický návrh pro `requirements.md` a `database.md` této specifikace. Popisuje **jak** se systém postaví: vrstvy, autentizace, autorizace, datový přístup, HTTP rozhraní, nasazení.

Obrazovky a jejich obsah jsou v `ui.md`. Datový model v `database.md`.

Jazykový model v tomto rozsahu nevystupuje. Sekce 15 popisuje, kam se našeptávač připojí.

---

## 1. Architektonický přehled

Serverem vykreslovaná aplikace ve čtyřech vrstvách. Závislosti míří vždy dovnitř, nikdy naopak.

```
web        →  HTTP, šablony, formuláře, statické zdroje
services   →  business operace, transakce, audit
repositories → dotazy a zápisy do databáze
domain     →  výčty, pravidla, popisky. Bez závislostí
```

**Proč serverem vykreslované rozhraní a ne SPA.** Odděleným frontendem by vznikl druhý build, druhá sada závislostí a nutnost ověřovat token na dvou místech. Zadání hodnotí, že aplikace naběhne na první pokus, a ne bohatost rozhraní. Šablony na serveru navíc řeší požadavek R13.9 na běh bez internetu triviálně: veškeré HTML vzniká na serveru a statické zdroje se servírují z image.

**Proč čtyři vrstvy a ne dvě.** Klíčové je oddělení `domain` bez závislostí. Autorizační pravidla jsou pak čisté funkce, které lze testovat bez databáze a bez HTTP, a **stejné funkce používá backend guard i šablona** — viz sekce 4.3.

---

## 2. Technologický základ

| Vrstva | Volba | Proč |
|---|---|---|
| Jazyk | Python 3.12 | |
| Web framework | FastAPI | Nativní dependency injection, na které stojí autorizace. Typované modely pro validaci formulářů |
| Šablony | Jinja2 | |
| ORM | SQLAlchemy 2.0, typovaný styl | |
| Migrace | Alembic | Viz sekce 6.4 |
| Databáze | PostgreSQL | Rozhodnutí a zdůvodnění v `database.md` sekce 0 |
| OIDC klient | Authlib | Podporuje discovery, takže se nikam nezapisují konkrétní endpointy |
| Poskytovatel identity pro lokální běh | Dex | Viz sekce 4.1 |
| Konfigurace | pydantic-settings | Typované čtení proměnných prostředí, selhání při startu na chybějící hodnotě |
| Session | Podepsaná cookie, `itsdangerous` | Bez tabulky sessions |
| CSS | Tailwind, přeložený při buildu | Mocky jsou napsané v Tailwindu. Překlad při buildu odstraní CDN |
| Testy | pytest, httpx | |

**Verze.** Každá závislost se připne na přesnou verzi do `requirements.txt` *(R12.7)*. Konkrétní čísla se doplní při implementaci proti PyPI, ne odhadem v návrhu.

---

## 3. Struktura repozitáře

```
.
├─ docker-compose.yaml
├─ Dockerfile
├─ .env.example
├─ .gitignore
├─ README.md
├─ requirements.txt          připnuté verze
├─ package.json              pouze pro build CSS
├─ tailwind.config.js
├─ alembic.ini
├─ prompts/                  klíčové prompty
├─ design/mocks/             schválené HTML mocky
├─ deploy/dex/config.yaml    konfigurace mock poskytovatele identity
├─ src/regina/
│  ├─ main.py                složení aplikace, middleware, startup
│  ├─ config.py              nastavení z prostředí
│  ├─ logging.py             strukturované logování
│  ├─ domain/
│  │  ├─ enums.py            strojové kódy
│  │  ├─ labels.py           české popisky
│  │  └─ rules.py            autorizační pravidla, čisté funkce
│  ├─ db/
│  │  ├─ session.py
│  │  ├─ models/
│  │  └─ migrations/versions/
│  ├─ repositories/
│  ├─ services/
│  │  ├─ applications.py
│  │  ├─ classification.py
│  │  ├─ users.py
│  │  ├─ audit.py
│  │  ├─ export.py
│  │  └─ retention.py
│  ├─ auth/
│  │  ├─ oidc.py             klient nezávislý na poskytovateli
│  │  ├─ session.py
│  │  └─ deps.py             FastAPI závislosti pro guardy
│  ├─ web/
│  │  ├─ routes/
│  │  ├─ templates/
│  │  └─ static/{css,fonts}
│  └─ seed.py
└─ tests/
```

---

## 4. Identita a oprávnění

### 4.1 Poskytovatel identity pro lokální běh

**Volba: Dex** jako služba v compose.

Dex je malý OIDC poskytovatel se statickými uživateli v konfiguračním souboru. Nabízí skutečný discovery endpoint, takže náš klient mluví reálným protokolem, ne atrapou.

**Proč ne vlastní mock.** Vlastní falešný login by znamenal, že náš kód nikdy nemluvil s pravým OIDC. Záměna za Entra ID by pak byla přepis, ne změna konfigurace — přesně to, co má zadání vyloučit.

**Proč ne Keycloak.** Realističtější, ale startuje desítky sekund a je řádově těžší. „Naběhne na první pokus" je hodnocená položka.

**Demo účty.** Uživatelé a jejich hesla existují v konfiguraci Dexu, ne v naší databázi. Naše aplikace nemá tabulku hesel *(R1.2)*. Přihlašovací údaje demo účtů jsou syntetické a v README označené jako určené výhradně pro lokální běh.

### 4.2 Přihlašovací tok

```
1. Nepřihlášený požadavek           → redirect na /login
2. GET /login                        → redirect na authorization endpoint z discovery
3. Poskytovatel ověří uživatele      (heslo ani MFA nás nezajímá)
4. GET /auth/callback?code=…         → výměna kódu za tokeny
5. Ověření ID tokenu                 podpis, issuer, audience, expirace
6. Párování osoby                    podle oidc_subject, jinak podle e-mailu
7. Zápis podepsané session cookie    subject, jméno, e-mail, role
8. Audit SIGN_IN                     → redirect na /moje
```

Krok 6 detailně: hledá se `users` podle `oidc_subject`. Když není, hledá se podle e-mailu z claimu a při shodě se `oidc_subject` doplní. Když není ani to, vznikne nový řádek s rolí `USER`. Tím lze osobu zapsat do odpovědné trojice dřív, než se přihlásí *(R11.7)*.

**Odhlášení.** Session se zneplatní, zapíše se audit `SIGN_OUT` *(R1.8)*. Odhlášení u poskytovatele se neprovádí, protože jde o oddělenou odpovědnost — v README je to uvedené jako vědomé omezení.

**Co session obsahuje.** Pouze subject, jméno, e-mail a roli. Žádný access ani refresh token — nepotřebujeme mluvit s žádným API poskytovatele. Cookie je `HttpOnly`, `SameSite=Lax`, `Secure` řízené konfigurací.

### 4.3 Autorizace

Jádro celého návrhu. Pravidla jsou čisté funkce v `domain/rules.py`, bez databáze a bez HTTP:

```python
def can_edit(actor, app) -> bool
def can_set_classification(actor, app) -> bool
def can_override_classification(actor) -> bool
def can_decommission(actor) -> bool
def can_read_audit(actor) -> bool
def can_export(actor) -> bool
def can_manage_roles(actor) -> bool
```

`can_edit` porovnává `actor.id` proti `owner_user_id`, `deputy_user_id` a `tech_admin_user_id`, nebo vrací true pro roli Admin. Nikdy neporovnává jména *(R2.6)*.

**Jedno pravidlo, dvě použití.** Tytéž funkce volá:

1. **FastAPI závislost** před vykonáním operace — to je vynucení *(R2.2)*
2. **Šablona** při rozhodování, zda vykreslit tlačítko — to je pohodlnost *(R2.5)*

Rozhraní se tak nemůže rozejít s vynucením. Nemůže nastat, že tlačítko je vidět a operace selže, ani že tlačítko chybí, ačkoli operace je povolená. A hlavně: skrytí tlačítka není nikdy jediná ochrana.

**Zamítnutí.** Guard vyhodí `AuthorizationError`. Globální handler zapíše audit `ACCESS_DENIED` *(R2.3)* a vrátí stránku 403. Odepření se tedy loguje na jediném místě, ne v každé route.

**Capability matrix z R2 je přímo testovaná.** Pro každý řádek existuje test, který ověří, že operace roli Admin projde a roli User se zamítne. To je jediná část testů, kterou považuji za povinnou — je to důkaz bezpečnostního tvrzení.

### 4.4 Záměna za Microsoft Entra ID

Výhradně konfigurací *(R1.5)*. Kód nezná žádnou URL poskytovatele — vše se čte z discovery dokumentu.

| Proměnná | Lokálně (Dex) | Entra ID |
|---|---|---|
| `OIDC_ISSUER` | `http://dex:5556/dex` | `https://login.microsoftonline.com/{tenant}/v2.0` |
| `OIDC_CLIENT_ID` | z konfigurace Dexu | ID registrované aplikace |
| `OIDC_CLIENT_SECRET` | z `.env` | z `.env` |
| `OIDC_SCOPES` | `openid profile email groups` | `openid profile email` |
| `OIDC_ROLE_CLAIM` | `groups` | `roles` |
| `OIDC_ADMIN_ROLE_VALUE` | `regina-admins` | název app role |
| `OIDC_EMAIL_CLAIM` | `email` | `email` nebo `preferred_username` |
| `OIDC_NAME_CLAIM` | `name` | `name` |

Konfigurovatelné názvy claimů jsou to, co záměnu skutečně umožňuje. Entra pojmenovává role jinak než Dex; kdyby byl název claimu zadrátovaný v kódu, byla by výměna přepis.

**MFA se neimplementuje** *(R1.7)*. Řeší ho poskytovatel identity. Kdybychom ho vestavěli do aplikace, duplikovali bychom odpovědnost a oslabili model — aplikace by musela držet druhý faktor, tedy další tajemství.

---

## 5. Business operace

Každá operace je metoda služby, běží v jedné transakci a zapisuje audit.

| Operace | Guard | Zápisy |
|---|---|---|
| Výpis registru | přihlášení | — |
| Výpis mých aplikací | přihlášení | — |
| Detail záznamu | přihlášení | — |
| Vytvoření záznamu | přihlášení | `applications`, volitelně `classification_log`, `audit_log` |
| Editace záznamu | `can_edit` | `applications`, `audit_log` |
| Zápis klasifikace | `can_set_classification` | `classification_log`, `applications.classification`, `audit_log` |
| Přepis klasifikace | `can_override_classification` | totéž se `source=ADMIN_OVERRIDE` a důvodem |
| Vyřazení záznamu | `can_decommission` | `applications`, `audit_log` |
| Výpis auditu | `can_read_audit` | — |
| Export CSV | `can_export` | — |
| Změna role | `can_manage_roles` | `users`, `audit_log` |

### 5.1 Jediné místo, kde se mění klasifikace

`database.md` zavádí invariant: zápis do `classification_log` a aktualizace `applications.classification` probíhá v jedné transakci. Návrh ho drží tím, že existuje **jediná** funkce, která na ten sloupec smí sáhnout:

```python
def write_classification(session, app, new_level, actor, source, reason=None) -> None
```

Funkce v jedné transakci vloží řádek do `classification_log` s předchozí hodnotou a nastaví `applications.classification`. Vytvoření záznamu s klasifikací, editace i přepis správcem procházejí tudy.

Povinnost důvodu u `ADMIN_OVERRIDE` je navíc `CHECK` constraint v databázi, takže obejití aplikační cesty stejně skončí chybou.

### 5.2 Auditní zápis

`audit.py` nabízí jednu funkci, kterou služby volají ve stejné transakci jako změnu:

```python
def record(session, actor, action, entity_type=None, entity_id=None,
           summary="", changed_fields=None) -> None
```

Ukládá snapshot jména a e-mailu aktéra *(R8.3)*. `changed_fields` obsahuje **jen názvy** změněných atributů, nikoli hodnoty — jinak by se do auditu dostaly osobní údaje z odpovědné trojice *(R8.6, R12.10)*.

Audit je ve stejné transakci jako změna záměrně: nemůže vzniknout změna bez auditního záznamu ani naopak.

### 5.3 Vyřazení a návrat

Vyřazení nastaví `lifecycle_state` na `DECOMMISSIONED`, doplní `decommissioned_at` a `decommissioned_by`. Návrat oba sloupce vyprázdní *(R5.14)*, takže retenční lhůta začne znovu až při dalším vyřazení.

Obojí je vyhrazeno roli Admin, protože vyřazení startuje budoucí fyzické smazání záznamu.

---

## 6. Datová vrstva

### 6.1 Repozitáře

Jeden repozitář na agregát. Služby nikdy nepíšou SQL ani nedrží dotazy — díky tomu jsou testovatelné proti falešnému repozitáři.

### 6.2 Dotaz na výpis registru

Filtrování, řazení, vyhledávání a stránkování se skládají na jednom místě a provádí je databáze *(R3.6)*:

- základ: `WHERE lifecycle_state <> 'DECOMMISSIONED'`, pokud filtr stavu neurčí jinak
- vyhledávání: `lower(name) LIKE lower(:q)` s escapováním zástupných znaků
- filtry: rovnost na `department`, `classification`, `lifecycle_state`
- řazení: povolený seznam sloupců, nikdy název sloupce z parametru URL
- stránkování: `LIMIT`/`OFFSET` plus `COUNT` pro celkový počet

**Řazení podle povoleného seznamu** je bezpečnostní opatření: název sloupce nelze parametrizovat, takže jeho vložení z URL by bylo místo pro SQL injection.

### 6.3 Transakce

Jedna transakce na požadavek, otevřená FastAPI závislostí. Commit na konci úspěšného zpracování, rollback při výjimce. Služby ji nespravují — jen do ní zapisují.

### 6.4 Schéma a migrace

Alembic. Migrace se aplikují **automaticky při startu kontejneru**, před spuštěním serveru *(R12.8)*.

**Proč Alembic a ne `create_all()`.** Sám bych u nového projektu zvažoval jednodušší cestu, ale máme konkrétní důvod: `database.md` sekce 9 plánuje, že našeptávač přidá dvě tabulky, jeden nullable sloupec a rozšíří dva výčty. To je přesně jedna Alembic revize. Bez migračního nástroje by přidání našeptávače znamenalo smazat databázi.

Výčty jsou v databázi jako `text` s `CHECK` constraintem, ne jako nativní `ENUM` typ. Rozšíření výčtu je pak výměna constraintu místo `ALTER TYPE`, což je předvídatelnější.

---

## 7. HTTP rozhraní

Cesty česky bez diakritiky, konzistentně s českým rozhraním.

| Metoda | Cesta | Guard |
|---|---|---|
| GET | `/health` | veřejné |
| GET | `/login` | veřejné |
| GET | `/auth/callback` | veřejné |
| POST | `/odhlaseni` | přihlášení |
| GET | `/` → `/moje` | přihlášení |
| GET | `/moje` | přihlášení |
| GET | `/registr` | přihlášení |
| GET | `/registr/nova` | přihlášení |
| POST | `/registr` | přihlášení |
| GET | `/registr/{id}` | přihlášení |
| GET | `/registr/{id}/upravit` | `can_edit` |
| POST | `/registr/{id}` | `can_edit` |
| POST | `/registr/{id}/klasifikace` | `can_set_classification` |
| POST | `/registr/{id}/prepis-klasifikace` | `can_override_classification` |
| POST | `/registr/{id}/vyrazeni` | `can_decommission` |
| GET | `/registr/export.csv` | `can_export` |
| GET | `/uzivatele` | `can_manage_roles` |
| POST | `/uzivatele/{id}/role` | `can_manage_roles` |
| GET | `/audit` | `can_read_audit` |
| GET | `/audit/export.csv` | `can_export` |

**Zdravotní endpoint** je bez autentizace *(R12.2)*, ověří dostupnost databáze jednoduchým dotazem a vrátí stav služby. Neprozrazuje verze ani konfiguraci.

**Ochrana formulářů.** Každý `POST` nese CSRF token vázaný na session. Bez něj by přihlášený uživatel mohl být přinucen odeslat formulář z cizí stránky.

**Stavové kódy.** Úspěšný `POST` odpovídá přesměrováním, aby obnovení stránky operaci nezopakovalo. Chyba validace vrací formulář s vyplněnými hodnotami a chybami u polí.

---

## 8. Validace a chybové stavy

Vstupy formulářů se validují typovanými modely na vstupu do vrstvy služeb. Validace v prohlížeči je pouze pohodlnost.

| Situace | Chování |
|---|---|
| Chybí povinné pole | Formulář zpět, chyby u konkrétních polí *(R5.3)* |
| Neznámá hodnota výčtu | Odmítnutí, i když prohlížeč nabízel jen platné *(R5.4)* |
| Duplicitní název | Odmítnutí s vysvětlením *(R5.8)* |
| Přepis bez důvodu | Odmítnutí *(R7.3)* |
| Chybí právo | 403, audit `ACCESS_DENIED` |
| Neexistující záznam | 404 |
| Neošetřená výjimka | 500, zalogováno s identifikátorem, uživateli obecná zpráva bez detailů |

Chybové stránky nikdy neukazují stack trace ani obsah konfigurace.

---

## 9. Retence

Asynchronní úloha spuštěná při startu aplikace, běžící v konfigurovatelném intervalu *(R9.3)*. Bez plánovače navíc, bez ručního kroku.

Pro každou kategorii spočítá hranici, smaže překročené řádky a zaloguje kategorii, hranici a počet *(R9.5)*.

| Kategorie | Hranice od | Proměnná |
|---|---|---|
| Auditní záznamy | `occurred_at` | `RETENTION_AUDIT_LOG_DAYS` |
| Vyřazené záznamy | `decommissioned_at` | `RETENTION_DECOMMISSIONED_APP_DAYS` |

Smazání vyřazeného záznamu odstraní kaskádou jeho historii klasifikace, ale **auditní záznamy zůstávají** — `audit_log.entity_id` není cizí klíč *(R9.7)*.

**Vědomé omezení.** Při více instancích aplikace by úloha běžela vícekrát. Mazání je idempotentní, takže to nezpůsobí chybu, jen zbytečnou práci. Skutečné řešení je zámek v databázi nebo externí plánovač; pro jednu instanci je to nadbytečné a v README je to uvedené jako dluh.

---

## 10. Konfigurace

Vše z proměnných prostředí, čtené typovaně. **Chybějící povinná hodnota shodí start** s jasnou zprávou, místo aby se projevila později.

| Proměnná | Význam |
|---|---|
| `DATABASE_URL` | Připojení k databázi |
| `SESSION_SECRET` | Podpis session cookie |
| `SESSION_COOKIE_SECURE` | `true` v provozu, `false` pro lokální HTTP |
| `OIDC_*` | Viz tabulka v sekci 4.4 |
| `DEPARTMENTS` | Uzavřený výčet útvarů |
| `RETENTION_AUDIT_LOG_DAYS` | Výchozí 365 |
| `RETENTION_DECOMMISSIONED_APP_DAYS` | Výchozí 730 |
| `RETENTION_INTERVAL_HOURS` | Jak často běží úloha |
| `LOG_LEVEL` | |
| `SEED_ON_START` | Naplnění syntetickými daty |

`.env.example` obsahuje všechny proměnné s vysvětlením a **bez skutečných hodnot** *(R12.5)*. `.env` je v `.gitignore` *(R12.6)*.

---

## 11. Logování

Strukturované, na standardní výstup, aby si sběr logů řešilo prostředí.

Logují se: start aplikace, neošetřené chyby, přihlášení, odhlášení *(R12.3)*, běhy retence.

**Co se nikdy neloguje** *(R12.10)*: hesla, tokeny, obsah session cookie, e-maily a jména osob, celé řádky databáze. Přihlášení se loguje s identifikátorem osoby, ne s e-mailem — čitelná identita zůstává v auditním logu, který je chráněný rolí, ne v aplikačním logu, který může skončit kdekoli.

Každý požadavek nese korelační identifikátor, aby šla chyba dohledat bez ukládání jejího obsahu.

---

## 12. Statické zdroje a build rozhraní

Vícestupňový `Dockerfile`:

1. **Node stupeň** přeloží Tailwind podle `tailwind.config.js` do jednoho CSS souboru
2. **Python stupeň** nainstaluje připnuté závislosti a zkopíruje přeložené CSS

Do statických zdrojů se kopírují woff2 fonty z `brand-assets/fonts/` a podsoubor ikonového fontu. V hotové aplikaci nezůstane žádný odkaz na CDN *(R13.9)*.

Konfigurace Tailwindu přebírá barvy, typografii a rozestupy z mocků a z `.kiro/steering/brand-guidelines.md`.

---

## 13. Nasazení

`docker-compose.yaml` se třemi službami:

| Služba | Role | Publikovaný port |
|---|---|---|
| `db` | PostgreSQL, pojmenovaný volume, healthcheck | **žádný** |
| `dex` | Poskytovatel identity pro lokální běh | ano, kvůli přesměrování v prohlížeči |
| `app` | REGINA, `depends_on` databázi ve stavu healthy | ano |

**Databáze nepublikuje port.** Potřebuje ji jen aplikace na interní síti. Tím zmizí nejčastější příčina selhání u cizího člověka — obsazený port 5432.

Start aplikace: migrace → volitelné naplnění daty → server.

Celý běh je `docker compose up` po zkopírování `.env.example` do `.env` *(R12.1)*.

---

## 14. Syntetická data

Naplnění při prvním startu *(R12.9, R12.11)*, idempotentní — opakovaný start data nezduplikuje.

Vytvoří přibližně dvacet osob s českými jmény a pozicemi, jedna z nich má roli Admin a odpovídá demo účtu v Dexu. Dále přibližně třicet záznamů aplikací rozložených přes útvary, stavy a klasifikace, včetně několika **neklasifikovaných** a několika **vyřazených**, aby byly vidět i tyto stavy. U části záznamů historie klasifikace obsahuje přepis správcem s důvodem.

Všechna data jsou vymyšlená. Žádné skutečné jméno, e-mail ani telefon.

---

## 15. Kam se připojí našeptávač

Aditivně, viz `database.md` sekce 9.

| Vrstva | Doplnění |
|---|---|
| `domain` | Rozšíření výčtu `Classification_Source` o `AI` a `AI_OVERRIDDEN` |
| `db` | Alembic revize: dvě tabulky, nullable `suggestion_id`, výměna dvou `CHECK` constraintů |
| nová `llm/` | Abstrakční vrstva volání modelu, alespoň dvě implementace |
| `services` | Anonymizace, vyžádání doporučení, zápis logu volání |
| `web` | Dotazník, AI panel do vyhrazeného místa ve formuláři, výpis logů volání |

Podpis `write_classification` se **nemění**. Přidá se nepovinný parametr s odkazem na doporučení. Jádro tak zůstává beze změny a to je hlavní důvod, proč jsme rozdělení udělali.

---

## 16. Testy

Zadání testovací pokrytí nehodnotí, takže testy jsou cílené na místa, kde tvrdíme něco o bezpečnosti a integritě.

| Oblast | Co se ověřuje |
|---|---|
| Capability matrix | Každý řádek R2: povoleno pro Admin, zamítnuto pro User |
| Autorizace mimo rozhraní | Přímý `POST` na cizí záznam je zamítnut, i když v UI tlačítko není |
| Invariant klasifikace | Po zápisu odpovídá `applications.classification` poslednímu řádku logu |
| Povinný důvod | Přepis bez důvodu je odmítnut aplikací i databází |
| Retence | Záznam za hranicí se maže, jeho auditní záznamy zůstávají |
| Vyřazení | Pouze Admin; návrat vyprázdní časovou značku |
| Nemazatelnost auditu | Aplikace nenabízí cestu ke změně ani smazání záznamu |

---

## 17. Trasovatelnost

| Požadavek | Kde se realizuje |
|---|---|
| R1 Autentizace | `auth/oidc.py`, `auth/session.py`, sekce 4.1–4.4 |
| R2 Role a oprávnění | `domain/rules.py`, `auth/deps.py`, sekce 4.3 |
| R3 Seznam registru a mé aplikace | `repositories`, sekce 6.2, `ui.md` sekce 4 a 5 |
| R4 Detail aplikace | `web/routes`, `ui.md` sekce 7 |
| R5 Vytvoření a editace | `services/applications.py`, sekce 5 a 8 |
| R6 Zápis klasifikace | `services/classification.py`, sekce 5.1 |
| R7 Přepis správcem | tamtéž se `source=ADMIN_OVERRIDE` |
| R8 Auditní log | `services/audit.py`, sekce 5.2 |
| R9 Retence | `services/retention.py`, sekce 9 |
| R10 Export CSV | `services/export.py` |
| R11 Správa uživatelů | `services/users.py`, `ui.md` sekce 8 |
| R12 Provoz | Sekce 10, 11, 13, 14 |
| R13 Rozhraní a jazyk | `domain/labels.py`, sekce 12, `ui.md` |
