# Chime Ingestor — Current State

*June 8, 2026*

## Phase Status

| Phase | Status | Tests | Target |
|-------|--------|-------|--------|
| Phase 1 — Foundation + Single PDF Parser | **COMPLETE** | 28 passing | 15 |
| Phase 1.5 — Data Discovery & ADR-006 | **COMPLETE** | — | — |
| Phase 2 — Batch Ingestor + SQLite | **COMPLETE** | 79 passing | 35 |
| Phase 3 — Query Layer | **COMPLETE** | 94 passing | 50 |
| Phase 4 — MCP Tool Layer | **COMPLETE** | 102 passing | 60 |
| Phase 5 — Category Refinement + Analysis Tools | **COMPLETE** | 115 passing | 75 |

## Ingestion Results

| Metric | Value |
|--------|-------|
| Total PDFs processed | 278 |
| Chime PDFs | 108 (Checking: 35*, Savings: 36, Credit: 36) |
| CashApp PDFs | 49 |
| **Total transactions** | **10,968** |
| **Ingestion log entries** | **157** (unique files, deduplicated) |
| Idempotency verified | ✅ Second run: Processed: 0, Skipped: 157 |

*Checking missing March 2024 — data gap confirmed

## Phase 4 Tools (MCP Layer)

| Tool | Function |
|------|----------|
| `get_transactions` | Filtered transaction query |
| `get_balance` | Chime balance lookup |
| `get_spending_by_category` | Monthly spending by category |
| `get_spending_trends` | N-month trend analysis |
| `get_summary` | Database overview |
| `get_ingestion_status` | Ingestion log |

**MCP Server:** `plaid_mcp/server.py` — FastMCP stdio transport
**Entry point:** `uv run plaid-mcp`

**278 Anomaly Investigation:**
- **Actual PDF count:** 157 (verified by `find data/ -name "*.pdf" | wc -l`)
- **Root cause:** `rglob()` found CashApp PDFs at multiple paths during first ingestion
- **Fix:** Path deduplication by hash in `ingestor.py` + SQL cleanup of `ingestion_log`
- **Result:** 157 unique files, 157 log entries, 10,968 transactions

**Database:** `finance.db` (2.5MB, gitignored)

## Phase 5 — Real Spending Analysis

**Problem solved:** Internal transfers were inflating outflows by ~$16k/month. Now excluded via "Internal Transfer" category.

**New tools:**
| Tool | Function |
|------|----------|
| `get_top_merchants(month, limit)` | GROUP BY description, aggregate spend |
| `search_transactions(description, month)` | Case-insensitive merchant lookup |
| `get_net_spending(month)` | Real spending with internal transfers excluded |

**May 2026 real spending (excluded $26k internal):**
- Total outflow: -$1,942.35
- Top categories: Food & Dining ($356), Gas & Convenience ($342), Subscriptions ($286)

## Data Reorganization

**Files moved to subdirectories:**
- `data/Chime/` — 108 PDFs (36 Checking, 36 Savings, 36 Credit)
- `data/CashApp/` — 49 PDFs (generic numbered filenames)

## Missing Statement Gap Analysis

| Account | Count | Range | Status |
|---------|-------|-------|--------|
| Checking | 35 | 2023-06 → 2026-05 | **Missing March 2024** |
| Savings | 36 | 2023-06 → 2026-05 | ✓ Complete |
| Credit | 36 | 2023-06 → 2026-05 | ✓ Complete |

**Gap**: Checking missing **March 2024** (2024-03). This is likely a download omission, not a missing statement period.

## CashApp Discovery (Phase 0 for ADR-006)

**Critical finding**: CashApp PDFs use a **fundamentally different layout** than Chime.

| Aspect | Chime | CashApp |
|--------|-------|---------|
| **Date format** | `1/31/2025` (M/D/YYYY) | `Apr 8` (Mon D) |
| **Columns** | 6 (DATE, DESC, TYPE, AMOUNT, BALANCE, SETTLEMENT) | 5 (DATE, DESC, DETAILS, FEE, AMOUNT) |
| **Amount format** | `-$50.00` or `$200.00` | `$0.00 + $2.40` (fee shown separately) |
| **Polarity** | Negative sign for outflows | `+` / implicit `-` indicators |
| **Transaction types** | Transfer, Purchase, Direct Deposit | Cash App payment, Cash App Card, ATM withdrawal, Direct deposit |

**Conclusion**: Single regex parser won't work. Requires **multi-institution parser registry** (ADR-006).

## ADR-006: Multi-Institution Parser Registry

**Status**: Documented, awaiting implementation

**Decision**: Registry pattern with institution-specific parsers:
- `BaseParser` abstract interface
- `ChimeParser` — existing regex logic
- `CashAppParser` — new implementation for CashApp layout
- `PARSER_REGISTRY` — dispatch by institution name
- Institution detection via filename patterns

**Schema change**: `source_institution` field added to `ChimeTransaction` (default: "chime")

## What Works

### Parser (`chime_ingestor/parser.py`)
- **Text-based regex extraction**: Chime PDFs don't contain actual table structures
- **Three account types supported**: Checking, Savings, Credit — all tested
- **Transaction extraction**: Parses date, description, type, amount, balance, settlement date
- **Idempotent ready**: `source_file`, `account_type`, `source_institution` metadata

### Models (`chime_ingestor/models.py`)
- `ChimeTransaction` dataclass with frozen/slots for immutability and memory efficiency
- Validation: rejects zero amounts, empty descriptions
- Properties: `is_outflow`, `is_inflow`, `to_dict()` for serialization

### Test Coverage (`tests/test_parser.py`)
- 28 unit tests covering:
  - Account type detection from filenames
  - Date parsing (M/D/YYYY format)
  - Amount parsing ($ with polarity)
  - Transaction type normalization
  - Text extraction regex matching
  - Model validation and properties
  - Integration tests with real PDFs

## Test Results

```
============================= 28 passed in 3.26s =============================
```

## Verified Against Real Data

| Account | PDFs Tested | Transactions Extracted | Status |
|---------|-------------|------------------------|--------|
| Checking | 1 (Jan 2025) | 239 | ✓ |
| Savings | 1 (Jan 2025) | 93 | ✓ |
| Credit | 1 (Jan 2025) | 66 | ✓ |

**Total available PDFs**: 107 (36 Checking, 35 Savings, 36 Credit)

## Known Limitations

1. **Date format**: Only supports M/D/YYYY. If Chime changes format, parser needs update.
2. **Transaction type detection**: Uses substring matching with longest-first sort (so "Direct Deposit" matches before "Deposit").
3. **Layout sensitivity**: If Chime changes PDF text layout, regex patterns may need adjustment.

## Bug Fixes During Phase 1

**Issue**: Transaction type matching was non-deterministic due to set iteration order. "Deposit" would sometimes match before "Direct Deposit".

**Fix**: Sort known types by length (longest first) in `_find_transaction_type()` so specific types match before general ones.

## Next: Phase 2

Files to create:
- `chime_ingestor/db.py` — SQLite schema, upsert, ingestion_log
- `chime_ingestor/ingestor.py` — batch runner with SHA256 hash check
- `chime_ingestor/cli.py` — `python -m chime_ingestor ingest /data`
- `tests/test_db.py`, `tests/test_ingestor.py` — unit tests

Database schema already defined in SDD:
- `transactions` table with composite unique key `(source_file, date, description, amount)`
- `ingestion_log` table for audit trail

## Files Created (Phase 1)

```
chime-ingestor/
├── chime_ingestor/
│   ├── __init__.py
│   ├── models.py          ← ChimeTransaction dataclass
│   └── parser.py          ← parse_pdf() with regex extraction
├── tests/
│   ├── __init__.py
│   └── test_parser.py     ← 28 unit tests
├── docs/
│   └── state/
│       └── current.md     ← this file
├── pyproject.toml         ← project config with pytest settings
└── .venv/                 ← uv-managed virtual environment
```

## Data Discovery

Original SDD assumed 108 PDFs. Actual count: **107 PDFs**
- Chime-Checking-Statement: 36 PDFs (July 2023 - June 2026)
- Chime-Savings-Statement: 35 PDFs (missing July 2023 or June 2026)
- Chime-Credit-Statement: 36 PDFs (July 2023 - June 2026)

All three account types present. Date range: ~3 years of transaction history.
