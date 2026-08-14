---
name: spendly-ui-designer
description: Designs and codes UI pages/components for Spendly, a Flask-based personal expense tracker (github.com/shandilya3031/expensely), matching its existing hand-written design system (dark green + warm gold palette, DM Serif/DM Sans fonts, card-based fintech layout). Use this whenever the user asks to design, build, create, redesign, or improve a page or component for Spendly or "my expense tracker" — e.g. "design the add expense page," "build UI for the profile screen," "redesign the dashboard," "create a component for the expense list." Also use it for any expense-tracker UI work even if Spendly isn't named explicitly, as long as the project context (Flask app, templates/ + static/ folders, ₹ currency) matches. Produces a UI structure summary plus copy-pasteable Jinja2 HTML + CSS snippets, not a full app scaffold.
---

# Spendly UI designer

Spendly is a Flask app with server-rendered Jinja2 templates and a hand-written CSS design system — not a React/Tailwind project. The single biggest way to produce a bad result here is to design something generically "modern" that ignores that: a JSX component, a Tailwind-class-soup snippet, or a fresh color palette will look like it was airlifted in from a different app. The job is to extend what's already there, not to reimagine it.

Read the design system snapshot below before designing anything — it's ground truth for what "matches the existing design" means. Don't guess at hex codes or invent new button styles when equivalents already exist there.

## Design system snapshot

Captured from `github.com/shandilya3031/expensely` (repo name `expensely`, product name `Spendly`) on 2026-08-14. This is a snapshot, not a live fetch — it can drift as the project evolves. If a generated page looks visibly out of step with the live site, or the user mentions they've changed the design, re-fetch `static/css/style.css` and `templates/base.html` from the repo and update this section.

### Stack reality check

- **Backend**: Flask (Python), server-rendered with Jinja2 templates in `templates/`.
- **Frontend**: plain HTML + hand-written CSS in `static/css/style.css` + vanilla JS in `static/js/main.js`. No React, Vue, Tailwind, or any build step.
- **Templates extend `base.html`** via `{% extends "base.html" %}` and fill `{% block content %}` (and optionally `{% block head %}` / `{% block scripts %}`).

Generated code should be Jinja-flavored HTML and plain CSS that a Flask dev can paste straight into this project — not JSX, not Tailwind classes, not styled-components.

### Colors

```css
--ink: #0f0f0f;          /* primary text */
--ink-soft: #2d2d2d;     /* secondary text, labels */
--ink-muted: #6b6b6b;    /* tertiary text, subtitles */
--ink-faint: #a0a0a0;    /* placeholders, disabled */

--paper: #f7f6f3;        /* page background */
--paper-warm: #f0ede6;   /* alternate section background */
--paper-card: #ffffff;   /* card/panel background */

--accent: #1a472a;       /* dark green — primary brand accent, hovers, CTAs */
--accent-light: #e8f0eb; /* light green — accent backgrounds, badges */
--accent-2: #c17f24;     /* warm gold — secondary accent */
--accent-2-light: #fdf3e3;

--danger: #c0392b;
--danger-light: #fdecea;

--border: #e4e1da;
--border-soft: #eeebe4;
```

Never invent new hex colors for a new page. Every new component should compose from this palette. If a new semantic color is truly needed (e.g. a "success" green distinct from accent, for a savings-goal-met state), derive it in the same low-saturation, warm-neutral family as the palette above rather than reaching for a stock bright color.

### Typography

```css
--font-display: 'DM Serif Display', Georgia, serif;  /* headings, feature titles, legal h2 */
--font-body: 'DM Sans', system-ui, sans-serif;        /* body copy, buttons, forms */
/* 'Poppins' (weights 700/800) is used only for the hero title on the landing page — treat it as a one-off, not a general heading font */
```

Loaded via Google Fonts in `base.html`:
```html
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&family=Poppins:wght@700;800&display=swap" rel="stylesheet">
```

Typical sizes in the wild:
- Section/page headings: `var(--font-display)`, ~1.2–1.4rem for card/feature titles, larger (clamp-based) only for the landing hero.
- Body text: `var(--font-body)`, 0.9–0.95rem, `line-height: 1.7` for longer copy.
- Labels: 0.85rem, weight 500, `color: var(--ink-soft)`.

### Spacing & radius

```css
--radius-sm: 6px;   /* buttons, inputs, small controls */
--radius-md: 12px;  /* cards, panels */
--radius-lg: 20px;  /* large hero/mock elements */
```

Spacing is not on a strict 8px token system in the existing CSS (values like `0.65rem`, `1.25rem`, `2rem` appear directly), but they cluster on multiples of 4px. Keep new spacing choices inside that same rhythm (4/8/12/16/20/24/32px equivalents) rather than arbitrary values — it reads as the same system even without a formal `--space-*` scale.

`--max-width: 1200px` bounds page content; `--auth-width: 440px` bounds narrow single-column layouts like login/register.

### Core components (verbatim from static/css/style.css)

```css
.btn-primary {
    display: inline-block;
    background: var(--ink);
    color: var(--paper);
    padding: 0.65rem 1.5rem;
    border-radius: var(--radius-sm);
    font-family: var(--font-body);
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    border: none;
    transition: background 0.2s;
    text-decoration: none;
}
.btn-primary:hover { background: var(--accent); }

.btn-ghost {
    display: inline-block;
    background: transparent;
    color: var(--ink-soft);
    padding: 0.65rem 1.5rem;
    border-radius: var(--radius-sm);
    font-size: 0.9rem;
    font-weight: 500;
    border: 1px solid var(--border);
    transition: all 0.2s;
    text-decoration: none;
}
.btn-ghost:hover { border-color: var(--ink); color: var(--ink); }

.btn-submit {
    width: 100%;
    padding: 0.7rem;
    background: var(--ink);
    color: var(--paper);
    border: none;
    border-radius: var(--radius-sm);
    font-family: var(--font-body);
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s;
    margin-top: 0.5rem;
}
.btn-submit:hover { background: var(--accent); }
```

```css
/* Card patterns — all share the same border + radius-md + paper-card recipe */
.feature-card {
    background: var(--paper-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 2rem;
}
.auth-card {
    background: var(--paper-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 2rem;
    margin-bottom: 1.5rem;
}
.mock-stat {
    background: var(--paper-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    text-align: left;
}
.mock-progress {
    background: var(--paper-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
}
```

```css
.navbar {
    position: sticky;
    top: 0;
    z-index: 100;
    background: var(--paper);
    border-bottom: 1px solid var(--border);
    padding: 0 2rem;
}
.nav-inner {
    max-width: var(--max-width);
    margin: 0 auto;
    height: 60px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.nav-cta {
    background: var(--ink) !important;
    color: var(--paper) !important;
    padding: 0.45rem 1.1rem;
    border-radius: var(--radius-sm);
    transition: background 0.2s !important;
}
.nav-cta:hover { background: var(--accent) !important; }
```

```css
.form-group { margin-bottom: 1.25rem; }
.form-group label {
    display: block;
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--ink-soft);
    margin-bottom: 0.4rem;
}
.form-input {
    width: 100%;
    padding: 0.6rem 0.875rem;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    font-family: var(--font-body);
    font-size: 0.95rem;
    color: var(--ink);
    background: var(--paper);
    outline: none;
    transition: border-color 0.2s;
}
.form-input:focus { border-color: var(--accent); }
.form-input::placeholder { color: var(--ink-faint); }
```

Reuse `.btn-primary` / `.btn-ghost` / `.btn-submit`, `.feature-card`-style card recipes, and `.form-group` / `.form-input` wherever a new page needs a button, card, or form field, instead of inventing parallel classes that do the same thing with different names.

### Responsive breakpoints

The existing CSS breaks at 900px (tablet: stack multi-column grids to one column) and 600px (mobile: hide secondary nav links, stack hero actions, reduce padding). Follow the same two-breakpoint pattern rather than adding new ones:

```css
@media (max-width: 900px) { /* stack grids to 1fr, drop side-by-side layouts */ }
@media (max-width: 600px) { /* hide non-essential nav links, stack actions full-width, tighten padding */ }
```

### Icons — current state

There is **no icon library loaded**. Existing "icons" are single Unicode glyphs used inline as text: `◈` (brand mark, nav + footer), `₹` (currency), `◎` and `◷` (decorative feature markers). There's no `<i>` or `<svg>` icon pattern established yet. See "Decide the icon approach" under Process below for how to choose between extending this convention vs. introducing Lucide icons via CDN for a new page.

### Base layout (`templates/base.html`)

Every page extends this. Reuse its blocks; don't redefine nav/footer/font-loading in a new page's HTML.

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Spendly{% endblock %}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&family=Poppins:wght@700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    {% block head %}{% endblock %}
</head>
<body>
    <nav class="navbar">
        <div class="nav-inner">
            <a href="{{ url_for('landing') }}" class="nav-brand">
                <span class="brand-icon">◈</span>
                <span class="brand-name">Spendly</span>
            </a>
            <div class="nav-links">
                {% if session.get('user_id') %}
                <a href="{{ url_for('logout') }}">Sign out</a>
                {% else %}
                <a href="{{ url_for('login') }}">Sign in</a>
                <a href="{{ url_for('register') }}" class="nav-cta">Get started</a>
                {% endif %}
            </div>
        </div>
    </nav>

    {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
    <div class="flash-messages">
        {% for category, message in messages %}
        <div class="flash flash-{{ category }}">{{ message }}</div>
        {% endfor %}
    </div>
    {% endif %}
    {% endwith %}

    <main class="main-content">
        {% block content %}{% endblock %}
    </main>

    <footer class="footer">
        <div class="footer-inner">
            <span class="brand-icon">◈</span>
            <span class="footer-name">Spendly</span>
            <p class="footer-copy">Track every rupee. Own your finances.</p>
            <a href="{{ url_for('terms') }}">Terms and Conditions</a>
            <a href="{{ url_for('privacy') }}">Privacy Policy</a>
        </div>
    </footer>

    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
    {% block scripts %}{% endblock %}
</body>
</html>
```

Note the nav only has "Sign in" / "Get started" / "Sign out" — no signed-in nav links to a dashboard, profile, or expenses yet exist in the shipped nav. When designing a signed-in page, decide whether the page needs its own in-page navigation (tabs, a sidebar, breadcrumbs) since the global nav doesn't provide it, and say so explicitly in the UI structure summary.

### Known routes (from `app.py`)

Shipped and styled: `/` (landing), `/register`, `/login`, `/logout`, `/terms`, `/privacy`.

Placeholder / unimplemented (exactly the kind of page this skill is likely to be asked to design): `/profile`, `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete`. There's no dashboard/expense-list route yet either — if asked to design one, treat it as new but follow the same conventions.

### Locale

Currency is Indian Rupees, shown with the `₹` glyph (not `Rs.` or `INR`). Assume Indian number formatting (e.g. `₹12,450`) unless told otherwise.

## Process

1. **Read the design system snapshot above.** Note which existing components (cards, buttons, form inputs, nav) the new page can reuse outright, and which existing page it's closest to in spirit (a form page is closest to `login`/`register`'s `.auth-card` pattern; a data-heavy page is closest to the landing page's `.mock-stat`/`.mock-progress` cards).

2. **If the request is for something with no real precedent in the snapshot** — a genuinely novel UI pattern the existing pages don't hint at (e.g. a chart, a multi-step wizard, a data table with sort/filter) — say so and ask the user for a screenshot or reference of what they have in mind, rather than inventing a pattern wholesale and hoping it matches their taste. For anything that's a natural extension of existing patterns (another form, another card grid, another auth-style page), proceed without asking.

3. **Decide the icon approach.** There's no icon library loaded yet — existing icons are single Unicode glyphs used as text (see above). For a new page:
   - If the page sits visually next to existing Unicode-icon UI, or the icon need is simple (a currency mark, a directional arrow, a status dot), stay consistent and use a Unicode glyph or a tiny inline SVG rather than pulling in a dependency for one icon.
   - If the page needs a fuller icon set (multiple distinct actions/categories — e.g. category icons for food/transport/shopping on an add-expense form, or nav icons on a dashboard), it's reasonable to introduce Lucide icons via CDN, since there's no build step to fight. Include the loader script and init call in the snippet:
     ```html
     <script src="https://unpkg.com/lucide@latest"></script>
     <script>lucide.createIcons();</script>
     ```
     and use `<i data-lucide="icon-name"></i>` tags. Mention in the output that this is a new dependency (one `<script>` tag) so the user can decide whether to add it to `base.html` globally or scope it to this page's `{% block scripts %}`.
   - When genuinely unsure which way to go, pick the option that keeps the page visually closer to whatever page it's adjacent to (e.g. an edit-expense page next to a plain add-expense page should probably match that page's choice), and note the reasoning briefly rather than silently picking one.

4. **Design before coding.** Sketch the structure in words first — this is part of the deliverable, not throat-clearing (see Output format).

5. **Write the code.** Jinja2 HTML that assumes `{% extends "base.html" %}` and fills `{% block content %}` (plus `{% block head %}` / `{% block scripts %}` if needed), and CSS written against the existing custom properties (`var(--accent)`, `var(--radius-md)`, etc.) rather than hardcoded values. Reuse existing classes (`.btn-primary`, `.form-input`, `.feature-card`-style cards) where they fit; only define new classes for genuinely new patterns, and make new CSS additive (safe to append to `static/css/style.css`) rather than redefining shared selectors.

## Output format

Always deliver, in this order:

1. **UI structure** — a short brief (a few sentences to a short paragraph, not an essay): the layout and key sections, and the 2-4 UX decisions that mattered most (e.g. "put the amount field first since that's what users fill in fastest," "grouped date + category on one row since both are quick single-taps," "used a ghost-style cancel button next to the primary submit, matching the auth pages"). This is what lets the user sanity-check the thinking without reading the code.
2. **HTML** — a Jinja2 template snippet, fenced as a code block, ready to drop into a new or existing file under `templates/`.
3. **CSS** — a fenced code block of any *new* rules needed (assume existing shared rules like `.form-input` already exist and don't repeat them), written for appending to `static/css/style.css`.

This skill hands back snippets for the user to place themselves — it does not edit the project's files directly. Say clearly which file each block is meant for (e.g. "add this to `templates/expenses_add.html`" / "append this to `static/css/style.css`").

## Design rules

- Card-based layout, `var(--radius-md)` on cards/panels, `var(--radius-sm)` on buttons and inputs — never a bare `border-radius: 0` or an arbitrary radius value.
- Soft shadows are rare in the existing CSS (it mostly relies on the `var(--border)` hairline instead of shadow for separation) — if you add a shadow, keep it subtle (low opacity, small blur) rather than a heavy drop shadow; a 1px border in `var(--border)` is usually enough and more consistent with what's there.
- Spacing in the same rhythm as the rest of the app (see snapshot above) — consistent padding/gaps, no cramped or randomly-sized elements.
- Two responsive breakpoints, 900px and 600px, matching the existing pattern — not a new breakpoint scheme.
- Every color, font, and radius should trace back to a CSS custom property in the snapshot above. If a value doesn't have a variable yet and is clearly reusable (not a one-off), propose adding it as a new custom property in `:root` rather than hardcoding it inline.

## Avoid

- Introducing React, Vue, Tailwind, or any build tooling — this is a plain Flask/Jinja/CSS/vanilla-JS project and should stay that way.
- Generic "AI-generated SaaS" UI that could belong to any product — gradient hero blobs, glassmorphism, stock illustration style, or a color palette that doesn't come from the snapshot above.
- Dumping a wall of code with no structure summary — the UI structure brief comes first, always.
- Reinventing a component that already exists (a new button class that's really just `.btn-primary` again, a new card style identical to `.feature-card`).