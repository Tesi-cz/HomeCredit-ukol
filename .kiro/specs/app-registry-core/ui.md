# Uživatelské rozhraní — jádro evidence

## Účel dokumentu

Inventář obrazovek odvozený ze schválených HTML mocků. Popisuje, co je na které obrazovce, jak se mapuje na požadavky a co z mocků vědomě nepřejímáme.

Doprovází `requirements.md` a `design.md`. Samotné HTML mocky patří do `design/mocks/` v repozitáři, aby byly verzované a otevřitelné v prohlížeči.

---

## 1. Produktový název

**REGINA** — REGistr INterních Aplikací.

- Hlavní logotyp: `REGINA`, Montserrat Bold, bílá na tmavém sidebaru
- Podtitul: `REGistr INterních Aplikací` s rozlišenými písmeny R-E-G-IN-A v brand červené
- V mocku je podtitul bez diakritiky („REGistr INternich Aplikaci"). Správná varianta je s diakritikou.
- Patička zůstává `© Home Credit International`

---

## 2. Zdrojové mocky

| Mock | Obrazovka | Stav |
|---|---|---|
| Uživatelský Portál — Moje Aplikace | Moje aplikace (karty) | Přejato |
| Průvodce Registrací Aplikace | Registrace záznamu | Přejato částečně, viz sekce 6 |
| Správa Registru Aplikací | Registr (tabulka) | Přejato |
| Detail Aplikace (Uživatel) | Detail záznamu | Přejato částečně, viz sekce 5 |

Pro obrazovky **Uživatelé** a **Auditní logy** mock neexistuje. Použijí vzor tabulky ze Správy registru.

---

## 3. Navigace

Sidebar, tmavý (`#303030`), pevný, šířka 256 px.

| Položka | Cesta | Viditelnost |
|---|---|---|
| Moje aplikace | `/moje` | všichni |
| Registr | `/registr` | všichni |
| Uživatelé | `/uzivatele` | pouze Role_Admin |
| Auditní logy | `/audit` | pouze Role_Admin |

Pod navigací primární akce **Nová aplikace** (žlutý pill button). Dole blok přihlášeného uživatele: iniciály, jméno, e-mail, odhlášení.

**Co z mocku nepřejímáme.** Sidebar v mockách obsahuje `Dashboard` a `Settings`. Žádný požadavek je nepokrývá — přehledový dashboard není v rozsahu a konfigurace se řeší proměnnými prostředí. Položky vypadávají.

Skrytí položek pro Role_User je pohodlnost, ne ochrana. Cesty `/uzivatele` a `/audit` jsou chráněné na backendu *(R2.2)*.

### Horní lišta

Název sekce vlevo, vyhledávací pole vpravo. **Zvonek notifikací a ikona nápovědy z mocku vypadávají** — jsou v sekci vědomého dluhu. Avatar je nahrazen iniciálami, protože ukládání profilových fotek není v rozsahu.

---

## 4. Obrazovka: Moje aplikace

Cesta `/moje`. Vstupní obrazovka po přihlášení.

Zobrazuje záznamy, kde je přihlášený uživatel členem odpovědné trojice — tedy ty, které smí editovat.

**Struktura.**

- Hero blok: text „Spravujte své existující aplikace nebo registrujte nové", vyhledávací pole, tlačítko **Registrovat novou aplikaci**
- Mřížka karet, 3 sloupce na desktopu, 2 na tabletu, 1 na mobilu

**Karta záznamu.**

| Prvek | Obsah |
|---|---|
| Ikona | Podle útvaru, z vestavěné sady |
| Badge stavu | Lifecycle_State, barevný |
| Badge klasifikace | MALÁ / STŘEDNÍ / VELKÁ, neutrální; při chybějící klasifikaci **Neklasifikováno** *(R3.8)* |
| Nadpis | Název záznamu |
| Text | Popis, zkrácený |
| Patička | Datum poslední úpravy a odkaz **Detail** |

**Prázdný stav.** Když uživatel není nikde v odpovědné trojici, zobrazí se vysvětlení a tlačítko na registraci. Mock prázdný stav neřeší, ale u nové instalace je to první, co uživatel uvidí.

**Vztah k požadavkům.** Tato obrazovka není v `requirements.md` popsaná — R3 pokrývá jen tabulkový výpis. Je to **doplněk odvozený z mocku** a vyžaduje nový akceptační kritérium v R3.

---

## 5. Obrazovka: Registr

Cesta `/registr`. Tabulkový výpis **všech** záznamů. Obě role vidí totéž, Role_Admin má navíc akce.

**Ovládací prvky.** Nadpis „Správa registru", filtry v pruhu nad tabulkou: Útvar, Klasifikace, Stav. Vyhledávání podle názvu. Tlačítko **Exportovat CSV** pouze pro Role_Admin *(R10.4)*.

**Sloupce.**

| Sloupec | Poznámka |
|---|---|
| Název | Řaditelný *(R3.4)*, odkaz na detail |
| Vlastník | Jméno z adresáře osob |
| Útvar | |
| Klasifikace | Badge, nebo **Neklasifikováno** |
| AI model | Model použitý evidovanou aplikací, nebo pomlčka |
| Stav | Badge |
| Akce | **Přepsat klasifikaci** a **Vyřadit**, pouze Role_Admin |

Zebra striping `#F6F6F6`, hlavička sticky, stránkování s textem „Zobrazeno 1–20 z 128 záznamů".

**Co z mocku nepřejímáme.**

| Prvek v mocku | Důvod |
|---|---|
| Sloupec `Tier` s hodnotami Tier 1/2/3 | Zadání vyžaduje MALÁ / STŘEDNÍ / VELKÁ. Sloučeno do sloupce Klasifikace |
| Sloupec `AI Class.` s doménovou kategorií | Dvě klasifikace vedle sebe jsou zbytečná složitost. Jedna autoritativní klasifikace |
| Ikona robota s tooltipem důvěry | Patří našeptávači, v jádru nemá zdroj dat |
| Zaškrtávací políčka a hromadné akce | Hromadné operace jsou v sekci vědomého dluhu |
| Stav `Review` | Vznikal z nízké důvěry AI. Klasifikaci zapisuje vždy člověk, takže stav ke kontrole neexistuje |
| Stav `Archived` | Archivace zrušena, zůstává stav Vyřazená |

---

## 6. Obrazovka: Registrace a editace záznamu

Cesty `/registr/nova` a `/registr/{id}/upravit`.

**Rozhodnutí: tři kroky v jádru, čtvrtý přinese našeptávač.**

Mock navrhuje čtyři kroky: Základní data → Infrastruktura → Bezpečnost → Souhrn. Kroky Infrastruktura a Bezpečnost by potřebovaly `data_class`, hosting a frameworky, tedy vědomě odložená pole. Otázky z mocku o typu dat, počtu uživatelů a přístupu z internetu jsou naopak **klasifikační dotazník**, tedy našeptávač.

Průvodce má proto tolik kroků, kolik máme skutečného obsahu:

| Krok | Název | Pole | Povinnost |
|---|---|---|---|
| 1 | Základní údaje | Název, Popis, Útvar | název a útvar povinné |
| 2 | Odpovědnost | Vlastník, Zástupce, Technický správce | vlastník a technický správce povinní |
| 3 | Provoz a klasifikace | Stav, AI model, Klasifikace | stav povinný, klasifikace nepovinná |

Našeptávač později vloží krok **Charakteristika dat** s dotazníkem před krok 3, a průvodce bude mít čtyři kroky přesně jako mock. Ukazatel průběhu z mocku se tedy nepřekresluje, jen se rozšíří.

**Vyhrazené místo pro AI panel.** V kroku 3, kde se rozhoduje o klasifikaci, zůstává pravý sloupec prázdný. Tam později přijde panel s doporučením modelu, jeho zdůvodněním a mírou důvěry. Rozvržení kroku se přidáním našeptávače nemění.

**Jeden formulář, jedno odeslání.** Kroky jsou vizuální — přepínají se v prohlížeči, ale záznam vzniká **jediným** odesláním na konci. Důsledek: nevzniká rozpracovaný stav v session ani polovičatý záznam v databázi, když uživatel průvodce opustí. Validace je vždy na serveru nad celou sadou polí *(R5.3)*.

**Chování.**

- Vlastník je předvyplněn přihlášeným uživatelem, lze změnit *(R5.5)*
- Osoby se vybírají z adresáře, ne psaním jména — autorizace stojí na identitě *(R2.6)*
- Stav `Vyřazená` **není ve výběru pro Role_User** *(R5.12)*
- Chyby validace u konkrétních polí, ne jako jedna hláška *(R5.3)*
- Zrušení a Pokračovat v patičce, jak v mocku

---

## 7. Obrazovka: Detail záznamu

Cesta `/registr/{id}`. Bento mřížka, 12 sloupců.

**Prvky.**

| Blok | Obsah |
|---|---|
| Drobenka | „Registr › {název}" *(R4.1)* |
| Indikátor režimu | **Pouze pro čtení**, když uživatel nemá právo editovat *(R4.8)* |
| Hlavní karta | Název, badge stavu, badge klasifikace, popis |
| Odpovědnost | Vlastník a technický správce s pozicí, zástupce pokud je vyplněn *(R4.3)* |
| Klasifikace | Platná hodnota, způsob zápisu, datum. U přepisu správcem i důvod *(R4.4, R4.5)* |
| Historie klasifikace | Seznam od nejnovějšího: hodnota, způsob, kdo, kdy *(R4.6)* |
| AI model | Model použitý evidovanou aplikací, nebo informace že žádný *(R4.7)* |
| Akce | **Upravit** při právu editace, **Přepsat klasifikaci** a **Vyřadit** pro Role_Admin |

**Co z mocku nepřejímáme.**

| Prvek v mocku | Důvod |
|---|---|
| Karta Security & Privacy | Obsahovala stav anonymizace, `Data_Class` a datum auditu. Anonymizace patří našeptávači, `Data_Class` je odložená |
| Blok Technical Specifications | Hosting, frameworky, cíl dostupnosti jsou odložené |
| Badge `AI Tier 2` | Tier nahrazen klasifikací |
| Fotky osob | Nahrazeny iniciálami |

Uvolněné místo v pravém sloupci zaujme **historie klasifikace**, která je v jádru novým a nejinformativnějším blokem.

---

## 8. Obrazovka: Uživatelé

Cesta `/uzivatele`, pouze Role_Admin. Mock neexistuje, použije se vzor tabulky.

Sloupce: Jméno, E-mail, Pozice, Role, Zdroj role, Akce.

- Přepnutí role mezi Uživatel a Správce *(R11.2)*
- Vlastní roli si správce odebrat nemůže, akce je nedostupná *(R11.5)*
- Sloupec Zdroj role rozlišuje, zda role přišla z poskytovatele identity, nebo byla nastavena lokálně *(R11.6)*
- Obrazovka **nezakládá ani nemaže identity** *(R11.3)*, což je na ní uvedeno textem

---

## 9. Obrazovka: Auditní logy

Cesta `/audit`, pouze Role_Admin. Mock neexistuje.

Sloupce: Čas, Aktér, Akce, Objekt, Popis.

Filtry podle typu akce, aktéra a časového rozsahu, stránkování *(R8.7)*. Export CSV *(R10.2)*.

Nad tabulkou informace, že záznamy nelze měnit ani mazat a že podléhají retenční lhůtě.

---

## 10. Statické zdroje bez internetu

Požadavek R13.9 vyžaduje, aby se rozhraní vykreslilo správně i bez připojení. Mocky tahají z CDN Tailwind, Google Fonts a Material Symbols. Nic z toho v hotové aplikaci nezůstane.

| Zdroj v mocku | Řešení |
|---|---|
| `cdn.tailwindcss.com` | Tailwind se přeloží při buildu image do jednoho CSS souboru |
| Google Fonts — Montserrat, Source Sans Pro | Woff2 soubory už jsou v `brand-assets/fonts/`, zkopírují se do statických zdrojů |
| Material Symbols z CDN | Vložený podsoubor fontu ve statických zdrojích |
| Fotky osob z `googleusercontent.com` | Nepoužívají se, iniciály |

---

## 11. Konflikty proti dosavadní specifikaci

Tři věci v nových mockách si odporují s tím, co je zapsané. Rozhodnutí je zde, k potvrzení.

| Konflikt | Rozhodnutí |
|---|---|
| Mock ukazuje stavy `Aktivní` a `Údržba` | Zůstává pět stavů z glosáře. `Aktivní` odpovídá **Produkce**. `Údržba` se nezavádí — je to provozní okolnost, ne fáze životního cyklu |
| Průvodce zobrazuje `Tier 2 / Důvěrné` | Zadání vyžaduje MALÁ / STŘEDNÍ / VELKÁ. Tier se nepoužije nikde |
| Registrace jako průvodce se čtyřmi kroky | V jádru jednostránkový formulář se sekcemi. Průvodce vznikne s našeptávačem, který doplní dotazník |

---

## 12. Nová akceptační kritéria k doplnění

Obrazovka **Moje aplikace** není v `requirements.md`. Vyžaduje doplnění R3:

- Systém poskytne výpis záznamů, kde je přihlášený uživatel členem odpovědné trojice, jako mřížku karet
- Karta zobrazí název, stav, klasifikaci, zkrácený popis a datum poslední úpravy
- Když uživatel není členem žádné odpovědné trojice, zobrazí se vysvětlující prázdný stav s výzvou k registraci
- Výpis je vstupní obrazovkou po přihlášení
