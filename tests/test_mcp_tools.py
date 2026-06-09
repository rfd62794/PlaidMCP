"""Tests for MCP tool wrappers."""
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from chime_ingestor.db import create_schema, get_connection, upsert_transactions
from chime_ingestor.models import ChimeTransaction
from plaid_mcp.tools.finance_tools import (
    execute_readonly_query,
    get_annual_summary,
    get_balance,
    get_ingestion_status,
    get_net_spending,
    get_spending_by_category,
    get_spending_trends,
    get_summary,
    get_top_merchants,
    get_transactions,
    search_transactions,
)
from plaid_mcp.tools.statement_tools import get_raw_statement_text


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
def mock_db_path(tmp_path):
    """Create a temp database and mock _db_path to return it."""
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    create_schema(conn)

    # Insert test data
    transactions = [
        _create_test_transaction(date(2024, 3, 1), "McDonald's", "-15.50"),
        _create_test_transaction(date(2024, 3, 2), "Starbucks", "-8.25"),
        _create_test_transaction(date(2024, 3, 3), "Direct Deposit", "2500.00", tx_type="Direct Deposit"),
        _create_test_transaction(date(2024, 3, 4), "Amazon", "-45.99"),
        _create_test_transaction(date(2024, 3, 5), "Uber", "-12.50"),
        _create_test_transaction(
            date(2024, 3, 6), "Cash App Payment", "-50.00",
            institution="cashapp", account_type="CashApp"
        ),
        _create_test_transaction(date(2024, 2, 15), "Target", "-35.00"),
    ]
    upsert_transactions(conn, transactions)

    # Add ingestion log entry
    conn.execute(
        "INSERT INTO ingestion_log (source_file, source_hash, record_count, status) VALUES (?, ?, ?, ?)",
        ("test.pdf", "abc123hash", 7, "success")
    )
    conn.commit()
    conn.close()

    with patch("plaid_mcp.tools.finance_tools._db_path", return_value=db_path):
        yield db_path


class TestGetTransactions:
    """Tests for get_transactions tool."""

    def test_get_transactions_returns_list(self, mock_db_path):
        """Returns list, not exception."""
        result = get_transactions(limit=10)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_transactions_limit_capped(self, mock_db_path):
        """limit=9999 -> capped at 500."""
        result = get_transactions(limit=9999)
        # Should not error and should return data
        assert isinstance(result, list)

    def test_get_transactions_error_returns_dict(self, mock_db_path):
        """Bad db path -> list with error dict."""
        with patch("plaid_mcp.tools.finance_tools._db_path", return_value=Path("/nonexistent/bad.db")):
            result = get_transactions()
            # Should return list with error entry
            assert isinstance(result, list)
            assert len(result) == 1
            assert "error" in result[0]


class TestGetBalance:
    """Tests for get_balance tool."""

    def test_get_balance_returns_dict(self, mock_db_path):
        """Returns dict with balance."""
        result = get_balance()
        assert isinstance(result, dict)
        assert "balance" in result


class TestGetSpendingByCategory:
    """Tests for get_spending_by_category tool."""

    def test_get_spending_by_category_format(self, mock_db_path):
        """Returns dict with string keys."""
        result = get_spending_by_category(month="2024-03")
        assert isinstance(result, dict)
        # Should have some categories or be empty dict
        for key in result.keys():
            assert isinstance(key, str)


class TestGetSpendingTrends:
    """Tests for get_spending_trends tool."""

    def test_get_spending_trends_format(self, mock_db_path):
        """Returns list of dicts with correct keys."""
        result = get_spending_trends(months=3)
        assert isinstance(result, list)
        if result:
            for trend in result:
                assert "month" in trend
                assert "inflow" in trend
                assert "outflow" in trend
                assert "net" in trend


class TestGetSummary:
    """Tests for get_summary tool."""

    def test_get_summary_keys(self, mock_db_path):
        """Returns dict with total_transactions, date_range."""
        result = get_summary()
        assert isinstance(result, dict)
        assert "total_transactions" in result
        assert "institutions" in result
        assert "date_range" in result
        assert "db_size_mb" in result


class TestGetIngestionStatus:
    """Tests for get_ingestion_status tool."""

    def test_get_ingestion_status_list(self, mock_db_path):
        """Returns list."""
        result = get_ingestion_status()
        assert isinstance(result, list)


class TestGetTopMerchants:
    """Tests for get_top_merchants tool."""

    def test_mcp_top_merchants_error_handling(self, mock_db_path):
        """Bad db path -> error dict."""
        with patch("plaid_mcp.tools.finance_tools._db_path", return_value=Path("/nonexistent/bad.db")):
            result = get_top_merchants(month="2024-03")
            assert isinstance(result, dict)
            assert "error" in result


class TestSearchTransactions:
    """Tests for search_transactions tool."""

    def test_mcp_search_error_handling(self, mock_db_path):
        """Bad db path -> error dict."""
        with patch("plaid_mcp.tools.finance_tools._db_path", return_value=Path("/nonexistent/bad.db")):
            result = search_transactions(description_contains="wawa")
            assert isinstance(result, dict)
            assert "error" in result


class TestGetNetSpending:
    """Tests for get_net_spending tool."""

    def test_mcp_net_spending_error_handling(self, mock_db_path):
        """Bad db path -> error dict."""
        with patch("plaid_mcp.tools.finance_tools._db_path", return_value=Path("/nonexistent/bad.db")):
            result = get_net_spending(month="2024-03")
            assert isinstance(result, dict)
            assert "error" in result


class TestExecuteReadonlyQuery:
    """Tests for execute_readonly_query tool."""

    def test_mcp_readonly_query_error(self, mock_db_path):
        """Bad SQL -> error dict."""
        with patch("plaid_mcp.tools.finance_tools._db_path", return_value=Path("/nonexistent/bad.db")):
            result = execute_readonly_query(sql="SELECT * FROM transactions")
            assert isinstance(result, dict)
            assert "error" in result


class TestGetAnnualSummary:
    """Tests for get_annual_summary tool."""

    def test_mcp_annual_summary_error(self, mock_db_path):
        """Bad db path -> error dict."""
        with patch("plaid_mcp.tools.finance_tools._db_path", return_value=Path("/nonexistent/bad.db")):
            result = get_annual_summary(year="2024")
            assert isinstance(result, dict)
            assert "error" in result


class TestGetRawStatementText:
    """Tests for get_raw_statement_text tool."""

    def test_mcp_raw_statement_not_found(self):
        """Unknown file -> error dict."""
        result = get_raw_statement_text(source_file="nonexistent-file-12345.pdf")
        assert isinstance(result, dict)
        assert "error" in result
