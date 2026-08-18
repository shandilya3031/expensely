"""
Tests for Spec 09: Delete Expense.

Spec: .claude/specs/09-delete-expense.md

Scope (per spec):
- GET /expenses/<id>/delete renders a confirmation page showing the
  expense's amount, category, date, and description -- logged-in only
  (redirect to /login when no session); 404 via abort(404) if the
  expense doesn't exist or isn't owned by the current user.
- POST /expenses/<id>/delete deletes the expense (same ownership /
  404 rule), flashes a success message, and redirects to /profile --
  logged-in only.
- Both GET and POST are handled by a single delete_expense(expense_id)
  view (methods=["GET", "POST"]), matching the edit_expense pattern.
- Ownership is mandatory: every lookup and delete is scoped to
  WHERE id = ? AND user_id = ? -- a user must never be able to view or
  delete another user's expense by guessing an id.
- The delete requires a POST (confirmation page, not a one-click GET
  link) -- a bare GET must never remove the expense.
- "Cancel" on the confirmation page is just a link back to /profile;
  it performs no request against the delete route, so simply not
  POSTing must leave the expense untouched.
- No new pip packages were required for this feature.

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


def _delete_url(expense_id):
    return f"/expenses/{expense_id}/delete"


# --------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------- #
# NOTE on DB isolation for this codebase (mirrors test_08-edit-expense.py):
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


# --------------------------------------------------------------------- #
# Routes: auth guard -- "An unauthenticated request to either method
# redirects to /login"
# --------------------------------------------------------------------- #
class TestAuthGuard:
    def test_get_without_login_redirects_to_login(self, client):
        response = client.get(_delete_url(1))
        assert response.status_code == 302, "Unauthenticated GET should redirect"
        assert "/login" in response.headers["Location"]

    def test_post_without_login_redirects_to_login(self, client):
        response = client.post(_delete_url(1))
        assert response.status_code == 302, "Unauthenticated POST should redirect"
        assert "/login" in response.headers["Location"]

    def test_post_without_login_does_not_delete_expense(self, auth_client, client):
        # Create an expense while logged in, then log out and attempt an
        # unauthenticated delete of it.
        expense_id = _create_expense_for(auth_client.user_id)
        auth_client.get("/logout")

        client.post(_delete_url(expense_id), follow_redirects=True)

        rows = _expense_rows(auth_client.user_id)
        assert len(rows) == 1, "Unauthenticated POST must not delete the expense"
        assert rows[0]["id"] == expense_id

    def test_get_without_login_does_not_delete_expense(self, auth_client, client):
        expense_id = _create_expense_for(auth_client.user_id)
        auth_client.get("/logout")

        client.get(_delete_url(expense_id), follow_redirects=True)

        rows = _expense_rows(auth_client.user_id)
        assert len(rows) == 1, "Unauthenticated GET must not delete the expense"


# --------------------------------------------------------------------- #
# DoD: "Visiting GET /expenses/<id>/delete for a nonexistent id, or an
# id owned by a different user, returns a 404" / "Submitting POST
# /expenses/<id>/delete for a nonexistent id, or an id owned by a
# different user, returns a 404 and performs no deletion"
# --------------------------------------------------------------------- #
class TestNotFound:
    def test_get_nonexistent_expense_returns_404(self, auth_client):
        response = auth_client.get(_delete_url(999999))
        assert response.status_code == 404

    def test_post_nonexistent_expense_returns_404(self, auth_client):
        response = auth_client.post(_delete_url(999999))
        assert response.status_code == 404

    def test_post_nonexistent_expense_performs_no_deletion(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id, description="StillHere")
        auth_client.post(_delete_url(999999))

        rows = _expense_rows(auth_client.user_id)
        assert len(rows) == 1, "A 404 on a nonexistent id must not touch unrelated rows"
        assert rows[0]["id"] == expense_id
        assert rows[0]["description"] == "StillHere"

    def test_get_expense_owned_by_different_user_returns_404(self, auth_client, client):
        other_id = _create_expense_for(auth_client.user_id, description="OwnerOnly")
        auth_client.get("/logout")

        _register(client, name="Other User", email="other@example.com")
        _login(client, email="other@example.com")

        response = client.get(_delete_url(other_id))
        assert response.status_code == 404, "A user must not be able to view another user's delete confirmation"

    def test_post_expense_owned_by_different_user_returns_404(self, auth_client, client):
        other_id = _create_expense_for(auth_client.user_id, description="OwnerOnly")
        owner_id = auth_client.user_id
        auth_client.get("/logout")

        _register(client, name="Other User", email="other@example.com")
        _login(client, email="other@example.com")

        response = client.post(_delete_url(other_id))
        assert response.status_code == 404, "A user must not be able to delete another user's expense"

        # Confirm the original owner's row was left untouched.
        rows = _expense_rows(owner_id)
        assert len(rows) == 1, "A cross-user POST must not delete the expense"
        assert rows[0]["id"] == other_id
        assert rows[0]["description"] == "OwnerOnly"


# --------------------------------------------------------------------- #
# DoD: "Visiting GET /expenses/<id>/delete for your own expense renders
# a confirmation page showing that expense's amount, category, date,
# and description"
# --------------------------------------------------------------------- #
class TestGetDeleteConfirmationPage:
    def test_get_owned_expense_returns_200(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id)
        response = auth_client.get(_delete_url(expense_id))
        assert response.status_code == 200

    def test_get_confirmation_page_shows_expense_details(self, auth_client):
        expense_id = _create_expense_for(
            auth_client.user_id,
            amount=123.45,
            category="Entertainment",
            date="2026-03-14",
            description="PiDayMovie",
        )
        response = auth_client.get(_delete_url(expense_id))
        body = response.data.decode()

        assert "123.45" in body, "Amount should be shown on the confirmation page"
        assert "Entertainment" in body, "Category should be shown on the confirmation page"
        assert "2026-03-14" in body, "Date should be shown on the confirmation page"
        assert "PiDayMovie" in body, "Description should be shown on the confirmation page"

    def test_get_confirmation_page_has_post_form_to_this_id(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id)
        response = auth_client.get(_delete_url(expense_id))
        body = response.data.decode()

        assert 'method="POST"' in body, "The confirmation page must submit via POST"
        assert f'action="{_delete_url(expense_id)}"' in body, \
            "The confirmation form must post back to this expense's delete route"

    def test_get_confirmation_page_has_cancel_link_to_profile(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id)
        response = auth_client.get(_delete_url(expense_id))
        body = response.data.decode()

        assert "Cancel" in body, "The confirmation page must offer a Cancel option"
        assert PROFILE_URL in body, "Cancel should link back to /profile"

    def test_get_does_not_delete_the_expense(self, auth_client):
        # A bare GET (confirmation page view) must never be destructive.
        expense_id = _create_expense_for(auth_client.user_id)
        auth_client.get(_delete_url(expense_id))

        rows = _expense_rows(auth_client.user_id)
        assert len(rows) == 1, "GET must only render the confirmation page, never delete"
        assert rows[0]["id"] == expense_id


# --------------------------------------------------------------------- #
# DoD: "Submitting the confirmation form (POST) for your own expense
# removes it from the database and redirects to /profile with a
# success flash message" / "The deleted expense no longer appears in
# the profile's transaction table or summary stats after redirect"
# --------------------------------------------------------------------- #
class TestSuccessfulDelete:
    def test_post_redirects_to_profile(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id)
        response = auth_client.post(_delete_url(expense_id), follow_redirects=False)
        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

    def test_post_removes_expense_from_db(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id)
        auth_client.post(_delete_url(expense_id), follow_redirects=True)

        rows = _expense_rows(auth_client.user_id)
        assert len(rows) == 0, "The expense must be removed from the database"
        assert db_module.get_expense_by_id(expense_id, auth_client.user_id) is None

    def test_post_only_deletes_the_targeted_expense(self, auth_client):
        keep_id = _create_expense_for(auth_client.user_id, description="Keep")
        delete_id = _create_expense_for(auth_client.user_id, description="Delete")

        auth_client.post(_delete_url(delete_id), follow_redirects=True)

        rows = _expense_rows(auth_client.user_id)
        assert len(rows) == 1
        assert rows[0]["id"] == keep_id
        assert rows[0]["description"] == "Keep"

    def test_post_shows_flash_message_on_redirect(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id)
        response = auth_client.post(_delete_url(expense_id), follow_redirects=True)
        body = response.data.decode()
        assert "flash-messages" in body, "A flash message should be shown after a successful delete"

    def test_deleted_expense_absent_from_profile_transactions(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id, description="GoneNowMarker")
        auth_client.post(_delete_url(expense_id), follow_redirects=True)

        response = auth_client.get(PROFILE_URL)
        body = response.data.decode()
        assert "GoneNowMarker" not in body, \
            "Deleted expense must not appear in the Recent Transactions table"

    def test_deleted_expense_reflected_in_summary_stats(self, auth_client):
        _create_expense_for(auth_client.user_id, amount=10.0, description="Kept")
        expense_id = _create_expense_for(auth_client.user_id, amount=500.0, description="Removed")

        auth_client.post(_delete_url(expense_id), follow_redirects=True)

        stats = db_module.get_summary_stats(auth_client.user_id)
        assert stats["total"] == 10.0, "Summary total must exclude the deleted expense"
        assert stats["count"] == 1

    def test_deleted_expense_reflected_in_category_breakdown(self, auth_client):
        _create_expense_for(auth_client.user_id, category="Food", amount=10.0)
        expense_id = _create_expense_for(auth_client.user_id, category="Shopping", amount=60.0)

        auth_client.post(_delete_url(expense_id), follow_redirects=True)

        rows = db_module.get_category_breakdown(auth_client.user_id)
        categories = [row["category"] for row in rows]
        assert "Shopping" not in categories, "Deleted expense's category must not appear in the breakdown"
        assert "Food" in categories


# --------------------------------------------------------------------- #
# Cancel flow: "Clicking 'Cancel' on the confirmation page returns to
# /profile without deleting anything". Cancel is a plain link (not a
# request to the delete route), so this is exercised by confirming
# that simply visiting the confirmation page and never submitting the
# POST form leaves the expense fully intact and still reachable from
# /profile.
# --------------------------------------------------------------------- #
class TestCancelFlow:
    def test_viewing_confirmation_then_not_posting_leaves_expense_untouched(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id, description="CancelMeNot")
        auth_client.get(_delete_url(expense_id))  # simulates viewing the confirmation page

        # No POST is made -- the user "cancels" by navigating away.
        unchanged = db_module.get_expense_by_id(expense_id, auth_client.user_id)
        assert unchanged is not None, "Cancelling must not delete the expense"
        assert unchanged["description"] == "CancelMeNot"

    def test_cancel_link_target_still_shows_expense_on_profile(self, auth_client):
        expense_id = _create_expense_for(auth_client.user_id, description="StillOnProfile")
        auth_client.get(_delete_url(expense_id))

        response = auth_client.get(PROFILE_URL)
        body = response.data.decode()
        assert "StillOnProfile" in body, "After cancelling, the expense should still be listed on /profile"


# --------------------------------------------------------------------- #
# Database changes: "Ownership is mandatory: every lookup and delete
# must be scoped to WHERE id = ? AND user_id = ?"
# --------------------------------------------------------------------- #
class TestExpenseOwnership:
    def test_deleting_own_expense_does_not_affect_other_users_expenses(self, auth_client, client):
        own_id = _create_expense_for(auth_client.user_id, description="MineOriginal")
        auth_client.get("/logout")

        _register(client, name="Other User", email="other@example.com")
        _login(client, email="other@example.com")
        other_user = db_module.get_user_by_email("other@example.com")
        other_id = _create_expense_for(other_user["id"], description="TheirsOriginal")

        client.post(_delete_url(other_id), follow_redirects=True)

        # The first user's expense is untouched.
        first_user_rows = _expense_rows(auth_client.user_id)
        assert len(first_user_rows) == 1
        assert first_user_rows[0]["id"] == own_id
        assert first_user_rows[0]["description"] == "MineOriginal"

        # Only the acting user's own expense was deleted.
        assert db_module.get_expense_by_id(other_id, other_user["id"]) is None


# --------------------------------------------------------------------- #
# Rules: "Use CSS variables — never hardcode hex values" / all templates
# extend base.html
# --------------------------------------------------------------------- #
class TestTemplateConventions:
    HEX_PATTERN = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b")

    def test_delete_expense_template_extends_base(self):
        content = (PROJECT_ROOT / "templates" / "delete_expense.html").read_text(encoding="utf-8")
        assert '{% extends "base.html" %}' in content

    def test_delete_expense_template_has_no_hardcoded_hex_colors(self):
        content = (PROJECT_ROOT / "templates" / "delete_expense.html").read_text(encoding="utf-8")
        matches = self.HEX_PATTERN.findall(content)
        assert not matches, f"delete_expense.html must only use CSS variables, found hex colors: {matches}"


# --------------------------------------------------------------------- #
# DoD: "No new pip packages were added to requirements.txt"
# --------------------------------------------------------------------- #
class TestNoNewDependencies:
    def test_requirements_txt_has_no_new_packages(self):
        content = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
        package_names = set()
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name = re.split(r"[=<>!~\[]", line, maxsplit=1)[0].strip().lower()
            package_names.add(name)

        expected = {"flask", "werkzeug", "pytest", "pytest-flask"}
        assert package_names == expected, (
            "requirements.txt should still only contain the pre-existing packages "
            f"({expected}); found {package_names}. The delete-expense feature "
            "requires no new pip packages."
        )
