import os
import sqlite3
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "expense_tracker.db")

CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_user_by_email(email):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    return user


def get_user_by_id(user_id):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return user


# ------------------------------------------------------------------ #
# Profile: recent transactions (Subagent 1)                          #
# ------------------------------------------------------------------ #
def get_recent_transactions(user_id, limit=5):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, amount, category, date, description
        FROM expenses
        WHERE user_id = ?
        ORDER BY date DESC, id DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    conn.close()
    return rows


# ------------------------------------------------------------------ #
# Profile: monthly summary stats (Subagent 2)                        #
# ------------------------------------------------------------------ #
def get_monthly_summary(user_id):
    conn = get_db()

    now = datetime.now()
    current_month = now.strftime("%Y-%m")
    first_of_this_month = now.replace(day=1)
    last_day_prev_month = first_of_this_month - timedelta(days=1)
    previous_month = last_day_prev_month.strftime("%Y-%m")

    row = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count
        FROM expenses
        WHERE user_id = ? AND strftime('%Y-%m', date) = ?
        """,
        (user_id, current_month),
    ).fetchone()
    total_this_month = row["total"]

    total_count_row = conn.execute(
        "SELECT COUNT(*) AS count FROM expenses WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    total_count = total_count_row["count"]

    top_row = conn.execute(
        """
        SELECT category, COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = ? AND strftime('%Y-%m', date) = ?
        GROUP BY category
        ORDER BY total DESC, category ASC
        LIMIT 1
        """,
        (user_id, current_month),
    ).fetchone()
    top_category_name = top_row["category"] if top_row else None
    top_category_total = top_row["total"] if top_row else 0

    prev_row = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = ? AND strftime('%Y-%m', date) = ?
        """,
        (user_id, previous_month),
    ).fetchone()
    total_prev_month = prev_row["total"]

    seven_days_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    today_str = now.strftime("%Y-%m-%d")
    week_row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM expenses
        WHERE user_id = ? AND date >= ? AND date <= ?
        """,
        (user_id, seven_days_ago, today_str),
    ).fetchone()
    count_last_7_days = week_row["count"]

    conn.close()

    if total_prev_month > 0:
        percent_change = ((total_this_month - total_prev_month) / total_prev_month) * 100
    else:
        percent_change = None  # no prior-month data to compare against

    return {
        "total_this_month": total_this_month,
        "total_count": total_count,
        "top_category_name": top_category_name,
        "top_category_total": top_category_total,
        "count_last_7_days": count_last_7_days,
        "percent_change": percent_change,
    }


# ------------------------------------------------------------------ #
# Profile: category breakdown (Subagent 3)                           #
# ------------------------------------------------------------------ #
def get_category_breakdown(user_id):
    conn = get_db()
    now = datetime.now()
    current_month = now.strftime("%Y-%m")

    rows = conn.execute(
        """
        SELECT category, COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = ? AND strftime('%Y-%m', date) = ?
        GROUP BY category
        ORDER BY total DESC, category ASC
        """,
        (user_id, current_month),
    ).fetchall()
    conn.close()
    return rows


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
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
        """
    )
    conn.commit()
    conn.close()


def seed_db():
    conn = get_db()

    existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing > 0:
        conn.close()
        return

    password_hash = generate_password_hash("demo123")
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", password_hash),
    )
    user_id = cursor.lastrowid

    today = datetime.now()
    sample_expenses = [
        (user_id, 42.50, "Food", (today.replace(day=1)).strftime("%Y-%m-%d"), "Groceries"),
        (user_id, 15.00, "Transport", (today.replace(day=1) + timedelta(days=2)).strftime("%Y-%m-%d"), "Bus pass"),
        (user_id, 89.99, "Bills", (today.replace(day=1) + timedelta(days=4)).strftime("%Y-%m-%d"), "Electricity bill"),
        (user_id, 25.00, "Health", (today.replace(day=1) + timedelta(days=6)).strftime("%Y-%m-%d"), "Pharmacy"),
        (user_id, 60.00, "Entertainment", (today.replace(day=1) + timedelta(days=9)).strftime("%Y-%m-%d"), "Movie night"),
        (user_id, 120.75, "Shopping", (today.replace(day=1) + timedelta(days=12)).strftime("%Y-%m-%d"), "New shoes"),
        (user_id, 10.00, "Other", (today.replace(day=1) + timedelta(days=15)).strftime("%Y-%m-%d"), "Miscellaneous"),
        (user_id, 33.20, "Food", (today.replace(day=1) + timedelta(days=18)).strftime("%Y-%m-%d"), "Restaurant"),
    ]

    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        sample_expenses,
    )

    conn.commit()
    conn.close()
