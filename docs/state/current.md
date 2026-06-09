# Chime Ingestor — Current State

*June 8, 2026*

## Phase Status

| Phase | Status | Tests | Target |
|-------|--------|-------|--------|
| Phase 1 — Foundation + Single PDF Parser | **COMPLETE** | 28 passing | 15 |
| Phase 2 — Batch Ingestor + SQLite | Not started | — | 35 |
| Phase 3 — Query Layer | Not started | — | 50 |
| Phase 4 — MCP Tool Layer | Not started | — | 60 |

## What Works

### Parser (`chime_ingestor/parser.py`)
- **Text-based regex extraction**: Chime PDFs don't contain actual table structures, so the parser uses regex patterns on extracted text
- **Three account types supported**: Checking, Savings, Credit — all tested against real statements
- **Transaction extraction**: Parses date, description, type, amount, balance, settlement date
- **Idempotent ready**: Each transaction carries `source_file` and `account_type` metadata

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
