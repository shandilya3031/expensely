"""
Tests for Spec 08: Edit Expense.

Spec: .claude/specs/08-edit-expense.md

Scope (per spec):
- GET /expenses/<id>/edit renders a form pre-filled with an existing
  expense's amount, category, date, and description -- logged-in only
  (redirect to /login when no session); 404 via abort(404) if the
  expense doesn't exist or isn't owned by the current user.
- POST /expenses/<id>/edit validates the submitted data (same rules as
  add_expense: amount must be a positive, finite number; category must
  be one of CATEGORIES; date must be a valid YYYY-MM-DD string;
  description is optional), UPDATEs the existing row (never inserts a
  new one), and redirects to /profile on success -- logged-in only;
  404 via abort(404) if the expense doesn't exist or isn't owned by the
  current user.
- On any validation failure, the form re-renders (200, not a redirect)
  with an inline error (the `.auth-error` convention) and preserves the
  other submitted field values.
- Ownership is mandatory: every lookup and update is scoped to
  WHERE id = ? AND user_id = ? -- a user must never be able to view or
  edit another user's expense by guessing an id.

These tests assert against the documented spec contract only (Routes,
Rules, Definition of Done) -- not against implementation internals.
"""

import re
from pathlib import Path

import pytest

import database.db as db_module
from app import app as flask_app

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PROFILE_URL = "/profile"


def _edit_url(expense_id):
    return f"/expenses/{expense_id}/edit"


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


def _create_expense_for(user_id, amount=42.5, category="Food", date="2026-05-01", description="Original description"):
    """Directly inserts an expense row for `user_id` and returns its id."""
    db_module.create_expense(
        user_id=user_id, amount=amount, category=category, date=date, description=description
    )
    conn = db_module.get_db()
    row = conn.execute(
        "SELECT id FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
    ).fetchone()
    conn.close()
    return row["id"]


def _valid_payload(**overrides):
    payload = {
        "amount": "99.99",
        "category": "Bills",
        "date": "2026-06-15",
        "description": "Updated description",
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------- #
# Routes: auth guard -- "Unauthenticated access to either route must
# redirect to login, matching the pattern used by profile() and
# add_expense()"
# --------------------------------------------------------------------- #
class TestAuthGuard:
    def test_get_without_login_redirects_to_login(self, client):
        response = client.get(_edit_url(1))
        assert response.status_code == 302, "Unauthenticated GET should redirect"
        assert "/login" in response.headers["Location"]

    def test_post_without_login_redirects_to_login(self, client):
        response = client.post(_edit_url(1), data=_valid_payload())
        assert response.status_code == 302, "Unauthenticated POST should redirect"
        assert "/login" in response.headers["Location"]

    def test_post_without_login_does_not_modify_any_expense(self, auth_client, client):
        # Create an expense while logged in, then log out and attempt an
        # unauthenticated edit of it.
        expense_id = _create_expense_for(auth_client.user_id)
        auth_client.get("/logout")

        client.post(_edit_url(expense_id), data=_valid_payload(), follow_redirects=True)

        rows = _expense_rows(auth_client.user_id)
        assert len(rows) == 1
        assert rows[0]["amount"] == 42.5, "Unauthenticated POST must not update the expense"


# --------------------------------------------------------------------- #
# DoD: "Visiting /expenses/<id>/edit for an expense that doesn't exist
# returns a 404" / "...owned by a different user returns a 404"
# --------------------------------------------------------------------- #
class TestNotFound:
    def test_get_nonexistent_expense_returns_404(self, auth_client):
        response = auth_client.get(_edit_url(999999))
        assert response.status_code == 404

    def test_post_nonexistent_expense_returns_404(self, auth_client):
        response = auth_client.post(_edit_url(999999), data=_valid_payload())
        assert response.status_code == 404

    def test_get_expense_owned_by_different_user_returns_404(self, auth_client, client):
        other_id = _create_expense_for(auth_client.user_id, description="OwnerOnly")
        auth_client.get("/logout")

        _register(client, name="Other User", email="other@example.com")
        _login(client, email="other@example.com")

        response = client.get(_edit_url(other_id))
        assert response.status_code == 404, "A user must not be able to view another user's expense"

    def test_post_expense_owned_by_different_user_returns_404(self, auth_client, client):
        other_id = _create_expense_for(auth_client.user_id, description="OwnerOnly")
        owner_id = auth_client.user_id
        auth_client.get("/logout")

        _register(client, name="Other User", email="other@example.com")
        _login(client, email="other@example.com")

        response = client.post(_edit_url(other_id), data=_valid_payload())
        assert response.status_code == 404, "A user must not be able to edit another user's expense"

        # Confirm the original owner's row was left untouched.
        rows = _expense_rows(owner_id)
        assert len(rows) == 1
        assert rows[0]["description"] == "OwnerOnly", "A cross-user POST must not modify the expense"
        assert rows[0]["amount"] == 42.5


# --------------------------------------------------------------------- #
# DoD: "Visiting /expenses/<id>/edit for an expense the current user
# owns renders a form pre-filled with its amount, category, date, and
# description"
# --------------------------------------------------------------------- #
class TestGetEditExpenseForm:
    def test_get_owned_expense_returns_200(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id)
        response = auth_client.get(_edit_url(expense_id))
        assert response.status_code == 200

    def test_get_form_prefilled_with_existing_values(self, auth_client):
        expense_id = _create_expense_for(
            auth_client.user_id,
            amount=123.45,
            category="Entertainment",
            date="2026-03-14",
            description="PiDayMovie",
        )
        response = auth_client.get(_edit_url(expense_id))
        body = response.data.decode()

        assert 'value="123.45"' in body, "Amount should be pre-filled"
        assert '<option value="Entertainment" selected>Entertainment</option>' in body, \
            "Category should be pre-selected"
        assert 'value="2026-03-14"' in body, "Date should be pre-filled"
        assert 'value="PiDayMovie"' in body, "Description should be pre-filled"

    def test_get_form_has_all_required_fields(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id)
        response = auth_client.get(_edit_url(expense_id))
        body = response.data.decode()
        assert 'name="amount"' in body, "Form must have an amount field"
        assert 'name="category"' in body, "Form must have a category field"
        assert 'name="date"' in body, "Form must have a date field"
        assert 'name="description"' in body, "Form must have a description field"

    def test_get_form_submits_via_post_to_edit_expense_for_this_id(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id)
        response = auth_client.get(_edit_url(expense_id))
        body = response.data.decode()
        assert 'method="POST"' in body
        assert f'action="{_edit_url(expense_id)}"' in body


# --------------------------------------------------------------------- #
# DoD: "Submitting the form with valid data updates the existing row
# (not a new one) in expenses and redirects to /profile" / "The updated
# values appear in the Recent Transactions table and are reflected in
# the summary stats and category breakdown on /profile"
# --------------------------------------------------------------------- #
class TestSuccessfulUpdate:
    def test_valid_post_redirects_to_profile(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id)
        response = auth_client.post(_edit_url(expense_id), data=_valid_payload(), follow_redirects=False)
        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

    def test_valid_post_updates_existing_row_not_a_new_insert(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id)
        auth_client.post(_edit_url(expense_id), data=_valid_payload(), follow_redirects=True)

        rows = _expense_rows(auth_client.user_id)
        assert len(rows) == 1, "Editing must update the existing row, not create a new one"
        assert rows[0]["id"] == expense_id, "The updated row must have the same id"

    def test_valid_post_reflects_updated_values_in_db(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id)
        payload = _valid_payload(
            amount="250.75", category="Health", date="2026-09-09", description="UpdatedMarker"
        )
        auth_client.post(_edit_url(expense_id), data=payload, follow_redirects=True)

        updated = db_module.get_expense_by_id(expense_id, auth_client.user_id)
        assert updated is not None
        assert updated["amount"] == 250.75
        assert updated["category"] == "Health"
        assert updated["date"] == "2026-09-09"
        assert updated["description"] == "UpdatedMarker"

    def test_valid_post_shows_flash_message_on_redirect(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id)
        response = auth_client.post(_edit_url(expense_id), data=_valid_payload(), follow_redirects=True)
        body = response.data.decode()
        assert "flash-messages" in body, "A flash message should be shown after a successful edit"

    def test_updated_expense_appears_in_recent_transactions_on_profile(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id)
        marker = "RecentTxnEditMarker"
        auth_client.post(_edit_url(expense_id), data=_valid_payload(description=marker), follow_redirects=True)

        response = auth_client.get(PROFILE_URL)
        body = response.data.decode()
        assert marker in body, "Updated expense should appear in Recent Transactions"

    def test_updated_expense_reflected_in_summary_stats(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id, amount=10.0)
        auth_client.post(_edit_url(expense_id), data=_valid_payload(amount="500.00"), follow_redirects=True)

        stats = db_module.get_summary_stats(auth_client.user_id)
        assert stats["total"] == 500.00
        assert stats["count"] == 1

    def test_updated_expense_reflected_in_category_breakdown(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id, category="Food", amount=10.0)
        auth_client.post(
            _edit_url(expense_id),
            data=_valid_payload(category="Shopping", amount="60"),
            follow_redirects=True,
        )

        rows = db_module.get_category_breakdown(auth_client.user_id)
        assert len(rows) == 1
        assert rows[0]["category"] == "Shopping"
        assert rows[0]["total"] == 60


# --------------------------------------------------------------------- #
# Rules: "description is optional"
# --------------------------------------------------------------------- #
class TestDescriptionOptional:
    def test_omitting_description_field_succeeds(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id)
        payload = _valid_payload()
        del payload["description"]

        response = auth_client.post(_edit_url(expense_id), data=payload, follow_redirects=False)
        assert response.status_code == 302, "Omitting description entirely must still succeed"

        updated = db_module.get_expense_by_id(expense_id, auth_client.user_id)
        assert updated["description"] in (None, ""), "Description should be cleared when omitted"

    def test_empty_string_description_succeeds(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id)
        response = auth_client.post(
            _edit_url(expense_id), data=_valid_payload(description=""), follow_redirects=False
        )
        assert response.status_code == 302, "An empty description must still succeed"


# --------------------------------------------------------------------- #
# Rules: "amount must be a positive number"
# DoD: "Submitting with a missing/invalid amount (blank, zero, negative,
# non-numeric) re-renders the form with an error and preserves the
# other entered values"
# --------------------------------------------------------------------- #
AMOUNT_CASES = ["", "0", "-10", "abc", "NaN", "Infinity"]
AMOUNT_IDS = ["blank", "zero", "negative", "non_numeric", "nan", "infinite"]


class TestAmountValidation:
    @pytest.mark.parametrize("bad_amount", AMOUNT_CASES, ids=AMOUNT_IDS)
    def test_invalid_amount_rerenders_form_with_error(self, auth_client, bad_amount):
        expense_id = _create_expense_for(auth_client.user_id)
        payload = _valid_payload(amount=bad_amount, category="Bills", date="2026-06-15", description="KeepMe")
        response = auth_client.post(_edit_url(expense_id), data=payload, follow_redirects=False)

        assert response.status_code == 200, f"Invalid amount {bad_amount!r} should re-render the form, not redirect"
        body = response.data.decode()
        assert "auth-error" in body, "An inline error should be shown for an invalid amount"

    @pytest.mark.parametrize("bad_amount", AMOUNT_CASES, ids=AMOUNT_IDS)
    def test_invalid_amount_preserves_other_field_values(self, auth_client, bad_amount):
        expense_id = _create_expense_for(auth_client.user_id)
        payload = _valid_payload(amount=bad_amount, category="Bills", date="2026-06-15", description="KeepMe")
        response = auth_client.post(_edit_url(expense_id), data=payload, follow_redirects=False)
        body = response.data.decode()

        assert '<option value="Bills" selected>Bills</option>' in body, "Category should be preserved"
        assert 'value="2026-06-15"' in body, "Date should be preserved"
        assert 'value="KeepMe"' in body, "Description should be preserved"

    @pytest.mark.parametrize("bad_amount", AMOUNT_CASES, ids=AMOUNT_IDS)
    def test_invalid_amount_does_not_update_expense(self, auth_client, bad_amount):
        expense_id = _create_expense_for(auth_client.user_id, amount=42.5, description="Original description")
        payload = _valid_payload(amount=bad_amount)
        auth_client.post(_edit_url(expense_id), data=payload, follow_redirects=False)

        unchanged = db_module.get_expense_by_id(expense_id, auth_client.user_id)
        assert unchanged["amount"] == 42.5, f"Invalid amount {bad_amount!r} must not update the DB row"
        assert unchanged["description"] == "Original description"


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
        expense_id = _create_expense_for(auth_client.user_id)
        payload = _valid_payload(category=bad_category, amount="55", date="2026-07-01", description="KeepMe2")
        response = auth_client.post(_edit_url(expense_id), data=payload, follow_redirects=False)

        assert response.status_code == 200, f"Invalid category {bad_category!r} should re-render the form"
        body = response.data.decode()
        assert "auth-error" in body, "An inline error should be shown for an invalid category"

    @pytest.mark.parametrize("bad_category", CATEGORY_CASES, ids=CATEGORY_IDS)
    def test_invalid_category_preserves_other_field_values(self, auth_client, bad_category):
        expense_id = _create_expense_for(auth_client.user_id)
        payload = _valid_payload(category=bad_category, amount="55", date="2026-07-01", description="KeepMe2")
        response = auth_client.post(_edit_url(expense_id), data=payload, follow_redirects=False)
        body = response.data.decode()

        assert 'value="55"' in body, "Amount should be preserved"
        assert 'value="2026-07-01"' in body, "Date should be preserved"
        assert 'value="KeepMe2"' in body, "Description should be preserved"

    @pytest.mark.parametrize("bad_category", CATEGORY_CASES, ids=CATEGORY_IDS)
    def test_invalid_category_does_not_update_expense(self, auth_client, bad_category):
        expense_id = _create_expense_for(auth_client.user_id, category="Food", description="Original description")
        payload = _valid_payload(category=bad_category)
        auth_client.post(_edit_url(expense_id), data=payload, follow_redirects=False)

        unchanged = db_module.get_expense_by_id(expense_id, auth_client.user_id)
        assert unchanged["category"] == "Food", f"Invalid category {bad_category!r} must not update the DB row"
        assert unchanged["description"] == "Original description"


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
        expense_id = _create_expense_for(auth_client.user_id)
        payload = _valid_payload(date=bad_date, amount="19.99", category="Shopping", description="KeepMe3")
        response = auth_client.post(_edit_url(expense_id), data=payload, follow_redirects=False)

        assert response.status_code == 200, f"Invalid date {bad_date!r} should re-render the form"
        body = response.data.decode()
        assert "auth-error" in body, "An inline error should be shown for an invalid date"

    @pytest.mark.parametrize("bad_date", DATE_CASES, ids=DATE_IDS)
    def test_invalid_date_preserves_other_field_values(self, auth_client, bad_date):
        expense_id = _create_expense_for(auth_client.user_id)
        payload = _valid_payload(date=bad_date, amount="19.99", category="Shopping", description="KeepMe3")
        response = auth_client.post(_edit_url(expense_id), data=payload, follow_redirects=False)
        body = response.data.decode()

        assert 'value="19.99"' in body, "Amount should be preserved"
        assert '<option value="Shopping" selected>Shopping</option>' in body, "Category should be preserved"
        assert 'value="KeepMe3"' in body, "Description should be preserved"

    @pytest.mark.parametrize("bad_date", DATE_CASES, ids=DATE_IDS)
    def test_invalid_date_does_not_update_expense(self, auth_client, bad_date):
        expense_id = _create_expense_for(auth_client.user_id, date="2026-05-01", description="Original description")
        payload = _valid_payload(date=bad_date)
        auth_client.post(_edit_url(expense_id), data=payload, follow_redirects=False)

        unchanged = db_module.get_expense_by_id(expense_id, auth_client.user_id)
        assert unchanged["date"] == "2026-05-01", f"Invalid date {bad_date!r} must not update the DB row"
        assert unchanged["description"] == "Original description"


# --------------------------------------------------------------------- #
# Database changes: "Ownership is mandatory: every lookup and update
# must be scoped to WHERE id = ? AND user_id = ?"
# --------------------------------------------------------------------- #
class TestExpenseOwnership:
    def test_updating_own_expense_does_not_affect_other_users_expenses(self, auth_client, client):
        own_id = _create_expense_for(auth_client.user_id, description="MineOriginal")
        auth_client.get("/logout")

        _register(client, name="Other User", email="other@example.com")
        _login(client, email="other@example.com")
        other_user = db_module.get_user_by_email("other@example.com")
        other_id = _create_expense_for(other_user["id"], description="TheirsOriginal")

        client.post(_edit_url(other_id), data=_valid_payload(description="TheirsUpdated"), follow_redirects=True)

        # The other (first) user's expense is untouched.
        original_owner_rows = _expense_rows(auth_client.user_id)
        assert len(original_owner_rows) == 1
        assert original_owner_rows[0]["description"] == "MineOriginal"

        # Only the acting user's own expense was updated.
        acting_user_row = db_module.get_expense_by_id(other_id, other_user["id"])
        assert acting_user_row["description"] == "TheirsUpdated"


# --------------------------------------------------------------------- #
# Rules: "Use CSS variables — never hardcode hex values" / all templates
# extend base.html
# --------------------------------------------------------------------- #
class TestTemplateConventions:
    HEX_PATTERN = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b")

    def test_edit_expense_template_extends_base(self):
        content = (PROJECT_ROOT / "templates" / "edit_expense.html").read_text(encoding="utf-8")
        assert '{% extends "base.html" %}' in content

    def test_edit_expense_template_has_no_hardcoded_hex_colors(self):
        content = (PROJECT_ROOT / "templates" / "edit_expense.html").read_text(encoding="utf-8")
        matches = self.HEX_PATTERN.findall(content)
        assert not matches, f"edit_expense.html must only use CSS variables, found hex colors: {matches}"
