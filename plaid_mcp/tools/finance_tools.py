"""Async MCP tool wrappers for finance queries."""
import os
from pathlib import Path

from chime_ingestor.db import get_connection
from chime_ingestor.queries import (
    get_balance as _get_balance,
    get_spending_by_category as _get_spending_by_category,
    get_spending_trends as _get_spending_trends,
    get_transactions as _get_transactions,
)


def _db_path() -> Path:
    """Get database path from environment or default."""
    return Path(os.getenv("PLAID_DB_PATH", "finance.db"))


async def get_transactions(
    start_date: str | None = None,
    end_date: str | None = None,
    institution: str | None = None,
    account_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    Return transactions filtered by date range, institution, or account type.

    Args:
        start_date: Filter transactions on or after this date (ISO format: "2024-03-15")
        end_date: Filter transactions on or before this date (ISO format: "2024-03-15")
        institution: 'chime' | 'cashapp' | None (all)
        account_type: 'Checking' | 'Savings' | 'Credit' | None (all)
        limit: max rows returned (default 50, max 500)

    Returns:
        List of transaction dictionaries
    """
    try:
        # Clamp limit to max 500
        if limit > 500:
            limit = 500
        if limit < 1:
            limit = 50

        db_path = _db_path()
        return _get_transactions(
            start_date=start_date,
            end_date=end_date,
            institution=institution,
            account_type=account_type,
            limit=limit,
            db_path=db_path,
        )
    except Exception as e:
        return [{"error": str(e)}]


async def get_balance(
    date: str | None = None,
    account_type: str | None = None,
) -> dict:
    """
    Return most recent Chime balance on or before date.

    Args:
        date: ISO string e.g. '2026-05-31' — defaults to today.
        account_type: Filter by account type (Checking, Savings, Credit)

    Returns:
        Dict with balance or error

    Note:
        CashApp excluded (no balance data). Only Chime accounts have balance.
    """
    try:
        db_path = _db_path()
        balance = _get_balance(
            date=date,
            account_type=account_type,
            db_path=db_path,
        )
        return {"balance": balance}
    except Exception as e:
        return {"error": str(e)}


async def get_spending_by_category(
    month: str,
    institution: str | None = None,
) -> dict:
    """
    Return outflow totals by category for a given month.

    Args:
        month: '2026-05' format.
        institution: 'chime' | 'cashapp' | None (all)

    Returns:
        Dict mapping {category: total_outflow} — outflows are negative floats.
    """
    try:
        db_path = _db_path()
        return _get_spending_by_category(
            month=month,
            institution=institution,
            db_path=db_path,
        )
    except Exception as e:
        return {"error": str(e)}


async def get_spending_trends(
    months: int = 6,
) -> list[dict]:
    """
    Return monthly inflow/outflow/net summary for last N months.

    Args:
        months: Number of months to analyze (default 6)

    Returns:
        List of dicts [{month, inflow, outflow, net}] newest first.
    """
    try:
        db_path = _db_path()
        return _get_spending_trends(
            months=months,
            db_path=db_path,
        )
    except Exception as e:
        return [{"error": str(e)}]


async def get_summary() -> dict:
    """
    Return overview of finance.db contents.

    Returns:
        Dict with total_transactions, institutions, date_range, db_size_mb
    """
    try:
        db_path = _db_path()
        conn = get_connection(db_path)

        # Total transactions
        cursor = conn.execute("SELECT COUNT(*) FROM transactions")
        total_transactions = cursor.fetchone()[0]

        # Institutions
        cursor = conn.execute("SELECT DISTINCT source_institution FROM transactions")
        institutions = [row[0] for row in cursor.fetchall()]

        # Date range
        cursor = conn.execute("SELECT MIN(date), MAX(date) FROM transactions")
        min_date, max_date = cursor.fetchone()

        # DB size
        db_size_mb = db_path.stat().st_size / (1024 * 1024) if db_path.exists() else 0

        conn.close()

        return {
            "total_transactions": total_transactions,
            "institutions": institutions,
            "date_range": {"min": min_date, "max": max_date},
            "db_size_mb": round(db_size_mb, 2),
        }
    except Exception as e:
        return {"error": str(e)}


async def get_ingestion_status() -> list[dict]:
    """
    Return ingestion log — which files have been processed and when.

    Returns:
        List of log entry dicts ordered by ingested_at desc.
    """
    try:
        db_path = _db_path()
        conn = get_connection(db_path)

        cursor = conn.execute(
            """
            SELECT source_file, source_hash, record_count, status, ingested_at
            FROM ingestion_log
            ORDER BY ingested_at DESC
            """
        )
        rows = cursor.fetchall()

        conn.close()

        return [
            {
                "source_file": row["source_file"],
                "source_hash": row["source_hash"][:16] + "...",
                "record_count": row["record_count"],
                "status": row["status"],
                "ingested_at": row["ingested_at"],
            }
            for row in rows
        ]
    except Exception as e:
        return [{"error": str(e)}]


def register_finance_tools(mcp):
    """Register all finance tools with the MCP server."""
    mcp.tool()(get_transactions)
    mcp.tool()(get_balance)
    mcp.tool()(get_spending_by_category)
    mcp.tool()(get_spending_trends)
    mcp.tool()(get_summary)
    mcp.tool()(get_ingestion_status)
