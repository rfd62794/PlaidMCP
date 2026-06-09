"""Query functions for finance.db."""
from pathlib import Path
from typing import Optional

from chime_ingestor.db import get_connection


def get_transactions(
    start_date: str | None = None,
    end_date: str | None = None,
    institution: str | None = None,
    account_type: str | None = None,
    limit: int = 100,
    db_path: Path = Path("finance.db"),
) -> list[dict]:
    """Return transactions filtered by date range and/or institution.

    Args:
        start_date: Filter transactions on or after this date (ISO format: "2024-03-15")
        end_date: Filter transactions on or before this date (ISO format: "2024-03-15")
        institution: Filter by source_institution ("chime" or "cashapp")
        account_type: Filter by account type ("Checking", "Savings", "Credit", "CashApp")
        limit: Maximum number of transactions to return
        db_path: Path to SQLite database

    Returns:
        List of transaction dictionaries
    """
    conn = get_connection(db_path)

    conditions = []
    params = []

    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)
    if institution:
        conditions.append("source_institution = ?")
        params.append(institution)
    if account_type:
        conditions.append("account_type = ?")
        params.append(account_type)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    query = f"""
        SELECT date, description, amount, balance, tx_type, account_type, source_institution, source_file
        FROM transactions
        WHERE {where_clause}
        ORDER BY date DESC
        LIMIT ?
    """
    params.append(limit)

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()

    conn.close()

    return [
        {
            "date": row["date"],
            "description": row["description"],
            "amount": row["amount"],
            "balance": row["balance"],
            "tx_type": row["tx_type"],
            "account_type": row["account_type"],
            "source_institution": row["source_institution"],
            "source_file": row["source_file"],
        }
        for row in rows
    ]


def get_balance(
    date: str | None = None,
    account_type: str | None = None,
    db_path: Path = Path("finance.db"),
) -> float:
    """Return most recent balance on or before date. Chime only.

    Args:
        date: Date to check balance (ISO format). If None, uses current date.
        account_type: Filter by account type. If None, aggregates all Chime accounts.
        db_path: Path to SQLite database

    Returns:
        Balance amount (float)

    Raises:
        ValueError: If institution is cashapp (CashApp has no balance column)
    """
    conn = get_connection(db_path)

    # Build query for Chime only (CashApp has no balance data)
    conditions = ["source_institution = 'chime'"]
    params = []

    if date:
        conditions.append("date <= ?")
        params.append(date)
    if account_type:
        conditions.append("account_type = ?")
        params.append(account_type)

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT balance
        FROM transactions
        WHERE {where_clause} AND balance IS NOT NULL
        ORDER BY date DESC
        LIMIT 1
    """

    cursor = conn.execute(query, params)
    row = cursor.fetchone()

    conn.close()

    if row is None or row["balance"] is None:
        return 0.0

    return float(row["balance"])


def get_spending_by_category(
    month: str,
    institution: str | None = None,
    db_path: Path = Path("finance.db"),
) -> dict[str, float]:
    """Return {category: total_outflow} for the given month.

    Args:
        month: Month to analyze (ISO format: "2024-03")
        institution: Filter by institution ("chime" or "cashapp")
        db_path: Path to SQLite database

    Returns:
        Dictionary mapping category to total outflow (negative amounts)
    """
    # Import inside function to keep queries.py testable without categories.yaml
    from chime_ingestor.categorizer import categorize, load_categories

    conn = get_connection(db_path)

    # Build date range for the month
    start_date = f"{month}-01"
    if month.endswith("-12"):
        year = int(month[:4]) + 1
        end_date = f"{year}-01-01"
    else:
        month_num = int(month[5:7]) + 1
        end_month = f"{month_num:02d}"
        end_date = f"{month[:4]}-{end_month}-01"

    conditions = ["date >= ?", "date < ?", "amount < 0"]
    params = [start_date, end_date]

    if institution:
        conditions.append("source_institution = ?")
        params.append(institution)

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT description, amount
        FROM transactions
        WHERE {where_clause}
    """

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()

    conn.close()

    # Load categories and categorize each transaction
    try:
        categories = load_categories()
    except FileNotFoundError:
        # If no categories file, return all as Uncategorized
        total = sum(float(row["amount"]) for row in rows)
        return {"Uncategorized": total} if rows else {}

    spending: dict[str, float] = {}
    for row in rows:
        description = row["description"]
        amount = float(row["amount"])
        category = categorize(description, categories)
        spending[category] = spending.get(category, 0.0) + amount

    return spending


def get_spending_trends(
    months: int = 6,
    db_path: Path = Path("finance.db"),
) -> list[dict]:
    """Return monthly summary for last N months.

    Args:
        months: Number of months to analyze
        db_path: Path to SQLite database

    Returns:
        List of dicts with keys: month, inflow, outflow, net
    """
    conn = get_connection(db_path)

    # Get monthly aggregations
    query = """
        SELECT
            strftime('%Y-%m', date) as month,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as inflow,
            SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as outflow
        FROM transactions
        GROUP BY month
        ORDER BY month DESC
        LIMIT ?
    """

    cursor = conn.execute(query, (months,))
    rows = cursor.fetchall()

    conn.close()

    trends = []
    for row in rows:
        inflow = float(row["inflow"]) if row["inflow"] else 0.0
        outflow = float(row["outflow"]) if row["outflow"] else 0.0
        trends.append({
            "month": row["month"],
            "inflow": inflow,
            "outflow": outflow,
            "net": inflow + outflow,
        })

    return trends
