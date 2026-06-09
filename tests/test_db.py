"""Tests for database operations."""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from chime_ingestor.db import (
    create_schema,
    get_connection,
    is_already_ingested,
    log_ingestion,
    upsert_transactions,
)
from chime_ingestor.models import ChimeTransaction


@pytest.fixture
def db_conn():
    """In-memory database connection for tests."""
    conn = get_connection(Path(":memory:"))
    create_schema(conn)
    yield conn
    conn.close()


class TestSchemaCreation:
    """Tests for database schema."""

    def test_schema_creates_transactions_table(self, db_conn) -> None:
        """Schema creates transactions table."""
        cursor = db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'"
        )
        assert cursor.fetchone() is not None

    def test_schema_creates_ingestion_log_table(self, db_conn) -> None:
        """Schema creates ingestion_log table."""
        cursor = db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ingestion_log'"
        )
        assert cursor.fetchone() is not None


class TestUpsertTransactions:
    """Tests for transaction upserts."""

    def test_upsert_inserts_new_transaction(self, db_conn) -> None:
        """New transaction → inserted, count +1."""
        tx = ChimeTransaction(
            transaction_date=date(2025, 1, 15),
            description="Test Transaction",
            transaction_type="Purchase",
            amount=Decimal("-50.00"),
            settlement_date=date(2025, 1, 15),
            source_file="test.pdf",
            account_type="Checking",
            source_institution="chime",
        )

        inserted = upsert_transactions(db_conn, [tx])
        assert inserted == 1

        # Verify it exists
        cursor = db_conn.execute("SELECT COUNT(*) FROM transactions")
        assert cursor.fetchone()[0] == 1

    def test_upsert_deduplicates(self, db_conn) -> None:
        """Same transaction twice → only 1 row."""
        tx = ChimeTransaction(
            transaction_date=date(2025, 1, 15),
            description="Duplicate Test",
            transaction_type="Purchase",
            amount=Decimal("-50.00"),
            settlement_date=date(2025, 1, 15),
            source_file="test.pdf",
            account_type="Checking",
            source_institution="chime",
        )

        # Insert twice
        upsert_transactions(db_conn, [tx])
        inserted = upsert_transactions(db_conn, [tx])

        # Second insert should be ignored
        assert inserted == 0

        # Verify only 1 row exists
        cursor = db_conn.execute("SELECT COUNT(*) FROM transactions")
        assert cursor.fetchone()[0] == 1

    def test_upsert_multiple_transactions(self, db_conn) -> None:
        """Insert multiple transactions at once."""
        txs = [
            ChimeTransaction(
                transaction_date=date(2025, 1, 15),
                description="Transaction 1",
                transaction_type="Purchase",
                amount=Decimal("-50.00"),
                settlement_date=date(2025, 1, 15),
                source_file="test.pdf",
                account_type="Checking",
                source_institution="chime",
            ),
            ChimeTransaction(
                transaction_date=date(2025, 1, 16),
                description="Transaction 2",
                transaction_type="Purchase",
                amount=Decimal("-25.00"),
                settlement_date=date(2025, 1, 16),
                source_file="test.pdf",
                account_type="Checking",
                source_institution="chime",
            ),
        ]

        inserted = upsert_transactions(db_conn, txs)
        assert inserted == 2


class TestIngestionLog:
    """Tests for ingestion log."""

    def test_log_written(self, db_conn) -> None:
        """After upsert → log row exists with correct count."""
        log_ingestion(db_conn, "test.pdf", "abc123", 5, "success")

        cursor = db_conn.execute(
            "SELECT source_file, source_hash, record_count, status FROM ingestion_log"
        )
        row = cursor.fetchone()

        assert row["source_file"] == "test.pdf"
        assert row["source_hash"] == "abc123"
        assert row["record_count"] == 5
        assert row["status"] == "success"

    def test_already_ingested_true(self, db_conn) -> None:
        """File hash in log → True."""
        log_ingestion(db_conn, "test.pdf", "hash123", 5, "success")
        assert is_already_ingested(db_conn, "hash123") is True

    def test_already_ingested_false(self, db_conn) -> None:
        """Unknown hash → False."""
        assert is_already_ingested(db_conn, "unknown_hash") is False

    def test_different_hashes_distinct(self, db_conn) -> None:
        """Different files with different hashes both tracked."""
        log_ingestion(db_conn, "file1.pdf", "hash1", 5, "success")
        log_ingestion(db_conn, "file2.pdf", "hash2", 10, "success")

        assert is_already_ingested(db_conn, "hash1") is True
        assert is_already_ingested(db_conn, "hash2") is True
        assert is_already_ingested(db_conn, "hash3") is False
