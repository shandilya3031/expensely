# Spec: Edit Expense

## Overview
This feature implements the `/expenses/<id>/edit` route, letting a logged-in user modify an existing expense they own. It replaces the current stub route (which returns a raw string) with a real GET/POST flow that loads the expense, pre-fills a form, validates input on submit, updates the row in the `expenses` table, and redirects back to the profile page where the updated transaction, stats, and category breakdown are reflected. It also adds an "Edit" entry point to each row in the Recent Transactions table on the profile page, which currently has no way to reach an individual expense.

## Depends on
- Step 01 — Database setup (`expenses` table, `get_db()`)
- Step 03 — Login/Logout (`session["user_id"]`, auth gating)
- Step 04/05 — Profile page and backend routes (destination after a successful edit, and the Recent Transactions table this feature adds a link to)
- Step 07 — Add Expense (established the form/validation pattern this feature reuses)

## Routes
- `GET /expenses/<id>/edit` — renders the edit-expense form pre-filled with the existing expense's values — logged-in only (redirect to `login` if no session); 404 via `abort(404)` if the expense doesn't exist or doesn't belong to the current user
- `POST /expenses/<id>/edit` — validates form input, updates the expense, redirects to `profile` — logged-in only (redirect to `login` if no session); 404 via `abort(404)` if the expense doesn't exist or doesn't belong to the current user

## Database changes
No database changes. The `expenses` table (`database/db.py`) already has all required columns: `user_id`, `amount`, `category`, `date`, `description`. No new tables, columns, or constraints are needed.

## Templates
- **Create:** `templates/edit_expense.html` — extends `base.html`; same field set and layout as `templates/add_expense.html` (amount, category select from `CATEGORIES`, date, description) but pre-filled with the existing expense's values and posting to `edit_expense`; shows validation errors the same way (`auth-error` block, re-populated field values on error)
- **Modify:** `templates/profile.html` — add an "Edit" link per row in the `transaction-table` body (around line 61-67), using `url_for('edit_expense', id=txn.id)`

## Files to change
- `app.py`:
  - Replace the stub `edit_expense(id)` route with GET/POST handling, ownership check, validation, and redirect logic (mirrors `add_expense`'s validation rules)
  - `_build_transactions()` — include `txn["id"] = row["id"]` in the dict it builds (the underlying `get_recent_transactions` query already selects `id`; it's just not passed through), so `profile.html` can link to each row's edit page
- `database/db.py` — add:
  - `get_expense_by_id(expense_id, user_id)` — parameterized `SELECT` scoped to both `id` and `user_id`, returning `None` if not found or not owned by the user
  - `update_expense(expense_id, user_id, amount, category, date, description)` — parameterized `UPDATE` scoped to both `id` and `user_id`
- `templates/profile.html` — add the per-row "Edit" link
- `CLAUDE.md` — update the routes table to mark `GET /expenses/<id>/edit` as implemented once this step is done (do this only after implementation, not as part of the spec)

## Files to create
- `templates/edit_expense.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders) — no f-strings in SQL
- All DB logic lives in `database/db.py`, never inline in `app.py`
- Passwords hashed with werkzeug (not applicable to this feature, but keep existing auth code untouched)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Ownership is mandatory: every lookup and update must be scoped to `WHERE id = ? AND user_id = ?` — a user must never be able to view or edit another user's expense by guessing an id
- Use `abort(404)` when the expense doesn't exist or isn't owned by the current user — not a bare string return, not a silent redirect
- Validate on the server exactly as `add_expense` does: amount must be a positive number, category must be one of `CATEGORIES`, date must be a valid `YYYY-MM-DD` string, description is optional
- Never hardcode URLs in templates — always use `url_for()`
- Unauthenticated access to either route must redirect to `login`, matching the pattern used by `profile()` and `add_expense()`

## Definition of done
- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to `/login`
- [ ] Visiting `/expenses/<id>/edit` for an expense that doesn't exist returns a 404
- [ ] Visiting `/expenses/<id>/edit` for an expense owned by a different user returns a 404
- [ ] Visiting `/expenses/<id>/edit` for an expense the current user owns renders a form pre-filled with its amount, category, date, and description
- [ ] The Recent Transactions table on `/profile` shows an Edit link/button per row that navigates to that expense's edit page
- [ ] Submitting the form with valid data updates the existing row (not a new one) in `expenses` and redirects to `/profile`
- [ ] The updated values appear in the Recent Transactions table and are reflected in the summary stats and category breakdown on `/profile`
- [ ] Submitting with a missing/invalid amount (blank, zero, negative, non-numeric) re-renders the form with an error and preserves the other entered values
- [ ] Submitting with an invalid category (not in `CATEGORIES`) is rejected with an error
- [ ] Submitting with a missing or malformed date is rejected with an error
- [ ] No new pip packages were added and `requirements.txt` is unchanged
