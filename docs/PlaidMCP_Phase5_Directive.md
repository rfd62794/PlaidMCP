# PlaidMCP — Phase 5 Directive: Category Refinement + Analysis Tools

*June 2026 | Read fully before executing anything.*

---

> ⛔ **STOP:** Run pytest before touching any file.
> Must report **102 passing, 0 failing, 0 skipped**.
> If count differs, stop and report — do not proceed.

---

## §0 Context

**The problem discovered from live data analysis:**

`get_spending_by_category` is useless because 96% of "outflows" are internal Chime
account mechanics — not real spending. The cross-account payment pipeline produces:
- "Moved to/from Secured Deposit Account" — Credit card payment transfers
- "Transfer from Visa 1473" — CashApp to Chime settlement
- "Chime San Francisco CA" (CashApp) — Chime account payments
- "Card Payment from Secured Account" — monthly credit card payment (already counted in purchases)
- "My Pay Advance" / "My Pay Repayment" — Chime short-term advance product
- "Transfer to/from Chime Savings Account" — savings moves

These must be identified and excluded from spending analysis. The categories.yaml
must reflect real merchant data extracted from actual transaction history.

**What this phase delivers:**
- §5a: `config/categories.yaml` — complete replacement with real merchants + Internal Transfer category
- §5b: `get_top_merchants(month, limit)` — GROUP BY description, aggregate spend
- §5c: `search_transactions(description_contains, month)` — targeted merchant lookup
- §5d: `get_net_spending(month)` — real spending only, internal transfers excluded

**What is NOT in scope:**
- Modifying existing query functions
- Changing the database schema
- Any ingestion logic

---

## §1 Scope Statement

| File | Status | Action |
|---|---|---|
| `config/categories.yaml` | Modify | Complete replacement with real merchant data |
| `chime_ingestor/queries.py` | Modify | Add 3 new functions |
| `plaid_mcp/tools/finance_tools.py` | Modify | Register 3 new MCP tools |
| `tests/test_queries.py` | Modify | Add tests for 3 new functions |
| `tests/test_mcp_tools.py` | Modify | Add tests for 3 new tools |
| `docs/state/current.md` | Modify | Update at end of phase |

**Read-only — do not touch:**
All other files. Do not modify existing query functions or tool functions — append only.

---

## §2 Implementation

### §5a — categories.yaml replacement

Replace `config/categories.yaml` entirely with the following. This is derived from
real transaction data and must not be modified by the agent:

```yaml
# Internal transfers — EXCLUDED from spending analysis
# These are Chime account mechanics, not real spending
Internal Transfer:
  - moved to secured deposit account
  - moved from secured deposit account
  - transfer from visa 1473
  - chime san francisco ca
  - chime card payment
  - card payment from secured account
  - transfer to chime savings account
  - transfer from chime savings account
  - transfer to secured deposit account
  - transfer from secured deposit account
  - transfer to secured account
  - transfer from secured account
  - my pay advance
  - my pay repayment
  - my pay instant advance fees
  - moved from checking account
  - moved to checking account
  - moved from credit account
  - moved to credit account
  - paycheck: transfer to savings
  - from savings
  - to savings
  - chime transfer

# Income
Income:
  - integrity fulfil
  - payroll
  - direct deposit
  - from ralph
  - from star
  - from ricardo
  - transfer from ralph
  - cash back
  - refund
  - spotme line of credit

# Car
Auto:
  - westlake payment
  - auto insurance
  - insurance
  - instant loan payment

# Gas & Convenience
Gas & Convenience:
  - wawa
  - marathon
  - chevron
  - raceway
  - crown
  - 7 eleven
  - shell
  - bp
  - sunoco
  - circle k

# Food & Dining
Food & Dining:
  - mcdonald
  - mc donald
  - little caesars
  - taco bell
  - burger king
  - publix
  - uber eats
  - doordash
  - grubhub
  - chipotle
  - chick-fil-a
  - starbucks
  - dunkin
  - pizza
  - domino
  - subway

# Grocery & Household
Grocery & Household:
  - walmart
  - target
  - dollar general
  - dollar tree
  - amazon
  - costco
  - sam's club
  - whole foods

# Tobacco & Vape
Tobacco & Vape:
  - smokers oasis
  - exotic retail
  - smoke

# Subscriptions & Digital
Subscriptions:
  - hulu
  - netflix
  - spotify
  - google one
  - google you tube
  - youtube
  - snapchat
  - talkspace
  - claude.ai
  - claude.ai subscription
  - anthropic
  - microsoft
  - apple
  - disney

# Gaming
Gaming:
  - steam
  - steamgames
  - wl *steam
  - playstation
  - xbox
  - nintendo
  - itch.io

# ATM & Cash
ATM & Cash:
  - pnc bank
  - atm withdrawal
  - cash advance
  - cash withdrawal

# Person-to-Person Transfers
P2P Transfer:
  - transfer to roger
  - transfer to ralph
  - transfer to guineviere
  - to guineviere
  - from star
  - cash app*

# Government & Fees
Government & Fees:
  - nic* mydmvportal
  - dmv
  - fee
  - penalty

# Uncategorized: []
```

> ⚠️ RULE: Do not add, remove, or reorder categories. Do not modify keyword strings.
> This file is derived from live transaction data analysis. Treat it as read-only after replacement.

---

### §5b — `get_top_merchants`

Add to `chime_ingestor/queries.py`:

```python
def get_top_merchants(
    month: str,                          # "2026-05" format
    limit: int = 20,
    account_type: str | None = None,
    institution: str | None = None,
    db_path: Path = Path("finance.db"),
) -> list[dict]:
    """
    Return top merchants by total spend for a given month.
    Outflows only (amount < 0). Groups by description, sums amounts.
    Returns [{description, total, count, avg}] sorted by total desc.
    """
```

SQL pattern:
```sql
SELECT
    description,
    ROUND(SUM(amount), 2) as total,
    COUNT(*) as count,
    ROUND(AVG(amount), 2) as avg
FROM transactions
WHERE date LIKE :month_prefix
  AND amount < 0
  -- optional filters
GROUP BY description
ORDER BY total ASC  -- most negative first = largest outflows
LIMIT :limit
```

> ⚠️ RULE: `month_prefix` = `"2026-05%"`. Use `LIKE` not date parsing — dates are stored as text.

---

### §5c — `search_transactions`

Add to `chime_ingestor/queries.py`:

```python
def search_transactions(
    description_contains: str,
    month: str | None = None,           # "2026-05" format, optional
    institution: str | None = None,
    limit: int = 100,
    db_path: Path = Path("finance.db"),
) -> list[dict]:
    """
    Return transactions where description contains the search string (case-insensitive).
    Optional month filter. Returns full transaction rows.
    """
```

SQL pattern:
```sql
SELECT * FROM transactions
WHERE LOWER(description) LIKE LOWER('%' || :search || '%')
  -- optional month and institution filters
ORDER BY date DESC
LIMIT :limit
```

> ⚠️ RULE: Search is case-insensitive substring match. Never use regex in SQL — LIKE only.

---

### §5d — `get_net_spending`

Add to `chime_ingestor/queries.py`:

```python
def get_net_spending(
    month: str,                          # "2026-05" format
    db_path: Path = Path("finance.db"),
) -> dict:
    """
    Return real spending for a month with internal transfers excluded.
    Loads categories from config/categories.yaml, identifies Internal Transfer
    keywords, excludes matching transactions from totals.

    Returns:
    {
        month: str,
        total_outflow: float,           # sum of real spending (negative)
        total_inflow: float,            # sum of real income (positive)
        net: float,
        excluded_transfer_volume: float,  # how much was filtered out
        by_category: dict[str, float]   # category totals, transfers excluded
    }
    """
```

> ⚠️ RULE: Load `categories.yaml` inside this function — do not import at module level.
> The "Internal Transfer" category keywords define what gets excluded. If the category
> is renamed in the YAML, the function must still work — match by category name
> "Internal Transfer" exactly.

> ⚠️ RULE: `excluded_transfer_volume` must be reported so the caller can see how much
> was filtered. This prevents silent data loss from over-aggressive exclusion.

---

### MCP tool registration

Add to `plaid_mcp/tools/finance_tools.py`:

```python
def get_top_merchants(
    month: str,
    limit: int = 20,
    account_type: str = None,
    institution: str = None,
) -> list[dict]:
    """
    Return top merchants by total spend for a given month.
    month: '2026-05' format. Returns [{description, total, count, avg}].
    """

def search_transactions(
    description_contains: str,
    month: str = None,
    institution: str = None,
    limit: int = 100,
) -> list[dict]:
    """
    Search transactions by description (case-insensitive substring).
    Optional month filter in '2026-05' format.
    """

def get_net_spending(month: str) -> dict:
    """
    Real spending for a month with internal Chime transfers excluded.
    Returns total_outflow, total_inflow, net, excluded_transfer_volume, by_category.
    """
```

Add to `register_finance_tools(mcp)`:
```python
mcp.tool()(get_top_merchants)
mcp.tool()(search_transactions)
mcp.tool()(get_net_spending)
```

---

## §3 Test Anchors

| Test | File | Behaviour |
|---|---|---|
| `test_get_top_merchants_returns_list` | `test_queries.py` | Returns list of dicts |
| `test_get_top_merchants_outflows_only` | `test_queries.py` | No positive amounts in results |
| `test_get_top_merchants_sorted` | `test_queries.py` | First entry has lowest (most negative) total |
| `test_get_top_merchants_limit` | `test_queries.py` | Returns at most `limit` rows |
| `test_search_transactions_match` | `test_queries.py` | "wawa" returns rows with "Wawa" in description |
| `test_search_transactions_case_insensitive` | `test_queries.py` | "WAWA" matches "Wawa" |
| `test_search_transactions_month_filter` | `test_queries.py` | Wrong month returns no results |
| `test_get_net_spending_excludes_internal` | `test_queries.py` | "Moved to Secured" not in totals |
| `test_get_net_spending_reports_excluded_volume` | `test_queries.py` | `excluded_transfer_volume` > 0 |
| `test_get_net_spending_by_category_keys` | `test_queries.py` | Returns dict with category strings |
| `test_mcp_top_merchants_error_handling` | `test_mcp_tools.py` | Bad db path → `{"error": ...}` |
| `test_mcp_search_error_handling` | `test_mcp_tools.py` | Bad db path → `{"error": ...}` |
| `test_mcp_net_spending_error_handling` | `test_mcp_tools.py` | Bad db path → `{"error": ...}` |

All tests use in-memory SQLite with fixture rows. No reads from `finance.db`.

**Target floor: 115 passing, 0 failing, 0 skipped**

---

## §4 Completion Criteria

- [ ] `uv run pytest` reports **102/0/0** before any file is touched
- [ ] `config/categories.yaml` replaced exactly as specified
- [ ] 3 query functions added to `queries.py`
- [ ] 3 MCP tools added to `finance_tools.py` and registered
- [ ] `uv run pytest` reports **115/0/0**
- [ ] Live spot check — paste raw output of:
  `get_net_spending("2026-05")` via MCP
  `get_top_merchants("2026-05", limit=10)` via MCP
- [ ] `docs/state/current.md` updated

---

## §5 Quick Reference

| Key | Value |
|---|---|
| Pre-flight floor | 102/0/0 |
| Target floor | 115/0/0 |
| Core problem | Internal transfers inflating outflow by ~$16k/month |
| Exclusion mechanism | "Internal Transfer" category in categories.yaml |
| Month format | "2026-05" → SQL LIKE "2026-05%" |
| Merchant sort | ASC by total (most negative = largest spend first) |
| Search method | LOWER(description) LIKE LOWER('%query%') |
| No regex in SQL | LIKE only — never REGEXP |
| Append only | Do not modify existing query functions or tools |
