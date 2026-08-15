import sqlite3
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import (
    init_db,
    seed_db,
    get_db,
    get_user_by_email,
    get_user_by_id,
    get_recent_transactions,
    get_summary_stats,
    get_category_breakdown,
)

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"

with app.app_context():
    init_db()
    seed_db()


@app.context_processor
def inject_current_user():
    user_id = session.get("user_id")
    return {"current_user": get_user_by_id(user_id) if user_id else None}


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name:
        error = "Name is required."
    elif not email or "@" not in email:
        error = "Please enter a valid email address."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    elif password != confirm_password:
        error = "Passwords do not match."
    else:
        error = None

    if error:
        return render_template("register.html", error=error, name=name, email=email)

    password_hash = generate_password_hash(password)
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
    except sqlite3.IntegrityError:
        conn.close()
        return render_template(
            "register.html", error="Email already registered", name=name, email=email
        )

    conn.commit()
    conn.close()

    flash("Registration successful! Please sign in.", "success")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    user = get_user_by_email(email)

    if user is None or not check_password_hash(user["password_hash"], password):
        flash("Invalid email or password.", "error")
        return redirect(url_for("login"))

    session["user_id"] = user["id"]
    flash("Logged in successfully!", "success")
    return redirect(url_for("profile"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    db_user = get_user_by_id(user_id)

    name = db_user["name"] if db_user else ""
    initials = "".join(w[0] for w in name.split()[:2]).upper() if name else ""

    member_since = ""
    if db_user and db_user["created_at"]:
        created_dt = datetime.strptime(db_user["created_at"][:19], "%Y-%m-%d %H:%M:%S")
        member_since = created_dt.strftime("%B %Y")

    user = {
        "name": name,
        "email": db_user["email"] if db_user else "",
        "initials": initials,
        "member_since": member_since,
    }

    raw_start = request.args.get("start_date", "").strip()
    raw_end = request.args.get("end_date", "").strip()

    filter_error = None
    if raw_start and raw_end and raw_start > raw_end:
        filter_error = "Start date must be before end date."
        start_date = ""
        end_date = ""
    else:
        start_date = raw_start
        end_date = raw_end

    date_filter = {
        "start_date": start_date,
        "end_date": end_date,
        "error": filter_error,
        "is_active": bool(start_date or end_date),
    }

    summary_stats = _build_summary_stats(user_id, start_date=start_date, end_date=end_date)
    transactions = _build_transactions(user_id, start_date=start_date, end_date=end_date)
    category_breakdown = _build_category_breakdown(user_id, start_date=start_date, end_date=end_date)

    return render_template(
        "profile.html",
        user=user,
        summary_stats=summary_stats,
        transactions=transactions,
        category_breakdown=category_breakdown,
        date_filter=date_filter,
    )


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


# ------------------------------------------------------------------ #
# Profile view helpers                                                #
# ------------------------------------------------------------------ #

def _build_transactions(user_id, start_date="", end_date=""):
    rows = get_recent_transactions(
        user_id,
        limit=5,
        start_date=start_date or None,
        end_date=end_date or None,
    )
    transactions = []
    for row in rows:
        date_obj = datetime.strptime(row["date"], "%Y-%m-%d")
        transactions.append({
            "date": date_obj.strftime("%b %d, %Y"),
            "description": row["description"] or "",
            "category": row["category"],
            "amount": f"₹{row['amount']:,.2f}",
        })
    return transactions


def _build_summary_stats(user_id, start_date="", end_date=""):
    stats = get_summary_stats(user_id, start_date=start_date or None, end_date=end_date or None)

    count = stats["count"]
    total_value = f"₹{stats['total']:,.0f}"
    if count:
        total_delta = f"Across {count} transaction{'s' if count != 1 else ''}"
    else:
        total_delta = "No transactions in this range" if (start_date or end_date) else "No transactions yet"

    transactions_value = str(count)
    transactions_delta = f"{stats['count_last_7_days']} this week"

    if stats["top_category_name"]:
        top_category_value = stats["top_category_name"]
        top_category_delta = f"₹{stats['top_category_total']:,.0f} spent"
    else:
        top_category_value = "—"
        top_category_delta = "No spending yet"

    return [
        {"label": "Total Spent", "value": total_value, "delta": total_delta, "delta_class": "mock-stat-delta-neutral"},
        {"label": "Transactions", "value": transactions_value, "delta": transactions_delta, "delta_class": "mock-stat-delta-neutral"},
        {"label": "Top Category", "value": top_category_value, "delta": top_category_delta, "delta_class": "mock-stat-delta-neutral"},
    ]


def _build_category_breakdown(user_id, start_date="", end_date=""):
    rows = get_category_breakdown(user_id, start_date=start_date or None, end_date=end_date or None)
    total = sum(row["total"] for row in rows)

    breakdown = []
    for row in rows:
        amount = row["total"]
        percent = (amount / total * 100) if total > 0 else 0

        rounded_percent = int(round(percent / 10.0) * 10)
        if amount > 0:
            rounded_percent = max(rounded_percent, 10)
        rounded_percent = min(rounded_percent, 100)

        breakdown.append({
            "name": row["category"],
            "amount": f"₹{amount:,.0f}",
            "percent": round(percent),
            "css_class": f"category-{row['category'].lower()}",
            "width_class": f"bar-w-{rounded_percent}",
        })

    return breakdown


if __name__ == "__main__":
    app.run(debug=True, port=5001)
