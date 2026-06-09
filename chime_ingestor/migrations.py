"""
Migration: invert Credit card transaction amounts.
Run once after §6a parser fix is confirmed correct.
Safe to re-run — uses conditional WHERE clause.
"""
from pathlib import Path
from chime_ingestor.db import get_connection


def migrate_credit_polarity(db_path: Path = Path("finance.db")) -> dict:
    """
    Invert amount sign for Credit purchases and payments.
    Returns {outflow_corrected: int, inflow_corrected: int, total_updated: int}.
    """
    conn = get_connection(db_path)

    # Invert purchases → negative (only if currently positive)
    cursor = conn.execute(
        """UPDATE transactions
           SET amount = -ABS(amount)
           WHERE account_type = 'Credit'
             AND tx_type IN ('Purchase', 'ATM Withdrawal', 'Cash Advance')
             AND amount > 0""",
    )
    outflow_updated = cursor.rowcount

    # Invert payments → positive (only if currently negative)
    cursor = conn.execute(
        """UPDATE transactions
           SET amount = ABS(amount)
           WHERE account_type = 'Credit'
             AND tx_type IN ('Payment', 'Refund')
             AND amount < 0""",
    )
    inflow_updated = cursor.rowcount

    conn.commit()
    conn.close()

    return {
        "outflow_corrected": outflow_updated,
        "inflow_corrected": inflow_updated,
        "total_updated": outflow_updated + inflow_updated,
    }
