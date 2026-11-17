"""Tests for the money maths. Run with:  pytest"""
import pytest

from tracker.finance import (budget_report, budget_status, category_totals, format_pence, guess_category,
                             parse_statement, summary, to_pence)


# 1. Amounts are converted to whole pence exactly, with no floating-point errors
@pytest.mark.parametrize("text, pence", [
    ("12.50", 1250), ("£1,200", 120000), ("3", 300), ("0.10", 10), (" 7.05 ", 705), ("-4.99", -499),
])
def test_to_pence_converts_exactly(text, pence):
    assert to_pence(text) == pence


def test_to_pence_rejects_bad_input():
    for bad in ["abc", "", "1.234", "NaN", "inf"]:
        with pytest.raises(ValueError):
            to_pence(bad)


# 2. Adding 10p ten times gives exactly £1.00 (with floats it doesn't)
def test_no_floating_point_drift():
    total = 0.0
    for _ in range(10):
        total += 0.10                       # adding up a running balance, like a real app would
    assert total != 1.0                     # the float problem: total is 0.9999999999999999
    assert 0.1 + 0.2 != 0.3                 # same problem: 0.30000000000000004
    assert sum(to_pence("0.10") for _ in range(10)) == 100   # whole pence fixes it


def test_format_pence():
    assert format_pence(1250) == "£12.50"
    assert format_pence(123456) == "£1,234.56"
    assert format_pence(-305) == "-£3.05"
    assert format_pence(0) == "£0.00"


# 3. Category totals add up correctly and ignore income
def test_category_totals():
    entries = [
        {"kind": "expense", "category": "food", "amount_pence": 1250},
        {"kind": "expense", "category": "food", "amount_pence": 799},
        {"kind": "expense", "category": "rent", "amount_pence": 45000},
        {"kind": "income", "category": "wages", "amount_pence": 60000},
    ]
    assert category_totals(entries) == {"rent": 45000, "food": 2049}
    assert list(category_totals(entries)) == ["rent", "food"]  # biggest first


def test_summary_income_minus_spending():
    entries = [
        {"kind": "income", "category": "wages", "amount_pence": 41280},
        {"kind": "expense", "category": "rent", "amount_pence": 45000},
    ]
    assert summary(entries) == {"income": 41280, "spent": 45000, "left": -3720}


# 4. Budget warnings: ok below 80%, near at 80% or more, over when spending exceeds the limit
@pytest.mark.parametrize("spent, limit, state", [
    (7999, 10000, "ok"),
    (8000, 10000, "near"),   # exactly 80% triggers the warning
    (10000, 10000, "near"),  # spending exactly the limit is not over it
    (10001, 10000, "over"),  # one penny over is over
])
def test_budget_status_boundaries(spent, limit, state):
    assert budget_status(spent, limit)["state"] == state


def test_budget_report_orders_worst_first_and_counts_unspent_categories():
    report = budget_report({"food": 16000, "fun": 2000}, {"food": 15000, "fun": 10000, "transport": 5000})
    assert [r["category"] for r in report] == ["food", "fun", "transport"]
    assert report[0]["state"] == "over" and report[0]["remaining"] == -1000
    assert report[2]["spent"] == 0  # a budget with no spending yet still shows


def test_budget_limit_must_be_positive():
    with pytest.raises(ValueError):
        budget_status(100, 0)


# 5. Bank statement import: signs, dates, categories and bad lines
def test_parse_statement():
    csv_text = (
        "Date,Description,Amount\n"
        "03/11/2026,TESCO STORES CARDIFF,-23.45\n"
        "05/11/2026,PART-TIME JOB PAYROLL,412.80\n"
        "2026-11-07,NETFLIX.COM,-5.99\n"
        "\n"
        "08/11/2026,MYSTERY SHOP,not-a-number\n"
    )
    entries, errors = parse_statement(csv_text)
    assert len(entries) == 3
    tesco, wages, netflix = entries
    assert tesco == {"date": "2026-11-03", "description": "TESCO STORES CARDIFF", "kind": "expense",
                     "category": "food", "amount_pence": 2345}
    assert wages["kind"] == "income" and wages["amount_pence"] == 41280
    assert netflix["category"] == "fun" and netflix["date"] == "2026-11-07"
    assert len(errors) == 1 and "Line 6" in errors[0]


def test_parse_statement_reports_missing_columns():
    entries, errors = parse_statement("When,What\n01/01/2026,thing\n")
    assert entries == [] and "Missing column" in errors[0]


def test_guess_category_avoids_partial_word_matches():
    assert guess_category("UBER EATS ORDER") == "food"     # not transport
    assert guess_category("UBER TRIP") == "transport"
    assert guess_category("BUSINESS RATES REFUND") == "other"  # 'bus' inside 'business' doesn't count
