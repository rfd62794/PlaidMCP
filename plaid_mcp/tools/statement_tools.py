"""
Tools for raw statement inspection and data verification.
"""
import os
from pathlib import Path

import pdfplumber

DATA_DIR = Path(os.getenv("PLAID_DATA_DIR", "data"))


def get_raw_statement_text(source_file: str, page: int | None = None) -> dict:
    """
    Return raw pdfplumber text extract for a specific source file.
    Used for data verification — compare raw PDF against parsed DB records.

    source_file: filename as stored in DB e.g.
        'Chime-Credit-Statement-May-2026.pdf'
        'monthly-statement.pdf'
    page: optional — return only this page number (1-indexed).
          If None, returns all pages concatenated.

    Returns: {source_file, page_count, text, pages: [str]}
    """
    # Search for file recursively under DATA_DIR
    matches = list(DATA_DIR.rglob(source_file))
    if not matches:
        return {"error": f"File not found: {source_file}", "searched": str(DATA_DIR)}
    path = matches[0]

    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        if page is not None:
            idx = page - 1
            if idx < 0 or idx >= page_count:
                return {"error": f"Page {page} out of range (1-{page_count})"}
            pages = [pdf.pages[idx].extract_text() or ""]
        else:
            pages = [p.extract_text() or "" for p in pdf.pages]

    return {
        "source_file": source_file,
        "path": str(path),
        "page_count": page_count,
        "text": "\n\n--- PAGE BREAK ---\n\n".join(pages),
        "pages": pages,
    }


def register_statement_tools(mcp):
    """Register statement tools with the MCP server."""
    mcp.tool()(get_raw_statement_text)
