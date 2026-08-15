"""
Tests for Spec 06: Date Filter For Profile Page.

Spec: .claude/specs/06-date-filter-profile-page.md

Scope (per spec):
- GET /profile (modified route) reads optional `start_date` / `end_date`
  query params (YYYY-MM-DD) and filters the Recent Transactions table,
  summary stats, and category breakdown accordingly.
- database/db.py helpers `get_recent_transactions`, `get_summary_stats`,
  `get_category_breakdown` accept optional `start_date`/`end_date` kwargs.
- Auth guard on /profile is unchanged (redirect to /login when logged out).

These tests assert against the documented spec contract only (Routes,
Database changes, Templates, Rules, Definition of Done) -- not against
implementation internals.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

import database.db as db_module
from app import app as flask_app

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------- #
# NOTE on DB isolation for this codebase:
# `database/db.py` has no dependency-injectable DB config -- `get_db()`
# always opens the module-level `DB_PATH` (a hardcoded sqlite file on
# disk); there is no `app.config["DATABASE"]` hook and no `:memory:`
# support. `app.py` also calls `init_db()`/`seed_db()` once at import
# time against the real project DB file, which a test file cannot
# intercept without editing source.
#
# To get full per-test isolation anyway, we repoint `database.db.DB_PATH`
# at a fresh temp sqlite file for every test and re-run `init_db()`
# against it. Because `get_db()` re-reads the module-level `DB_PATH` on
# every call (not just once at import time), this is sufficient to fully
# isolate each test's reads/writes -- including calls made through
# `app.py`'s routes -- from the real db file and from other tests.

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


def _insert_expense(user_id, amount, category, date, description=""):
    conn = db_module.get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, date, description),
    )
    conn.commit()
    conn.close()


def _create_user(email, name="Helper User"):
    """Create a user directly via the DB layer, for db-helper-level tests
    that don't need a Flask test client / session."""
    conn = db_module.get_db()
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, generate_password_hash("password123")),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return user_id


def days_ago(n):
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


# --------------------------------------------------------------------- #
# Auth guard (DoD: "Visiting /profile without being logged in still
# redirects to /login")
# --------------------------------------------------------------------- #
class TestAuthGuard:
    def test_profile_without_login_redirects_to_login(self, client):
        response = client.get("/profile")
        assert response.status_code == 302, "Unauthenticated /profile should redirect"
        assert "/login" in response.headers["Location"], "Should redirect to the login page"

    def test_profile_with_filter_params_without_login_still_redirects(self, client):
        response = client.get("/profile?start_date=2026-01-01&end_date=2026-01-31")
        assert response.status_code == 302, "Auth guard must apply even with filter params present"
        assert "/login" in response.headers["Location"]


# --------------------------------------------------------------------- #
# DoD: "Visiting /profile with no query parameters shows all-time
# summary stats, all-time category breakdown, and the 5 most recent
# transactions"
# --------------------------------------------------------------------- #
class TestNoFilterDefaultView:
    def test_no_query_params_shows_alltime_data_not_month_locked(self, auth_client):
        old_desc = "OldExpenseOutsideCurrentMonth"
        recent_desc = "RecentExpenseMarker"
        _insert_expense(auth_client.user_id, 50, "Food", days_ago(400), old_desc)
        _insert_expense(auth_client.user_id, 20, "Transport", days_ago(1), recent_desc)

        response = auth_client.get("/profile")
        assert response.status_code == 200
        body = response.data.decode()
        assert old_desc in body, "All-time default view must include expenses from any month, not just the current one"
        assert recent_desc in body

    def test_no_query_params_caps_transaction_table_at_five_most_recent(self, auth_client):
        descs = [f"TxnMarker{i}" for i in range(7)]
        for i, desc in enumerate(descs):
            _insert_expense(auth_client.user_id, 10 + i, "Other", days_ago(i), desc)

        response = auth_client.get("/profile")
        body = response.data.decode()

        for desc in descs[:5]:
            assert desc in body, f"{desc} is among the 5 most recent and should be shown"
        for desc in descs[5:]:
            assert desc not in body, f"{desc} is older than the 5 most recent and should not be shown"

    def test_no_query_params_filter_ui_is_not_active(self, auth_client):
        response = auth_client.get("/profile")
        body = response.data.decode()
        assert "Clear filter" not in body, "Clear filter link must not show when no filter is active"


# --------------------------------------------------------------------- #
# DoD: "Visiting /profile?start_date=...&end_date=... scopes the
# transaction table (no 5-row cap), summary stats, and category
# breakdown to that inclusive range"
# --------------------------------------------------------------------- #
class TestValidRangeFilter:
    def test_range_filter_includes_only_expenses_within_range(self, auth_client):
        uid = auth_client.user_id
        in_desc1, in_desc2 = "InRangeA", "InRangeB"
        out_before, out_after = "BeforeRange", "AfterRange"
        _insert_expense(uid, 10, "Food", "2026-02-01", in_desc1)
        _insert_expense(uid, 20, "Food", "2026-02-15", in_desc2)
        _insert_expense(uid, 30, "Food", "2026-01-01", out_before)
        _insert_expense(uid, 40, "Food", "2026-03-01", out_after)

        response = auth_client.get("/profile?start_date=2026-02-01&end_date=2026-02-28")
        assert response.status_code == 200
        body = response.data.decode()
        assert in_desc1 in body
        assert in_desc2 in body
        assert out_before not in body
        assert out_after not in body

    def test_range_filter_boundaries_are_inclusive(self, auth_client):
        uid = auth_client.user_id
        start_marker, end_marker = "OnStartBoundary", "OnEndBoundary"
        _insert_expense(uid, 10, "Food", "2026-05-01", start_marker)
        _insert_expense(uid, 10, "Food", "2026-05-31", end_marker)

        response = auth_client.get("/profile?start_date=2026-05-01&end_date=2026-05-31")
        body = response.data.decode()
        assert start_marker in body, "Expense dated exactly on start_date must be included (inclusive range)"
        assert end_marker in body, "Expense dated exactly on end_date must be included (inclusive range)"

    def test_range_filter_removes_five_row_cap_on_transaction_table(self, auth_client):
        uid = auth_client.user_id
        descs = [f"RangeTxn{i}" for i in range(8)]
        for i, desc in enumerate(descs):
            _insert_expense(uid, 10, "Food", f"2026-04-{i + 1:02d}", desc)

        response = auth_client.get("/profile?start_date=2026-04-01&end_date=2026-04-30")
        body = response.data.decode()
        for desc in descs:
            assert desc in body, "All 8 matching rows should render when a filter is active, not capped at 5"


# --------------------------------------------------------------------- #
# DoD: "Supplying only start_date or only end_date filters as an
# open-ended range instead of erroring"
# --------------------------------------------------------------------- #
class TestOpenEndedFilter:
    def test_only_start_date_filters_open_ended_upper_bound(self, auth_client):
        uid = auth_client.user_id
        before, on, after = "BeforeStartOnly", "OnStartOnly", "AfterStartOnly"
        _insert_expense(uid, 10, "Food", "2026-01-01", before)
        _insert_expense(uid, 10, "Food", "2026-06-01", on)
        _insert_expense(uid, 10, "Food", "2026-12-31", after)

        response = auth_client.get("/profile?start_date=2026-06-01")
        assert response.status_code == 200
        body = response.data.decode()
        assert before not in body
        assert on in body
        assert after in body

    def test_only_end_date_filters_open_ended_lower_bound(self, auth_client):
        uid = auth_client.user_id
        before, on, after = "BeforeEndOnly", "OnEndOnly", "AfterEndOnly"
        _insert_expense(uid, 10, "Food", "2026-01-01", before)
        _insert_expense(uid, 10, "Food", "2026-06-01", on)
        _insert_expense(uid, 10, "Food", "2026-12-31", after)

        response = auth_client.get("/profile?end_date=2026-06-01")
        assert response.status_code == 200
        body = response.data.decode()
        assert before in body
        assert on in body
        assert after not in body

    def test_only_start_date_marks_filter_as_active(self, auth_client):
        response = auth_client.get("/profile?start_date=2026-01-01")
        body = response.data.decode()
        assert "Clear filter" in body, "A single-sided filter should still count as an active filter"

    def test_only_end_date_marks_filter_as_active(self, auth_client):
        response = auth_client.get("/profile?end_date=2026-01-01")
        body = response.data.decode()
        assert "Clear filter" in body


# --------------------------------------------------------------------- #
# DoD: "Supplying a start_date after end_date shows a validation error
# and falls back to the default unfiltered (all-time) view"
# --------------------------------------------------------------------- #
class TestValidationError:
    def test_start_after_end_shows_inline_error_via_auth_error_convention(self, auth_client):
        response = auth_client.get("/profile?start_date=2026-06-01&end_date=2026-01-01")
        assert response.status_code == 200
        body = response.data.decode()
        assert "auth-error" in body, "Invalid range must render via the existing .auth-error convention"

    def test_start_after_end_falls_back_to_alltime_unfiltered_view(self, auth_client):
        uid = auth_client.user_id
        far_past_marker = "FarPastFallbackMarker"
        _insert_expense(uid, 10, "Food", "2020-01-01", far_past_marker)

        response = auth_client.get("/profile?start_date=2026-06-01&end_date=2026-01-01")
        body = response.data.decode()
        assert far_past_marker in body, (
            "On an invalid range, the view should fall back to the all-time default "
            "and still show existing expenses, not an empty/errored result"
        )

    def test_start_after_end_does_not_present_as_an_active_filter(self, auth_client):
        response = auth_client.get("/profile?start_date=2026-06-01&end_date=2026-01-01")
        body = response.data.decode()
        assert "Clear filter" not in body, (
            "An invalid filter that falls back to the default view should not present as active"
        )

    def test_start_equal_to_end_is_a_valid_single_day_range_not_an_error(self, auth_client):
        uid = auth_client.user_id
        marker = "SingleDayRangeMarker"
        _insert_expense(uid, 10, "Food", "2026-07-04", marker)

        response = auth_client.get("/profile?start_date=2026-07-04&end_date=2026-07-04")
        body = response.data.decode()
        assert "auth-error" not in body, "start_date == end_date must not be treated as invalid"
        assert marker in body


# --------------------------------------------------------------------- #
# DoD: "Filtering to a range with no matching expenses shows the
# existing 'No transactions yet' empty-state row, ₹0 total spent, and
# an empty category breakdown — no errors"
# --------------------------------------------------------------------- #
class TestEmptyRangeFilterResult:
    def test_filter_with_no_matches_shows_empty_state_and_zero_total(self, auth_client):
        uid = auth_client.user_id
        marker = "OutsideEmptyRangeMarker"
        _insert_expense(uid, 99, "Food", "2026-01-01", marker)

        response = auth_client.get("/profile?start_date=2026-06-01&end_date=2026-06-30")
        assert response.status_code == 200
        body = response.data.decode()
        assert marker not in body, "Out-of-range expense must not be listed"
        assert "No transactions yet" in body, "Empty filtered range must show the existing empty-state row"
        assert "₹0" in body, "Total spent must render as ₹0 when nothing matches the filter"
        assert "auth-error" not in body, "A valid, merely-empty range is not a validation error"

    def test_filter_with_no_matches_does_not_error(self, auth_client):
        response = auth_client.get("/profile?start_date=2099-01-01&end_date=2099-12-31")
        assert response.status_code == 200


# --------------------------------------------------------------------- #
# DoD: "The date input fields are pre-populated with the currently
# active filter after submitting" / "A 'Clear filter' link appears when
# a filter is active and returns to the unfiltered /profile view"
# --------------------------------------------------------------------- #
class TestFilterUIState:
    def test_fields_are_prepopulated_with_active_filter_values(self, auth_client):
        response = auth_client.get("/profile?start_date=2026-03-01&end_date=2026-03-31")
        body = response.data.decode()
        assert 'name="start_date"' in body
        assert 'value="2026-03-01"' in body
        assert 'name="end_date"' in body
        assert 'value="2026-03-31"' in body

    def test_clear_filter_link_present_when_filter_active(self, auth_client):
        response = auth_client.get("/profile?start_date=2026-03-01&end_date=2026-03-31")
        body = response.data.decode()
        assert "Clear filter" in body

    def test_clear_filter_link_absent_without_filter(self, auth_client):
        response = auth_client.get("/profile")
        body = response.data.decode()
        assert "Clear filter" not in body

    def test_clear_filter_link_points_back_to_unfiltered_profile(self, auth_client):
        response = auth_client.get("/profile?start_date=2026-03-01&end_date=2026-03-31")
        body = response.data.decode()
        assert 'href="/profile"' in body, "Clear filter link must point back to the unfiltered /profile view"

    def test_filter_form_uses_get_method_and_targets_profile(self, auth_client):
        response = auth_client.get("/profile")
        body = response.data.decode()
        assert 'method="GET"' in body, "Filter form must submit via GET so the filtered view is a shareable URL"
        assert 'action="/profile"' in body


# --------------------------------------------------------------------- #
# Rules: defensive handling of malformed/partial input; parameterized
# queries only (no crashes, no data corruption)
# --------------------------------------------------------------------- #
class TestEdgeCasesAndSafety:
    def test_garbage_date_string_does_not_crash(self, auth_client):
        response = auth_client.get("/profile?start_date=not-a-date&end_date=also-not-a-date")
        assert response.status_code == 200

    def test_sql_injection_attempt_in_date_param_does_not_crash_or_corrupt_data(self, auth_client):
        uid = auth_client.user_id
        marker = "IntegrityCheckMarker"
        _insert_expense(uid, 15, "Food", "2026-01-01", marker)

        malicious = "2026-01-01'; DROP TABLE expenses; --"
        response = auth_client.get(f"/profile?start_date={malicious}")
        assert response.status_code == 200, "A malicious date string must not crash the request"

        follow_up = auth_client.get("/profile")
        assert follow_up.status_code == 200
        assert marker in follow_up.data.decode(), (
            "The expenses table must remain intact (parameterized queries) after a malicious date param"
        )

    def test_empty_string_date_params_behave_as_no_filter(self, auth_client):
        uid = auth_client.user_id
        marker = "EmptyParamsMarker"
        _insert_expense(uid, 15, "Food", "2020-01-01", marker)

        response = auth_client.get("/profile?start_date=&end_date=")
        body = response.data.decode()
        assert response.status_code == 200
        assert marker in body, "Blank date query params should behave like no filter at all"
        assert "Clear filter" not in body

    def test_whitespace_only_date_params_are_stripped_and_treated_as_no_filter(self, auth_client):
        response = auth_client.get("/profile?start_date=%20%20&end_date=%20%20")
        body = response.data.decode()
        assert response.status_code == 200
        assert "Clear filter" not in body, "Whitespace-only params should be stripped and treated as absent"


# --------------------------------------------------------------------- #
# Database changes: get_recent_transactions(user_id, limit=5,
# start_date=None, end_date=None)
# --------------------------------------------------------------------- #
class TestGetRecentTransactionsHelper:
    def test_no_filter_returns_five_most_recent_ordered_desc(self, app):
        uid = _create_user("helper1@example.com")
        for i in range(7):
            _insert_expense(uid, 10, "Food", days_ago(i), f"H{i}")

        rows = db_module.get_recent_transactions(uid)
        assert len(rows) == 5, "Default (unfiltered) behavior is unchanged: 5 most recent"
        returned_dates = [r["date"] for r in rows]
        assert returned_dates == sorted(returned_dates, reverse=True), "Must be ORDER BY date DESC"

    def test_filter_drops_limit_and_returns_all_matches(self, app):
        # Spec (Database changes): "When either is given, adds ... and
        # drops the LIMIT so all matching rows in range are returned."
        # This is documented as the helper's own behavior once a date
        # filter is supplied -- called here with the default `limit`
        # left untouched, matching the literal function-level contract.
        uid = _create_user("helper2@example.com")
        for i in range(8):
            _insert_expense(uid, 10, "Food", f"2026-04-{i + 1:02d}", f"H{i}")

        rows = db_module.get_recent_transactions(
            uid, start_date="2026-04-01", end_date="2026-04-30"
        )
        assert len(rows) == 8, "Supplying a date filter must drop the LIMIT cap, even with the default limit=5"

    def test_open_ended_start_only(self, app):
        uid = _create_user("helper3@example.com")
        _insert_expense(uid, 10, "Food", "2026-01-01", "old")
        _insert_expense(uid, 10, "Food", "2026-06-01", "new")

        rows = db_module.get_recent_transactions(uid, start_date="2026-03-01")
        descs = [r["description"] for r in rows]
        assert "new" in descs
        assert "old" not in descs

    def test_open_ended_end_only(self, app):
        uid = _create_user("helper4@example.com")
        _insert_expense(uid, 10, "Food", "2026-01-01", "old")
        _insert_expense(uid, 10, "Food", "2026-06-01", "new")

        rows = db_module.get_recent_transactions(uid, end_date="2026-03-01")
        descs = [r["description"] for r in rows]
        assert "old" in descs
        assert "new" not in descs

    def test_no_matching_rows_returns_empty_list(self, app):
        uid = _create_user("helper5@example.com")
        _insert_expense(uid, 10, "Food", "2020-01-01", "a")

        rows = db_module.get_recent_transactions(
            uid, start_date="2099-01-01", end_date="2099-12-31"
        )
        assert len(rows) == 0


# --------------------------------------------------------------------- #
# Database changes: get_summary_stats(user_id, start_date=None,
# end_date=None) — all-time by default, filter-scoped when active,
# count_last_7_days independent of the filter
# --------------------------------------------------------------------- #
class TestGetSummaryStatsHelper:
    def test_no_filter_is_alltime_not_current_month_locked(self, app):
        uid = _create_user("summary1@example.com")
        _insert_expense(uid, 100, "Food", "2020-01-01", "old")
        _insert_expense(uid, 50, "Food", days_ago(1), "recent")

        stats = db_module.get_summary_stats(uid)
        assert stats["total"] == 150
        assert stats["count"] == 2

    def test_filtered_range_scopes_total_and_count(self, app):
        uid = _create_user("summary2@example.com")
        _insert_expense(uid, 100, "Food", "2026-02-01", "in")
        _insert_expense(uid, 999, "Food", "2020-01-01", "out")

        stats = db_module.get_summary_stats(uid, start_date="2026-01-01", end_date="2026-03-01")
        assert stats["total"] == 100
        assert stats["count"] == 1

    def test_top_category_reflects_active_filter(self, app):
        uid = _create_user("summary3@example.com")
        _insert_expense(uid, 10, "Food", "2026-02-01", "a")
        _insert_expense(uid, 500, "Bills", "2020-01-01", "b")

        stats = db_module.get_summary_stats(uid, start_date="2026-01-01", end_date="2026-03-01")
        assert stats["top_category_name"] == "Food"
        assert stats["top_category_total"] == 10

    def test_count_last_7_days_is_independent_of_active_filter(self, app):
        uid = _create_user("summary4@example.com")
        _insert_expense(uid, 10, "Food", days_ago(2), "recent-real-day")

        stats_unfiltered = db_module.get_summary_stats(uid)
        stats_filtered = db_module.get_summary_stats(uid, start_date="2020-01-01", end_date="2020-12-31")

        assert stats_unfiltered["count_last_7_days"] == 1
        assert stats_filtered["count_last_7_days"] == 1, (
            "count_last_7_days must reflect the last 7 real days regardless of the active date filter"
        )

    def test_no_expenses_returns_zero_total_and_no_top_category(self, app):
        uid = _create_user("summary5@example.com")

        stats = db_module.get_summary_stats(uid)
        assert stats["total"] == 0
        assert stats["count"] == 0
        assert stats["top_category_name"] is None


# --------------------------------------------------------------------- #
# Database changes: get_category_breakdown(user_id, start_date=None,
# end_date=None) — sorted by amount descending, all-time or filtered
# --------------------------------------------------------------------- #
class TestGetCategoryBreakdownHelper:
    def test_no_filter_is_alltime_and_sorted_desc(self, app):
        uid = _create_user("cat1@example.com")
        _insert_expense(uid, 10, "Food", "2020-01-01", "a")
        _insert_expense(uid, 50, "Bills", "2020-01-02", "b")
        _insert_expense(uid, 5, "Other", "2020-01-03", "c")

        rows = db_module.get_category_breakdown(uid)
        totals = [r["total"] for r in rows]
        assert totals == sorted(totals, reverse=True), "Category breakdown must be sorted by amount descending"
        assert rows[0]["category"] == "Bills"

    def test_filter_scopes_totals_to_range(self, app):
        uid = _create_user("cat2@example.com")
        _insert_expense(uid, 10, "Food", "2026-02-01", "in")
        _insert_expense(uid, 999, "Food", "2020-01-01", "out")

        rows = db_module.get_category_breakdown(uid, start_date="2026-01-01", end_date="2026-03-01")
        assert len(rows) == 1
        assert rows[0]["total"] == 10

    def test_no_matching_rows_returns_empty_result(self, app):
        uid = _create_user("cat3@example.com")
        _insert_expense(uid, 10, "Food", "2020-01-01", "a")

        rows = db_module.get_category_breakdown(uid, start_date="2099-01-01", end_date="2099-12-31")
        assert len(rows) == 0


# --------------------------------------------------------------------- #
# Rules: "Use CSS variables — never hardcode hex values" /
# DoD: "No hex colour values appear in any modified template or CSS
# file — only CSS variables"
# --------------------------------------------------------------------- #
class TestNoHardcodedHexColors:
    """
    DoD: "No hex colour values appear in any modified template or CSS
    file — only CSS variables". Scoped to the new date-filter-form CSS
    rules (and the whole profile.html template) rather than the entire
    style.css file, since style.css's pre-existing `:root` block
    necessarily defines hex values for the CSS variables themselves --
    that predates and is out of scope for this feature.
    """

    HEX_PATTERN = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b")

    def test_profile_template_has_no_hardcoded_hex_colors(self):
        content = (PROJECT_ROOT / "templates" / "profile.html").read_text(encoding="utf-8")
        matches = self.HEX_PATTERN.findall(content)
        assert not matches, f"profile.html must only use CSS variables, found hex colors: {matches}"

    def test_date_filter_css_rules_have_no_hardcoded_hex_colors(self):
        content = (PROJECT_ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")

        # Isolate the full CSS rule blocks (selector + body) introduced
        # for the date-filter form, wherever they appear in the file
        # (including inside @media blocks), so both selector lines and
        # multi-line rule bodies are covered.
        filter_rule_blocks = re.findall(r"\.date-filter[^{]*\{[^}]*\}", content)
        assert filter_rule_blocks, (
            "Expected to find .date-filter-* CSS rule blocks in style.css for the new filter form"
        )

        joined = "\n".join(filter_rule_blocks)
        matches = self.HEX_PATTERN.findall(joined)
        assert not matches, (
            f"date-filter CSS rules must only use CSS variables, found hex colors: {matches}"
        )
