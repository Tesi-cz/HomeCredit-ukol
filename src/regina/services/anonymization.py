"""Anonymizace a rehydratace osobních údajů (classification-advisor R5).

Žádný text nesmí odejít modelu s osobními údaji. Tento modul je **jediné**
místo, kde se text připravuje pro model: `anonymize` nahradí jména, e-maily
a telefony zástupnými symboly, `rehydrate` je po odpovědi vrátí zpět
(design.md 5.1). Klient v `llm/` dostává už jen maskovaný text.

**Deterministické mapování v rámci jednoho volání** (R5.5). Stejná hodnota →
stejný `Placeholder_Token`, takže se rehydratace nikdy nesplete a opakovaný
výskyt téhož jména dostane tentýž token. Mapování je lokální pro jedno volání
(nevzniká globální slovník osob).

**Bez závislostí na databázi.** Jména se předávají jako seznam (volající služba
je vezme z adresáře `users`). Modul tak zůstává čistý a testovatelný bez DB.
E-mail a telefon se poznají tvarem (regulární výraz), jméno shodou proti
předanému seznamu — konzervativně, aby se nemaskovala běžná slova.

Pořadí nahrazování je záměrné: nejdřív e-maily (obsahují tečky a zavináč),
pak telefony, nakonec jména. Jména se řadí od nejdelších, aby se „Jan Novák"
nahradil celý dřív než samotné „Jan".
"""

from __future__ import annotations

import re

#: E-mail: konzervativní tvar `local@domain.tld`.
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

#: Telefon: české i mezinárodní tvary, volitelná předvolba `+420`, mezery,
#: pomlčky a závorky. Vyžaduje aspoň 9 číslic, aby se nechytala běžná čísla.
_PHONE_RE = re.compile(
    r"(?<![\w])(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?){2,4}\d{2,4}(?![\w])"
)


def _mask_by_regex(
    text: str,
    pattern: re.Pattern[str],
    prefix: str,
    mapping: dict[str, str],
    counter_start: int,
) -> tuple[str, int]:
    """Nahradí výskyty vzoru zástupnými symboly. Vrátí text a další pořadí.

    Deterministické: každá jedinečná hodnota dostane token `[[PREFIX_n]]` a při
    opakování se použije tentýž (R5.5). `mapping` se plní token → původní
    hodnota pro pozdější rehydrataci.
    """
    value_to_token: dict[str, str] = {}
    counter = counter_start

    def _replace(match: re.Match[str]) -> str:
        nonlocal counter
        value = match.group(0)
        token = value_to_token.get(value)
        if token is None:
            token = f"[[{prefix}_{counter}]]"
            value_to_token[value] = token
            mapping[token] = value
            counter += 1
        return token

    return pattern.sub(_replace, text), counter


def anonymize(text: str, *, known_names: list[str] | None = None) -> tuple[str, dict[str, str]]:
    """Nahradí osobní údaje v textu zástupnými symboly (R5.1).

    Maskuje v pořadí e-mail → telefon → jméno. Jména se berou z `known_names`
    (adresář osob dodá volající služba) a nahrazují se od nejdelších, aby se
    celé jméno nahradilo dřív než jeho část.

    Vrací dvojici `(masked_text, mapping)`, kde `mapping` je token → původní
    hodnota pro `rehydrate`. Prázdný nebo `None` text projde beze změny.
    """
    if not text:
        return text, {}

    mapping: dict[str, str] = {}
    masked, next_counter = _mask_by_regex(text, _EMAIL_RE, "EMAIL", mapping, 1)
    masked, _ = _mask_by_regex(masked, _PHONE_RE, "TEL", mapping, 1)

    # Jména: přesná shoda proti adresáři, od nejdelších. Case-insensitive,
    # ale ukládá se původní podoba z textu (zachytí ji regex se skupinou).
    if known_names:
        name_counter = 1
        value_to_token: dict[str, str] = {}
        for name in sorted({n.strip() for n in known_names if n and n.strip()}, key=len, reverse=True):
            name_re = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)

            def _replace(match: re.Match[str]) -> str:
                nonlocal name_counter
                value = match.group(0)
                token = value_to_token.get(value.lower())
                if token is None:
                    token = f"[[JMENO_{name_counter}]]"
                    value_to_token[value.lower()] = token
                    mapping[token] = value
                    name_counter += 1
                return token

            masked = name_re.sub(_replace, masked)

    return masked, mapping


def rehydrate(text: str, mapping: dict[str, str]) -> str:
    """Vrátí původní hodnoty na místo zástupných symbolů (R5.2).

    Inverzní operace k `anonymize`: projde `mapping` a každý token nahradí zpět
    původní hodnotou. Tokeny mají jednoznačný tvar `[[...]]`, takže nedojde
    k záměně s běžným textem. Prázdné `mapping` nechá text beze změny.
    """
    if not text or not mapping:
        return text
    for token, original in mapping.items():
        text = text.replace(token, original)
    return text
