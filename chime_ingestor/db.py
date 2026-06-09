"""SQLite database operations for transaction storage."""
import hashlib
import sqlite3
from pathlib import Path
from typing import Optional

from chime_ingestor.models import ChimeTransaction


SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    description     TEXT NOT NULL,
    amount          REAL NOT NULL,
    balance         REAL,
    fee             REAL DEFAULT 0.0,
    tx_type         TEXT,
    account_type    TEXT,
    source_institution TEXT NOT NULL,
    source_file     TEXT NOT NULL,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_file, date, description, amount)
);

CREATE TABLE IF NOT EXISTS ingestion_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file     TEXT NOT NULL,
    source_hash     TEXT NOT NULL,
    record_count    INTEGER,
    status          TEXT,
    ingested_at     TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Get a SQLite connection with proper settings."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """Create database schema if it doesn't exist."""
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_transactions(conn: sqlite3.Connection, transactions: list[ChimeTransaction]) -> int:
    """Insert transactions, ignoring duplicates based on unique constraint.

    Uses INSERT OR IGNORE to preserve existing records.
    Never uses INSERT OR REPLACE (would change row id).

    Returns:
        Number of transactions actually inserted
    """
    if not transactions:
        return 0

    cursor = conn.cursor()
    inserted = 0

    for tx in transactions:
        cursor.execute(
            """
            INSERT OR IGNORE INTO transactions
            (date, description, amount, balance, fee, tx_type, account_type, source_institution, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tx.transaction_date.isoformat(),
                tx.description,
                float(tx.amount),
                float(tx.balance) if tx.balance else None,
                0.0,  # fee not yet implemented in model
                tx.transaction_type,
                tx.account_type,
                tx.source_institution,
                tx.source_file,
            ),
        )
        if cursor.rowcount > 0:
            inserted += 1

    conn.commit()
    return inserted


def log_ingestion(
    conn: sqlite3.Connection,
    source_file: str,
    source_hash: str,
    count: int,
    status: str,
) -> None:
    """Log an ingestion attempt."""
    conn.execute(
        """
        INSERT INTO ingestion_log (source_file, source_hash, record_count, status)
        VALUES (?, ?, ?, ?)
        """,
        (source_file, source_hash, count, status),
    )
    conn.commit()


def is_already_ingested(conn: sqlite3.Connection, source_hash: str) -> bool:
    """Check if a file has already been ingested by its hash."""
    cursor = conn.execute(
        "SELECT 1 FROM ingestion_log WHERE source_hash = ? LIMIT 1",
        (source_hash,),
    )
    return cursor.fetchone() is not None


def compute_file_hash(path: Path) -> str:
    """Compute SHA256 hash of file contents."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
