"""SQLite storage.

Tenant isolation rule: every function that reads or writes client data takes
a client_id and filters on it. There is no "get report by id" without the
client - a report id from another client simply isn't found.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

POST_COLUMNS = [
    "post_id", "date", "platform", "format", "topic",
    "impressions", "reach", "likes", "comments", "shares", "saves", "link_clicks",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT
);

CREATE TABLE IF NOT EXISTS posts (
    client_id   TEXT NOT NULL REFERENCES clients(id),
    post_id     TEXT NOT NULL,
    date        TEXT NOT NULL,
    platform    TEXT NOT NULL,
    format      TEXT NOT NULL,
    topic       TEXT NOT NULL,
    impressions INTEGER NOT NULL,
    reach       INTEGER NOT NULL,
    likes       INTEGER NOT NULL,
    comments    INTEGER NOT NULL,
    shares      INTEGER NOT NULL,
    saves       INTEGER NOT NULL,
    link_clicks INTEGER NOT NULL,
    PRIMARY KEY (client_id, post_id)
);

CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id   TEXT NOT NULL REFERENCES clients(id),
    period      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft',   -- draft | approved | rejected
    payload     TEXT NOT NULL,                    -- report JSON
    created_at  TEXT NOT NULL,
    reviewer    TEXT,
    reviewed_at TEXT,
    review_note TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL,
    report_id INTEGER,
    action    TEXT NOT NULL,
    actor     TEXT,
    note      TEXT,
    at        TEXT NOT NULL
);
"""


def db_path():
    # read at call time so tests can point it at a temp file
    return os.environ.get("DB_PATH", str(ROOT / "app.db"))


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)


def reset_demo():
    """Wipe everything and load the bundled synthetic data again."""
    with connect() as conn:
        conn.executescript(
            "DROP TABLE IF EXISTS audit_log; DROP TABLE IF EXISTS reports;"
            "DROP TABLE IF EXISTS posts; DROP TABLE IF EXISTS clients;"
        )
    init_db()
    seed_from_files()


def seed_from_files():
    import csv

    clients = json.loads((DATA_DIR / "clients.json").read_text(encoding="utf-8"))
    with connect() as conn:
        for c in clients:
            conn.execute(
                "INSERT OR IGNORE INTO clients (id, name, city) VALUES (?, ?, ?)",
                (c["id"], c["name"], c["city"]),
            )
    for c in clients:
        with (DATA_DIR / f"{c['id']}.csv").open(encoding="utf-8") as f:
            upsert_posts(c["id"], list(csv.DictReader(f)))


def is_empty():
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 0


# ---- clients -------------------------------------------------------------

def list_clients():
    with connect() as conn:
        rows = conn.execute(
            """SELECT c.id, c.name, c.city, COUNT(p.post_id) AS post_count,
                      MIN(p.date) AS first_date, MAX(p.date) AS last_date
               FROM clients c LEFT JOIN posts p ON p.client_id = c.id
               GROUP BY c.id ORDER BY c.name"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_client(client_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    return dict(row) if row else None


# ---- posts ---------------------------------------------------------------

def upsert_posts(client_id, rows):
    """rows are already-validated dicts. client_id comes from the URL, never the file."""
    with connect() as conn:
        conn.executemany(
            f"""INSERT OR REPLACE INTO posts (client_id, {", ".join(POST_COLUMNS)})
                VALUES (?, {", ".join("?" for _ in POST_COLUMNS)})""",
            [(client_id, *[r[c] for c in POST_COLUMNS]) for r in rows],
        )
    return len(rows)


def get_posts(client_id):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM posts WHERE client_id = ? ORDER BY date, post_id", (client_id,)
        ).fetchall()
    return [dict(r) for r in rows]


# ---- reports -------------------------------------------------------------

def create_report(client_id, period, payload):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO reports (client_id, period, payload, created_at) VALUES (?, ?, ?, ?)",
            (client_id, period, json.dumps(payload), now()),
        )
        return cur.lastrowid


def _report_from_row(row):
    report = dict(row)
    report["payload"] = json.loads(report["payload"])
    return report


def get_report(client_id, report_id):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM reports WHERE id = ? AND client_id = ?", (report_id, client_id)
        ).fetchone()
    return _report_from_row(row) if row else None


def list_reports(client_id):
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, client_id, period, status, created_at, reviewer, reviewed_at
               FROM reports WHERE client_id = ? ORDER BY id DESC""",
            (client_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def set_report_status(client_id, report_id, status, reviewer, note, payload=None):
    with connect() as conn:
        if payload is not None:
            conn.execute(
                "UPDATE reports SET payload = ? WHERE id = ? AND client_id = ?",
                (json.dumps(payload), report_id, client_id),
            )
        conn.execute(
            """UPDATE reports SET status = ?, reviewer = ?, reviewed_at = ?, review_note = ?
               WHERE id = ? AND client_id = ?""",
            (status, reviewer, now(), note, report_id, client_id),
        )


# ---- audit ---------------------------------------------------------------

def log(client_id, action, report_id=None, actor="system", note=None):
    with connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (client_id, report_id, action, actor, note, at) VALUES (?, ?, ?, ?, ?, ?)",
            (client_id, report_id, action, actor, note, now()),
        )


def get_audit(client_id, report_id=None):
    sql = "SELECT * FROM audit_log WHERE client_id = ?"
    args = [client_id]
    if report_id is not None:
        sql += " AND report_id = ?"
        args.append(report_id)
    with connect() as conn:
        rows = conn.execute(sql + " ORDER BY id", args).fetchall()
    return [dict(r) for r in rows]
