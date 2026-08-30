# Požadavky na projekt — HomeCredit domácí úkol

Tento dokument obsahuje závazné technické požadavky extrahované ze zadání. Vše zde uvedené MUSÍ být dodrženo při implementaci.

## Vybraná varianta

**A) Registr interních aplikací**

Evidence aplikací vytvořených ve firmě: název, vlastník, zástupce, technický správce, klasifikace (MALÁ, STŘEDNÍ, VELKÁ), stav, použitý AI model. Aplikace sama navrhne klasifikaci podle odpovědí uživatele a zdůvodní ji.

---

## Identita a přístup

- Přihlášení výhradně přes OIDC/OAuth2. Žádná vlastní tabulka uživatelů a hesel.
- Libovolný veřejný provider nebo lokální mock. Podmínka: výměna za Microsoft Entra ID = pouze změna konfigurace, ne přepis kódu.
- MFA neimplementovat — řeší identity provider. V README vysvětlit proč.
- Minimálně 2 role s odlišnými právy (např. user + admin).
- Autorizace vynucená na backendu, ne skrytím UI prvků.

## LLM a abstrakce

- Žádné přímé volání veřejného AI API z aplikačního kódu.
- Vlastní abstrakční vrstva pro LLM volání — musí být zaměnitelná za firemní AI Gateway.
- API klíč přes proměnnou prostředí (nikdy v kódu).
- Pokud varianta potřebuje přepis řeči → stejná abstrakce, zaměnitelnost je klíčová.
- Logy z volání modelu: model, čas, tokeny. BEZ obsahu promptu a bez přepisu.

## Data a soukromí

- Pracovat se syntetickými daty.
- Jednoduchá anonymizace: jméno, e-mail, telefon → zástupný symbol před zpracováním, po zpracování vrátit zpět.
- Pokud app zpracovává zvuk nebo osobní údaje → v README definovat retenční politiku (jak dlouho, kdy mazat) a naprogramovat ji.

## Provoz a deployment

- `Dockerfile` + `docker-compose.yaml` — aplikace MUSÍ naběhnout přes `docker compose up` bez ručních kroků.
- Žádné secrets v kódu, v image ani v repozitáři.
- Lokálně `.env`, v repu jen `.env.example`.
- `.gitignore` hlídá `.env` a další citlivé soubory.
- Health endpoint.
- Logování: start aplikace, chyby, přihlášení/odhlášení.
- Závislosti pinované na konkrétní verze (lockfile nebo requirements.txt).

## Struktura repozitáře

- Veřejný GitHub repo (splněno: Tesi-cz/HomeCredit-ukol).
- Commit zprávy musí dávat smysl.
- `README.md` s: popisem, spuštěním, použitým modelem, klasifikací aplikace + zdůvodnění, co je vědomý dluh.
- Složka `prompts/` s klíčovými prompty.
- V README uvést Master Prompt (zadání pro AI) + název a verzi modelu.

## Co se NEhodnotí

- Design/vzhled
- Počet funkcí
- Testovací pokrytí
- Počet řádků kódu

## Co SE hodnotí

- Běží to na první pokus podle README
- Rozumíš tomu co jsi odevzdal
- Kvalita README a klasifikace
- Čistota práce se secrets a daty
- Vědomé rozhodnutí co nedělat a proč
