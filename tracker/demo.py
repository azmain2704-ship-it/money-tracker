"""Sample data for the hosted demo, so a visitor sees a filled-in dashboard instead of an empty one.

Only runs when DEMO_DATA=1 and the database is empty. It loads examples/sample_statement.csv with the
dates moved into the current month, and sets a few budgets so the warnings show up.
"""
import os
from datetime import date

from . import db
from .finance import parse_statement

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "examples", "sample_statement.csv")
BUDGETS = {"food": 10000, "fun": 3000, "transport": 4000, "shopping": 5000}  # pence


def seed_if_empty(today=None):
    if db.months_with_entries():
        return 0
    today = today or date.today()
    with open(SAMPLE, encoding="utf-8-sig") as f:
        entries, _errors = parse_statement(f.read())
    for e in entries:
        day = min(int(e["date"][8:10]), today.day)
        when = today.replace(day=day).isoformat()
        db.add_entry(when, e["description"], e["kind"], e["category"], e["amount_pence"], "statement")
    for category, limit in BUDGETS.items():
        db.set_budget(category, limit)
    return len(entries)
