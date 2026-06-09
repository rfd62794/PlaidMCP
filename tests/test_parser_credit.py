"""Tests for Credit card polarity fix in parser."""
from decimal import Decimal

import pytest

from parsers.chime_parser import _normalize_credit_amount


class TestNormalizeCreditAmount:
    """Tests for _normalize_credit_amount function."""

    def test_credit_purchase_negated(self):
        """Purchase tx_type → negative amount."""
        assert _normalize_credit_amount(Decimal("29.04"), "Purchase") == Decimal("-29.04")
        assert _normalize_credit_amount(Decimal("100"), "Purchase") == Decimal("-100")

    def test_credit_payment_positive(self):
        """Payment tx_type → positive amount."""
        assert _normalize_credit_amount(Decimal("-2990.74"), "Payment") == Decimal("2990.74")
        assert _normalize_credit_amount(Decimal("-50"), "Payment") == Decimal("50")

    def test_credit_refund_positive(self):
        """Refund tx_type → positive amount."""
        assert _normalize_credit_amount(Decimal("-25.00"), "Refund") == Decimal("25.00")

    def test_credit_atm_withdrawal_negated(self):
        """ATM Withdrawal tx_type → negative amount."""
        assert _normalize_credit_amount(Decimal("100"), "ATM Withdrawal") == Decimal("-100")

    def test_credit_cash_advance_negated(self):
        """Cash Advance tx_type → negative amount."""
        assert _normalize_credit_amount(Decimal("200"), "Cash Advance") == Decimal("-200")

    def test_credit_transfer_unchanged(self):
        """Transfer tx_type → amount unchanged."""
        assert _normalize_credit_amount(Decimal("-500"), "Transfer") == Decimal("-500")
        assert _normalize_credit_amount(Decimal("500"), "Transfer") == Decimal("500")

    def test_credit_purchase_already_negative(self):
        """Purchase already negative stays negative."""
        assert _normalize_credit_amount(Decimal("-29.04"), "Purchase") == Decimal("-29.04")

    def test_credit_payment_already_positive(self):
        """Payment already positive stays positive."""
        assert _normalize_credit_amount(Decimal("2990.74"), "Payment") == Decimal("2990.74")
