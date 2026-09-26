from decimal import Decimal

import pytest

from categorisation import categorise, clean_merchant

# (counterparty, purpose, amount, expected category, expected merchant or None to skip the name check)
# Realistic German statement text: processors, legal forms, terminal ids, cities, mixed case.
LABELLED = [
    ("REWE Markt GmbH-Zw 1234", "REWE SAGT DANKE 44123//BERLIN/DE", -43.17, "Groceries", "REWE"),
    ("EDEKA Center Mueller//Muenchen", "2026-08-02 Debitk.3", -58.34, "Groceries", "Edeka"),
    ("LIDL DIENSTLEISTUNG", "LIDL SAGT DANKE", -31.20, "Groceries", "Lidl"),
    ("ALDI SUED", "ALDI SUED 0815//KOELN", -22.10, "Groceries", "Aldi"),
    ("Kaufland Dienstleistung", "Kaufland 1234 Leipzig", -64.00, "Groceries", "Kaufland"),
    ("dm-drogerie markt GmbH + Co. KG", "DM FIL.1234", -12.45, "Groceries", "dm"),
    ("ROSSMANN 2231", "", -8.99, "Groceries", "Rossmann"),
    ("NETTO MARKEN-DISCOUNT", "Netto Filiale 4411", -17.30, "Groceries", "Netto"),
    ("PENNY Markt", "PENNY 3312 Hamburg", -9.80, "Groceries", "Penny"),
    ("Flink SE", "Flink Lieferung 8842", -34.50, "Groceries", None),
    ("Lieferando.de", "LIEFERANDO.DE//BERLIN", -27.40, "Restaurant", "Lieferando"),
    ("Wolt Enterprises", "WOLT 99231 Berlin", -21.90, "Restaurant", "Wolt"),
    ("MCDONALDS 1123", "MCDONALDS DANKT//FRANKFURT", -11.20, "Restaurant", "McDonald's"),
    ("SumUp *Cafe Kranz", "SUMUP *CAFE KRANZ//BERLIN", -4.60, "Restaurant", "Cafe Kranz"),
    ("SQ *BAECKEREI SCHMIDT", "", -3.80, "Restaurant", "Baeckerei Schmidt"),
    ("Pizzeria Da Mario", "Kartenzahlung", -32.00, "Restaurant", "Pizzeria Da Mario"),
    ("STARBUCKS COFFEE 5521", "", -5.95, "Restaurant", "Starbucks"),
    ("Uber Eats", "UBER EATS help.uber.com", -24.80, "Restaurant", "Uber Eats"),
    ("DB Vertrieb GmbH", "Fahrkarte 123456789 Berlin-Hamburg", -59.90, "Transport", "Deutsche Bahn"),
    ("BVG Berliner Verkehrsbetriebe", "Deutschlandticket August", -49.00, "Transport", None),
    ("UBER *TRIP", "UBER *TRIP HELP.UBER.COM", -36.50, "Transport", "Uber"),
    ("Bolt Operations OU", "BOLT.EU/O/2208", -12.30, "Transport", "Bolt"),
    ("ARAL Station 2210", "ARAL SAGT DANKE", -78.40, "Transport", "Aral"),
    ("Shell Deutschland GmbH", "SHELL 4412 Muenchen", -65.10, "Transport", "Shell"),
    ("MVG Muenchner Verkehrsgesellschaft", "MVG Automat", -3.70, "Transport", "MVG"),
    ("NETFLIX INTERNATIONAL B.V.", "NETFLIX.COM 866-579-7172", -13.99, "Subscriptions", "Netflix"),
    ("Spotify AB", "Spotify P1A2B3C4D5", -10.99, "Subscriptions", "Spotify"),
    ("Amazon Digital Germany", "Amazon Prime Mitgliedschaft", -8.99, "Subscriptions", "Amazon Prime"),
    ("APPLE.COM/BILL", "", -2.99, "Subscriptions", "Apple"),
    ("Telekom Deutschland GmbH", "Rechnung 08/2026 Kundennr 12345", -39.95, "Subscriptions", "Telekom"),
    ("Vodafone GmbH", "Kabel Internet", -39.99, "Subscriptions", "Vodafone"),
    ("Disney Plus", "DisneyPlus Abo", -9.99, "Subscriptions", "Disney+"),
    ("PayPal Europe S.a.r.l. et Cie S.C.A", "PP.8812.PP . ZALANDO SE, Ihr Einkauf bei ZALANDO SE", -59.90, "Shopping", "Zalando"),
    ("AMAZON EU S.A R.L., NIEDERLASSUNG DEUTSCHLAND", "AMZN Mktp DE 302-1234567", -1249.00, "Shopping", "Amazon"),
    ("IKEA Deutschland GmbH & Co. KG", "IKEA Berlin-Tempelhof", -189.00, "Shopping", "IKEA"),
    ("MediaMarkt", "MEDIA MARKT 1102", -299.00, "Shopping", "MediaMarkt"),
    ("H&M Hennes & Mauritz", "H&M 221 Koeln", -39.98, "Shopping", "H&M"),
    ("Thalia Buecher GmbH", "", -16.00, "Shopping", "Thalia"),
    ("Hausverwaltung Kiefer GmbH", "Miete August 2026 Whg 3.OG links", -890.00, "Housing", None),
    ("Vonovia SE", "Nutzungsgebuehr Wohnung 4711", -1020.00, "Housing", None),
    ("Stadtwerke Musterstadt", "Abschlag Strom August", -64.00, "Utilities", None),
    ("Vattenfall Europe Sales", "Abschlag Gas", -88.00, "Utilities", None),
    ("ARD ZDF Deutschlandradio Beitragsservice", "Rundfunkbeitrag", -55.08, "Utilities", "Rundfunkbeitrag"),
    ("Apotheke am Markt", "2026-08-09 Debitk.3", -18.95, "Health", None),
    ("Zahnarzt Dr. Weber", "Rechnung 2231", -120.00, "Health", None),
    ("HUK-COBURG", "Kfz-Versicherung 2026", -42.10, "Insurance", None),
    ("Techniker Krankenkasse", "Zusatzbeitrag", -15.00, "Insurance", None),
    ("CineStar", "Kinotickets", -24.00, "Entertainment", None),
    ("EVENTIM", "Tickets Konzert", -89.00, "Entertainment", None),
    ("Kita Sonnenschein e.V.", "Kita Beitrag August", -180.00, "Childcare & education", None),
    ("", "Bargeldauszahlung GAA 01234 Sparkasse Berlin", -100.00, "Cash", "Cash withdrawal"),
    ("Max Mustermann", "Umbuchung auf Tagesgeld", -200.00, "Transfers", None),
    ("Max Mustermann", "Kreditkartenabrechnung August", -412.30, "Transfers", None),
    ("Max Mustermann", "Uebertrag vom Tagesgeld", 500.00, "Transfers", None),
    ("Arbeitgeber GmbH", "Gehalt August 2026 PersNr 4711", 2850.00, "Income", None),
    ("Familienkasse", "Kindergeld 08/2026", 250.00, "Income", None),
    ("PayPal Europe S.a.r.l. et Cie S.C.A", "Rueckzahlung ZALANDO SE Retoure 88213", 59.90, "Refunds", "Zalando"),
    ("Anna Beispiel", "Anteil Urlaub Ferienwohnung", 320.00, "Income", None),
    ("Mobilfunk Nord GmbH", "Rechnung 08/2026", -19.99, "Other", "Mobilfunk Nord"),
    ("XYZ Handels UG", "Rechnung 4411", -45.00, "Other", "Xyz Handels"),
]


def run():
    return [(case, categorise(case[0], case[1], Decimal(str(case[2])))) for case in LABELLED]


def test_category_accuracy_on_labelled_statement_lines():
    results = run()
    wrong = [(c[0], c[1], c[3], r.category) for c, r in results if r.category != c[3]]
    accuracy = 1 - len(wrong) / len(results)
    print(f"\ncategory accuracy {accuracy:.1%} on {len(results)} labelled lines; wrong: {wrong}")
    assert accuracy >= 0.95, wrong


def test_merchant_names_are_clean():
    results = run()
    wrong = [(c[0], c[4], r.merchant) for c, r in results if c[4] and r.merchant != c[4]]
    assert not wrong, wrong


def test_direction_follows_the_money():
    for case, result in run():
        assert result.direction == ("in" if case[2] > 0 else "out"), case


def test_every_result_says_which_rule_decided_it():
    for _, result in run():
        assert result.rule


@pytest.mark.parametrize("raw, clean", [
    ("PAYPAL *ZALANDO 1043-2231//BERLIN/DE", "Zalando"),
    ("REWE Markt GmbH-Zw 1234", "Rewe Markt"),
    ("SumUp *Cafe Kranz", "Cafe Kranz"),
    ("", ""),
])
def test_clean_merchant(raw, clean):
    assert clean_merchant(raw) == clean
