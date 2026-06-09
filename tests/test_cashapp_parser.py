"""Unit tests for the CashApp PDF parser."""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from chime_ingestor.models import ChimeTransaction
from parsers.cashapp_parser import (
    CashAppParser,
    _extract_statement_year,
    _extract_transactions_from_text,
    _parse_amount,
    _parse_cashapp_date,
    _parse_fee,
    _find_transaction_type,
)


class TestExtractStatementYear:
    """Tests for year extraction from statement header."""

    def test_year_from_full_date_range(self) -> None:
        """Extract year from 'April 1 – April 30, 2024' format."""
        text = "April 2024\nAccount Statement\nApril 1 – April 30, 2024"
        assert _extract_statement_year(text) == 2024

    def test_year_from_month_year(self) -> None:
        """Extract year from 'April 2024' format."""
        text = "April 2024\nAccount Statement\nCash App"
        assert _extract_statement_year(text) == 2024

    def test_year_from_short_month(self) -> None:
        """Extract year from 'Apr 2024' format."""
        text = "Apr 2024\nAccount Statement"
        assert _extract_statement_year(text) == 2024

    def test_year_not_found_raises(self) -> None:
        """Raise ValueError if no year in header."""
        text = "Some random text without year"
        with pytest.raises(ValueError, match="Cannot determine statement year"):
            _extract_statement_year(text)


class TestParseCashAppDate:
    """Tests for CashApp date parsing with year."""

    def test_short_month_format(self) -> None:
        """Parse 'Apr 8' with year 2024."""
        result = _parse_cashapp_date("Apr 8", 2024)
        assert result == date(2024, 4, 8)

    def test_full_month_format(self) -> None:
        """Parse 'April 15' with year 2024."""
        result = _parse_cashapp_date("April 15", 2024)
        assert result == date(2024, 4, 15)

    def test_single_digit_day(self) -> None:
        """Parse 'Jan 5' with year 2025."""
        result = _parse_cashapp_date("Jan 5", 2025)
        assert result == date(2025, 1, 5)

    def test_invalid_date_returns_none(self) -> None:
        """Return None for unparseable dates."""
        assert _parse_cashapp_date("Invalid", 2024) is None
        assert _parse_cashapp_date("", 2024) is None


class TestParseAmount:
    """Tests for CashApp amount parsing."""

    def test_positive_amount(self) -> None:
        """Parse inflow amount."""
        assert _parse_amount("+$2.40") == Decimal("2.40")
        assert _parse_amount("$15.00") == Decimal("15.00")

    def test_negative_amount(self) -> None:
        """Parse outflow amount."""
        assert _parse_amount("-$50.00") == Decimal("-50.00")
        assert _parse_amount("-$0.83") == Decimal("-0.83")

    def test_amount_with_commas(self) -> None:
        """Parse amount with commas."""
        assert _parse_amount("+$1,234.56") == Decimal("1234.56")

    def test_invalid_amount_returns_none(self) -> None:
        """Return None for invalid amounts."""
        assert _parse_amount("") is None
        assert _parse_amount("invalid") is None


class TestParseFee:
    """Tests for fee parsing."""

    def test_zero_fee(self) -> None:
        """Parse $0.00 fee."""
        assert _parse_fee("$0.00") == Decimal("0.00")

    def test_nonzero_fee(self) -> None:
        """Parse $2.50 fee."""
        assert _parse_fee("$2.50") == Decimal("2.50")


class TestFindTransactionType:
    """Tests for CashApp transaction type detection."""

    def test_cash_app_card(self) -> None:
        """Cash App Card → Purchase."""
        assert _find_transaction_type("Cash App Card", "Wal Mart") == "Purchase"

    def test_cash_app_payment(self) -> None:
        """Cash App payment → Transfer."""
        assert _find_transaction_type("Cash App payment", "From Mike") == "Transfer"

    def test_direct_deposit(self) -> None:
        """Direct deposit → Direct Deposit."""
        assert _find_transaction_type("Direct deposit", "Paycheck") == "Direct Deposit"

    def test_atm_withdrawal(self) -> None:
        """ATM withdrawal → ATM Withdrawal."""
        assert _find_transaction_type("ATM withdrawal", "Chase Bank") == "ATM Withdrawal"

    def test_loan_repayment(self) -> None:
        """Loan repayment → Loan Repayment."""
        assert _find_transaction_type("Loan repayment", "Cash App") == "Loan Repayment"


class TestExtractTransactionsFromText:
    """Tests for text-based transaction extraction."""

    def test_extract_single_transaction(self) -> None:
        """Extract a single CashApp transaction."""
        text = "Apr 8 Wal Mart West Palm Bea FL Cash App Card $0.00 $0.83"
        txs = _extract_transactions_from_text(text, 2024, "test.pdf")

        assert len(txs) == 1
        assert txs[0].transaction_date == date(2024, 4, 8)
        assert txs[0].description == "Wal Mart West Palm Bea FL"
        assert txs[0].transaction_type == "Purchase"
        assert txs[0].amount == Decimal("-0.83")
        assert txs[0].settlement_date == date(2024, 4, 8)
        assert txs[0].source_file == "test.pdf"
        assert txs[0].account_type == "CashApp"
        assert txs[0].source_institution == "cashapp"

    def test_extract_inflow_transaction(self) -> None:
        """Extract an inflow transaction with + sign."""
        text = "Apr 8 From Ricardo Diez Cash App payment $0.00 + $9.00"
        txs = _extract_transactions_from_text(text, 2024, "test.pdf")

        assert len(txs) == 1
        assert txs[0].amount == Decimal("9.00")
        assert txs[0].is_inflow is True
        assert txs[0].is_outflow is False

    def test_extract_outflow_transaction(self) -> None:
        """Extract an outflow transaction."""
        text = "Apr 7 Cash App Loan repayment $0.00 $25.73"
        txs = _extract_transactions_from_text(text, 2024, "test.pdf")

        assert len(txs) == 1
        assert txs[0].amount == Decimal("-25.73")
        assert txs[0].is_outflow is True

    def test_extract_direct_deposit(self) -> None:
        """Extract direct deposit transaction."""
        text = "Apr 8 INTEGRITY FULFIL PAYROLL Direct deposit $0.00 + $211.35"
        txs = _extract_transactions_from_text(text, 2024, "test.pdf")

        assert len(txs) == 1
        assert txs[0].transaction_type == "Direct Deposit"
        assert txs[0].amount == Decimal("211.35")

    def test_multiple_transactions(self) -> None:
        """Extract multiple transactions from text block."""
        text = """
Apr 8 Wal Mart Cash App Card $0.00 $0.83
Apr 8 From Star Cash App payment $0.00 + $15.00
Apr 7 Pnc Bank ATM withdrawal $2.50 $82.50
"""
        txs = _extract_transactions_from_text(text, 2024, "test.pdf")
        assert len(txs) == 3


class TestCashAppParserIntegration:
    """Integration tests for CashAppParser."""

    def test_parser_file_not_found(self, tmp_path: Path) -> None:
        """Raise FileNotFoundError for missing file."""
        parser = CashAppParser()
        with pytest.raises(FileNotFoundError):
            parser.parse(tmp_path / "nonexistent.pdf")

    def test_parser_not_pdf(self, tmp_path: Path) -> None:
        """Raise ValueError for non-PDF files."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("not a pdf")
        parser = CashAppParser()
        with pytest.raises(ValueError, match="not a PDF"):
            parser.parse(txt_file)

    def test_parser_source_institution(self) -> None:
        """All transactions have source_institution='cashapp'."""
        text = "Apr 8 Wal Mart Cash App Card $0.00 $0.83"
        txs = _extract_transactions_from_text(text, 2024, "test.pdf")
        assert all(tx.source_institution == "cashapp" for tx in txs)

    def test_parser_account_type(self) -> None:
        """All transactions have account_type='CashApp'."""
        text = "Apr 8 Wal Mart Cash App Card $0.00 $0.83"
        txs = _extract_transactions_from_text(text, 2024, "test.pdf")
        assert all(tx.account_type == "CashApp" for tx in txs)
