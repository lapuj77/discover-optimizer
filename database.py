import sqlite3
from contextlib import contextmanager

import os

DB_PATH = os.getenv("DB_PATH", "discover.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guid TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    link TEXT NOT NULL,
    author TEXT,
    published_at TEXT,
    categories TEXT,
    description TEXT,
    full_content TEXT,
    og_image TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES articles(id),
    score_before INTEGER,
    score_after INTEGER,
    report_html TEXT NOT NULL,
    report_json TEXT NOT NULL,
    discord_sent INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
