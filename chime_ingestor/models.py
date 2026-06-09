"""Data models for Chime transactions."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True, slots=True)
class ChimeTransaction:
    """Normalized representation of a Chime transaction.

    Attributes:
        transaction_date: Date the transaction occurred (from first column)
        description: Merchant or transaction description
        transaction_type: Type of transaction (Purchase, Transfer, Payment, etc.)
        amount: Transaction amount as Decimal. Positive = inflow (deposit),
            Negative = outflow (spending/transfer out)
        settlement_date: Date the transaction settled (may equal transaction_date)
        balance: Optional running balance after this transaction
        source_file: Filename of the source PDF
        account_type: Type of account (Checking, Savings, Credit)
    """

    transaction_date: date
    description: str
    transaction_type: str
    amount: Decimal
    settlement_date: date
    balance: Optional[Decimal] = None
    source_file: str = ""
    account_type: str = ""

    def __post_init__(self) -> None:
        """Validate the transaction data."""
        if self.amount == 0:
            raise ValueError("Transaction amount cannot be zero")
        if not self.description.strip():
            raise ValueError("Description cannot be empty")

    @property
    def is_outflow(self) -> bool:
        """Return True if this is money leaving the account."""
        return self.amount < 0

    @property
    def is_inflow(self) -> bool:
        """Return True if this is money entering the account."""
        return self.amount > 0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "transaction_date": self.transaction_date.isoformat(),
            "description": self.description,
            "transaction_type": self.transaction_type,
            "amount": str(self.amount),
            "settlement_date": self.settlement_date.isoformat(),
            "balance": str(self.balance) if self.balance else None,
            "source_file": self.source_file,
            "account_type": self.account_type,
        }
