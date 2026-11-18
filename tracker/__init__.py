"""Money tracker: a small Flask app for logging income and spending, with budgets and bank statement import."""
import os
import re
import secrets
from datetime import date

from flask import Flask, flash, redirect, render_template, request, url_for

from . import db
from .finance import (EXPENSE_CATEGORIES, INCOME_CATEGORIES, budget_report, category_totals,
                      format_pence, parse_date, parse_statement, summary, to_pence)

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        # On Render there's no SECRET_KEY set, so make a random one each start (it only protects flash messages)
        SECRET_KEY=os.environ.get("SECRET_KEY") or (secrets.token_hex(32) if os.environ.get("RENDER") else "dev-only-change-me"),
        DEMO_DATA=os.environ.get("DEMO_DATA") == "1",
        DATABASE=os.path.join(app.instance_path, "tracker.sqlite"),
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,  # reject uploads over 1 MB
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)

    app.teardown_appcontext(db.close_db)
    with app.app_context():
        db.init_db()
        if app.config["DEMO_DATA"]:
            from .demo import seed_if_empty
            seed_if_empty()

    app.jinja_env.filters["money"] = format_pence

    def current_month():
        m = request.args.get("month", "")
        return m if MONTH_RE.match(m) else date.today().strftime("%Y-%m")

    @app.context_processor
    def inject_globals():
        return {"expense_categories": EXPENSE_CATEGORIES, "income_categories": INCOME_CATEGORIES,
                "demo_mode": app.config["DEMO_DATA"]}

    @app.route("/", methods=["GET", "POST"])
    def dashboard():
        if request.method == "POST":
            form = request.form
            kind = form.get("kind", "expense")
            category = form.get("category", "")
            allowed = EXPENSE_CATEGORIES if kind == "expense" else INCOME_CATEGORIES
            errors = []
            try:
                amount = to_pence(form.get("amount", ""))
                if amount <= 0:
                    errors.append("Amount must be more than zero.")
            except ValueError as exc:
                errors.append(str(exc))
            try:
                entry_date = parse_date(form.get("date", ""))
            except ValueError:
                errors.append("Please pick a valid date.")
            if kind not in ("income", "expense") or category not in allowed:
                errors.append("Please pick a valid category.")
            if errors:
                for e in errors:
                    flash(e, "error")
            else:
                db.add_entry(entry_date, form.get("description", "").strip()[:100], kind, category, amount)
                flash(f"Added {format_pence(amount)} ({category}).", "success")
                return redirect(url_for("dashboard", month=entry_date[:7]))
            return redirect(url_for("dashboard"))

        month = current_month()
        entries = db.entries_for_month(month)
        totals = category_totals(entries)
        report = budget_report(totals, db.get_budgets())
        biggest = max(totals.values(), default=0)
        return render_template(
            "dashboard.html", month=month, entries=entries[:5], summary=summary(entries), totals=totals,
            biggest=biggest, report=report, months=db.months_with_entries(), today=date.today().isoformat(),
            alerts=[r for r in report if r["state"] in ("over", "near")],
            budget_by_cat={r["category"]: r for r in report},
        )

    @app.route("/entries")
    def entries():
        month = current_month()
        return render_template("entries.html", month=month, entries=db.entries_for_month(month),
                               months=db.months_with_entries())

    @app.post("/entries/<int:entry_id>/delete")
    def delete(entry_id):
        db.delete_entry(entry_id)
        flash("Entry deleted.", "success")
        return redirect(request.referrer or url_for("entries"))

    @app.route("/budgets", methods=["GET", "POST"])
    def budgets():
        if request.method == "POST":
            category = request.form.get("category", "")
            if category not in EXPENSE_CATEGORIES:
                flash("Please pick a valid category.", "error")
            elif request.form.get("action") == "remove":
                db.remove_budget(category)
                flash(f"Removed the {category} budget.", "success")
            else:
                try:
                    limit = to_pence(request.form.get("limit", ""))
                    if limit <= 0:
                        raise ValueError("Limit must be more than zero.")
                    db.set_budget(category, limit)
                    flash(f"{category.title()} budget set to {format_pence(limit)} a month.", "success")
                except ValueError as exc:
                    flash(str(exc), "error")
            return redirect(url_for("budgets"))
        return render_template("budgets.html", budgets=db.get_budgets())

    @app.route("/upload", methods=["GET", "POST"])
    def upload():
        if request.method == "POST":
            file = request.files.get("statement")
            if not file or not file.filename:
                flash("Please choose a CSV file.", "error")
                return redirect(url_for("upload"))
            if not file.filename.lower().endswith(".csv"):
                flash("Only .csv files are supported.", "error")
                return redirect(url_for("upload"))
            try:
                text = file.read().decode("utf-8-sig")
            except UnicodeDecodeError:
                flash("That file isn't readable text. Export your statement as CSV.", "error")
                return redirect(url_for("upload"))

            parsed, errors = parse_statement(text)
            added = skipped = 0
            for e in parsed:
                # Skip rows already imported, so uploading the same statement twice doesn't double-count
                if db.entry_exists(e["date"], e["description"], e["amount_pence"], e["kind"]):
                    skipped += 1
                    continue
                db.add_entry(e["date"], e["description"], e["kind"], e["category"], e["amount_pence"], "statement")
                added += 1
            for err in errors[:5]:
                flash(err, "error")
            if len(errors) > 5:
                flash(f"...and {len(errors) - 5} more problem lines.", "error")
            flash(f"Imported {added} transaction(s). Skipped {skipped} already imported.", "success")
            latest = max((e["date"] for e in parsed), default=None)
            return redirect(url_for("entries", month=latest[:7]) if latest else url_for("upload"))
        return render_template("upload.html")

    @app.errorhandler(413)
    def too_large(_e):
        flash("That file is too big (max 1 MB).", "error")
        return redirect(url_for("upload"))

    return app
