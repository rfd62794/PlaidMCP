"""Batch ingestor for processing PDF directories."""
from pathlib import Path

from parsers import detect_institution, get_parser
from chime_ingestor.db import (
    compute_file_hash,
    create_schema,
    get_connection,
    is_already_ingested,
    log_ingestion,
    upsert_transactions,
)


def ingest_directory(data_dir: Path, db_path: Path) -> dict:
    """Process all PDFs in data_dir and subdirectories.

    Skips files already in ingestion_log by hash.
    Failed files are collected and reported at the end.

    Args:
        data_dir: Root directory containing PDFs
        db_path: Path to SQLite database

    Returns:
        Dict with keys: processed, skipped, failed, total_transactions
    """
    conn = get_connection(db_path)
    create_schema(conn)

    stats = {
        "processed": 0,
        "skipped": 0,
        "failed": [],
        "total_transactions": 0,
    }

    # Find all PDF files recursively
    pdf_files = list(data_dir.rglob("*.pdf"))

    for pdf_path in pdf_files:
        try:
            # Compute file hash for idempotency check
            file_hash = compute_file_hash(pdf_path)

            if is_already_ingested(conn, file_hash):
                stats["skipped"] += 1
                continue

            # Detect institution and get appropriate parser
            institution = detect_institution(pdf_path)
            parser = get_parser(institution)

            # Parse PDF
            transactions = parser.parse(pdf_path)

            # Upsert to database
            inserted = upsert_transactions(conn, transactions)
            stats["total_transactions"] += inserted

            # Log successful ingestion
            log_ingestion(conn, pdf_path.name, file_hash, len(transactions), "success")
            stats["processed"] += 1

        except Exception as e:
            # Log failed ingestion
            error_msg = str(e)
            try:
                file_hash = compute_file_hash(pdf_path) if pdf_path.exists() else "unknown"
            except:
                file_hash = "unknown"

            log_ingestion(conn, pdf_path.name, file_hash, 0, f"failed: {error_msg}")
            stats["failed"].append(f"{pdf_path.name}: {error_msg}")

    conn.close()
    return stats
