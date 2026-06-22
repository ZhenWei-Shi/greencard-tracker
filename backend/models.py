import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "greencard.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS visa_bulletin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            chart_type TEXT NOT NULL CHECK(chart_type IN ('A', 'B')),
            category TEXT NOT NULL,
            country TEXT NOT NULL,
            cutoff_date TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(year, month, chart_type, category, country)
        );

        CREATE TABLE IF NOT EXISTS user_profile (
            id INTEGER PRIMARY KEY DEFAULT 1,
            category TEXT,
            country TEXT,
            priority_date TEXT,
            email TEXT,
            alert_days INTEGER DEFAULT 90
        );

        INSERT OR IGNORE INTO user_profile (id) VALUES (1);
    """)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"数据库初始化完成: {DB_PATH}")
