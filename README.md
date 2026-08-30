# REGINA — REGistr INterních Aplikací

Interní evidence aplikací vytvořených ve firmě. U každé aplikace se sleduje
název, odpovědná trojice (vlastník, zástupce, technický správce), útvar,
klasifikace velikosti (**MALÁ / STŘEDNÍ / VELKÁ**), stav životního cyklu a
použitý AI model. Nad registrem je vyhledávání, filtrování, auditní stopa a
retenční politika.

Přihlášení je výhradně přes externího poskytovatele identity (OIDC/OAuth2).
Aplikace neukládá žádná hesla. Autorizace je vynucená na backendu, ne skrytím
ovládacích prvků v rozhraní.

> **Povaha projektu.** Jde o domácí úkol / demo. Všechna data jsou syntetická —
> žádné skutečné jméno, e-mail ani telefon. Demo účty a jejich hesla jsou
> veřejná a určená výhradně pro lokální běh (viz [Demo účty](#demo-účty)).

---

## Obsah

- [Popis](#popis)
- [Spuštění na jeden příkaz](#spuštění-na-jeden-příkaz)
- [Demo účty](#demo-účty)
- [Použitý model a Master Prompt](#použitý-model-a-master-prompt)
- [AI funkce](#ai-funkce)
- [Klasifikace samotné REGINY](#klasifikace-samotné-reginy)
- [Retenční lhůty](#retenční-lhůty)
- [Záměna poskytovatele identity za Microsoft Entra ID](#záměna-poskytovatele-identity-za-microsoft-entra-id)
- [Proč se neimplementuje MFA](#proč-se-neimplementuje-mfa)
- [Vědomý dluh](#vědomý-dluh)

---

## Popis

REGINA (**REG**istr **IN**terních **A**plikací) eviduje aplikace, které vznikají
uvnitř firmy. Cílem je mít jedno místo, kde je vidět, kdo za kterou aplikaci
odpovídá, jak je významná a jak nakládá s daty.

Každý záznam v registru nese:

- **název** a **popis** aplikace,
- **odpovědnou trojici** — vlastníka, zástupce a technického správce,
- **útvar** (uzavřený výčet v konfiguraci),
- **klasifikaci velikosti** — `MALÁ`, `STŘEDNÍ`, nebo `VELKÁ`; klasifikaci vždy
  zadává člověk a každá její změna se ukládá do nemazatelné historie,
- **stav životního cyklu** — `Návrh` → `Ve vývoji` → `Testování` → `Produkce` →
  `Vyřazená`,
- **použitý AI model**, nebo informaci, že aplikace žádný nepoužívá.

Rozhraní je celé v češtině. Existují dvě role s odlišnými právy:

- **Uživatel** — čte celý registr a spravuje pouze záznamy, u kterých je členem
  odpovědné trojice,
- **Správce (Admin)** — spravuje všechny záznamy, přepisuje klasifikaci cizích
  záznamů s povinným důvodem, vyřazuje záznamy, spravuje role a čte auditní log.

Práva jsou vynucená na serveru u každé operace. Skrytí tlačítka v rozhraní je
jen pohodlnost navíc, nikdy jediná ochrana.

---

## Spuštění na jeden příkaz

Předpoklad: nainstalovaný **Docker** s **Docker Compose** (Docker Desktop na
Windows/macOS, nebo Docker Engine na Linuxu).

Potřebné jsou přesně dva kroky — zkopírovat vzor konfigurace a spustit compose:

**Windows (PowerShell):**

```powershell
Copy-Item .env.example .env
docker compose up
```

**Linux / macOS (bash):**

```bash
cp .env.example .env
docker compose up
```

To je vše. Žádný další ruční krok není potřeba. Při startu se automaticky:

1. zvedne databáze (PostgreSQL) a poskytovatel identity (Dex),
2. **aplikují migrace schématu** (`alembic upgrade head` v entrypointu kontejneru),
3. **naplní syntetická data** (řídí proměnná `SEED_ON_START`, ve vzoru zapnutá) —
   registr tedy není při hodnocení prázdný,
4. spustí se aplikační server.

Po naběhnutí je aplikace na:

```
http://localhost:8000
```

Kořenová adresa přesměruje na **/moje** (moje aplikace). Protože nejste
přihlášení, aplikace vás pošle na přihlášení přes Dex — přihlaste se některým
z [demo účtů](#demo-účty) níže.

**Health endpoint** je dostupný bez přihlášení a hlásí připravenost služby včetně
databáze:

```
http://localhost:8000/health
```

> **Poznámka k `.env`.** Vzor `.env.example` obsahuje hodnoty určené pro lokální
> běh. Soubor `.env` je v `.gitignore` a do repozitáře nepatří. Pro reálné
> nasazení se mění databázové přihlášení, `SESSION_SECRET` a celá skupina
> `OIDC_*`.

---

## Demo účty

Přihlašuje se přes lokální poskytovatel identity **Dex**. Účty existují pouze
v konfiguraci Dexu (`deploy/dex/config.yaml`), **ne** v databázi aplikace —
REGINA nemá žádnou tabulku hesel.

> ⚠️ **Upozornění.** Následující účty i jejich hesla jsou **syntetické, veřejné a
> určené výhradně pro lokální běh**. Nechrání žádná data a existují jen uvnitř
> demo kontejneru. **Nikdy je nepoužívejte v produkci.** V reálném nasazení
> přebírá přihlašování Microsoft Entra ID.

| Účel | E-mail | Heslo | Jméno | Role |
|---|---|---|---|---|
| Správce | `spravce@regina.local` | `demo-spravce` | Jana Nováková | Správce (Admin) |
| Uživatel | `uzivatel@regina.local` | `demo-uzivatel` | Petr Svoboda | Uživatel |

Účet **Jana Nováková** má roli Správce (přidělená seedem), takže na něm je vidět
správa registru, přepis klasifikace, vyřazování záznamů, správa rolí a auditní
logy. Účet **Petr Svoboda** ukazuje pohled běžného uživatele včetně režimu
„Pouze pro čtení" u cizích záznamů.

---

## Použitý model a Master Prompt

### Model použitý při vývoji

Řešení bylo postavené ve spolupráci s AI asistentem v prostředí Kiro.

- **Model:** Anthropic Claude (Sonnet)
- **Verze:** `<přesná verze modelu — doplní autor>`

> Přesné označení a verzi modelu doplňte podle prostředí, ve kterém byl úkol
> zpracován (v Kiro je zvolený model uvedený v nastavení asistenta). Placeholder
> je zde záměrně, aby v README nebyla nepodložená verze.

### Model uvnitř aplikace

REGINA volá jazykový model ve dvou funkcích (specifikace `classification-advisor`):
**klasifikační poradce** (návrh úrovně z dotazníku + zdůvodnění) a **AI úprava
popisu**. Obě popisuje sekce [AI funkce](#ai-funkce).

- **Poskytovatel (výchozí):** [OpenRouter](https://openrouter.ai)
- **Model (výchozí):** `openai/gpt-4o-mini` — rychlý a levný ne-reasoning model,
  vhodný pro krátké zdůvodnění a přepis textu. Lze přepnout na jiný (např.
  `deepseek/deepseek-v4-flash`) změnou `LLM_MODEL` v `.env`.
- **Reasoning:** proměnná `LLM_REASONING` (výchozí `off`). U reasoning modelů
  vypne řetěz úvah kvůli rychlosti a ceně; ne-reasoning modely ji ignorují.
  Hodnoty: `off` / `low` / `medium` / `high` / `auto`.
- **Kde se nastaví:** proměnné `LLM_*` v `.env` (viz `.env.example`). Model ani
  poskytovatel nejsou napevno v kódu.

Volání jde **výhradně přes vlastní abstrakční vrstvu** (`src/regina/llm/`) — ani
jedna funkce nevolá veřejné API modelu přímo. Poskytovatel je proto zaměnitelný
za firemní AI Gateway pouhou změnou konfigurace (`LLM_BASE_URL`, `LLM_MODEL`),
bez zásahu do kódu.

**API klíč je nepovinný.** Bez `OPENROUTER_API_KEY` aplikace **naběhne stejně**
a poradce běží v **mock / deterministickém režimu** (návrh z bodového skóre bez
volání sítě, úprava popisu jen lehce normalizuje text). Reálný klíč patří jen do
lokálního `.env` (v `.gitignore`), nikdy do kódu, image ani repozitáře. Klíč se
získá na <https://openrouter.ai/keys>.

Pole „použitý AI model" u záznamu je něco jiného — je to údaj o **evidované
aplikaci**, který zadává člověk, ne model používaný samotnou REGINOU.

### Master Prompt

**Master Prompt (zadání předané AI) je původní zadání domácího úkolu** — nebylo
přepsané ani zkrácené. Jeho plné znění je v repozitáři v souboru
[`docs/Domácí_úkol_—_AI_Implementation_Expert_(zadání).md`](docs/Domácí_úkol_—_AI_Implementation_Expert_(zadání).md) a zároveň v
[`prompts/00-master-prompt.md`](prompts/00-master-prompt.md), aby byl čitelný
přímo ze složky s prompty.

Zadání se nepředalo jako jediný „vygeneruj aplikaci" prompt. Bylo výchozím
bodem, ze kterého vznikla řízená sada specifikací (požadavky → návrh → rozhraní
→ databáze → plán úkolů) a teprve podle nich probíhala implementace. Klíčové
prompty pro jednotlivé kroky jsou ve složce [`prompts/`](prompts/):

| Soubor | Co obsahuje |
|---|---|
| [`prompts/00-master-prompt.md`](prompts/00-master-prompt.md) | Master Prompt — plné znění zadání + název a verze modelu |
| [`prompts/10-pozadavky.md`](prompts/10-pozadavky.md) | Prompt, kterým vznikl `requirements.md` |
| [`prompts/20-navrh.md`](prompts/20-navrh.md) | Prompt, kterým vznikl `design.md` |
| [`prompts/30-rozhrani.md`](prompts/30-rozhrani.md) | Prompt, kterým vznikl `ui.md` |
| [`prompts/40-databaze.md`](prompts/40-databaze.md) | Prompt, kterým vznikl `database.md` |
| [`prompts/50-plan-a-implementace.md`](prompts/50-plan-a-implementace.md) | Prompt, kterým vznikl `tasks.md` a podle kterého probíhala implementace |

Autoritativními pracovními prompty byly samotné specifikační dokumenty v
`.kiro/specs/app-registry-core/`. Schválené vizuální mocky jsou verzované v
[`design/mocks/`](design/mocks/).

---

## AI funkce

REGINA používá jazykový model ve dvou místech. Obě volají model **výhradně přes
vlastní abstrakční vrstvu** (`src/regina/llm/`), obě **anonymizují osobní údaje**
před odesláním a obě zapisují **technický log volání bez obsahu**. Obě fungují
i **bez API klíče** (mock / deterministický režim).

### 1) Klasifikační poradce

Ve formuláři aplikace je panel „Poradce klasifikace" se šesti otázkami
(dimenzemi):

1. počet uživatelů,
2. citlivost zpracovávaných dat,
3. byznys kritičnost,
4. integrační složitost,
5. regulatorní dopad,
6. míra použití AI.

Každá odpověď nese body (1–3). Z jejich součtu (6–18) vznikne **deterministická
baseline** úroveň (6–9 → `MALÁ`, 10–13 → `STŘEDNÍ`, 14–18 → `VELKÁ`). Model přes
abstrakci dodá **české zdůvodnění**; panel ukáže navrženou úroveň, zdůvodnění a
rozpad bodů po dimenzích. Uživatel návrh **přijme** (zdroj `AI`), přijme s jinou
úrovní (`AI_OVERRIDDEN`), nebo ho ignoruje a zvolí ručně (`HUMAN`).

Zápis klasifikace jde **vždy** přes jediného zapisovače
(`services/classification.py`) se stejným transakčním invariantem a autorizací
na backendu jako ruční zápis. Odkaz na doporučení se uloží do historie
klasifikace. Když model není dostupný nebo selže, poradce vrátí **deterministický
návrh označený jako záložní** — nikdy nespadne.

### 2) AI úprava popisu

U pole „Popis" je tlačítko „AI úprava". Přepíše zadaný popis do kultivovanějšího
českého znění. Výsledek je **návrh** — uživatel ho převezme (nahradí pole) nebo
zahodí; nikam se automaticky neukládá a uloží se až s celým formulářem. Při
chybě modelu zůstává původní popis beze změny (nezávazná chyba).

### Anonymizace a log volání

- **Anonymizace.** Před odesláním modelu se v textu (poznámka poradce, popis)
  nahradí **jméno, e-mail a telefon** zástupným symbolem (`[[JMENO_1]]`,
  `[[EMAIL_1]]`, `[[TEL_1]]`); po návratu se vrátí zpět. Mapování je
  deterministické v rámci jednoho volání.
- **Log volání** (jen role Admin, obrazovka „Volání AI" / `/volani-ai`). Ukládá
  se **implementace, model, operace, počty tokenů, latence, stav a čas** —
  **nikdy obsah promptu ani odpovědi** (v tabulce `llm_call_log` pro obsah
  neexistuje sloupec). Retence logů viz [Retenční lhůty](#retenční-lhůty).

---

## Klasifikace samotné REGINY

Kdyby REGINA byla evidovaná ve svém vlastním registru, klasifikoval bych ji
podle stejných kritérií, jaká používá pro ostatní aplikace, takto:

### Výsledek: **STŘEDNÍ**

### Zdůvodnění

- **Zpracovává osobní údaje.** REGINA drží jména, e-maily a pracovní pozice
  zaměstnanců v odpovědných trojicích a v seznamu uživatelů. To ji zvedá nad
  úroveň `MALÁ`. Zároveň jde v demu výhradně o **syntetická** data a v provozu
  o interní firemní kontakty, ne o citlivé kategorie osobních údajů ani o data
  klientů — proto ne `VELKÁ`.
- **Interní nástroj s omezeným okruhem uživatelů.** Cílová skupina jsou vlastníci
  aplikací a správci registru, ne veřejnost ani celá firma. Rozsah a dopad
  výpadku jsou tím omezené.
- **Auditní a retenční povinnosti.** Aplikace vede nemazatelný auditní log a má
  definovanou a naprogramovanou retenční politiku. To je typické pro úroveň
  `STŘEDNÍ` — vyžaduje to péči, ale nejde o systém s kritickým dopadem na
  finance nebo bezpečnost.
- **Bez kritické dostupnosti.** Registr je evidence, ne transakční ani provozně
  kritický systém. Krátký výpadek nezpůsobí finanční ztrátu ani regulatorní
  problém, což by jinak posouvalo klasifikaci k `VELKÁ`.

Souhrnně: netriviální práce s osobními údaji a auditní povinnosti vylučují
`MALÁ`, ale interní charakter, omezený okruh uživatelů a nekritická dostupnost
vylučují `VELKÁ`. Přiměřená úroveň je proto **STŘEDNÍ**.

---

## Retenční lhůty

Osobní údaje se v registru nedrží donekonečna. Retence je automatická úloha,
která pro každou kategorii spočítá časovou hranici a smaže záznamy za ní.
Nespouští se ručně — úloha běží **hned při startu aplikace** a pak se opakuje
v konfigurovatelném intervalu, takže žádný ruční krok ani externí plánovač
nejsou potřeba.

Retence má dvě kategorie:

| Kategorie | Lhůta | Hranice se počítá od | Proměnná |
|---|---|---|---|
| Auditní záznamy | **365 dní (≈ 1 rok)** | `occurred_at` (čas události) | `RETENTION_AUDIT_LOG_DAYS` |
| Vyřazené aplikace | **730 dní (≈ 2 roky)** | `decommissioned_at` (čas vyřazení) | `RETENTION_DECOMMISSIONED_APP_DAYS` |
| Logy volání modelu | **90 dní (≈ 3 měsíce)** | `occurred_at` (čas volání) | `RETENTION_LLM_CALL_LOG_DAYS` |
| Doporučení poradce | **180 dní (≈ 6 měsíců)** | `created_at` (čas vzniku) | `RETENTION_SUGGESTION_DAYS` |

Interval běhu je **24 hodin** (`RETENTION_INTERVAL_HOURS`) — po startu se úloha
spustí a pak se opakuje jednou denně.

### Zdůvodnění lhůt

- **Auditní záznamy — ≈ 1 rok.** Auditní stopa slouží k dohledání, kdo a kdy
  co změnil. Roční okno pokrývá běžný interní přehled a zpětné dotazy, aniž by
  se osobní údaje aktérů (jméno, e-mail ve snímku záznamu) držely déle, než je
  k účelu potřeba.
- **Vyřazené aplikace — ≈ 2 roky.** Delší lhůta dává čas na doběhnutí navazujících
  procesů po vyřazení aplikace (odkazy, závislosti, případné dohledání
  historie), pak už záznam nemá důvod trvat. Hranice se **vždy počítá od
  `decommissioned_at`** (okamžiku vyřazení), nikdy od času poslední úpravy —
  editace vyřazeného záznamu jeho retenci neprodlouží.
- **Logy volání modelu — ≈ 3 měsíce.** Slouží jen k přehledu o využití a
  nákladech; neobsahují osobní údaje ani obsah. Krátká lhůta stačí na provozní
  přehled a drží databázi štíhlou.
- **Doporučení poradce — ≈ 6 měsíců.** Uchovávají odpovědi dotazníku a
  zdůvodnění po dobu, kdy dává smysl dohledat, proč záznam dostal danou úroveň.
  Smazání doporučení **nikdy neutrhne historii klasifikace** — vazba
  `classification_log.suggestion_id` je `ON DELETE SET NULL`, takže se jen
  vynuluje odkaz a nemazatelná historie zůstává.

### Co se maže a co zůstává

- Smazání vyřazené aplikace odstraní **kaskádou** i její historii klasifikace
  (`classification_log` má na aplikaci vazbu `ON DELETE CASCADE`).
- **Auditní záznamy o aplikaci přežívají** její smazání — `audit_log.entity_id`
  není cizí klíč, takže na aplikaci nedrží žádnou vazbu a maže se samostatně
  až po vlastní lhůtě (365 dní od `occurred_at`).
- Každý běh se loguje po kategoriích (kategorie, hranice, počet smazaných řádků),
  ale **bez osobních údajů** — žádná jména, e-maily ani obsah smazaných řádků.

### Konfigurovatelnost

Všechny lhůty i interval jsou konfigurovatelné přes proměnné prostředí
`RETENTION_*` (viz `.env.example`); retenci lze úplně vypnout hodnotou
`RETENTION_ENABLED=false`. Hodnoty výše odpovídají vzoru `.env.example`.

---

## Záměna poskytovatele identity za Microsoft Entra ID

Přechod z lokálního **Dexu** na **Microsoft Entra ID** je **výhradně změna
konfigurace, žádný zásah do kódu** *(R1.5)*.

Důvod je zabudovaný do návrhu OIDC klienta (`src/regina/auth/oidc.py`).
Aplikace **nezná žádnou konkrétní adresu poskytovatele**. Jediná adresa v
konfiguraci je `OIDC_ISSUER`; z ní si klient stáhne discovery dokument
(`{OIDC_ISSUER}/.well-known/openid-configuration`) a všechny ostatní endpointy
— **authorization, token i jwks** — čte odtud. Žádný z těchto endpointů není
nikde v kódu napevno. Záměna poskytovatele tak spočívá v přesměrování
`OIDC_ISSUER` na jiného vydavatele.

Druhá polovina zaměnitelnosti jsou **konfigurovatelné názvy claimů**. Každý
poskytovatel pojmenovává claimy jinak (Dex posílá role v `groups`, Entra typicky
v `roles`). Protože názvy claimů čte kód z proměnných `OIDC_*_CLAIM`, pokryje
odlišná pojmenování Entra opět jen konfigurace, ne úprava kódu.

### Mapování proměnných

Všechny proměnné jsou skupina `OIDC_*`. Lokální hodnoty odpovídají vzoru
`.env.example` a konfiguraci Dexu (`deploy/dex/config.yaml`).

| Proměnná | Co je to | Lokálně (Dex) | Microsoft Entra ID |
|---|---|---|---|
| `OIDC_ISSUER` | Vydavatel; jediná adresa v konfiguraci, zbytek přijde z discovery | `http://host.docker.internal:5556/dex` | `https://login.microsoftonline.com/{tenant-id}/v2.0` |
| `OIDC_CLIENT_ID` | Identifikátor klienta | `regina` | Client ID z registrace aplikace v Entra |
| `OIDC_CLIENT_SECRET` | Tajemství klienta (jen v `.env`, nikdy v kódu) | lokální hodnota z `.env` | Client secret z registrace aplikace v Entra |
| `OIDC_SCOPES` | Požadované scope, oddělené mezerou | `openid profile email groups` | `openid profile email` (+ scope pro role/skupiny podle konfigurace Entra) |
| `OIDC_EMAIL_CLAIM` | Název claimu s e-mailem | `email` | `email`, případně `preferred_username` |
| `OIDC_NAME_CLAIM` | Název claimu se jménem | `name` | `name` |
| `OIDC_JOB_TITLE_CLAIM` | Název claimu s pracovní pozicí (výchozí hodnota v kódu, ve vzoru `.env` se neuvádí) | `job_title` | název claimu s pozicí podle nastavení Entra |
| `OIDC_ROLE_CLAIM` | Název claimu, ze kterého se čte role | `groups` | `roles` nebo `groups` podle konfigurace Entra |
| `OIDC_ADMIN_ROLE_VALUE` | Hodnota v claimu rolí, která mapuje na Správce (Admin) | `regina-admins` | název app role, resp. ID/název skupiny přiřazené správcům v Entra |

Hodnoty v posledním sloupci závislé na konkrétním nasazení (tenant, registrace
aplikace, app role či skupiny) jsou vodítka a zástupné hodnoty — vyplní se podle
konkrétní Entra tenanta.

### Shrnutí

Mění se **jen `.env`**, žádný kód. Endpointy přicházejí z discovery dokumentu,
v konfiguraci je jediná adresa poskytovatele (`OIDC_ISSUER`) a názvy claimů jsou
konfigurovatelné. Tím je splněn požadavek, že výměna za Microsoft Entra ID je
pouze změna konfigurace *(R1.5)*.

---

## Proč se neimplementuje MFA

Vícefaktorové ověření (MFA) v aplikaci **vědomě neimplementujeme**. Přihlašování
je celé delegované na externího poskytovatele identity (OIDC/OAuth2 — lokálně
Dex, v produkci Microsoft Entra ID). MFA se konfiguruje a vynucuje **na úrovni
poskytovatele identity**, ne v kódu aplikace.

REGINA nikdy nevidí ani neukládá přihlašovací údaje — dostane až ověřený ID
token po úspěšném přihlášení. Implementovat MFA přímo v aplikaci by proto bylo:

- **nesprávné** — duplikovalo by odpovědnost, která patří poskytovateli
  identity, a oslabilo by bezpečnostní model (aplikace by musela sáhnout na
  faktory ověření, které záměrně nikdy nedostává),
- **technicky nemožné** — aplikace nemá přístup k heslům ani k žádnému
  ověřovacímu kroku, takže není kam druhý faktor napojit.

Zapnutí MFA je tak čistě konfigurace poskytovatele identity (u Microsoft Entra
ID přes Conditional Access), bez jakéhokoli zásahu do kódu REGINY. To odpovídá
i explicitnímu pokynu ze zadání, aby MFA řešil poskytovatel identity.

---

## Vědomý dluh

Co v tomto rozsahu **vědomě není** a proč. Každá položka uvádí, co chybí, proč
je to teď přijatelné a jak by vypadalo skutečné řešení. Cílem je, aby bylo
vidět rozhodnutí, ne opomenutí.

### Návrh úrovně od modelu vychází z deterministické baseline

Klasifikační poradce ([AI funkce](#ai-funkce)) **je implementovaný** — dotazník,
doporučení se zdůvodněním, zaměnitelná abstrakce, anonymizace i log volání bez
obsahu. Jedno vědomé zjednodušení: **navrženou úroveň drží deterministické
bodové skóre**, model dodává jen slovní zdůvodnění (nepřepisuje úroveň z vlastní
úvahy). **Proč:** bodová baseline je stabilní, obhajitelná a testovatelná — nemůže
kolísat mezi voláními ani „ujet" k nesmyslu, a zůstává srozumitelná i v mock
režimu bez klíče. **Skutečné řešení, kdyby se úroveň měla brát od modelu:** nechat
model vrátit i úroveň, validovat ji proti povoleným hodnotám a při rozporu s
baseline ukázat obojí; je to aditivní změna ve `services/advisor.py` bez dopadu
na zápis klasifikace.

### Návrh klasifikace nečte úroveň z textu modelu

Panel poradce ukáže zdůvodnění od modelu, ale tlačítko „Použít" předvyplní
**baseline** úroveň (viz výše). **Proč je to teď přijatelné:** uživatel může
úroveň v poli klasifikace kdykoli ručně změnit a zápis to korektně zaznamená jako
`AI_OVERRIDDEN`. **Skutečné řešení:** viz předchozí bod — parsovat úroveň z
odpovědi modelu.

### Přesná verze modelu je zatím zástupná

V sekci [Použitý model a Master Prompt](#použitý-model-a-master-prompt) je verze
modelu uvedená jako placeholder `<přesná verze modelu — doplní autor>`. **Proč:**
přesné označení a verzi zná až prostředí, ve kterém byl úkol zpracován; raději
placeholder než nepodložené číslo v README. **Skutečné řešení:** autor doplní
konkrétní verzi podle nastavení asistenta v Kiro.

### Retence běží per-instance bez distribučního zámku

Retenční úloha běží uvnitř aplikačního procesu a spouští se při startu a pak
v intervalu. Při **více instancích** aplikace by běžela vícekrát paralelně.
**Proč je to teď přijatelné:** mazání je idempotentní, takže vícenásobný běh
nezpůsobí chybu, jen zbytečnou práci; nasazení je jednoinstanční. **Skutečné
řešení:** zámek v databázi (advisory lock) nebo externí plánovač, který úlohu
spustí právě jednou. Poznámka je i přímo v `src/regina/services/retention.py`.

### Cesty exportu se liší od původního návrhu

Export CSV je na cestách `/export/registr` a `/export/audit`, kdežto `design.md`
sekce 7 původně počítala s `/registr/export.csv` a `/audit/export.csv`. **Proč:**
seskupení obou exportů pod společný prefix `/export` je čitelnější než přípona
`.csv` na konci cesty; chování (jen role Admin, filtrovaná množina, UTF-8) je
beze změny. **Skutečné řešení, pokud by na cestách záleželo:** sjednotit názvy
mezi návrhem a implementací — jde o kosmetickou úpravu routeru.

### Automatizované testy jsou jen cílené, ne plošné

Testovací pokrytí není hodnocená oblast, takže testy míří jen na místa, kde
tvrdíme něco o bezpečnosti a integritě. Neimplementované zůstávají označené
volitelné testy z plánu:

- property-based / tabulkové testy autorizace proti capability matrix (úkol 5.4),
- testy autorizace přes HTTP, že přímý `POST` na cizí záznam projde jen roli
  Admin i bez tlačítka v UI (úkol 6.5),
- testy invariantu klasifikace, že `applications.classification` odpovídá
  poslednímu řádku logu a přepis bez důvodu odmítne aplikace i databáze
  (úkol 13.3),
- testy retence, že záznam za hranicí se smaže, jeho historie klasifikace odejde
  kaskádou a jeho auditní záznamy zůstanou (úkol 19.3).

**Proč je to teď přijatelné:** invarianty jsou vynucené i na úrovni databáze
(`CHECK` constrainty pro povinný důvod přepisu a pro `decommissioned_at`,
`ON DELETE CASCADE` u historie klasifikace) a autorizace stojí na čistých
funkcích v `domain/rules.py`, které volá jak backend guard, tak šablona — takže
se rozhraní nemůže rozejít s vynucením. **Skutečné řešení:** doplnit výše
uvedené testy; jsou už rozepsané v plánu jako samostatné úkoly a návrh je psaný
tak, aby šly přidat bez úprav produkčního kódu.

### Menší vědomá vynechání z rozsahu jádra

Následující věci pocházejí z mocků nebo z bohatšího návrhu, ale zadání je
nevyžaduje a v jádře evidence nepřinášejí novou vlastnost:

- **MFA se neimplementuje** — patří poskytovateli identity, viz [samostatná
  sekce](#proč-se-neimplementuje-mfa). Vestavění do aplikace by duplikovalo
  odpovědnost a oslabilo bezpečnostní model.
- **Reálný Entra ID tenant** — nahrazený lokálním mockem (Dex) s totožným OIDC
  rozhraním; výměna je [pouhá změna konfigurace](#záměna-poskytovatele-identity-za-microsoft-entra-id).
- **Fyzické mazání záznamů** — registr je evidence; odstranění z provozu je stav
  `Vyřazená`, aby zůstala historie. Fyzicky maže jen retenční rutina.
- **Notifikace, sekce Nastavení, avatary, správa taxonomie útvarů, monitoring
  SLA, hromadné operace** — prvky z mocku bez přínosu pro hodnocené oblasti;
  konfigurace jde přes proměnné prostředí, útvary jsou uzavřený výčet, iniciály
  nahrazují avatary.
- **Citlivost dat a technická metadata** (karty Security & Privacy a Technical
  Specifications z mocku) — zadání je nežádá; přidání je aditivní (sloupec a pole
  ve formuláři), lze doplnit kdykoli.

Podrobná tabulka těchto rozhodnutí je ve specifikaci `app-registry-core`
(`requirements.md`, sekce *Vědomý dluh*).
