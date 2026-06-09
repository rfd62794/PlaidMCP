"""Chime PDF parser — extracted from chime_ingestor/parser.py."""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import pdfplumber

from chime_ingestor.models import ChimeTransaction


# Account type detection from filename patterns
ACCOUNT_TYPE_PATTERNS = {
    "Checking": re.compile(r"chime-checking", re.IGNORECASE),
    "Savings": re.compile(r"chime-savings", re.IGNORECASE),
    "Credit": re.compile(r"chime-credit", re.IGNORECASE),
}

# Regex to match Chime transaction lines
# Format: DATE DESCRIPTION TYPE AMOUNT BALANCE SETTLEMENT_DATE
TRANSACTION_PATTERN = re.compile(
    r"^(?P<tx_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<description>.+?)\s+"
    r"(?P<tx_type>(?:Transfer|Purchase|Payment|Direct\s+Deposit|Round\s+Up\s+Transfer|Interest\s+Paid|Chime\s+Promo|SpotMe|Deposit|ATM\s+Withdrawal|Fee|Refund|Adjustment))\s+"
    r"(?P<amount>-?\$[\d,]+\.\d{2})\s+"
    r"(?P<balance>-?\$[\d,]+\.\d{2})\s+"
    r"(?P<settlement_date>\d{1,2}/\d{1,2}/\d{4})$"
)

# Alternative pattern for lines without balance (seen in some statements)
TRANSACTION_PATTERN_NO_BALANCE = re.compile(
    r"^(?P<tx_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<description>.+?)\s+"
    r"(?P<tx_type>(?:Transfer|Purchase|Payment|Direct\s+Deposit|Round\s+Up\s+Transfer|Interest\s+Paid|Chime\s+Promo|SpotMe|Deposit|ATM\s+Withdrawal|Fee|Refund|Adjustment))\s+"
    r"(?P<amount>-?\$[\d,]+\.\d{2})\s+"
    r"(?P<settlement_date>\d{1,2}/\d{1,2}/\d{4})$"
)


KNOWN_TX_TYPES = {
    "Transfer", "Purchase", "Payment", "Direct Deposit", "Round Up Transfer",
    "Interest Paid", "Chime Promo", "SpotMe", "Deposit", "ATM Withdrawal",
    "Fee", "Refund", "Adjustment"
}


def _detect_account_type(filename: str) -> str:
    """Detect account type from filename."""
    for account_type, pattern in ACCOUNT_TYPE_PATTERNS.items():
        if pattern.search(filename):
            return account_type
    return "Unknown"


def _parse_date(date_str: str) -> Optional[date]:
    """Parse M/D/YYYY date string."""
    date_str = date_str.strip()
    if not date_str:
        return None

    try:
        dt = datetime.strptime(date_str, "%m/%d/%Y")
        return dt.date()
    except ValueError:
        return None


def _parse_amount(amount_str: str) -> Optional[Decimal]:
    """Parse amount string, handling $ and polarity."""
    if not amount_str:
        return None

    cleaned = amount_str.replace("$", "").replace(",", "").strip()

    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _find_transaction_type(description: str, raw_type: str) -> str:
    """Determine transaction type from description and raw type."""
    # Sort by length (longest first) so specific types match before general ones
    for known in sorted(KNOWN_TX_TYPES, key=len, reverse=True):
        if known.lower() in raw_type.lower():
            return known

    # Fallback: infer from description
    desc_lower = description.lower()
    if "transfer" in desc_lower:
        return "Transfer"
    if any(word in desc_lower for word in ["purchase", "buy", "payment to"]):
        return "Purchase"
    if "deposit" in desc_lower or "direct dep" in desc_lower:
        return "Direct Deposit"
    if "interest" in desc_lower:
        return "Interest Paid"
    if "atm" in desc_lower or "withdrawal" in desc_lower:
        return "ATM Withdrawal"
    if "fee" in desc_lower:
        return "Fee"
    if "refund" in desc_lower:
        return "Refund"

    return raw_type if raw_type else "Unknown"


def _extract_transactions_from_text(
    text: str,
    source_file: str,
    account_type: str,
) -> list[ChimeTransaction]:
    """Extract transactions from PDF text using regex."""
    transactions: list[ChimeTransaction] = []
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try full pattern first (with balance column)
        match = TRANSACTION_PATTERN.match(line)

        # If that fails, try pattern without balance
        if not match:
            match = TRANSACTION_PATTERN_NO_BALANCE.match(line)

        if match:
            tx_date_str = match.group("tx_date")
            description = match.group("description").strip()
            tx_type_raw = match.group("tx_type")
            amount_str = match.group("amount")
            settlement_date_str = match.group("settlement_date")

            tx_date = _parse_date(tx_date_str)
            settlement_date = _parse_date(settlement_date_str)
            amount = _parse_amount(amount_str)

            if not tx_date or amount is None:
                continue

            # Normalize transaction type
            tx_type = _find_transaction_type(description, tx_type_raw)

            # Normalize Credit polarity: purchases → negative, payments → positive
            if account_type == "Credit":
                amount = _normalize_credit_amount(amount, tx_type)

            try:
                # Determine balance if present in match
                balance = None
                if "balance" in match.groupdict():
                    balance_str = match.group("balance")
                    balance = _parse_amount(balance_str)

                tx = ChimeTransaction(
                    transaction_date=tx_date,
                    description=description,
                    transaction_type=tx_type,
                    amount=amount,
                    settlement_date=settlement_date or tx_date,
                    balance=balance,
                    source_file=source_file,
                    account_type=account_type,
                    source_institution="chime",
                )
                transactions.append(tx)
            except ValueError:
                continue

    return transactions


class ChimeParser:
    """Parser for Chime PDF statements."""

    def parse(self, path: Path) -> list[ChimeTransaction]:
        """Parse a Chime PDF statement into a list of transactions.

        Args:
            path: Path to the PDF file

        Returns:
            List of ChimeTransaction objects

        Raises:
            FileNotFoundError: If the PDF does not exist
            ValueError: If the PDF cannot be parsed
        """
        pdf_path = Path(path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        if not pdf_path.suffix.lower() == ".pdf":
            raise ValueError(f"File is not a PDF: {pdf_path}")

        source_file = pdf_path.name
        account_type = _detect_account_type(source_file)

        transactions: list[ChimeTransaction] = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        page_transactions = _extract_transactions_from_text(
                            text, source_file, account_type
                        )
                        transactions.extend(page_transactions)

        except Exception as e:
            raise ValueError(f"Failed to parse PDF {source_file}: {e}") from e

        # Sort by transaction date
        transactions.sort(key=lambda x: x.transaction_date)

        return transactions
