"""'Ask about my money': question answering over verified numbers.

    question -> router (LLM picks a query from a fixed catalog; code validates it,
                with a keyword router as fallback)
             -> analytics.queries computes the answer with pandas
             -> LLM phrases the verified result
             -> guardrails check the wording; the template answer replaces it on failure

The LLM never sees raw transactions and never does arithmetic. Questions asking
for investment advice are declined by code before any model is involved.
"""

import json
import logging
import re

import pandas as pd

from ai.guardrails import collect_allowed_numbers, validate_sentence
from ai.providers import get_provider
from analytics import queries
from analytics.spending import available_months, spending_only

logger = logging.getLogger(__name__)

MAX_ANSWER_LENGTH = 480

MONTH_NAMES = {
    name: number
    for number, names in enumerate(
        [("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",), ("june", "jun"),
         ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"), ("october", "oct"),
         ("november", "nov"), ("december", "dec")],
        start=1,
    )
    for name in names
}

# Regulated advice is out of scope for a spending assistant (MiFID II); decline without the LLM.
ADVICE_PATTERN = re.compile(
    r"\b(invest\w*|stocks?|shares|etfs?|crypto\w*|bitcoin|portfolio|trading|trade|buy .* (stock|fund)|mortgage|loan|credit score)\b",
    re.IGNORECASE,
)
ADVICE_REPLY = (
    "I can explain your own spending and income, but I can't give investment, credit or other "
    "financial advice. For that, please talk to {contact}."
)

SUGGESTIONS = [
    "How much did I spend on restaurants this month?",
    "Am I within my budgets?",
    "Where did most of my money go?",
    "Compare my groceries with last month",
    "What were my biggest payments?",
    "How much did I save this month?",
]


# ---------------------------------------------------------------- context

def _context(df: pd.DataFrame, month: str) -> dict:
    spending = spending_only(df)
    merchants = spending.groupby("merchant")["amount"].sum().sort_values(ascending=False)
    return {
        "months": [str(m) for m in available_months(df)],
        "month": month,
        "categories": sorted(spending["category"].unique()),
        "merchants": list(merchants.index[:40]),
    }


def _match(value, options: list[str]) -> str | None:
    """Case-insensitive match that also accepts simple plurals ("restaurants")."""
    if not isinstance(value, str) or not value.strip():
        return None
    wanted = value.strip().lower()
    for option in options:
        lowered = option.lower()
        if wanted in (lowered, lowered + "s", lowered + "es") or wanted.rstrip("s") == lowered:
            return option
    return None


def _explicit_months(question: str, ctx: dict) -> list[str]:
    """Months named in the question, resolved to the most recent matching month in the data."""
    lowered = question.lower()
    current = pd.Period(ctx["month"], freq="M")
    found: list[str] = []

    for phrase, period in (("this month", current), ("last month", current - 1), ("previous month", current - 1)):
        if phrase in lowered:
            found.append(str(period))

    for word in re.findall(r"[a-z]+", lowered):
        number = MONTH_NAMES.get(word)
        if number is None or (word == "may" and not re.search(r"\bmay\b(?!\s+i\b)", lowered)):
            continue
        candidates = [m for m in ctx["months"] if int(m[5:]) == number and m <= ctx["month"]]
        if candidates and candidates[-1] not in found:
            found.append(candidates[-1])

    return [m for m in found if m in ctx["months"]]


# ---------------------------------------------------------------- routing

def _router_prompt(question: str, ctx: dict, previous: dict | None) -> str:
    tools = "\n".join(f'- "{name}": {description}' for name, (_, description) in queries.TOOLS.items())
    earlier = (
        f"\nThe previous question used: {json.dumps(previous)}. Reuse its values if this is a follow-up."
        if previous
        else ""
    )
    return f"""You route a banking customer's question to exactly one query.

Queries:
{tools}
- "unsupported": the question is not about this customer's own spending or income.

Known categories: {", ".join(ctx["categories"])}
Known merchants: {", ".join(ctx["merchants"])}
Months with data (YYYY-MM): {", ".join(ctx["months"])}
The month the customer is looking at: {ctx["month"]}{earlier}

Question: "{question}"

Return a JSON object: {{"tool": "...", "category": null or a known category, "merchant": null or a known merchant,
"month": "YYYY-MM" or null, "compare_month": "YYYY-MM" or null, "n": null or a number}}"""


# Everyday words for categories; only used when that category exists in the customer's data.
CATEGORY_SYNONYMS = {
    "Restaurant": ("eating out", "eat out", "dining", "restaurant", "takeaway", "food delivery", "lunch", "dinner"),
    "Groceries": ("grocer", "supermarket", "food shopping"),
    "Transport": ("taxi", "uber", "train", "travel", "fuel", "petrol", "commute", "transport"),
    "Shopping": ("clothes", "shopping", "online shopping"),
    "Housing": ("rent", "housing"),
    "Subscriptions": ("subscription", "streaming"),
    "Entertainment": ("entertainment", "cinema", "concert", "going out"),
    "Health": ("health", "pharmacy", "doctor"),
}

# Clear phrasings route deterministically; the LLM only decides the ambiguous rest.
KEYWORD_RULES = [
    (("budget", "limit i set", "over my limit"), "budget_status"),
    (("compare", " vs", "versus", "than last", "than in", "difference between"), "compare"),
    (("unusual", "suspicious", "strange", "weird", "fraud", "anything odd"), "unusual"),
    (("biggest payment", "largest", "most expensive", "biggest purchase", "biggest expense", "biggest payments"),
     "largest_payments"),
    (("which shop", "which store", "which merchant", "top merchant", "where do i spend the most at"), "top_merchants"),
    (("where did", "where does", "most of my money", "breakdown", "split", "by category"), "breakdown"),
    (("average", "usually", "typical", "normally", "per month on average"), "monthly_average"),
    (("save", "saved", "saving", "income", "salary", "earn", "left over", "kept", "money in", "came in",
      "in and out", "went out"), "income"),
]


def _keyword_route(question: str) -> dict:
    q = question.lower()
    for keywords, tool in KEYWORD_RULES:
        if any(keyword in q for keyword in keywords):
            return {"tool": tool}
    if any(word in q for word in ("spend", "spent", "cost", "pay", "paid", "how much")):
        return {"tool": "spending"}
    return {"tool": "unsupported"}


def _category_in_question(question: str, ctx: dict) -> str | None:
    lowered = question.lower()
    for category in ctx["categories"]:
        if re.search(rf"\b{re.escape(category.lower())}", lowered):
            return category
    for category, words in CATEGORY_SYNONYMS.items():
        if category in ctx["categories"] and any(word in lowered for word in words):
            return category
    return None


def _grounded(value: str | None, lowered_question: str) -> str | None:
    """Keep a model-picked name only if a word of it (4+ letters) appears in the question."""
    if value and any(word in lowered_question for word in re.findall(r"[a-z']{4,}", value.lower())):
        return value
    return None


FOLLOW_UP_PATTERN = re.compile(r"^\s*(and|what about|how about|same for|also)\b", re.IGNORECASE)


def _validated_route(raw: dict, question: str, ctx: dict, previous: dict | None = None) -> dict:
    keyword_tool = _keyword_route(question)["tool"]
    tool = raw.get("tool")
    if keyword_tool not in ("spending", "unsupported") or tool not in (*queries.TOOLS, "unsupported"):
        tool = keyword_tool  # an unambiguous phrasing, or the model returned something unusable

    lowered = question.lower()
    # A category or merchant is only used when the question mentions it; the model may not add one.
    category = _category_in_question(question, ctx) or _grounded(_match(raw.get("category"), ctx["categories"]), lowered)
    merchant = next((m for m in ctx["merchants"] if m.lower() in lowered), None) or _grounded(
        _match(raw.get("merchant"), ctx["merchants"]), lowered
    )

    # "and in July?" / "what about groceries?" continue the previous question.
    follow_up = previous if previous and FOLLOW_UP_PATTERN.search(question) else None
    if follow_up:
        if keyword_tool in ("spending", "unsupported") and follow_up.get("tool") in queries.TOOLS:
            tool = follow_up["tool"]
        if not category and not merchant:
            category, merchant = follow_up.get("category"), follow_up.get("merchant")

    # Months come from the question text, a follow-up, or the viewed month; never from the model's guess.
    explicit = _explicit_months(question, ctx)
    if tool == "compare" and len(explicit) == 1 and explicit[0] != ctx["month"]:
        explicit = [ctx["month"], explicit[0]]  # "compare with last month" = viewed month vs that month
    fallback_month = follow_up["month"] if follow_up and follow_up.get("month") in ctx["months"] else ctx["month"]
    month = explicit[0] if explicit else fallback_month
    compare_month = explicit[1] if len(explicit) > 1 else None
    if tool != "compare":
        compare_month = None
    elif compare_month not in ctx["months"] or compare_month == month:
        previous = str(pd.Period(month, freq="M") - 1)
        compare_month = previous if previous in ctx["months"] else None
        if compare_month is None:
            tool = "spending"

    n = raw.get("n")
    n = int(n) if isinstance(n, (int, float)) and 1 <= n <= 10 else 3

    return {"tool": tool, "category": category, "merchant": merchant, "month": month,
            "compare_month": compare_month, "n": n}


def route(question: str, ctx: dict, previous: dict | None = None) -> tuple[dict, str]:
    """Return (validated route, router used: 'ai' | 'keywords')."""
    try:
        raw = get_provider().complete_json(_router_prompt(question, ctx, previous))
        used = "ai"
    except Exception as exc:
        logger.warning("LLM router unavailable, using keywords: %s", exc)
        raw, used = _keyword_route(question), "keywords"
    return _validated_route(raw, question, ctx, previous), used


# ---------------------------------------------------------------- answering

def _run_query(df: pd.DataFrame, plan: dict, budgets: dict[str, float] | None = None) -> dict:
    function, _ = queries.TOOLS[plan["tool"]]
    month = pd.Period(plan["month"], freq="M")
    compare_month = pd.Period(plan["compare_month"], freq="M") if plan.get("compare_month") else None
    return function(
        df, month=month, compare_month=compare_month, category=plan["category"],
        merchant=plan["merchant"], n=plan["n"], budgets=budgets,
    )


def _answer_prompt(question: str, result: dict) -> str:
    facts = "\n".join(f"- {label}: {value}" for label, value in result["facts"].items())
    return f"""You are NarrAI, a friendly assistant inside a banking app.

Customer question: "{question}"

Verified result:
{facts}

Answer the question in 1 to 3 short sentences, speaking to the customer as "you".
Rules:
0. Always say what the numbers are about, as given in "What" (for example the category or merchant).
1. Use ONLY numbers from the verified result, written exactly as shown. Never calculate anything new.
2. State facts only. Never guess reasons ("because", "due to", "likely") and never give advice.
3. If the result does not answer the question, say what it does show.

Return a JSON object: {{"answer": "..."}}"""


def _allowed_numbers(result: dict) -> set[float]:
    # Labels contain numbers too (months, "#1"), so check against labels and values alike.
    return collect_allowed_numbers({"facts": [f"{k} {v}" for k, v in result["facts"].items()], "args": result["args"]})


OVER_LEFT_PATTERN = re.compile(r"€\s?(\d[\d,]*(?:\.\d+)?)\s+(over|left|remaining|under)\b", re.IGNORECASE)


def _budget_difference_ok(text: str, result: dict) -> bool:
    """'€X over' / '€X left' must be a verified budget difference, not any number from the facts."""
    if result["tool"] != "budget_status":
        return True
    verified = {
        float(str(value).replace("€", "").replace(",", ""))
        for label, value in result["facts"].items()
        if label.endswith(("over budget by", "left in budget"))
    }
    return all(float(amount.replace(",", "")) in verified for amount, _ in OVER_LEFT_PATTERN.findall(text))


def _names_scope(text: str, plan: dict, question: str) -> bool:
    """A category or merchant answer must say what it is about, in our words or the customer's."""
    target = plan.get("merchant") or plan.get("category")
    if not target:
        return True
    lowered, asked = text.lower(), question.lower()
    words = {target.lower()} | {w for w in CATEGORY_SYNONYMS.get(plan.get("category") or "", ()) if w in asked}
    return any(word in lowered for word in words)


def answer_question(
    df: pd.DataFrame,
    question: str,
    month: str,
    previous: dict | None = None,
    advice_contact: str = "a licensed adviser at your bank",
    budgets: dict[str, float] | None = None,
) -> dict:
    question = question.strip()[:500]
    ctx = _context(df, month)
    base = {"question": question, "month": month, "suggestions": SUGGESTIONS[:3]}

    if ADVICE_PATTERN.search(question):
        return {**base, "answer": ADVICE_REPLY.format(contact=advice_contact), "source": "policy", "tool": "unsupported", "plan": None,
                "facts": {}, "issues": [], "router": "policy"}

    plan, router = route(question, ctx, previous)

    if plan["tool"] == "unsupported":
        reply = (
            "I can only answer questions about your own spending and income, for example: "
            "\"How much did I spend on groceries last month?\""
        )
        return {**base, "answer": reply, "source": "policy", "tool": "unsupported", "plan": plan,
                "facts": {}, "issues": [], "router": router}

    try:
        result = _run_query(df, plan, budgets)
    except ValueError as exc:
        return {**base, "answer": f"I couldn't calculate that: {exc}", "source": "policy", "tool": plan["tool"],
                "plan": plan, "facts": {}, "issues": [], "router": router}

    text, issues = "", ["not generated"]
    try:
        draft = get_provider().complete_json(_answer_prompt(question, result)).get("answer")
        if isinstance(draft, str) and draft.strip():
            text = draft.strip()
            issues = validate_sentence(text, _allowed_numbers(result), max_length=MAX_ANSWER_LENGTH)
            if not _names_scope(text, plan, question):
                issues.append("missing topic (category or merchant)")
            if not _budget_difference_ok(text, result):
                issues.append("wrong budget difference")
    except Exception as exc:
        logger.warning("LLM answer unavailable, using template: %s", exc)

    if issues:
        if text:
            logger.info("Rejected AI answer (%s): %r", ", ".join(issues), text)
        text, source = result["summary"], "template"
    else:
        source = "ai"

    return {**base, "answer": text, "source": source, "tool": plan["tool"], "plan": plan,
            "facts": result["facts"], "issues": issues, "router": router}
