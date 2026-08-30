"""Anonymizace a rehydratace osobních údajů (classification-advisor R5, úkol 3.2).

Bezpečnostní tvrzení: jméno, e-mail a telefon zmizí z textu **před** voláním
modelu a vrátí se **po** něm. Mapování je deterministické — stejná hodnota
dostane stejný token.
"""

from __future__ import annotations

from regina.services.anonymization import anonymize, rehydrate


def test_email_a_telefon_zmizi_a_vrati_se() -> None:
    text = "Kontakt: jan.novak@firma.cz nebo +420 601 234 567."
    masked, mapping = anonymize(text)

    # V maskovaném textu už nesmí být původní údaje.
    assert "jan.novak@firma.cz" not in masked
    assert "601 234 567" not in masked
    assert "[[EMAIL_1]]" in masked
    assert "[[TEL_1]]" in masked

    # Rehydratace vrátí přesně původní text.
    assert rehydrate(masked, mapping) == text


def test_jmeno_z_adresare_zmizi_a_vrati_se() -> None:
    text = "Vlastníkem je Jan Novák a zástupcem Eva Marková."
    masked, mapping = anonymize(text, known_names=["Jan Novák", "Eva Marková"])

    assert "Jan Novák" not in masked
    assert "Eva Marková" not in masked
    assert "[[JMENO_1]]" in masked
    assert rehydrate(masked, mapping) == text


def test_stejna_hodnota_stejny_token() -> None:
    text = "Napiš na info@firma.cz, opravdu na info@firma.cz."
    masked, mapping = anonymize(text)

    # Dvakrát tentýž e-mail → jeden token, dvakrát použitý.
    assert masked.count("[[EMAIL_1]]") == 2
    assert "[[EMAIL_2]]" not in masked
    assert rehydrate(masked, mapping) == text


def test_prazdny_text_projde_beze_zmeny() -> None:
    masked, mapping = anonymize("")
    assert masked == ""
    assert mapping == {}
    assert rehydrate("", {}) == ""


def test_delsi_jmeno_ma_prednost() -> None:
    # "Jan Novák" se má nahradit celé, ne jen "Jan".
    text = "Jan Novák tu byl."
    masked, mapping = anonymize(text, known_names=["Jan", "Jan Novák"])
    assert "Novák" not in masked
    assert rehydrate(masked, mapping) == text
