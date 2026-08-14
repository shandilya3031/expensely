import sqlite3

from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import init_db, seed_db, get_db, get_user_by_email

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"

with app.app_context():
    init_db()
    seed_db()


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

    user = {
        "name": "Demo User",
        "email": "demo@spendly.com",
        "initials": "DU",
        "member_since": "January 2025",
    }

    summary_stats = [
        {"label": "Total Spent", "value": "₹42,180", "delta": "+8% vs last month", "delta_class": "mock-stat-delta-up"},
        {"label": "Transactions", "value": "37", "delta": "5 this week", "delta_class": "mock-stat-delta-neutral"},
        {"label": "Top Category", "value": "Food", "delta": "₹14,320 spent", "delta_class": "mock-stat-delta-neutral"},
    ]

    transactions = [
        {"date": "Aug 12, 2026", "description": "Grocery run — BigBasket", "category": "Food", "amount": "₹1,240.00"},
        {"date": "Aug 10, 2026", "description": "Uber to airport", "category": "Transport", "amount": "₹680.00"},
        {"date": "Aug 08, 2026", "description": "Electricity bill", "category": "Bills", "amount": "₹2,150.00"},
        {"date": "Aug 05, 2026", "description": "Pharmacy — vitamins", "category": "Health", "amount": "₹540.00"},
        {"date": "Aug 02, 2026", "description": "Movie night", "category": "Entertainment", "amount": "₹850.00"},
    ]

    category_breakdown = [
        {"name": "Food", "amount": "₹14,320", "percent": 34, "css_class": "category-food", "width_class": "bar-w-30"},
        {"name": "Bills", "amount": "₹9,650", "percent": 23, "css_class": "category-bills", "width_class": "bar-w-20"},
        {"name": "Transport", "amount": "₹6,200", "percent": 15, "css_class": "category-transport", "width_class": "bar-w-20"},
        {"name": "Entertainment", "amount": "₹4,980", "percent": 12, "css_class": "category-entertainment", "width_class": "bar-w-10"},
        {"name": "Health", "amount": "₹3,510", "percent": 8, "css_class": "category-health", "width_class": "bar-w-10"},
        {"name": "Shopping", "amount": "₹2,400", "percent": 6, "css_class": "category-shopping", "width_class": "bar-w-10"},
        {"name": "Other", "amount": "₹1,120", "percent": 2, "css_class": "category-other", "width_class": "bar-w-10"},
    ]

    return render_template(
        "profile.html",
        user=user,
        summary_stats=summary_stats,
        transactions=transactions,
        category_breakdown=category_breakdown,
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


if __name__ == "__main__":
    app.run(debug=True, port=5001)
