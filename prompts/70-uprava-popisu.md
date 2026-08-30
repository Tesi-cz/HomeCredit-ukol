# Prompt — AI úprava popisu

Systémový prompt, který se za běhu posílá jazykovému modelu při úpravě popisu
aplikace (funkce AI úpravy popisu, spec `classification-advisor`).
Autoritativní podobou je konstanta `REWRITE_SYSTEM_PROMPT` v
`src/regina/services/description_rewrite.py` — tento soubor ji zrcadlí pro
dohledatelnost.

## Kontext použití

- **Kdy:** uživatel ve formuláři aplikace klikne u pole „Popis" na tlačítko
  „AI úprava".
- **Jak:** volání jde **výhradně** přes vlastní abstrakci (`src/regina/llm/`),
  nikdy přímo z aplikačního kódu. Poskytovatel je zaměnitelný konfigurací.
- **Vstup je anonymizovaný:** popis projde anonymizací (jméno/e-mail/telefon →
  zástupný symbol) **před** odesláním; výsledek se po návratu rehydratuje.
- **Nezávazný výsledek:** návrh se nikam neukládá. Uživatel ho převezme
  (nahradí pole) nebo zahodí; uložení proběhne až odesláním formuláře. Při
  chybě modelu zůstává původní popis beze změny.

## Systémový prompt (české znění)

> Přepiš popis interní firemní aplikace do jasnějšího a kultivovanějšího
> českého znění. Zachovej význam i všechny faktické údaje, neměň smysl,
> nepřidávej nové informace. Vstup může obsahovat zástupné symboly typu
> `[[JMENO_1]]` — ponech je beze změny. Vrať jen upravený popis bez úvodu a bez
> nadpisů.

## Uživatelský prompt

Uživatelský prompt je přímo anonymizovaný text popisu z formuláře, bez další
úpravy.
