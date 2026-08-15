# Spec: Date Filter For Profile Page

## Overview
This feature adds a date-range filter to the Recent Transactions table on the profile page. Currently `/profile` always shows the user's 5 most recent expenses with no way to narrow the view. This step lets a logged-in user pick a start and end date to see all their expenses in that range, submitted as simple GET query parameters so the filtered view is a shareable/bookmarkable URL. As implemented, the summary stats and category breakdown sections also respect the active date filter (see the note at the end of this spec — this extends beyond the original design and reflects a deliberate follow-up decision made during implementation).

## Depends on
- Step 1: Database setup (`expenses` table must exist)
- Step 3: Login + Logout (session must be set; `/profile` must be a protected route)
- Step 5: Profile Backend Routes (`/profile` must already read real data via `get_recent_transactions`)

## Routes
- `GET /profile` — modified, not new — now also reads optional `start_date` and `end_date` query parameters (`YYYY-MM-DD`) and filters the transaction table, summary stats, and category breakdown accordingly — logged-in only (unchanged: redirect to `/login` if not authenticated).

No new routes besides the modified GET /profile.

## Database changes
No new tables or columns. `database/db.py` helpers accept optional `start_date`/`end_date` keyword arguments:
- `get_recent_transactions(user_id, limit=5, start_date=None, end_date=None)` — when neither is given, behavior is unchanged (5 most recent, `ORDER BY date DESC, id DESC`). When either is given, adds `AND date >= ?` / `AND date <= ?` (parameterized) and drops the `LIMIT` so all matching rows in range are returned.
- `get_summary_stats(user_id, start_date=None, end_date=None)` — replaces the old month-locked `get_monthly_summary`. Computes total spent, transaction count, and top category (name + total) over all-time when no filter is given, or over the given range when a filter is active. Also returns a fixed "transactions in the last 7 real days" count, independent of the filter.
- `get_category_breakdown(user_id, start_date=None, end_date=None)` — per-category totals, sorted by amount descending, over all-time when no filter is given, or over the given range when active.

## Templates
- **Modify:** `templates/profile.html`:
  - A date-range filter form above the "Recent Transactions" table:
    - Two `<input type="date">` fields (`start_date`, `end_date`) plus a submit button, method `GET`, action `{{ url_for('profile') }}`.
    - Fields pre-filled with the currently active filter values.
    - A "Clear filter" link (`<a href="{{ url_for('profile') }}">`) shown only when a filter is active.
    - A validation error (start date after end date) shown inline via the existing `.auth-error` convention.
  - No structural changes to the summary stats or category breakdown sections — only the Jinja values fed into them change based on the active filter.

## Files to change
- `app.py`:
  - `profile()` reads `start_date`/`end_date` from `request.args`, strips whitespace, validates (`start_date > end_date` with both present → error, filter not applied, falls back to the default unfiltered view).
  - Passes `start_date`, `end_date`, and the error (if any) into a `date_filter` context dict for the template.
  - `_build_transactions()`, `_build_summary_stats()`, and `_build_category_breakdown()` all accept `start_date`/`end_date` and thread them through to the corresponding `database/db.py` helpers.
  - When a filter is active, `_build_transactions()` calls with no `limit` so all matching rows are returned instead of capping at 5.
- `database/db.py` — `get_recent_transactions`, `get_summary_stats`, `get_category_breakdown` as described above.
- `static/css/style.css` — styles for the new filter form (inline layout for the two date inputs + button + clear link), using existing CSS variables only.

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — never string-format SQL, including the date-range clauses
- Passwords hashed with werkzeug (unaffected by this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- DB logic belongs only in `database/db.py` — no raw SQL in `app.py`, no separate `database/queries.py` module
- Authentication guard unchanged: check `session.get("user_id")`; if absent, `redirect(url_for("login"))`
- Treat malformed or partial date input defensively: a single date supplied (only `start_date` or only `end_date`) is valid and should filter as an open-ended range, not an error. A garbage/non-date string should not crash the app (plain string comparison and an inert SQL bind parameter tolerate it — no extra validation/regex needed)

## Definition of done
- [ ] Visiting `/profile` with no query parameters shows all-time summary stats, all-time category breakdown, and the 5 most recent transactions
- [ ] Visiting `/profile?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` scopes the transaction table (no 5-row cap), summary stats, and category breakdown to that inclusive range
- [ ] Supplying only `start_date` or only `end_date` filters as an open-ended range instead of erroring
- [ ] Supplying a `start_date` after `end_date` shows a validation error and falls back to the default unfiltered (all-time) view
- [ ] The date input fields are pre-populated with the currently active filter after submitting
- [ ] A "Clear filter" link appears when a filter is active and returns to the unfiltered `/profile` view
- [ ] Filtering to a range with no matching expenses shows the existing "No transactions yet" empty-state row, ₹0 total spent, and an empty category breakdown — no errors
- [ ] Visiting `/profile` without being logged in still redirects to `/login`
- [ ] No hex colour values appear in any modified template or CSS file — only CSS variables

## Note on scope (recorded 2026-08-16)
The original version of this spec scoped the date filter to the transaction table only, explicitly keeping summary stats and category breakdown locked to the current calendar month (matching Step 5). During manual testing, that month-locked behavior produced a broken-looking ₹0 / blank "Top Category" for any user whose seeded data didn't fall in the current month. Per direct follow-up instruction, `get_summary_stats` and `get_category_breakdown` were changed to default to all-time totals (instead of current-month) and to respect the same `start_date`/`end_date` filter as the transaction table. This spec has been updated to reflect that as the actual, intended behavior.
