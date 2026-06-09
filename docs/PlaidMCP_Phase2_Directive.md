# PlaidMCP — Phase 2 Directive: Registry, CashApp Parser, Batch Ingestor

*June 2026 | Read fully before executing anything.*

---

> ⛔ **STOP:** Run pytest before touching any file.
> Must report **28 passing, 0 failing, 0 skipped**.
> If count differs, stop and report — do not proceed.

---

## §0 Context

**What exists:**
- `chime_ingestor/parser.py` — Chime-only regex parser, 28 certified tests passing
- `chime_ingestor/models.py` — `ChimeTransaction` dataclass with `source_institution` field
- `data/Chime/` — 108 PDFs (36 Checking, 36 Savings, 36 Credit)
- `data/CashApp/` — 49 PDFs, generic numbered filenames, no date in filename
- ADR-006 — parser registry pattern locked

**What this phase delivers:**
- §2a: Parser registry refactor — Chime logic moved to `parsers/chime_parser.py`, registry dispatch in `parsers/__init__.py`
- §2b: CashApp parser — `parsers/cashapp_parser.py` with year inference from PDF header
- §2c: SQLite schema, batch ingestor, CLI — all 157 PDFs ingested into `finance.db`

**What is NOT in scope:**
- Query layer (Phase 3)
- MCP tool layer (Phase 4)
- Any attempt to fetch the missing Checking March 2024 statement
- Category classification
- CashApp fee reconciliation beyond storing raw fee value

**Gate rule:** Stop and report pytest output after each section (§2a, §2b, §2c) before proceeding to the next. Do not chain sections without a human-visible checkpoint.

---

## §1 Scope Statement

| File | Status | Action |
|---|---|---|
| `parsers/__init__.py` | New | Registry dispatch — routes PDF to correct parser by institution |
| `parsers/chime_parser.py` | New | Chime logic extracted from `chime_ingestor/parser.py` |
| `parsers/cashapp_parser.py` | New | CashApp regex parser with year inference |
| `chime_ingestor/parser.py` | Modify | Thin shim — imports and re-exports from `parsers/chime_parser.py` |
| `chime_ingestor/db.py` | New | SQLite schema, upsert, ingestion log |
| `chime_ingestor/ingestor.py` | New | Batch runner — processes all PDFs in a directory |
| `chime_ingestor/cli.py` | New | `python -m chime_ingestor ingest <data_dir>` |
| `tests/test_registry.py` | New | Registry dispatch unit tests |
| `tests/test_cashapp_parser.py` | New | CashApp parser unit tests |
| `tests/test_db.py` | New | Schema, upsert, deduplication tests |
| `tests/test_ingestor.py` | New | Batch runner tests (mock filesystem) |
| `docs/state/current.md` | Modify | Update at end of phase |

**Read-only — do not touch:**
`chime_ingestor/models.py`, `tests/test_parser.py`, `docs/adr/ADR-001.md` through `ADR-006.md`

Report before fixing any bug found in read-only files. Do not silently modify out-of-scope files.

---

## §2 Implementation

### §2a — Parser Registry Refactor

**`parsers/__init__.py`**

```python
from pathlib import Path
from typing import Protocol
from chime_ingestor.models import ChimeTransaction

class PDFParser(Protocol):
    def parse(self, path: Path) -> list[ChimeTransaction]: ...

def get_parser(institution: str) -> PDFParser:
    if institution == "chime":
        from parsers.chime_parser import ChimeParser
        return ChimeParser()
    if institution == "cashapp":
        from parsers.cashapp_parser import CashAppParser
        return CashAppParser()
    raise ValueError(f"Unknown institution: {institution}")

def detect_institution(path: Path) -> str:
    """Detect institution from parent directory name."""
    parent = path.parent.name.lower()
    if "chime" in parent:
        return "chime"
    if "cashapp" in parent or "cash" in parent:
        return "cashapp"
    raise ValueError(f"Cannot detect institution from path: {path}")

def parse_pdf(path: Path) -> list[ChimeTransaction]:
    institution = detect_institution(path)
    parser = get_parser(institution)
    return parser.parse(path)
```

> ⚠️ RULE: Institution detection is directory-based only. Never inspect PDF content to detect institution — that creates circular dependency with the parsers.

**`parsers/chime_parser.py`**

Extract all existing logic from `chime_ingestor/parser.py` verbatim. No changes to logic — pure extraction. The `ChimeParser.parse()` method wraps the existing `parse_pdf()` function.

**`chime_ingestor/parser.py`** (shim)

```python
# Compatibility shim — do not add logic here
from parsers import parse_pdf
__all__ = ["parse_pdf"]
```

> ⚠️ RULE: After §2a, run pytest. Must still report 28/0/0. If any test fails, the extraction broke something — fix before proceeding to §2b.

---

### §2b — CashApp Parser

**`parsers/cashapp_parser.py`**

CashApp PDF format (confirmed from inspection):
- 5 columns: DATE | DESCRIPTION | DETAILS | FEE | AMOUNT
- Date format: `Apr 8` (no year — must be inferred)
- Amount format: `+$2.40` or `-$50.00`
- Fee format: `$0.00` (always present, often zero)

**Year inference — critical:**

CashApp PDFs have generic numbered filenames. The year is not in the filename. Extract it from the PDF header text, which contains a statement period such as `April 1 – April 30, 2024` or `Statement Period: Apr 2024`.

```python
def _extract_statement_year(self, text: str) -> int:
    """Extract year from statement period in PDF header text."""
    # Match patterns like "April 1 – April 30, 2024" or "Apr 2024"
    match = re.search(r'\b(20\d{2})\b', text[:500])  # Year in first 500 chars
    if match:
        return int(match.group(1))
    raise ValueError("Cannot determine statement year from PDF header")
```

> ⚠️ RULE: Never assume the current year for CashApp dates. If `_extract_statement_year` raises, the parse for that file must fail loudly with the filename in the error message. Do not silently default to any year.

**Amount parsing:**

```python
def _parse_amount(self, amount_str: str, fee_str: str) -> float:
    """Parse CashApp amount. Positive = inflow, negative = outflow."""
    clean = amount_str.replace('$', '').replace(',', '').strip()
    amount = float(clean)  # sign already present as +/-
    fee = float(fee_str.replace('$', '').strip())
    # Return net amount (amount already includes sign)
    # Store fee separately in ChimeTransaction.tx_type or notes field
    return amount
```

> ⚠️ RULE: The fee value must be preserved. Add a `fee: float = 0.0` field to `ChimeTransaction` in `models.py` — this is the only permitted modification to a read-only file, and only because CashApp requires it. Report before making this change.

**`CashAppParser.parse()` signature:**
```python
def parse(self, path: Path) -> list[ChimeTransaction]:
    ...
```

Sets `source_institution = "cashapp"` on every returned transaction.

> ⚠️ RULE: After §2b, stop and report pytest count before touching any db or ingestor file.

---

### §2c — SQLite Schema, Batch Ingestor, CLI

**`chime_ingestor/db.py`**

```python
SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    description     TEXT NOT NULL,
    amount          REAL NOT NULL,
    balance         REAL,
    fee             REAL DEFAULT 0.0,
    tx_type         TEXT,
    account_type    TEXT,
    source_institution TEXT NOT NULL,
    source_file     TEXT NOT NULL,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_file, date, description, amount)
);

CREATE TABLE IF NOT EXISTS ingestion_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file     TEXT NOT NULL,
    source_hash     TEXT NOT NULL,
    record_count    INTEGER,
    status          TEXT,
    ingested_at     TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

def get_connection(db_path: Path) -> sqlite3.Connection: ...
def create_schema(conn: sqlite3.Connection) -> None: ...
def upsert_transactions(conn, transactions: list[ChimeTransaction]) -> int: ...
def log_ingestion(conn, source_file: str, source_hash: str, count: int, status: str) -> None: ...
def is_already_ingested(conn, source_hash: str) -> bool: ...
```

> ⚠️ RULE: `upsert_transactions` uses `INSERT OR IGNORE` against the UNIQUE constraint. Never use `INSERT OR REPLACE` — it changes the row id and breaks audit trails.

**`chime_ingestor/ingestor.py`**

```python
def ingest_directory(data_dir: Path, db_path: Path) -> dict:
    """
    Process all PDFs in data_dir and subdirectories.
    Skips files already in ingestion_log by hash.
    Returns: {processed: int, skipped: int, failed: list[str]}
    """
```

> ⚠️ RULE: Failed files are collected and reported at the end — never halt the batch on a single parse failure. A parse failure writes status="failed" to ingestion_log with the error message.

**`chime_ingestor/cli.py`**

```python
# Usage: python -m chime_ingestor ingest <data_dir> [--db finance.db]
```

Prints summary on completion:
```
Processed: 157 files
Skipped (already ingested): 0
Failed: 0
Total transactions: XXXX
```

---

## §3 Test Anchors

| Test | File | Behaviour |
|---|---|---|
| `test_detect_institution_chime` | `test_registry.py` | Path with `Chime` parent → `"chime"` |
| `test_detect_institution_cashapp` | `test_registry.py` | Path with `CashApp` parent → `"cashapp"` |
| `test_detect_institution_unknown` | `test_registry.py` | Unknown parent → raises `ValueError` |
| `test_get_parser_chime` | `test_registry.py` | Returns `ChimeParser` instance |
| `test_get_parser_cashapp` | `test_registry.py` | Returns `CashAppParser` instance |
| `test_cashapp_year_extraction` | `test_cashapp_parser.py` | Header text `"April 1 – April 30, 2024"` → year `2024` |
| `test_cashapp_year_missing_raises` | `test_cashapp_parser.py` | No year in header → raises `ValueError` with filename |
| `test_cashapp_date_parse` | `test_cashapp_parser.py` | `"Apr 8"` + year 2024 → `date == "2024-04-08"` |
| `test_cashapp_amount_positive` | `test_cashapp_parser.py` | `"+$2.40"` → `amount == 2.40` |
| `test_cashapp_amount_negative` | `test_cashapp_parser.py` | `"-$50.00"` → `amount == -50.00` |
| `test_cashapp_fee_preserved` | `test_cashapp_parser.py` | `fee="$1.50"` → `transaction.fee == 1.50` |
| `test_cashapp_source_institution` | `test_cashapp_parser.py` | All transactions → `source_institution == "cashapp"` |
| `test_schema_creation` | `test_db.py` | `create_schema()` creates both tables |
| `test_upsert_inserts` | `test_db.py` | New transaction → inserted, count +1 |
| `test_upsert_deduplicates` | `test_db.py` | Same transaction twice → only 1 row |
| `test_ingestion_log_written` | `test_db.py` | After upsert → log row exists with correct count |
| `test_already_ingested_true` | `test_db.py` | File hash in log → `True` |
| `test_already_ingested_false` | `test_db.py` | Unknown hash → `False` |
| `test_ingestor_skips_ingested` | `test_ingestor.py` | Pre-logged hash → skipped, not re-parsed |
| `test_ingestor_failed_continues` | `test_ingestor.py` | One bad PDF → rest of batch continues |
| `test_ingestor_summary` | `test_ingestor.py` | Returns correct processed/skipped/failed counts |

All external calls mocked. No real PDFs read during tests. No real SQLite file written — use `:memory:`.

**Target floor: 65 passing, 0 failing, 0 skipped**

---

## §4 Completion Criteria

- [ ] Pre-flight: 28/0/0 confirmed before any file touched
- [ ] §2a complete: pytest reports ≥28/0/0, Chime parser behaviour unchanged
- [ ] §2b complete: CashApp parser tested, year inference confirmed, pytest floor reported
- [ ] §2c complete: `python -m chime_ingestor ingest data/` runs without error
- [ ] `finance.db` exists with transactions from both institutions
- [ ] `SELECT COUNT(*) FROM transactions` returns a real number (report it)
- [ ] `SELECT COUNT(*) FROM ingestion_log` returns 157 (report it)
- [ ] Second run of ingest produces 0 new rows (idempotency confirmed)
- [ ] `ingestion_log` contains a row for the missing March 2024 Checking statement if re-added, or notes its absence
- [ ] pytest final floor: **65 passing, 0 failing, 0 skipped**
- [ ] `docs/state/current.md` updated

---

## §5 Quick Reference

| Key | Value |
|---|---|
| Pre-flight floor | 28/0/0 |
| Target floor | 65/0/0 |
| Chime PDF count | 108 (36 Checking, 36 Savings, 36 Credit) |
| CashApp PDF count | 49 |
| Total PDFs | 157 |
| Known gap | Checking March 2024 — ingest if present, skip if absent |
| Data paths | `data/Chime/`, `data/CashApp/` |
| DB file | `finance.db` (gitignored) |
| DB test mode | `:memory:` only — never write to `finance.db` during tests |
| CashApp date source | PDF header text, first 500 chars |
| Deduplication key | `UNIQUE(source_file, date, description, amount)` |
| Upsert method | `INSERT OR IGNORE` — never `INSERT OR REPLACE` |
| Institution detection | Parent directory name — never PDF content inspection |
| Gate rule | Stop and report pytest after each of §2a, §2b, §2c |
