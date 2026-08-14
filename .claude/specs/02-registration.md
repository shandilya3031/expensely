# Spec: Registration

## Overview
This step implements real user registration for Spendly. The `register.html` template and its `POST /register` form already exist, but the route only renders the page — there is no backend logic to validate input, hash the password, or insert the user into the `users` table. On success the user is shown a success message and redirected to the login page, where they sign in themselves — registration does not auto-log-in. This step wires that up so a visitor can create a real account, using the `users` table and `get_db()`/`init_db()` foundation built in Step 1.

## Depends on
- Step 1 — Database Setup (`.claude/specs/01-database-setup.md`): requires `users` table, `get_db()`, and `werkzeug` password hashing to already be in place.

## Routes
- `GET /register` — renders the registration form — public (already exists, unchanged)
- `POST /register` — validates input, creates the user, flashes a success message, redirects to `/login` — public

## Database changes
No database changes. The `users` table from Step 1 (`id`, `name`, `email`, `password_hash`, `created_at`) already supports registration as-is. `email` is already `UNIQUE NOT NULL`, which is relied on for duplicate-email rejection.

## Templates
- **Create:** none
- **Modify:**
  - `templates/register.html` — `{% if error %}` block reused to display validation/duplicate-email errors on failed submission; `value="{{ name }}"`/`value="{{ email }}"` added to the name/email inputs so entered values are preserved (password and confirm-password fields left blank); add a new `confirm_password` input directly after the `password` input
  - `templates/base.html` — add a flashed-messages block (via `get_flashed_messages(with_categories=true)`) so the success message set on `/register` can be displayed after the redirect to `/login`; styled with CSS variables, reusable by any future page that calls `flash()`

## Files to change
- `app.py` — add `app.secret_key` config (needed for Flask sessions), implement `POST /register` handling (validation, hashing, insert, flash success message, redirect to `/login`)
- `database/db.py` — no changes needed if Step 1 was implemented as specced; verify `get_db()` and the `users` schema match before implementing
- `templates/base.html` — render flashed messages (see Templates section)
- `static/css/style.css` — add styling for the new flashed-message block, using existing CSS variables (e.g. `--accent`/`--accent-light`) — no hardcoded hex values

## Files to create
- None

## New dependencies
No new dependencies. `werkzeug.security` (`generate_password_hash`) and Flask's built-in `session` are already available via existing packages in `requirements.txt`.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (`generate_password_hash`), never stored or logged in plaintext
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Validate on the server even though the form has `required`/`type=email` attributes client-side: name and email non-empty, email contains `@`, password at least 8 characters, and `confirm_password` matches `password` exactly
- On duplicate email (`UNIQUE` constraint violation), show a friendly error via the existing `error` template var — do not leak whether it's the email specifically that's registered vs. a generic failure being preferable, but a clear "Email already registered" message is acceptable here since this is a demo app
- On success, do **not** set a session (registration does not auto-log-in) — flash a success message (e.g. "Registration successful! Please sign in.") and redirect to `/login`
- Do not implement `/login` or `/logout` logic in this step — those are separate steps

## Definition of done
- [ ] Submitting the register form with valid name/email/password (8+ chars) creates a row in `users` with a hashed (not plaintext) password
- [ ] After successful registration, the browser is redirected to `/login` and a success message is visible on the login page (no `session` is set by registration itself)
- [ ] Submitting with an email that already exists in `users` re-renders `register.html` with an error message and does not create a duplicate row
- [ ] Submitting with a password under 8 characters re-renders `register.html` with a validation error and does not create a user
- [ ] Submitting with a confirm-password value that doesn't match the password re-renders `register.html` with a validation error and does not create a user
- [ ] Submitting with an empty name or malformed email re-renders `register.html` with a validation error and does not create a user
- [ ] Registering two different users with different emails both succeed and both rows exist in `users`
- [ ] App starts without errors and `GET /register` still renders the form as before
