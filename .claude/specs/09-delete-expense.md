# Spec: Delete Expense

## Overview
This feature lets a logged-in user permanently remove one of their own expenses from Spendly. It replaces the current `GET /expenses/<id>/delete` stub (which returns a bare placeholder string) with a real confirmation-then-delete flow: the user clicks "Delete" on an expense row in their profile, lands on a confirmation page showing that expense's details, and either confirms (removing it from the database) or cancels (returning to the profile unchanged). This is the final CRUD operation for expenses, completing the add/edit/delete set for Spendly's expense management.

## Depends on
- Step 01 (Database setup) — `expenses` table and `get_db()` must exist.
- Step 03 (Login/Logout) — session-based auth (`session["user_id"]`) required to gate this route.
- Step 04/05 (Profile page & backend routes) — the profile page's transaction table is where the Delete action is triggered from and where the user returns to afterward.
- Step 08 (Edit expense) — establishes the ownership-check pattern (`get_expense_by_id(expense_id, user_id)` + `abort(404)`) that this feature reuses directly.

## Routes
- `GET /expenses/<int:expense_id>/delete` — renders a confirmation page showing the expense's details; ownership-checked, `abort(404)` if the expense doesn't exist or isn't owned by the current user — access level: logged-in
- `POST /expenses/<int:expense_id>/delete` — deletes the expense (ownership-checked, same 404 rule), flashes a success message, redirects to `/profile` — access level: logged-in

Both methods are handled by a single `delete_expense(expense_id)` view function (`methods=["GET", "POST"]`), matching the existing `edit_expense` pattern. An unauthenticated request to either method redirects to `/login`.

## Database changes
No schema changes. The `expenses` table (defined in `database/db.py`'s `init_db()`) already supports this feature as-is:
```sql
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    date TEXT NOT NULL,
    description TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
)
```
One new helper is needed in `database/db.py`:
```python
def delete_expense(expense_id, user_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM expenses WHERE id = ? AND user_id = ?",
        (expense_id, user_id),
    )
    conn.commit()
    conn.close()
```
The `WHERE id = ? AND user_id = ?` clause is the enforcement layer — even if the route-level ownership check were somehow bypassed, the delete itself cannot touch another user's row.

## Templates
- **Create:** `templates/delete_expense.html` — extends `base.html`; follows `edit_expense.html`'s `auth-section` / `auth-container` / `auth-card` structure. Shows a summary of the expense (amount, category, date, description) with a clear warning that this action can't be undone, a `POST` form with a single confirm button, and a plain "Cancel" link back to `url_for('profile')`.
- **Modify:** `templates/profile.html` — add a "Delete" link/button in the `txn-action-col` of each transaction row, next to the existing Edit link, pointing to `url_for('delete_expense', expense_id=txn.id)`.

## Files to change
- `app.py` — replace the `delete_expense` stub with the real `GET`/`POST` implementation (auth check, ownership check via `get_expense_by_id`, `abort(404)`, render confirmation template on `GET`, call `delete_expense()` + flash + redirect on `POST`).
- `database/db.py` — add the `delete_expense(expense_id, user_id)` helper.
- `templates/profile.html` — add the Delete link to each transaction row.
- `static/css/style.css` — add a `.btn-danger` style (using the existing `--danger` / `--danger-light` CSS variables) for the delete confirm button and/or the profile row's delete link, following the pattern of the existing `.btn-submit` / `.btn-primary` classes.

## Files to create
- `templates/delete_expense.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (n/a to this feature, but no regressions to existing auth code)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Ownership is mandatory: every lookup and delete must be scoped to `WHERE id = ? AND user_id = ?` — a user must never be able to view or delete another user's expense by guessing an id
- Use `abort(404)` for not-found/not-owned expenses — never a bare string return
- Unauthenticated access to either method redirects to `login`
- Never hardcode URLs — always use `url_for()`
- DB logic (the `DELETE` query) lives only in `database/db.py`, never inline in `app.py`
- The delete must require a `POST` (a confirmation page, not a one-click `GET` link) so the destructive action can't be triggered by a bare hyperlink, prefetch, or crawler

## Definition of done
- [ ] Visiting `GET /expenses/<id>/delete` while logged out redirects to `/login`
- [ ] Visiting `GET /expenses/<id>/delete` for a nonexistent id, or an id owned by a different user, returns a 404
- [ ] Visiting `GET /expenses/<id>/delete` for your own expense renders a confirmation page showing that expense's amount, category, date, and description
- [ ] Submitting the confirmation form (`POST`) for your own expense removes it from the database and redirects to `/profile` with a success flash message
- [ ] The deleted expense no longer appears in the profile's transaction table or summary stats after redirect
- [ ] Submitting `POST /expenses/<id>/delete` for a nonexistent id, or an id owned by a different user, returns a 404 and performs no deletion
- [ ] Clicking "Cancel" on the confirmation page returns to `/profile` without deleting anything
- [ ] No new pip packages were added to `requirements.txt`
