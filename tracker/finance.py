"""
The money maths, kept separate from Flask so it can be tested on its own.

All money is stored as whole pence (integers), never as floats.
Floats can't represent 0.1 exactly, so 0.1 + 0.2 == 0.30000000000000004,
and those tiny errors add up across hundreds of transactions.
"""
import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

EXPENSE_CATEGORIES = ["food", "rent", "bills", "transport", "fun", "shopping", "other"]
INCOME_CATEGORIES = ["wages", "student loan", "other income"]

# Warn when spending reaches this share of a budget
NEAR_LIMIT = Decimal("0.8")

# Keyword rules for auto-categorising bank statement lines (checked in order)
CATEGORY_RULES = [
    ("rent", ["rent", "letting", "landlord"]),
    ("food", ["tesco", "sainsbury", "aldi", "lidl", "asda", "morrisons", "co-op", "greggs",
              "deliveroo", "just eat", "uber eats", "mcdonald", "nando", "subway", "costa", "starbucks"]),
    ("transport", ["uber", "trainline", "gwr", "tfw", " bus ", "stagecoach", "shell", "esso", " bp ", "parking"]),
    ("bills", [" ee ", "vodafone", " o2 ", " three ", "giffgaff", "british gas", "octopus", "water", "council tax",
               "virgin media", " bt "]),
    ("fun", ["netflix", "spotify", "disney", "cinema", "odeon", "steam", "playstation", "xbox", "ticketmaster"]),
    ("shopping", ["amazon", "primark", "asos", "argos", "ebay", "boots", "superdrug"]),
]


def to_pence(text):
    """Turn user text like '12.50', '£1,200' or '3' into whole pence (1250, 120000, 300).

    Raises ValueError for anything that isn't a valid amount with at most 2 decimal places.
    """
    cleaned = str(text).strip().replace("£", "").replace(",", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"'{text}' is not a valid amount")
    if not value.is_finite():
        raise ValueError(f"'{text}' is not a valid amount")
    if value != value.quantize(Decimal("0.01")):
        raise ValueError(f"'{text}' has more than 2 decimal places")
    return int(value * 100)


def format_pence(pence):
    """1250 -> '£12.50', -300 -> '-£3.00', 123456 -> '£1,234.56'."""
    sign = "-" if pence < 0 else ""
    pounds, p = divmod(abs(pence), 100)
    return f"{sign}£{pounds:,}.{p:02d}"


def category_totals(entries):
    """Total spent per expense category, biggest first. entries: dicts with kind, category, amount_pence."""
    totals = {}
    for e in entries:
        if e["kind"] == "expense":
            totals[e["category"]] = totals.get(e["category"], 0) + e["amount_pence"]
    return dict(sorted(totals.items(), key=lambda kv: kv[1], reverse=True))


def summary(entries):
    """Income, spending and what's left over (all in pence)."""
    income = sum(e["amount_pence"] for e in entries if e["kind"] == "income")
    spent = sum(e["amount_pence"] for e in entries if e["kind"] == "expense")
    return {"income": income, "spent": spent, "left": income - spent}


def budget_status(spent_pence, limit_pence):
    """'over', 'near' (80%+), or 'ok' for one category, plus the percentage used."""
    if limit_pence <= 0:
        raise ValueError("Budget limit must be more than zero")
    used = Decimal(spent_pence) / Decimal(limit_pence)
    if spent_pence > limit_pence:
        state = "over"
    elif used >= NEAR_LIMIT:
        state = "near"
    else:
        state = "ok"
    return {"state": state, "percent": int(used * 100), "remaining": limit_pence - spent_pence}


def budget_report(totals, budgets):
    """Combine category totals with budget limits. budgets: {category: limit_pence}."""
    report = []
    for category, limit in budgets.items():
        spent = totals.get(category, 0)
        report.append({"category": category, "spent": spent, "limit": limit, **budget_status(spent, limit)})
    order = {"over": 0, "near": 1, "ok": 2}
    return sorted(report, key=lambda r: (order[r["state"]], -r["percent"]))


def guess_category(description):
    text = f" {description.lower()} "
    for category, keywords in CATEGORY_RULES:
        if any(k in text for k in keywords):
            return category
    return "other"


def parse_statement(file_text):
    """Read a bank statement CSV with columns Date, Description, Amount.

    Negative amounts are money going out (expenses); positive amounts are money coming in.
    Dates can be DD/MM/YYYY (UK banks) or YYYY-MM-DD. Returns (entries, errors).
    """
    reader = csv.DictReader(io.StringIO(file_text.lstrip("﻿")))
    if reader.fieldnames is None:
        return [], ["The file is empty."]
    columns = {name.strip().lower(): name for name in reader.fieldnames}
    missing = [c for c in ("date", "description", "amount") if c not in columns]
    if missing:
        return [], [f"Missing column(s): {', '.join(missing)}. Expected Date, Description, Amount."]

    entries, errors = [], []
    for row in reader:
        line_no = reader.line_num  # real line in the file, even after blank lines
        raw_date = (row[columns["date"]] or "").strip()
        description = (row[columns["description"]] or "").strip()
        raw_amount = (row[columns["amount"]] or "").strip()
        if not (raw_date or description or raw_amount):
            continue  # blank line
        try:
            date = parse_date(raw_date)
            pence = to_pence(raw_amount)
        except ValueError as exc:
            errors.append(f"Line {line_no}: {exc}")
            continue
        if pence == 0:
            continue
        is_income = pence > 0
        entries.append({
            "date": date,
            "description": description[:100] or "Bank transaction",
            "kind": "income" if is_income else "expense",
            "category": "other income" if is_income else guess_category(description),
            "amount_pence": abs(pence),
        })
    return entries, errors


def parse_date(text):
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"'{text}' is not a date (use DD/MM/YYYY)")
