import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from backend.catalog import seed_catalog

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, consent_at TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id),
 guest_name TEXT NOT NULL DEFAULT '', interests TEXT NOT NULL DEFAULT '[]',
 csrf TEXT NOT NULL, expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bookmarks (
 owner TEXT NOT NULL, document_id TEXT NOT NULL REFERENCES documents(id),
 kind TEXT NOT NULL CHECK(kind IN ('saved','followed')), created_at TEXT NOT NULL,
 PRIMARY KEY(owner,document_id,kind)
);
CREATE TABLE IF NOT EXISTS votes (
 user_id INTEGER REFERENCES users(id), document_id TEXT REFERENCES documents(id),
 choice TEXT NOT NULL CHECK(choice IN ('agree','neutral','disagree')), updated_at TEXT NOT NULL,
 PRIMARY KEY(user_id,document_id)
);
CREATE TABLE IF NOT EXISTS comments (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 document_id TEXT NOT NULL REFERENCES documents(id), body TEXT NOT NULL,
 created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS feedback (
 owner TEXT NOT NULL, document_id TEXT NOT NULL REFERENCES documents(id), helpful INTEGER NOT NULL,
 PRIMARY KEY(owner,document_id)
);
'''


@contextmanager
def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.executescript(SCHEMA)
        for item in seed_catalog():
            db.execute('INSERT OR IGNORE INTO documents VALUES (?,?)', (item['id'], json.dumps(item, ensure_ascii=False)))


def catalog(db):
    return [json.loads(row['payload']) for row in db.execute('SELECT payload FROM documents')]
