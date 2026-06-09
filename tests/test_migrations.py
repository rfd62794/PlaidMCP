"""Tests for database migrations."""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import tempfile

from chime_ingestor.db import create_schema, get_connection
from chime_ingestor.migrations import migrate_credit_polarity


class TestMigrateCreditPolarity:
    """Tests for migrate_credit_polarity function."""

    def _create_credit_transaction(self, conn, description, amount, tx_type, date_str="2024-03-15"):
        """Helper to insert a credit transaction."""
        conn.execute(
            """INSERT INTO transactions
               (date, description, amount, balance, fee, tx_type, account_type, source_institution, source_file)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (date_str, description, float(amount), None, 0.0, tx_type, "Credit", "chime", "test.pdf")
        )

    def test_migration_inverts_purchases(self):
        """Positive Credit purchase → negative."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        # Create a Credit purchase with positive amount (wrong polarity)
        self._create_credit_transaction(conn, "McDonald's", Decimal("29.04"), "Purchase")
        conn.commit()

        # Verify initial state
        cursor = conn.execute("SELECT amount FROM transactions WHERE tx_type = 'Purchase'")
        assert cursor.fetchone()["amount"] == 29.04

        conn.close()

        # Run migration
        result = migrate_credit_polarity(db_path)

        # Verify updated
        assert result["outflow_corrected"] == 1

        conn = get_connection(db_path)
        cursor = conn.execute("SELECT amount FROM transactions WHERE tx_type = 'Purchase'")
        assert cursor.fetchone()["amount"] == -29.04
        conn.close()

        db_path.unlink()

    def test_migration_inverts_payments(self):
        """Negative Credit payment → positive."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        # Create a Credit payment with negative amount (wrong polarity)
        self._create_credit_transaction(conn, "Card Payment", Decimal("-2990.74"), "Payment")
        conn.commit()
        conn.close()

        # Run migration
        result = migrate_credit_polarity(db_path)

        assert result["inflow_corrected"] == 1

        conn = get_connection(db_path)
        cursor = conn.execute("SELECT amount FROM transactions WHERE tx_type = 'Payment'")
        assert cursor.fetchone()["amount"] == 2990.74
        conn.close()

        db_path.unlink()

    def test_migration_safe_rerun(self):
        """Second run changes 0 rows."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)
        self._create_credit_transaction(conn, "Purchase", Decimal("29.04"), "Purchase")
        conn.commit()
        conn.close()

        # First run
        result1 = migrate_credit_polarity(db_path)
        assert result1["total_updated"] > 0

        # Second run
        result2 = migrate_credit_polarity(db_path)
        assert result2["total_updated"] == 0

        db_path.unlink()

    def test_migration_transfers_unchanged(self):
        """Transfer rows not touched."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        # Create a transfer (should not be touched)
        self._create_credit_transaction(conn, "Moved to Secured", Decimal("-500"), "Transfer")
        conn.commit()
        conn.close()

        # Run migration
        result = migrate_credit_polarity(db_path)

        # No transfers should be updated
        conn = get_connection(db_path)
        cursor = conn.execute("SELECT amount FROM transactions WHERE tx_type = 'Transfer'")
        assert cursor.fetchone()["amount"] == -500.00
        conn.close()

        db_path.unlink()

    def test_migration_only_affects_credit(self):
        """Non-Credit accounts not affected."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        # Create a Checking purchase (should not be touched)
        conn.execute(
            """INSERT INTO transactions
               (date, description, amount, balance, fee, tx_type, account_type, source_institution, source_file)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2024-03-15", "Purchase", 29.04, None, 0.0, "Purchase", "Checking", "chime", "test.pdf")
        )
        conn.commit()
        conn.close()

        # Run migration
        result = migrate_credit_polarity(db_path)

        # Checking should be unchanged
        conn = get_connection(db_path)
        cursor = conn.execute("SELECT amount FROM transactions WHERE account_type = 'Checking'")
        assert cursor.fetchone()["amount"] == 29.04
        conn.close()

        db_path.unlink()
