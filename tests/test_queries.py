"""Tests for query functions."""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from chime_ingestor.db import create_schema, get_connection, upsert_transactions
from chime_ingestor.models import ChimeTransaction
from chime_ingestor.queries import (
    get_balance,
    get_net_spending,
    get_spending_by_category,
    get_spending_trends,
    get_top_merchants,
    get_transactions,
    search_transactions,
)


def _create_test_transaction(
    tx_date: date,
    description: str,
    amount: str,
    institution: str = "chime",
    account_type: str = "Checking",
    tx_type: str = "Purchase",
    balance: str | None = "1000.00",
) -> ChimeTransaction:
    """Helper to create test transactions."""
    return ChimeTransaction(
        transaction_date=tx_date,
        description=description,
        transaction_type=tx_type,
        amount=Decimal(amount),
        settlement_date=tx_date,
        balance=Decimal(balance) if balance else None,
        source_file="test.pdf",
        account_type=account_type,
        source_institution=institution,
    )


@pytest.fixture
def mock_db():
    """In-memory database with test data."""
    conn = get_connection(Path(":memory:"))
    create_schema(conn)

    # Insert test transactions
    transactions = [
        _create_test_transaction(date(2024, 3, 1), "McDonald's", "-15.50"),
        _create_test_transaction(date(2024, 3, 2), "Starbucks", "-8.25"),
        _create_test_transaction(date(2024, 3, 3), "Direct Deposit", "2500.00", tx_type="Direct Deposit"),
        _create_test_transaction(date(2024, 3, 4), "Amazon", "-45.99"),
        _create_test_transaction(date(2024, 3, 5), "Uber", "-12.50"),
        # CashApp transaction
        _create_test_transaction(
            date(2024, 3, 6), "Cash App Payment", "-50.00",
            institution="cashapp", account_type="CashApp"
        ),
        # Different month
        _create_test_transaction(date(2024, 2, 15), "Target", "-35.00"),
        # Different year
        _create_test_transaction(date(2023, 12, 31), "Walmart", "-78.50"),
    ]

    upsert_transactions(conn, transactions)

    # Close and reopen to get a fresh connection
    conn.close()

    db_path = Path(":memory:")

    # For in-memory, we need to use the same connection
    return db_path


class TestGetTransactions:
    """Tests for get_transactions()."""

    def test_get_transactions_no_filter(self, mock_db):
        """Returns up to limit rows from mock db."""
        # Use a file-based temp db for this test
        import tempfile
        import sqlite3

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 3, 1), "Test 1", "-10.00"),
            _create_test_transaction(date(2024, 3, 2), "Test 2", "-20.00"),
            _create_test_transaction(date(2024, 3, 3), "Test 3", "-30.00"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        result = get_transactions(limit=10, db_path=db_path)
        assert len(result) == 3
        assert result[0]["description"] == "Test 3"  # Most recent first

        db_path.unlink()

    def test_get_transactions_date_range(self, mock_db):
        """Filters correctly by start/end date."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 3, 1), "Early March", "-10.00"),
            _create_test_transaction(date(2024, 3, 15), "Mid March", "-20.00"),
            _create_test_transaction(date(2024, 4, 1), "April", "-30.00"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        result = get_transactions(start_date="2024-03-10", end_date="2024-03-31", db_path=db_path)
        assert len(result) == 1
        assert result[0]["description"] == "Mid March"

        db_path.unlink()

    def test_get_transactions_by_institution(self, mock_db):
        """institution='cashapp' returns only CashApp rows."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 3, 1), "Chime Tx", "-10.00", institution="chime"),
            _create_test_transaction(date(2024, 3, 2), "CashApp Tx", "-20.00", institution="cashapp", account_type="CashApp"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        result = get_transactions(institution="cashapp", limit=100, db_path=db_path)
        assert len(result) == 1
        assert result[0]["source_institution"] == "cashapp"

        db_path.unlink()


class TestGetBalance:
    """Tests for get_balance()."""

    def test_get_balance_chime_only(self):
        """Returns most recent balance <= date."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 3, 1), "Tx 1", "-10.00", balance="990.00"),
            _create_test_transaction(date(2024, 3, 2), "Tx 2", "-20.00", balance="970.00"),
            _create_test_transaction(date(2024, 3, 3), "Tx 3", "-30.00", balance="940.00"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        balance = get_balance(date="2024-03-02", db_path=db_path)
        assert balance == 970.00

        db_path.unlink()


class TestGetSpendingByCategory:
    """Tests for get_spending_by_category()."""

    def test_get_spending_by_category_outflows(self):
        """Only negative amounts included."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 3, 1), "McDonald's", "-15.50"),
            _create_test_transaction(date(2024, 3, 2), "Income", "2500.00"),
            _create_test_transaction(date(2024, 3, 3), "Starbucks", "-8.25"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        spending = get_spending_by_category(month="2024-03", db_path=db_path)

        # Should only have outflows (negative amounts)
        total = sum(spending.values())
        assert total < 0

        db_path.unlink()

    def test_get_spending_by_category_month(self):
        """Filters to correct month."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 2, 28), "Feb Tx", "-10.00"),
            _create_test_transaction(date(2024, 3, 1), "March Tx", "-20.00"),
            _create_test_transaction(date(2024, 4, 1), "April Tx", "-30.00"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        spending = get_spending_by_category(month="2024-03", db_path=db_path)

        # Should only have March transactions
        total = sum(spending.values())
        assert total == -20.00

        db_path.unlink()


class TestGetSpendingTrends:
    """Tests for get_spending_trends()."""

    def test_get_spending_trends_n_months(self):
        """Returns N dicts with correct keys."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 1, 1), "Jan", "-10.00"),
            _create_test_transaction(date(2024, 2, 1), "Feb", "-20.00"),
            _create_test_transaction(date(2024, 3, 1), "Mar", "-30.00"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        trends = get_spending_trends(months=2, db_path=db_path)

        assert len(trends) == 2
        for trend in trends:
            assert "month" in trend
            assert "inflow" in trend
            assert "outflow" in trend
            assert "net" in trend

        db_path.unlink()

    def test_get_spending_trends_net(self):
        """net == inflow + outflow for each month."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 3, 1), "Outflow", "-50.00"),
            _create_test_transaction(date(2024, 3, 2), "Inflow", "2000.00"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        trends = get_spending_trends(months=1, db_path=db_path)

        assert len(trends) == 1
        trend = trends[0]
        assert trend["net"] == trend["inflow"] + trend["outflow"]

        db_path.unlink()


class TestGetTopMerchants:
    """Tests for get_top_merchants()."""

    def test_get_top_merchants_returns_list(self):
        """Returns list of dicts."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 3, 1), "Wawa", "-15.50"),
            _create_test_transaction(date(2024, 3, 2), "Wawa", "-8.25"),
            _create_test_transaction(date(2024, 3, 3), "Target", "-45.99"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        result = get_top_merchants(month="2024-03", db_path=db_path)

        assert isinstance(result, list)
        assert len(result) > 0
        for item in result:
            assert "description" in item
            assert "total" in item
            assert "count" in item
            assert "avg" in item

        db_path.unlink()

    def test_get_top_merchants_outflows_only(self):
        """No positive amounts in results."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 3, 1), "Income", "2500.00"),
            _create_test_transaction(date(2024, 3, 2), "Wawa", "-15.50"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        result = get_top_merchants(month="2024-03", db_path=db_path)

        # All totals should be negative (outflows only)
        for item in result:
            assert item["total"] < 0

        db_path.unlink()

    def test_get_top_merchants_sorted(self):
        """First entry has lowest (most negative) total."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 3, 1), "Small", "-10.00"),
            _create_test_transaction(date(2024, 3, 2), "Large", "-100.00"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        result = get_top_merchants(month="2024-03", db_path=db_path)

        assert result[0]["total"] < result[1]["total"]  # Most negative first

        db_path.unlink()

    def test_get_top_merchants_limit(self):
        """Returns at most limit rows."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 3, i), f"Merchant{i}", f"-10.{i:02d}")
            for i in range(1, 6)
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        result = get_top_merchants(month="2024-03", limit=3, db_path=db_path)

        assert len(result) <= 3

        db_path.unlink()


class TestSearchTransactions:
    """Tests for search_transactions()."""

    def test_search_transactions_match(self):
        """'wawa' returns rows with 'Wawa' in description."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 3, 1), "Wawa Store 1234", "-15.50"),
            _create_test_transaction(date(2024, 3, 2), "Target", "-45.99"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        result = search_transactions(description_contains="wawa", db_path=db_path)

        assert len(result) == 1
        assert "Wawa" in result[0]["description"]

        db_path.unlink()

    def test_search_transactions_case_insensitive(self):
        """'WAWA' matches 'Wawa'."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 3, 1), "Wawa Store", "-15.50"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        result = search_transactions(description_contains="WAWA", db_path=db_path)

        assert len(result) == 1

        db_path.unlink()

    def test_search_transactions_month_filter(self):
        """Wrong month returns no results."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 3, 1), "Wawa", "-15.50"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        result = search_transactions(description_contains="wawa", month="2024-04", db_path=db_path)

        assert len(result) == 0

        db_path.unlink()


class TestGetNetSpending:
    """Tests for get_net_spending()."""

    def test_get_net_spending_excludes_internal(self):
        """'Moved to Secured' not in totals."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 3, 1), "Moved to Secured Deposit Account", "-500.00"),
            _create_test_transaction(date(2024, 3, 2), "Wawa", "-15.50"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        result = get_net_spending(month="2024-03", db_path=db_path)

        # Internal transfer should be excluded
        assert "Internal Transfer" not in result["by_category"]
        assert result["total_outflow"] == -15.50

        db_path.unlink()

    def test_get_net_spending_reports_excluded_volume(self):
        """excluded_transfer_volume > 0 when internal transfers exist."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 3, 1), "Moved to Secured Deposit Account", "-500.00"),
            _create_test_transaction(date(2024, 3, 2), "Wawa", "-15.50"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        result = get_net_spending(month="2024-03", db_path=db_path)

        assert result["excluded_transfer_volume"] > 0

        db_path.unlink()

    def test_get_net_spending_by_category_keys(self):
        """Returns dict with category strings."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = get_connection(db_path)
        create_schema(conn)

        transactions = [
            _create_test_transaction(date(2024, 3, 1), "Wawa", "-15.50"),
            _create_test_transaction(date(2024, 3, 2), "McDonald's", "-8.25"),
        ]
        upsert_transactions(conn, transactions)
        conn.close()

        result = get_net_spending(month="2024-03", db_path=db_path)

        assert isinstance(result["by_category"], dict)
        for key in result["by_category"].keys():
            assert isinstance(key, str)

        db_path.unlink()
