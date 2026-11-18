"""End-to-end tests through Flask's test client, each with a fresh temporary database."""
import io

import pytest

from tracker import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite"), "SECRET_KEY": "test"})
    return app.test_client()


def add(client, amount, category="food", kind="expense", date="2026-11-10"):
    return client.post("/", data={"kind": kind, "amount": amount, "category": category, "date": date},
                       follow_redirects=True)


def test_add_entry_and_see_totals(client):
    add(client, "12.50")
    add(client, "7.49")
    add(client, "450", category="wages", kind="income")
    page = client.get("/?month=2026-11").get_data(as_text=True)
    assert "£19.99" in page     # food total and money out
    assert "£450.00" in page    # money in
    assert "£430.01" in page    # left over


def test_invalid_amount_is_rejected(client):
    page = add(client, "twelve").get_data(as_text=True)
    assert "not a valid amount" in page
    assert "Nothing here for this month" in client.get("/entries?month=2026-11").get_data(as_text=True)


def test_budget_warning_appears_when_overspending(client):
    client.post("/budgets", data={"category": "fun", "limit": "20"})
    add(client, "25", category="fun")
    page = client.get("/?month=2026-11").get_data(as_text=True)
    assert "Over budget on fun" in page
    assert "£5.00 over" in page


def test_statement_upload_skips_duplicates(client):
    csv_bytes = b"Date,Description,Amount\n03/11/2026,TESCO,-10.00\n04/11/2026,NETFLIX,-5.99\n"
    for expected in ("Imported 2", "Imported 0"):
        page = client.post("/upload", data={"statement": (io.BytesIO(csv_bytes), "statement.csv")},
                           content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
        assert expected in page
    assert "£15.99" in client.get("/?month=2026-11").get_data(as_text=True)


def test_html_in_description_is_escaped(client):
    client.post("/", data={"kind": "expense", "amount": "1", "category": "food", "date": "2026-11-10",
                           "description": "<script>alert(1)</script>"})
    page = client.get("/entries?month=2026-11").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_demo_data_fills_an_empty_database(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "demo.sqlite"), "SECRET_KEY": "test",
                      "DEMO_DATA": True})
    from datetime import date
    page = app.test_client().get("/").get_data(as_text=True)
    assert "Live demo with sample data" in page
    assert "Over budget on fun" in page          # the sample month goes over the fun budget
    from tracker import db
    with app.app_context():
        assert date.today().strftime("%Y-%m") in db.months_with_entries()
        from tracker.demo import seed_if_empty
        assert seed_if_empty() == 0              # never seeds twice


def test_no_demo_banner_normally(client):
    assert "Live demo" not in client.get("/").get_data(as_text=True)
