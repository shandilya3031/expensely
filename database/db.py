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
