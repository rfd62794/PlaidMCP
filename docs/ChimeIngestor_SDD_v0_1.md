# Chime PDF Ingestor — SDD v0.1

*June 2026 | RFD IT Services Ltd.*

---

## Purpose

108 Chime PDF statements live in `/data`. They contain the complete financial history of the account but are locked in PDF format with no native export path. This system parses every PDF, extracts transactions into a normalized SQLite database, and exposes a query layer that will become an MCP tool set for Claude-accessible financial analysis.

**End state:** Claude can ask `get_transactions(days=90)` and get real spending data. No Plaid required.

---

## Architecture Overview

```
/data/*.pdf
    ↓
[Phase 1] PDF Parser (pdfplumber)
    → ChimeTransaction dataclass
    ↓
[Phase 2] Batch Ingestor
    → SQLite (finance.db)
    → ingestion_log (audit trail)
    ↓
[Phase 3] Query Layer
    → get_transactions(), get_balance(), get_spending_by_category(), get_trends()
    ↓
[Phase 4] MCP Tool Layer
    → FastAPI MCP server on Tower (NSSM)
    → Claude-accessible tools
```

---

## ADRs

### ADR-001: pdfplumber as PDF parser
**Status:** Accepted  
**Context:** Chime PDFs are clean digital format (not scanned). Multiple parser options exist.  
**Decision:** `pdfplumber` over PyPDF2/pdfminer/camelot. pdfplumber handles text extraction and table detection from clean digital PDFs reliably, is actively maintained, and is the standard for bank statement parsing in Python.  
**Consequences:** pdfplumber is a dependency. camelot deferred permanently (overkill for Chime's simple layout).

---

### ADR-002: SQLite for storage
**Status:** Accepted  
**Context:** 108 PDFs, ~3,000–8,000 estimated transactions. Personal use only.  
**Decision:** SQLite via Python stdlib `sqlite3`. Zero external dependency, queryable, consistent with existing stack (PrivyBot, TeleseroAdmin2026).  
**Consequences:** Not suitable for multi-user or high-concurrency access. Acceptable for personal MCP tool use.

---

### ADR-003: Idempotent ingestion via composite unique key
**Status:** Accepted  
**Context:** Re-running the ingestor across 108 PDFs must not produce duplicate records.  
**Decision:** Unique constraint on `(source_file, date, description, amount)`. Ingestion log tracks processed files by SHA256 hash. Already-processed files are skipped on re-run.  
**Consequences:** Transactions with identical date/description/amount in the same statement period are edge cases — flagged in ingestion log, not silently dropped.

---

### ADR-004: Python 3.11+
**Status:** Accepted  
**Decision:** Consistent with full stack. No exceptions.

---

### ADR-005: Separate ingestion_log table
**Status:** Accepted  
**Decision:** Every ingestion run writes a record: source file, hash, record count, status, timestamp. Provides audit trail and idempotency check without querying the transactions table.

---

## Data Model

### transactions
```sql
CREATE TABLE transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    description     TEXT NOT NULL,
    amount          REAL NOT NULL,
    balance         REAL,
    tx_type         TEXT,
    account_type    TEXT,
    source_file     TEXT NOT NULL,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_file, date, description, amount)
);
```

**amount convention:** positive = inflow (deposit, direct deposit), negative = outflow (purchase, withdrawal).

### ingestion_log
```sql
CREATE TABLE ingestion_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file     TEXT NOT NULL,
    source_hash     TEXT NOT NULL,
    record_count    INTEGER,
    status          TEXT,
    ingested_at     TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

## Phase Map

### Phase 1 — Foundation + Single PDF Parser
**Delivers:** Working parser for one PDF → structured Python objects.

Files:
- `chime_ingestor/parser.py` — `parse_pdf(path: Path) -> list[ChimeTransaction]`
- `chime_ingestor/models.py` — `ChimeTransaction` dataclass
- `tests/test_parser.py` — unit tests against fixture PDF
- `docs/state/current.md`

Target floor: **15 passing, 0 failing, 0 skipped**

---

### Phase 2 — Batch Ingestor + SQLite
**Delivers:** All 108 PDFs ingested into `finance.db`. Idempotent.

Files:
- `chime_ingestor/db.py` — schema creation, upsert, ingestion_log
- `chime_ingestor/ingestor.py` — batch runner, hash check, skip logic
- `chime_ingestor/cli.py` — `python -m chime_ingestor ingest /data`
- `tests/test_ingestor.py` — batch logic tests (mock filesystem)
- `tests/test_db.py` — schema, upsert, deduplication tests

Target floor: **35 passing, 0 failing, 0 skipped**

Proof required: `ingestion_log` shows 108 rows, `SELECT COUNT(*) FROM transactions` returns real number, no duplicates on second run.

---

### Phase 3 — Query Layer
**Delivers:** Python query functions + CLI for human-readable output.

Functions:
- `get_transactions(start_date, end_date, limit=100) -> list[ChimeTransaction]`
- `get_balance(date=None) -> float` — most recent balance on or before date
- `get_spending_by_category(month: str) -> dict[str, float]` — keyword-based categorization
- `get_spending_trends(months=6) -> list[dict]` — monthly inflow/outflow summary

Files:
- `chime_ingestor/queries.py`
- `chime_ingestor/categorizer.py` — keyword → category mapping (YAML-driven)
- `tests/test_queries.py`
- `config/categories.yaml` — editable category rules

Target floor: **50 passing, 0 failing, 0 skipped**

---

### Phase 4 — MCP Tool Layer
**Delivers:** FastAPI MCP server on Tower, tools accessible to Claude.

Tools exposed:
- `get_transactions(days: int)`
- `get_balance()`
- `get_spending_by_category(month: str)`
- `get_spending_trends(months: int)`

Files:
- `chime_ingestor/mcp_server.py` — FastAPI app
- `chime_ingestor/tools.py` — MCP tool wrappers
- Tower NSSM service config

Target floor: **60 passing, 0 failing, 0 skipped**

---

## Directory Structure

```
chime-ingestor/
├── chime_ingestor/
│   ├── __init__.py
│   ├── models.py
│   ├── parser.py
│   ├── db.py
│   ├── ingestor.py
│   ├── queries.py
│   ├── categorizer.py
│   ├── cli.py
│   └── mcp_server.py          ← Phase 4 only
├── config/
│   └── categories.yaml
├── data/                       ← 108 Chime PDFs (gitignored)
├── tests/
│   ├── fixtures/               ← 1-2 anonymized fixture PDFs
│   ├── test_parser.py
│   ├── test_db.py
│   ├── test_ingestor.py
│   └── test_queries.py
├── docs/
│   ├── adr/
│   │   ├── ADR-001.md
│   │   ├── ADR-002.md
│   │   ├── ADR-003.md
│   │   ├── ADR-004.md
│   │   └── ADR-005.md
│   └── state/
│       └── current.md
├── finance.db                  ← gitignored
├── .env                        ← gitignored
├── .gitignore
├── pyproject.toml
└── README.md
```

---

## Open Questions Before Phase 1

1. **Chime PDF layout** — Does Chime use a consistent column layout across all 108 statements, or did the format change over time? One pass through a sample from each year would confirm this before writing the parser.
2. **Account types** — Are all 108 PDFs from a single Chime Checking account, or are Savings statements also in `/data`? Affects the parser's column assumptions.
3. **Repo location** — New private repo on `rfd62794`, or does this live inside an existing repo?
4. **Fixture PDF** — One anonymized PDF needed in `tests/fixtures/` for parser unit tests. Sensitive data scrubbed or replaced with synthetic values.

---

## What This Is Not

- Not a budgeting app
- Not a multi-institution aggregator (Plaid deferred indefinitely)
- Not a real-time data feed — batch ingestion only
- Not public — private repo, personal financial data

---

*SDD v0.1 | Phase 1 directive ready once open questions resolved.*
