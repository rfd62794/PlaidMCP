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


def get_top_merchants(
    month: str,
    limit: int = 20,
    account_type: str | None = None,
    institution: str | None = None,
    db_path: Path = Path("finance.db"),
) -> list[dict]:
    """Return top merchants by total spend for a given month.

    Args:
        month: Month to analyze ("2026-05" format)
        limit: Maximum number of merchants to return
        account_type: Filter by account type
        institution: Filter by institution
        db_path: Path to SQLite database

    Returns:
        List of dicts with keys: description, total, count, avg
    """
    conn = get_connection(db_path)

    conditions = ["date LIKE ?", "amount < 0"]
    params = [f"{month}%"]

    if account_type:
        conditions.append("account_type = ?")
        params.append(account_type)
    if institution:
        conditions.append("source_institution = ?")
        params.append(institution)

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT
            description,
            ROUND(SUM(amount), 2) as total,
            COUNT(*) as count,
            ROUND(AVG(amount), 2) as avg
        FROM transactions
        WHERE {where_clause}
        GROUP BY description
        ORDER BY total ASC
        LIMIT ?
    """
    params.append(limit)

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()

    conn.close()

    return [
        {
            "description": row["description"],
            "total": float(row["total"]),
            "count": row["count"],
            "avg": float(row["avg"]),
        }
        for row in rows
    ]


def search_transactions(
    description_contains: str,
    month: str | None = None,
    institution: str | None = None,
    limit: int = 100,
    db_path: Path = Path("finance.db"),
) -> list[dict]:
    """Search transactions by description (case-insensitive substring match).

    Args:
        description_contains: Search string to match in description
        month: Optional month filter ("2026-05" format)
        institution: Optional institution filter
        limit: Maximum results to return
        db_path: Path to SQLite database

    Returns:
        List of transaction dictionaries
    """
    conn = get_connection(db_path)

    conditions = ["LOWER(description) LIKE LOWER(?)"]
    params = [f"%{description_contains}%"]

    if month:
        conditions.append("date LIKE ?")
        params.append(f"{month}%")
    if institution:
        conditions.append("source_institution = ?")
        params.append(institution)

    where_clause = " AND ".join(conditions)

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


def get_net_spending(
    month: str,
    db_path: Path = Path("finance.db"),
) -> dict:
    """Return real spending for a month with internal transfers excluded.

    Loads categories from config/categories.yaml and excludes any transactions
    matching the "Internal Transfer" category keywords.

    Args:
        month: Month to analyze ("2026-05" format)
        db_path: Path to SQLite database

    Returns:
        Dict with total_outflow, total_inflow, net, excluded_transfer_volume, by_category
    """
    from chime_ingestor.categorizer import categorize, load_categories

    conn = get_connection(db_path)

    # Load all transactions for the month
    cursor = conn.execute(
        "SELECT date, description, amount FROM transactions WHERE date LIKE ?",
        (f"{month}%",)
    )
    rows = cursor.fetchall()
    conn.close()

    # Load categories
    try:
        categories = load_categories()
    except FileNotFoundError:
        categories = {"Uncategorized": []}

    # Calculate totals with internal transfers excluded
    total_outflow = 0.0
    total_inflow = 0.0
    excluded_transfer_volume = 0.0
    by_category: dict[str, float] = {}

    for row in rows:
        description = row["description"]
        amount = float(row["amount"])
        category = categorize(description, categories)

        if category == "Internal Transfer":
            excluded_transfer_volume += abs(amount)
            continue

        if amount < 0:
            total_outflow += amount
        else:
            total_inflow += amount

        by_category[category] = by_category.get(category, 0.0) + amount

    return {
        "month": month,
        "total_outflow": round(total_outflow, 2),
        "total_inflow": round(total_inflow, 2),
        "net": round(total_outflow + total_inflow, 2),
        "excluded_transfer_volume": round(excluded_transfer_volume, 2),
        "by_category": {k: round(v, 2) for k, v in by_category.items()},
    }


def execute_readonly_query(
    sql: str,
    params: dict | None = None,
    limit: int = 500,
    db_path: Path = Path("finance.db"),
) -> list[dict]:
    """Execute a read-only SQL query against finance.db.

    SELECT statements only. Max 500 rows returned.

    Args:
        sql: SELECT query to execute
        params: Optional query parameters
        limit: Maximum rows to return (capped at 500)
        db_path: Path to SQLite database

    Returns:
        List of rows as dictionaries

    Raises:
        ValueError: If SQL is not a SELECT statement
    """
    # Validate SQL starts with SELECT
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        raise ValueError("Only SELECT statements permitted")

    # Check if LIMIT is already present
    has_limit = "LIMIT" in stripped

    # Cap limit at 500
    effective_limit = min(limit, 500)

    conn = get_connection(db_path)

    if not has_limit:
        sql = f"{sql.rstrip(';')} LIMIT {effective_limit}"

    cursor = conn.execute(sql, params or {})
    rows = cursor.fetchall()

    conn.close()

    return [dict(row) for row in rows]


def get_annual_summary(
    year: str,
    db_path: Path = Path("finance.db"),
) -> dict:
    """Return 12-month breakdown for a given year.

    Uses get_net_spending logic (internal transfers excluded) per month.

    Args:
        year: Year to analyze ("2026" format)
        db_path: Path to SQLite database

    Returns:
        Dict with year, months list, and annual_totals
    """
    months = []
    annual_outflow = 0.0
    annual_inflow = 0.0
    annual_net = 0.0
    annual_excluded = 0.0

    for month_num in range(1, 13):
        month_str = f"{year}-{month_num:02d}"
        month_data = get_net_spending(month_str, db_path)

        # Skip months with no transactions
        if month_data["total_outflow"] == 0 and month_data["total_inflow"] == 0:
            continue

        months.append({
            "month": month_str,
            "outflow": month_data["total_outflow"],
            "inflow": month_data["total_inflow"],
            "net": month_data["net"],
            "excluded": month_data["excluded_transfer_volume"],
        })

        annual_outflow += month_data["total_outflow"]
        annual_inflow += month_data["total_inflow"]
        annual_net += month_data["net"]
        annual_excluded += month_data["excluded_transfer_volume"]

    return {
        "year": year,
        "months": months,
        "annual_totals": {
            "outflow": round(annual_outflow, 2),
            "inflow": round(annual_inflow, 2),
            "net": round(annual_net, 2),
            "excluded_transfer_volume": round(annual_excluded, 2),
        },
    }
