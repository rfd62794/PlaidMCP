"""CashApp PDF parser — handles CashApp statement format."""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import pdfplumber

from chime_ingestor.models import ChimeTransaction


# CashApp date format: "Apr 8" (Mon D) without year
# Must combine with extracted year
CASHAPP_DATE_PATTERN = re.compile(r"^(?P<month>[A-Za-z]{3,})\s+(?P<day>\d{1,2})$")

# Year extraction from statement period header
# Looks for patterns like "April 2024", "Apr 2024", "2024" in header
YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")

# CashApp transaction line pattern
# Format: DATE DESCRIPTION DETAILS FEE AMOUNT
# Examples:
#   "Apr 8 Wal Mart West Palm Bea FL Cash App Card $0.00 $0.83" (outflow)
#   "Apr 8 From Ricardo Diez Cash App payment $0.00 + $9.00" (inflow)
#   "Apr 8 INTEGRITY FULFIL PAYROLL Direct deposit $0.00 + $211.35" (inflow)
#
# Amount patterns:
#   - Outflow: "$0.83" or "$50.00" (no sign = negative for CashApp)
#   - Inflow: "+ $9.00" or "+$211.35" (explicit + sign)
TRANSACTION_PATTERN = re.compile(
    r"^(?P<tx_date>[A-Za-z]{3,}\s+\d{1,2})\s+"
    r"(?P<description>.+?)\s+"
    r"(?P<details>(?:Cash App (?:Card|payment)|Direct deposit|ATM \w+|Transfer|Loan\s+\w+|Paycheck:?))\s+"
    r"(?P<fee>\$[\d,]+\.\d{2})\s+"
    r"(?:(?P<inflow_sign>\+\s*)?\$(?P<amount>[\d,]+\.\d{2}))$"
)


KNOWN_TX_TYPES = {
    "Cash App Card", "Cash App payment", "Direct deposit",
    "ATM withdrawal", "Transfer", "Loan repayment", "Loan refund",
    "Paycheck", "Refund"
}


def _extract_statement_year(text: str) -> int:
    """Extract year from statement period in PDF header text.

    Args:
        text: First page text content

    Returns:
        Year as integer (e.g., 2024)

    Raises:
        ValueError: If year cannot be determined from header
    """
    # Search first 1000 chars for year pattern
    search_text = text[:1000] if len(text) > 1000 else text

    matches = YEAR_PATTERN.findall(search_text)
    if matches:
        # Return first valid year found
        return int(matches[0])

    raise ValueError("Cannot determine statement year from PDF header")


def _parse_cashapp_date(date_str: str, year: int) -> Optional[date]:
    """Parse CashApp date format like "Apr 8" with extracted year.

    Args:
        date_str: Date string like "Apr 8" or "April 15"
        year: Extracted year from statement header

    Returns:
        Parsed date or None if unparseable
    """
    date_str = date_str.strip()
    if not date_str:
        return None

    # Try with full month name
    for fmt in ["%B %d", "%b %d"]:
        try:
            dt = datetime.strptime(f"{date_str} {year}", f"{fmt} %Y")
            return dt.date()
        except ValueError:
            continue

    return None


def _parse_amount(amount_str: str) -> Optional[Decimal]:
    """Parse amount string, handling $ and polarity.

    Args:
        amount_str: Amount string like "$14.92" or "+$2.40" or "-$50.00"

    Returns:
        Decimal amount or None if unparseable
    """
    if not amount_str:
        return None

    # Extract sign and clean the amount
    sign = ""
    if amount_str.startswith("+"):
        sign = ""
        amount_str = amount_str[1:]
    elif amount_str.startswith("-"):
        sign = "-"
        amount_str = amount_str[1:]

    cleaned = amount_str.replace("$", "").replace(",", "").strip()

    try:
        return Decimal(sign + cleaned)
    except InvalidOperation:
        return None


def _parse_fee(fee_str: str) -> Decimal:
    """Parse fee amount.

    Args:
        fee_str: Fee string like "$0.00" or "$2.50"

    Returns:
        Decimal fee amount (always positive or zero)
    """
    cleaned = fee_str.replace("$", "").replace(",", "").strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0.00")


def _find_transaction_type(details: str, description: str) -> str:
    """Determine transaction type from details and description."""
    details_lower = details.lower()
    desc_lower = description.lower()

    # Check known types in details field
    if "cash app card" in details_lower:
        return "Purchase"  # Card purchases
    if "cash app payment" in details_lower:
        return "Transfer"  # P2P payments
    if "direct deposit" in details_lower:
        return "Direct Deposit"
    if "atm" in details_lower:
        return "ATM Withdrawal"
    if "loan repayment" in details_lower:
        return "Loan Repayment"
    if "loan refund" in details_lower:
        return "Loan Refund"
    if "transfer" in details_lower or "paycheck" in desc_lower:
        return "Transfer"

    return "Other"


def _extract_transactions_from_text(
    text: str,
    year: int,
    source_file: str,
) -> list[ChimeTransaction]:
    """Extract transactions from CashApp PDF text.

    Args:
        text: Extracted text from PDF
        year: Statement year extracted from header
        source_file: Original filename

    Returns:
        List of ChimeTransaction objects
    """
    transactions: list[ChimeTransaction] = []
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try pattern
        match = TRANSACTION_PATTERN.match(line)

        if match:
            tx_date_str = match.group("tx_date")
            description = match.group("description").strip()
            details = match.group("details")
            fee_str = match.group("fee")

            # Check for inflow sign (+)
            # CashApp convention: + = inflow (positive), no sign = outflow (negative)
            raw_amount = match.group("amount")
            inflow_sign = match.group("inflow_sign")

            if inflow_sign:
                # Inflow - positive amount
                amount_str = f"+${raw_amount}"
            else:
                # Outflow - negative amount (CashApp shows positive, we negate)
                amount_str = f"-${raw_amount}"

            tx_date = _parse_cashapp_date(tx_date_str, year)
            if not tx_date:
                continue

            amount = _parse_amount(amount_str)
            if amount is None:
                continue

            fee = _parse_fee(fee_str)
            tx_type = _find_transaction_type(details, description)

            try:
                # CashApp has no settlement date or balance columns
                # Use transaction date as settlement date
                tx = ChimeTransaction(
                    transaction_date=tx_date,
                    description=description,
                    transaction_type=tx_type,
                    amount=amount,
                    settlement_date=tx_date,  # Same as transaction date for CashApp
                    balance=None,  # CashApp doesn't show running balance
                    source_file=source_file,
                    account_type="CashApp",  # Single account type for CashApp
                    source_institution="cashapp",
                )
                transactions.append(tx)
            except ValueError:
                continue

    return transactions


class CashAppParser:
    """Parser for CashApp PDF statements."""

    def parse(self, path: Path) -> list[ChimeTransaction]:
        """Parse a CashApp PDF statement into a list of transactions.

        Args:
            path: Path to the PDF file

        Returns:
            List of ChimeTransaction objects

        Raises:
            FileNotFoundError: If the PDF does not exist
            ValueError: If the PDF cannot be parsed or year cannot be extracted
        """
        pdf_path = Path(path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        if not pdf_path.suffix.lower() == ".pdf":
            raise ValueError(f"File is not a PDF: {pdf_path}")

        source_file = pdf_path.name
        transactions: list[ChimeTransaction] = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                # Extract year from first page header
                first_page_text = ""
                if pdf.pages:
                    first_page_text = pdf.pages[0].extract_text() or ""

                try:
                    year = _extract_statement_year(first_page_text)
                except ValueError as e:
                    raise ValueError(
                        f"Cannot parse {source_file}: {e}"
                    ) from e

                # Extract transactions from all pages
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        page_transactions = _extract_transactions_from_text(
                            text, year, source_file
                        )
                        transactions.extend(page_transactions)

        except Exception as e:
            if isinstance(e, (FileNotFoundError, ValueError)):
                raise
            raise ValueError(f"Failed to parse PDF {source_file}: {e}") from e

        # Sort by transaction date
        transactions.sort(key=lambda x: x.transaction_date)

        return transactions
