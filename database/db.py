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
def get_recent_transactions(user_id, limit=5, start_date=None, end_date=None):
    conn = get_db()

    query = """
        SELECT id, amount, category, date, description
        FROM expenses
        WHERE user_id = ?
    """
    params = [user_id]

    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
        limit = None
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
        limit = None

    query += " ORDER BY date DESC, id DESC"

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


# ------------------------------------------------------------------ #
# Profile: summary stats (Subagent 2)                                 #
# ------------------------------------------------------------------ #
def get_summary_stats(user_id, start_date=None, end_date=None):
    conn = get_db()

    total_query = "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count FROM expenses WHERE user_id = ?"
    total_params = [user_id]
    if start_date:
        total_query += " AND date >= ?"
        total_params.append(start_date)
    if end_date:
        total_query += " AND date <= ?"
        total_params.append(end_date)
    row = conn.execute(total_query, total_params).fetchone()
    total = row["total"]
    count = row["count"]

    top_query = "SELECT category, COALESCE(SUM(amount), 0) AS total FROM expenses WHERE user_id = ?"
    top_params = [user_id]
    if start_date:
        top_query += " AND date >= ?"
        top_params.append(start_date)
    if end_date:
        top_query += " AND date <= ?"
        top_params.append(end_date)
    top_query += " GROUP BY category ORDER BY total DESC, category ASC LIMIT 1"
    top_row = conn.execute(top_query, top_params).fetchone()
    top_category_name = top_row["category"] if top_row else None
    top_category_total = top_row["total"] if top_row else 0

    now = datetime.now()
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

    return {
        "total": total,
        "count": count,
        "top_category_name": top_category_name,
        "top_category_total": top_category_total,
        "count_last_7_days": count_last_7_days,
    }


# ------------------------------------------------------------------ #
# Profile: category breakdown (Subagent 3)                           #
# ------------------------------------------------------------------ #
def get_category_breakdown(user_id, start_date=None, end_date=None):
    conn = get_db()

    query = "SELECT category, COALESCE(SUM(amount), 0) AS total FROM expenses WHERE user_id = ?"
    params = [user_id]
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    query += " GROUP BY category ORDER BY total DESC, category ASC"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


# ------------------------------------------------------------------ #
# Expenses: create (Step 7)                                          #
# ------------------------------------------------------------------ #
def create_expense(user_id, amount, category, date, description):
    conn = get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, date, description),
    )
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ #
# Expenses: edit (Step 8)                                            #
# ------------------------------------------------------------------ #
def get_expense_by_id(expense_id, user_id):
    conn = get_db()
    expense = conn.execute(
        "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
        (expense_id, user_id),
    ).fetchone()
    conn.close()
    return expense


def update_expense(expense_id, user_id, amount, category, date, description):
    conn = get_db()
    conn.execute(
        """
        UPDATE expenses
        SET amount = ?, category = ?, date = ?, description = ?
        WHERE id = ? AND user_id = ?
        """,
        (amount, category, date, description, expense_id, user_id),
    )
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ #
# Expenses: delete (Step 9)                                          #
# ------------------------------------------------------------------ #
def delete_expense(expense_id, user_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM expenses WHERE id = ? AND user_id = ?",
        (expense_id, user_id),
    )
    conn.commit()
    conn.close()


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
