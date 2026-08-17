# Spec: Add Expense

## Overview
This feature implements the `/expenses/add` route, letting a logged-in user record a new expense through a form. It replaces the current stub route (which returns a raw string) with a real GET/POST flow that validates input, inserts the expense into the `expenses` table, and redirects back to the profile page where the new transaction, updated stats, and category breakdown are visible. This is the first step in the Spendly roadmap where a user can create data rather than just view seeded/demo data.

## Depends on
- Step 01 — Database setup (`expenses` table, `get_db()`)
- Step 03 — Login/Logout (`session["user_id"]`, auth gating)
- Step 04/05 — Profile page and backend routes (destination after a successful add, and the data this feature will make non-empty)

## Routes
- `GET /expenses/add` — renders the add-expense form — logged-in only (redirect to `login` if no session)
- `POST /expenses/add` — validates form input, inserts the expense, redirects to `profile` — logged-in only (redirect to `login` if no session)

## Database changes
No database changes. The `expenses` table (`database/db.py`) already has all required columns: `user_id`, `amount`, `category`, `date`, `description`. No new tables, columns, or constraints are needed.

## Templates
- **Create:** `templates/add_expense.html` — extends `base.html`; form with fields for amount, category (select, populated from `CATEGORIES` in `database/db.py`), date, and description; shows validation errors the same way `register.html`/`login.html` do (`auth-error` block, re-populated field values on error)
- **Modify:** `templates/profile.html` — add an "Add Expense" link/button (using `url_for('add_expense')`) near the profile header or the Recent Transactions block, so the feature is reachable from the UI

## Files to change
- `app.py` — replace the stub `add_expense()` route with GET/POST handling, validation, and redirect logic
- `database/db.py` — add a `create_expense(user_id, amount, category, date, description)` helper that performs the parameterized `INSERT`
- `templates/profile.html` — add the "Add Expense" entry point
- `CLAUDE.md` — update the routes table to mark `GET /expenses/add` as implemented once this step is done (do this only after implementation, not as part of the spec)

## Files to create
- `templates/add_expense.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders) — no f-strings in SQL
- All DB logic lives in `database/db.py`, never inline in `app.py`
- Passwords hashed with werkzeug (not applicable to this feature, but keep existing auth code untouched)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Validate on the server: amount must be a positive number, category must be one of `CATEGORIES`, date must be a valid `YYYY-MM-DD` string, description is optional
- Use `abort()` for HTTP errors, not bare `return "error string"` — this also removes the last stub-string return for this route
- Never hardcode URLs in templates — always use `url_for()`
- Unauthenticated access to either route must redirect to `login`, matching the pattern used by `profile()`

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in renders a form with amount, category, date, and description fields
- [ ] Submitting the form with valid data creates a new row in `expenses` for the current user and redirects to `/profile`
- [ ] The newly added expense appears in the "Recent Transactions" table and is reflected in the summary stats and category breakdown on `/profile`
- [ ] Submitting with a missing/invalid amount (blank, zero, negative, non-numeric) re-renders the form with an error and preserves the other entered values
- [ ] Submitting with an invalid category (not in `CATEGORIES`) is rejected with an error
- [ ] Submitting with a missing or malformed date is rejected with an error
- [ ] No new pip packages were added and `requirements.txt` is unchanged
