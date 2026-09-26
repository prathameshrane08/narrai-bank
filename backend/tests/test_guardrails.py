from ai.guardrails import collect_allowed_numbers, validate_sentence
from ai.storyteller import template_story

FACTS = {
    "month_label": "August 2026",
    "headline": {"category": "Restaurant", "current": 149.5, "change_pct": 196.0},
    "drivers": [{"merchant": "L'Osteria", "change_amount": 47.5}],
    "patterns": {"weekend_share_pct": 100.0, "transactions_current": 4},
}
ALLOWED = collect_allowed_numbers(FACTS)


def test_accepts_verified_numbers():
    text = "Your restaurant spending increased by 196.0% to €149.50 in August 2026."
    assert validate_sentence(text, ALLOWED, ("Restaurant",)) == []


def test_accepts_rounded_numbers():
    assert validate_sentence("Spending rose 196% to about €150.", ALLOWED) == []


def test_rejects_invented_number():
    issues = validate_sentence("Spending increased by 210% to €149.50.", ALLOWED)
    assert issues == ["unverified number 210"]


def test_rejects_speculation():
    issues = validate_sentence("You probably ate out more because you were busy.", ALLOWED)
    assert any("probably" in issue for issue in issues)


def test_requires_key_terms():
    issues = validate_sentence("A merchant added €47.50.", ALLOWED, ("L'Osteria",))
    assert issues == ["missing 'L'Osteria'"]


def test_template_story_passes_its_own_guardrails(sample_facts):
    allowed = collect_allowed_numbers(sample_facts)
    for text in template_story(sample_facts).values():
        assert validate_sentence(text, allowed) == [], text


def test_rejects_comparison_in_wrong_direction():
    allowed = collect_allowed_numbers({"a": 17.66, "b": 16.32})
    issues = validate_sentence("Your average was €17.66 this month, down from €16.32 last month.", allowed)
    assert len(issues) == 1 and issues[0].startswith("wrong direction")


def test_accepts_comparison_in_right_direction():
    allowed = collect_allowed_numbers({"a": 17.66, "b": 16.32})
    assert validate_sentence("Your average was €17.66 this month, up from €16.32.", allowed) == []


def test_headline_direction_must_match_facts():
    issues = validate_sentence("Your Groceries spending went up by 196%.", ALLOWED, expected_direction="decrease")
    assert issues == ["wrong direction: says up, facts say down"]


def test_from_to_comparison_uses_the_to_value():
    allowed = collect_allowed_numbers({"a": 66.36, "b": 0.0, "c": 37.50, "d": 42.70})
    text = "Lidl went from €66.36 to €0.00, and Netto increased from €37.50 to €42.70."
    assert validate_sentence(text, allowed) == []

    wrong = "Netto decreased from €37.50 to €42.70."
    assert validate_sentence(wrong, allowed)[0].startswith("wrong direction")


def test_numbers_with_thousands_separators_in_facts_are_allowed():
    allowed = collect_allowed_numbers({"Kept": "€2,424.32"})
    assert validate_sentence("You kept €2,424.32 this month.", allowed) == []


def test_transaction_count_must_match_its_month(sample_facts):
    from ai.storyteller import assemble_story

    p = sample_facts["patterns"]  # 4 restaurant payments in August, 2 in July
    swapped = {"meaning": f"You had {p['transactions_previous']} Restaurant transactions this month."}
    right = {"meaning": f"You had {p['transactions_current']} Restaurant transactions this month."}

    assert assemble_story(sample_facts, swapped, True)["sections"]["meaning"]["issues"] == [
        "wrong month for transaction count"
    ]
    assert assemble_story(sample_facts, right, True)["sections"]["meaning"]["source"] == "ai"
