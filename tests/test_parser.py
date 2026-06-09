"""Unit tests for the Chime PDF parser."""
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from chime_ingestor.models import ChimeTransaction
from chime_ingestor.parser import (
    _detect_account_type,
    _extract_transactions_from_text,
    _find_transaction_type,
    _parse_amount,
    _parse_date,
    parse_pdf,
)


class TestDetectAccountType:
    """Tests for account type detection from filenames."""

    def test_detect_checking(self) -> None:
        """Should detect Checking from filename."""
        assert _detect_account_type("Chime-Checking-Statement-Jan-2025.pdf") == "Checking"
        assert _detect_account_type("chime-checking-statement.pdf") == "Checking"
        assert _detect_account_type("CHIME-CHECKING-STATEMENT.pdf") == "Checking"

    def test_detect_savings(self) -> None:
        """Should detect Savings from filename."""
        assert _detect_account_type("Chime-Savings-Statement-Jan-2025.pdf") == "Savings"
        assert _detect_account_type("chime-savings-statement.pdf") == "Savings"

    def test_detect_credit(self) -> None:
        """Should detect Credit from filename."""
        assert _detect_account_type("Chime-Credit-Statement-Jan-2025.pdf") == "Credit"
        assert _detect_account_type("chime-credit-statement.pdf") == "Credit"

    def test_detect_unknown(self) -> None:
        """Should return Unknown for non-matching filenames."""
        assert _detect_account_type("random-file.pdf") == "Unknown"
        assert _detect_account_type("statement.pdf") == "Unknown"


class TestParseDate:
    """Tests for date parsing."""

    def test_parse_full_date(self) -> None:
        """Should parse M/D/YYYY format."""
        assert _parse_date("1/31/2025") == date(2025, 1, 31)
        assert _parse_date("12/25/2024") == date(2024, 12, 25)
        assert _parse_date("01/01/2023") == date(2023, 1, 1)

    def test_parse_single_digit_month_day(self) -> None:
        """Should handle single digit month and day."""
        assert _parse_date("1/5/2025") == date(2025, 1, 5)
        assert _parse_date("9/9/2024") == date(2024, 9, 9)

    def test_parse_invalid_date(self) -> None:
        """Should return None for invalid dates."""
        assert _parse_date("") is None
        assert _parse_date("invalid") is None
        assert _parse_date("2025-01-31") is None  # ISO format not supported


class TestParseAmount:
    """Tests for amount parsing."""

    def test_parse_positive_amount(self) -> None:
        """Should parse positive amounts."""
        assert _parse_amount("$200.00") == Decimal("200.00")
        assert _parse_amount("$14.92") == Decimal("14.92")
        assert _parse_amount("$1,000.50") == Decimal("1000.50")

    def test_parse_negative_amount(self) -> None:
        """Should parse negative amounts."""
        assert _parse_amount("-$200.00") == Decimal("-200.00")
        assert _parse_amount("-$1,234.56") == Decimal("-1234.56")

    def test_parse_invalid_amount(self) -> None:
        """Should return None for invalid amounts."""
        assert _parse_amount("") is None
        assert _parse_amount("invalid") is None
        assert _parse_amount("$") is None


class TestFindTransactionType:
    """Tests for transaction type normalization."""

    def test_known_types(self) -> None:
        """Should return known types directly."""
        assert _find_transaction_type("", "Transfer") == "Transfer"
        assert _find_transaction_type("", "Purchase") == "Purchase"
        assert _find_transaction_type("", "Payment") == "Payment"
        assert _find_transaction_type("", "Direct Deposit") == "Direct Deposit"

    def test_infer_from_description(self) -> None:
        """Should infer type from description when unknown."""
        assert _find_transaction_type("Transfer to Savings", "Unknown") == "Transfer"
        assert _find_transaction_type("Purchase at Target", "Unknown") == "Purchase"
        assert _find_transaction_type("Interest Paid this period", "Unknown") == "Interest Paid"
        assert _find_transaction_type("ATM Withdrawal at Chase", "Unknown") == "ATM Withdrawal"


class TestExtractTransactionsFromText:
    """Tests for text-based transaction extraction."""

    def test_extract_single_transaction(self) -> None:
        """Should extract a single transaction line."""
        text = "1/31/2025 Transfer to Savings Account Transfer $200.00 $500.00 1/31/2025"
        txs = _extract_transactions_from_text(text, "test.pdf", "Checking")

        assert len(txs) == 1
        assert txs[0].transaction_date == date(2025, 1, 31)
        assert txs[0].description == "Transfer to Savings Account"
        assert txs[0].transaction_type == "Transfer"
        assert txs[0].amount == Decimal("200.00")
        assert txs[0].balance == Decimal("500.00")
        assert txs[0].settlement_date == date(2025, 1, 31)
        assert txs[0].source_file == "test.pdf"
        assert txs[0].account_type == "Checking"

    def test_extract_negative_amount(self) -> None:
        """Should handle negative amounts (outflows)."""
        text = "1/31/2025 Purchase at Target Purchase -$50.00 $450.00 1/31/2025"
        txs = _extract_transactions_from_text(text, "test.pdf", "Checking")

        assert len(txs) == 1
        assert txs[0].amount == Decimal("-50.00")
        assert txs[0].is_outflow is True
        assert txs[0].is_inflow is False

    def test_extract_multiple_transactions(self) -> None:
        """Should extract multiple transactions from text."""
        text = """
1/31/2025 Transfer to Savings Transfer $200.00 $500.00 1/31/2025
1/30/2025 Purchase at Target Purchase -$50.00 $300.00 1/30/2025
1/29/2025 Direct Deposit Direct Deposit $1000.00 $350.00 1/29/2025
        """
        txs = _extract_transactions_from_text(text, "test.pdf", "Checking")
        assert len(txs) == 3

    def test_skip_header_lines(self) -> None:
        """Should skip header lines that look like transactions."""
        text = "TRANSACTION DATE DESCRIPTION TYPE AMOUNT BALANCE SETTLEMENT DATE"
        txs = _extract_transactions_from_text(text, "test.pdf", "Checking")
        assert len(txs) == 0

    def test_skip_non_transaction_lines(self) -> None:
        """Should skip lines that don't match transaction pattern."""
        text = "This is just some random text\nAnother line without date pattern"
        txs = _extract_transactions_from_text(text, "test.pdf", "Checking")
        assert len(txs) == 0


class TestChimeTransactionModel:
    """Tests for ChimeTransaction dataclass."""

    def test_transaction_creation(self) -> None:
        """Should create a valid transaction."""
        tx = ChimeTransaction(
            transaction_date=date(2025, 1, 31),
            description="Test Transaction",
            transaction_type="Purchase",
            amount=Decimal("-50.00"),
            settlement_date=date(2025, 1, 31),
        )
        assert tx.transaction_date == date(2025, 1, 31)
        assert tx.description == "Test Transaction"
        assert tx.amount == Decimal("-50.00")

    def test_transaction_validation_zero_amount(self) -> None:
        """Should reject zero amount transactions."""
        with pytest.raises(ValueError, match="cannot be zero"):
            ChimeTransaction(
                transaction_date=date(2025, 1, 31),
                description="Test",
                transaction_type="Purchase",
                amount=Decimal("0.00"),
                settlement_date=date(2025, 1, 31),
            )

    def test_transaction_validation_empty_description(self) -> None:
        """Should reject empty descriptions."""
        with pytest.raises(ValueError, match="cannot be empty"):
            ChimeTransaction(
                transaction_date=date(2025, 1, 31),
                description="   ",
                transaction_type="Purchase",
                amount=Decimal("-50.00"),
                settlement_date=date(2025, 1, 31),
            )

    def test_is_outflow_inflow(self) -> None:
        """Should correctly identify inflows and outflows."""
        outflow = ChimeTransaction(
            transaction_date=date(2025, 1, 31),
            description="Purchase",
            transaction_type="Purchase",
            amount=Decimal("-50.00"),
            settlement_date=date(2025, 1, 31),
        )
        inflow = ChimeTransaction(
            transaction_date=date(2025, 1, 31),
            description="Deposit",
            transaction_type="Direct Deposit",
            amount=Decimal("100.00"),
            settlement_date=date(2025, 1, 31),
        )
        assert outflow.is_outflow is True
        assert outflow.is_inflow is False
        assert inflow.is_outflow is False
        assert inflow.is_inflow is True

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        tx = ChimeTransaction(
            transaction_date=date(2025, 1, 31),
            description="Test",
            transaction_type="Purchase",
            amount=Decimal("-50.00"),
            settlement_date=date(2025, 1, 31),
            balance=Decimal("100.00"),
            source_file="test.pdf",
            account_type="Checking",
        )
        d = tx.to_dict()
        assert d["transaction_date"] == "2025-01-31"
        assert d["amount"] == "-50.00"
        assert d["balance"] == "100.00"


class TestParsePdfIntegration:
    """Integration tests for parse_pdf with real files."""

    def test_parse_pdf_file_not_found(self) -> None:
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            parse_pdf(Path("nonexistent.pdf"))

    def test_parse_pdf_not_pdf(self, tmp_path: Path) -> None:
        """Should raise ValueError for non-PDF files."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("not a pdf")
        with pytest.raises(ValueError, match="not a PDF"):
            parse_pdf(txt_file)

    def test_parse_real_checking_pdf(self) -> None:
        """Should parse real Checking PDF and return transactions."""
        pdf_path = Path("data/Chime-Checking-Statement-January-2025.pdf")
        if not pdf_path.exists():
            pytest.skip("Checking PDF not found")

        txs = parse_pdf(pdf_path)
        assert len(txs) > 0

        # All should have Checking account type
        assert all(tx.account_type == "Checking" for tx in txs)

        # All should have valid dates
        assert all(isinstance(tx.transaction_date, date) for tx in txs)

        # Transactions should be sorted by date
        dates = [tx.transaction_date for tx in txs]
        assert dates == sorted(dates)

    def test_parse_real_savings_pdf(self) -> None:
        """Should parse real Savings PDF and return transactions."""
        pdf_path = Path("data/Chime-Savings-Statement-January-2025.pdf")
        if not pdf_path.exists():
            pytest.skip("Savings PDF not found")

        txs = parse_pdf(pdf_path)
        assert len(txs) > 0
        assert all(tx.account_type == "Savings" for tx in txs)

    def test_parse_real_credit_pdf(self) -> None:
        """Should parse real Credit PDF and return transactions."""
        pdf_path = Path("data/Chime-Credit-Statement-January-2025.pdf")
        if not pdf_path.exists():
            pytest.skip("Credit PDF not found")

        txs = parse_pdf(pdf_path)
        assert len(txs) > 0
        assert all(tx.account_type == "Credit" for tx in txs)


# Count tests for SDD compliance
def test_count_tests() -> None:
    """Verify we meet the SDD target of 15+ tests."""
    # Count all test methods
    import inspect
    test_count = 0
    for name, obj in globals().items():
        if inspect.isclass(obj) and name.startswith("Test"):
            for method_name, method in inspect.getmembers(obj, inspect.isfunction):
                if method_name.startswith("test_"):
                    test_count += 1

    # This is a meta-test - we should have at least 15 actual tests
    # The actual count is much higher
    assert test_count >= 15, f"Expected at least 15 tests, found {test_count}"
