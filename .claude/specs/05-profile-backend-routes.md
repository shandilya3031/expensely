# Spec: Profile Backend Routes

## Overview
This feature replaces the hardcoded data in the `/profile` route (built in Step 4 purely for UI validation) with real queries against the `users` and `expenses` tables. The profile page keeps its existing layout and template — only the data source changes, from static Python dicts to values computed from the logged-in user's actual expense records. This is the step where the profile page becomes a real dashboard instead of a mockup.

## Depends on
- Step 1: Database setup (`users` and `expenses` tables must exist)
- Step 2: Registration (user accounts must be creatable)
- Step 3: Login + Logout (session must be set; `/profile` must be a protected route)
- Step 4: Profile Page (template and route already exist, currently with hardcoded data)

## Routes
No new routes. Modifies the existing `GET /profile` — logged-in only (redirect to `/login` if not authenticated) — so it builds `user`, `summary_stats`, `transactions`, and `category_breakdown` from the database instead of hardcoded values, keeping the exact same shape the template expects.

## Database changes
No new tables or columns. Add read-only helper functions to `database/db.py` (parameterized queries only):
- `get_user_by_id(user_id)` — fetch the logged-in user's row (`name`, `email`, `created_at`) for the header card.
- `get_recent_transactions(user_id, limit=5)` — the user's most recent expenses, ordered by `date DESC, id DESC`.
- `get_monthly_summary(user_id)` — for the current calendar month: total amount spent, transaction count, and the top category by amount (name + total). Also compute transaction count in the last 7 days (for the "Transactions" stat's delta) and the percent change in total spend vs. the previous calendar month (for the "Total Spent" stat's delta).
- `get_category_breakdown(user_id)` — total amount per category for the current calendar month, sorted by amount descending, including each category's percent share of the month's total spend.

## Templates
- **Modify:** `templates/profile.html` — only if an empty state is needed (e.g. "No transactions yet" row when `transactions` is empty). No structural changes otherwise — the route must keep passing data in the same shape the template already consumes (`stat.label/value/delta/delta_class`, `txn.date/description/category/amount`, `cat.name/amount/percent/css_class/width_class`).
- **Create:** none.

## Files to change
- `app.py` — replace the hardcoded dicts/lists in the `profile()` view with calls to the new `database/db.py` helpers, then transform the results into the same shapes `profile.html` already expects:
  - `user.initials` derived from the first letters of up to the first two words of `name`, uppercased.
  - `user.member_since` derived from `created_at`, formatted as `"%B %Y"` (e.g. "January 2025").
  - Total Spent formatted as `₹{amount:,.0f}` (no decimals, matches existing mock style); transaction row amounts formatted as `₹{amount:,.2f}` (with decimals).
  - `delta_class` chosen per stat: `mock-stat-delta-up` when spend increased vs. last month, `mock-stat-delta-down` when it decreased, `mock-stat-delta-neutral` when there's no prior-month data to compare or for the Transactions/Top Category stats (matching the existing mock's classes).
  - Category `css_class` = `"category-" + name.lower()` (matches `CATEGORIES` in `database/db.py` and the CSS already defined in `style.css`).
  - Category `width_class` = percent rounded to the nearest 10, mapped to `bar-w-{10..100}`, floored at `bar-w-10` for any category with a non-zero amount.
- `database/db.py` — add the four helper functions listed above.

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — never string-format SQL
- Passwords hashed with werkzeug (no changes to auth in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Authentication guard unchanged: check `session.get("user_id")`; if absent, `redirect(url_for("login"))`
- DB logic belongs only in `database/db.py` — no raw SQL in `app.py`
- Handle the zero-expenses case without errors: a brand-new user with no expenses should see `/profile` render with empty/zero stats, not a 500 (guard against division by zero when computing percentages)

## Definition of done
- [ ] Visiting `/profile` while logged in as the seeded demo user (`demo@spendly.com`) shows real totals matching the sum of that user's rows in the `expenses` table, not the old mock numbers
- [ ] The user info card shows the actual logged-in user's name, email, and initials, and a member-since date derived from their `created_at`
- [ ] The transaction table shows the user's real most-recent expenses (up to 5), correctly formatted
- [ ] The category breakdown reflects real per-category totals for the current month, with bar widths matching the nearest-10 percent
- [ ] A newly registered user with zero expenses can visit `/profile` and get a 200 response with empty/zero stats, not an error
- [ ] Visiting `/profile` without being logged in still redirects to `/login`
- [ ] No hex colour values appear in any modified template — only CSS variables
