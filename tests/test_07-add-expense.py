"""
Tests for Spec 07: Add Expense.

Spec: .claude/specs/07-add-expense.md

Scope (per spec):
- GET /expenses/add (implemented route) renders a form with amount,
  category, date, and description fields -- logged-in only (redirect
  to /login when no session).
- POST /expenses/add validates the submitted data, inserts a row into
  `expenses` via database/db.py's create_expense(), and redirects to
  /profile on success -- logged-in only (redirect to /login when no
  session).
- Validation rules: amount must be a positive, finite number; category
  must be one of CATEGORIES (database/db.py); date must be a valid
  YYYY-MM-DD string; description is optional.
- On any validation failure, the form re-renders (200, not a redirect)
  with an inline error (the existing `.auth-error` convention used by
  login.html/register.html) and preserves the other submitted field
  values.
- On success, the new expense appears in Recent Transactions and is
  reflected in summary stats / category breakdown on /profile.

These tests assert against the documented spec contract only (Routes,
Templates, Rules, Definition of Done) -- not against implementation
internals.
"""

import re
from pathlib import Path

import pytest

import database.db as db_module
from app import app as flask_app

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ADD_EXPENSE_URL = "/expenses/add"
PROFILE_URL = "/profile"


# --------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------- #
# NOTE on DB isolation for this codebase:
# `database/db.py` has no dependency-injectable DB config -- `get_db()`
# always opens the module-level `DB_PATH` (a hardcoded sqlite file on
# disk); there is no `app.config["DATABASE"]` hook and no `:memory:`
# support. To get full per-test isolation, we repoint
# `database.db.DB_PATH` at a fresh temp sqlite file for every test and
# re-run `init_db()` against it. Because `get_db()` re-reads the
# module-level `DB_PATH` on every call, this fully isolates each test's
# reads/writes -- including calls made through `app.py`'s routes --
# from the real db file and from other tests.

@pytest.fixture
def app(monkeypatch, tmp_path):
    db_path = tmp_path / "test_spendly.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))

    flask_app.config.update({"TESTING": True, "SECRET_KEY": "test-secret"})

    with flask_app.app_context():
        db_module.init_db()

    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def _register(client, name="Test User", email="test@example.com", password="password123"):
    return client.post(
        "/register",
        data={
            "name": name,
            "email": email,
            "password": password,
            "confirm_password": password,
        },
        follow_redirects=True,
    )


def _login(client, email="test@example.com", password="password123"):
    return client.post(
        "/login", data={"email": email, "password": password}, follow_redirects=True
    )


@pytest.fixture
def auth_client(client):
    """A logged-in test client. `.user_id` exposes the logged-in user's id."""
    _register(client)
    _login(client)
    user = db_module.get_user_by_email("test@example.com")
    client.user_id = user["id"]
    return client


def _expense_rows(user_id):
    conn = db_module.get_db()
    rows = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return rows


def _all_expense_count():
    conn = db_module.get_db()
    count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    conn.close()
    return count


def _valid_payload(**overrides):
    payload = {
        "amount": "42.50",
        "category": "Food",
        "date": "2026-05-01",
        "description": "Grocery run",
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------- #
# Routes: auth guard -- "Unauthenticated access to either route must
# redirect to login, matching the pattern used by profile()"
# --------------------------------------------------------------------- #
class TestAuthGuard:
    def test_get_without_login_redirects_to_login(self, client):
        response = client.get(ADD_EXPENSE_URL)
        assert response.status_code == 302, "Unauthenticated GET should redirect"
        assert "/login" in response.headers["Location"]

    def test_post_without_login_redirects_to_login(self, client):
        response = client.post(ADD_EXPENSE_URL, data=_valid_payload())
        assert response.status_code == 302, "Unauthenticated POST should redirect"
        assert "/login" in response.headers["Location"]

    def test_post_without_login_does_not_create_expense(self, client):
        client.post(ADD_EXPENSE_URL, data=_valid_payload(), follow_redirects=True)
        assert _all_expense_count() == 0, "Unauthenticated POST must not create an expense"


# --------------------------------------------------------------------- #
# DoD: "Visiting /expenses/add while logged in renders a form with
# amount, category, date, and description fields"
# --------------------------------------------------------------------- #
class TestGetAddExpenseForm:
    def test_get_while_logged_in_returns_200(self, auth_client):
        response = auth_client.get(ADD_EXPENSE_URL)
        assert response.status_code == 200

    def test_get_while_logged_in_renders_all_required_fields(self, auth_client):
        response = auth_client.get(ADD_EXPENSE_URL)
        body = response.data.decode()
        assert 'name="amount"' in body, "Form must have an amount field"
        assert 'name="category"' in body, "Form must have a category field"
        assert 'name="date"' in body, "Form must have a date field"
        assert 'name="description"' in body, "Form must have a description field"

    def test_get_form_category_select_lists_all_categories(self, auth_client):
        response = auth_client.get(ADD_EXPENSE_URL)
        body = response.data.decode()
        for category in db_module.CATEGORIES:
            assert f'value="{category}"' in body, f"{category} option missing from category select"

    def test_get_form_submits_via_post_to_add_expense(self, auth_client):
        response = auth_client.get(ADD_EXPENSE_URL)
        body = response.data.decode()
        assert 'method="POST"' in body
        assert 'action="/expenses/add"' in body


# --------------------------------------------------------------------- #
# DoD: "Submitting the form with valid data creates a new row in
# expenses for the current user and redirects to /profile" / "The newly
# added expense appears in the Recent Transactions table and is
# reflected in the summary stats and category breakdown on /profile"
# --------------------------------------------------------------------- #
class TestSuccessfulSubmission:
    def test_valid_post_redirects_to_profile(self, auth_client):
        response = auth_client.post(ADD_EXPENSE_URL, data=_valid_payload(), follow_redirects=False)
        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

    def test_valid_post_creates_expense_row_for_current_user(self, auth_client):
        payload = _valid_payload(description="UniqueCreateMarker")
        auth_client.post(ADD_EXPENSE_URL, data=payload, follow_redirects=True)

        rows = _expense_rows(auth_client.user_id)
        assert len(rows) == 1, "Exactly one expense row should be created"
        row = rows[0]
        assert row["amount"] == 42.5
        assert row["category"] == "Food"
        assert row["date"] == "2026-05-01"
        assert row["description"] == "UniqueCreateMarker"

    def test_valid_post_shows_flash_message_on_redirect(self, auth_client):
        response = auth_client.post(ADD_EXPENSE_URL, data=_valid_payload(), follow_redirects=True)
        body = response.data.decode()
        assert "flash-messages" in body, "A flash message should be shown after a successful add"

    def test_new_expense_appears_in_recent_transactions_on_profile(self, auth_client):
        marker = "RecentTxnAddMarker"
        auth_client.post(ADD_EXPENSE_URL, data=_valid_payload(description=marker), follow_redirects=True)

        response = auth_client.get(PROFILE_URL)
        body = response.data.decode()
        assert marker in body, "Newly created expense should appear in Recent Transactions"

    def test_new_expense_reflected_in_summary_stats(self, auth_client):
        auth_client.post(ADD_EXPENSE_URL, data=_valid_payload(amount="75.25"), follow_redirects=True)

        stats = db_module.get_summary_stats(auth_client.user_id)
        assert stats["total"] == 75.25
        assert stats["count"] == 1

    def test_new_expense_reflected_in_category_breakdown(self, auth_client):
        auth_client.post(
            ADD_EXPENSE_URL, data=_valid_payload(category="Entertainment", amount="30"), follow_redirects=True
        )

        rows = db_module.get_category_breakdown(auth_client.user_id)
        assert len(rows) == 1
        assert rows[0]["category"] == "Entertainment"
        assert rows[0]["total"] == 30


# --------------------------------------------------------------------- #
# Rules: "description is optional"
# --------------------------------------------------------------------- #
class TestDescriptionOptional:
    def test_omitting_description_field_succeeds(self, auth_client):
        payload = _valid_payload()
        del payload["description"]

        response = auth_client.post(ADD_EXPENSE_URL, data=payload, follow_redirects=False)
        assert response.status_code == 302, "Omitting description entirely must still succeed"
        assert "/profile" in response.headers["Location"]

        rows = _expense_rows(auth_client.user_id)
        assert len(rows) == 1, "Expense should be created even without a description field"

    def test_empty_string_description_succeeds(self, auth_client):
        response = auth_client.post(
            ADD_EXPENSE_URL, data=_valid_payload(description=""), follow_redirects=False
        )
        assert response.status_code == 302, "An empty description must still succeed"

        rows = _expense_rows(auth_client.user_id)
        assert len(rows) == 1


# --------------------------------------------------------------------- #
# Rules: "amount must be a positive, finite number"
# DoD: "Submitting with a missing/invalid amount (blank, zero, negative,
# non-numeric) re-renders the form with an error and preserves the
# other entered values"
# --------------------------------------------------------------------- #
AMOUNT_CASES = ["", "0", "-10", "abc", "NaN", "Infinity"]
AMOUNT_IDS = ["blank", "zero", "negative", "non_numeric", "nan", "infinite"]


class TestAmountValidation:
    @pytest.mark.parametrize("bad_amount", AMOUNT_CASES, ids=AMOUNT_IDS)
    def test_invalid_amount_rerenders_form_with_error(self, auth_client, bad_amount):
        payload = _valid_payload(amount=bad_amount, category="Bills", date="2026-06-15", description="KeepMe")
        response = auth_client.post(ADD_EXPENSE_URL, data=payload, follow_redirects=False)

        assert response.status_code == 200, f"Invalid amount {bad_amount!r} should re-render the form, not redirect"
        body = response.data.decode()
        assert "auth-error" in body, "An inline error should be shown for an invalid amount"

    @pytest.mark.parametrize("bad_amount", AMOUNT_CASES, ids=AMOUNT_IDS)
    def test_invalid_amount_preserves_other_field_values(self, auth_client, bad_amount):
        payload = _valid_payload(amount=bad_amount, category="Bills", date="2026-06-15", description="KeepMe")
        response = auth_client.post(ADD_EXPENSE_URL, data=payload, follow_redirects=False)
        body = response.data.decode()

        assert '<option value="Bills" selected>Bills</option>' in body, "Category should be preserved"
        assert 'value="2026-06-15"' in body, "Date should be preserved"
        assert 'value="KeepMe"' in body, "Description should be preserved"

    @pytest.mark.parametrize("bad_amount", AMOUNT_CASES, ids=AMOUNT_IDS)
    def test_invalid_amount_does_not_create_expense(self, auth_client, bad_amount):
        payload = _valid_payload(amount=bad_amount)
        auth_client.post(ADD_EXPENSE_URL, data=payload, follow_redirects=False)

        rows = _expense_rows(auth_client.user_id)
        assert len(rows) == 0, f"Invalid amount {bad_amount!r} must not create a DB row"


# --------------------------------------------------------------------- #
# Rules: "category must be one of CATEGORIES"
# DoD: "Submitting with an invalid category (not in CATEGORIES) is
# rejected with an error"
# --------------------------------------------------------------------- #
CATEGORY_CASES = ["", "Groceries", "food", "Other Stuff"]
CATEGORY_IDS = ["blank", "not_in_list", "wrong_case", "unknown"]


class TestCategoryValidation:
    @pytest.mark.parametrize("bad_category", CATEGORY_CASES, ids=CATEGORY_IDS)
    def test_invalid_category_rerenders_form_with_error(self, auth_client, bad_category):
        payload = _valid_payload(category=bad_category, amount="55", date="2026-07-01", description="KeepMe2")
        response = auth_client.post(ADD_EXPENSE_URL, data=payload, follow_redirects=False)

        assert response.status_code == 200, f"Invalid category {bad_category!r} should re-render the form"
        body = response.data.decode()
        assert "auth-error" in body, "An inline error should be shown for an invalid category"

    @pytest.mark.parametrize("bad_category", CATEGORY_CASES, ids=CATEGORY_IDS)
    def test_invalid_category_preserves_other_field_values(self, auth_client, bad_category):
        payload = _valid_payload(category=bad_category, amount="55", date="2026-07-01", description="KeepMe2")
        response = auth_client.post(ADD_EXPENSE_URL, data=payload, follow_redirects=False)
        body = response.data.decode()

        assert 'value="55"' in body, "Amount should be preserved"
        assert 'value="2026-07-01"' in body, "Date should be preserved"
        assert 'value="KeepMe2"' in body, "Description should be preserved"

    @pytest.mark.parametrize("bad_category", CATEGORY_CASES, ids=CATEGORY_IDS)
    def test_invalid_category_does_not_create_expense(self, auth_client, bad_category):
        payload = _valid_payload(category=bad_category)
        auth_client.post(ADD_EXPENSE_URL, data=payload, follow_redirects=False)

        rows = _expense_rows(auth_client.user_id)
        assert len(rows) == 0


# --------------------------------------------------------------------- #
# Rules: "date must be a valid YYYY-MM-DD string"
# DoD: "Submitting with a missing or malformed date is rejected with an
# error"
# --------------------------------------------------------------------- #
DATE_CASES = ["", "not-a-date", "2026-13-01", "2026-02-30", "08/17/2026", "2026/08/17"]
DATE_IDS = ["blank", "garbage", "invalid_month", "invalid_day", "wrong_format_slash", "wrong_order_slash"]


class TestDateValidation:
    @pytest.mark.parametrize("bad_date", DATE_CASES, ids=DATE_IDS)
    def test_invalid_date_rerenders_form_with_error(self, auth_client, bad_date):
        payload = _valid_payload(date=bad_date, amount="19.99", category="Shopping", description="KeepMe3")
        response = auth_client.post(ADD_EXPENSE_URL, data=payload, follow_redirects=False)

        assert response.status_code == 200, f"Invalid date {bad_date!r} should re-render the form"
        body = response.data.decode()
        assert "auth-error" in body, "An inline error should be shown for an invalid date"

    @pytest.mark.parametrize("bad_date", DATE_CASES, ids=DATE_IDS)
    def test_invalid_date_preserves_other_field_values(self, auth_client, bad_date):
        payload = _valid_payload(date=bad_date, amount="19.99", category="Shopping", description="KeepMe3")
        response = auth_client.post(ADD_EXPENSE_URL, data=payload, follow_redirects=False)
        body = response.data.decode()

        assert 'value="19.99"' in body, "Amount should be preserved"
        assert '<option value="Shopping" selected>Shopping</option>' in body, "Category should be preserved"
        assert 'value="KeepMe3"' in body, "Description should be preserved"

    @pytest.mark.parametrize("bad_date", DATE_CASES, ids=DATE_IDS)
    def test_invalid_date_does_not_create_expense(self, auth_client, bad_date):
        payload = _valid_payload(date=bad_date)
        auth_client.post(ADD_EXPENSE_URL, data=payload, follow_redirects=False)

        rows = _expense_rows(auth_client.user_id)
        assert len(rows) == 0


# --------------------------------------------------------------------- #
# Database changes: expenses are scoped to the owning user (`user_id`
# column, session-based auth) -- an expense created by one user must
# not leak into another user's profile view
# --------------------------------------------------------------------- #
class TestExpenseOwnership:
    def test_expense_is_associated_with_the_logged_in_user_only(self, client):
        _register(client, name="User One", email="one@example.com")
        _login(client, email="one@example.com")
        user_one = db_module.get_user_by_email("one@example.com")

        client.post(ADD_EXPENSE_URL, data=_valid_payload(description="UserOneExpense"), follow_redirects=True)
        client.get("/logout")

        _register(client, name="User Two", email="two@example.com")
        _login(client, email="two@example.com")
        user_two = db_module.get_user_by_email("two@example.com")

        response = client.get(PROFILE_URL)
        body = response.data.decode()
        assert "UserOneExpense" not in body, "A user must not see another user's expenses"

        rows_one = _expense_rows(user_one["id"])
        rows_two = _expense_rows(user_two["id"])
        assert len(rows_one) == 1
        assert len(rows_two) == 0


# --------------------------------------------------------------------- #
# Rules: "Use CSS variables — never hardcode hex values" / all templates
# extend base.html
# --------------------------------------------------------------------- #
class TestTemplateConventions:
    HEX_PATTERN = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b")

    def test_add_expense_template_extends_base(self):
        content = (PROJECT_ROOT / "templates" / "add_expense.html").read_text(encoding="utf-8")
        assert '{% extends "base.html" %}' in content

    def test_add_expense_template_has_no_hardcoded_hex_colors(self):
        content = (PROJECT_ROOT / "templates" / "add_expense.html").read_text(encoding="utf-8")
        matches = self.HEX_PATTERN.findall(content)
        assert not matches, f"add_expense.html must only use CSS variables, found hex colors: {matches}"
