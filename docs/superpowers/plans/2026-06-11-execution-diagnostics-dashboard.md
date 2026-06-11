# Execution Diagnostics Dashboard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add read-only execution diagnostics to the arbitrage scanner/dashboard so opportunities are classified as `ready`, `watch`, or `blocked` using Binance-Deribit-style pre-trade checks.

**Architecture:** Keep arbitrage calculation unchanged and add a focused diagnostics layer that consumes raw opportunities plus `MarketDataBatch` quotes. `ArbitrageMonitor.scan_once()` attaches diagnostics to `MonitoredOpportunity`; dashboard/API rendering then serializes those fields.

**Tech Stack:** Python stdlib dataclasses/Decimal, existing `option_taoli` models, pytest, existing vanilla JS dashboard bundle.

---

## File Structure

- Create `src/option_taoli/execution_diagnostics.py`
  - Owns diagnostic config, result dataclass, PCP strategy mapping, Maker/Taker estimate, DTE/moneyness/depth/freshness checks.
- Create `tests/test_execution_diagnostics.py`
  - Unit tests for ready/watch/blocked statuses, anchor selection, perpetual buy support assumptions, and missing/placeholder depth.
- Modify `src/option_taoli/monitor.py`
  - Add config field and `execution_diagnostic` field.
  - Compute diagnostics while `MarketDataBatch` is available.
  - Allow perpetual/future buy hedge legs while still blocking spot sell.
- Modify `tests/test_monitor.py`
  - Assert short synthetic + perpetual buy opportunity is retained.
  - Assert spot sell hedge remains rejected.
- Modify `dashboard_server.py`
  - Serialize diagnostics in scan JSON.
  - Add default diagnostic config.
- Modify `tests/test_dashboard_server.py`
  - Assert API/dashboard opportunity JSON includes execution fields.
- Modify `src/option_taoli/dashboard.py`
  - Render static diagnostic columns safely.
- Modify `tests/test_dashboard_list.py` or `tests/test_dashboard_detail.py`
  - Assert static HTML includes diagnostic status/reasons.
- Modify `src/dashboard_client.js`
  - Render diagnostic fields and status labels in the live dashboard table/details.
- Modify `public/dashboard.bundle.js`
  - Rebuild from source with existing npm script if available; otherwise apply equivalent generated bundle update.

## Task 1: Add Diagnostic Model and Core Rules

**Files:**
- Create: `src/option_taoli/execution_diagnostics.py`
- Test: `tests/test_execution_diagnostics.py`

- [ ] **Step 1: Write failing tests for PCP diagnostic statuses**

Add tests with local helper builders for `Instrument`, `ExecutableQuote`, `MarketDataBatch`, and `PutCallParityOpportunity`.

Cover:

```python
def test_marks_profitable_fresh_liquid_cross_exchange_pcp_ready():
    diagnostic = diagnose_execution(opportunity, batch, config, observed_at_ms=1810880000000, fee_rate="0")
    assert diagnostic.status == "ready"
    assert diagnostic.strategy_type == "sell_future_buy_synthetic"
    assert diagnostic.anchor_leg == "call"
    assert diagnostic.reject_reasons == []

def test_marks_sell_spot_hedge_blocked():
    diagnostic = diagnose_execution(spot_sell_opportunity, batch, config, observed_at_ms=1810880000000, fee_rate="0")
    assert diagnostic.status == "blocked"
    assert "spot_short_not_supported" in diagnostic.reject_reasons

def test_marks_stale_quote_watch():
    diagnostic = diagnose_execution(stale_opportunity, batch, config, observed_at_ms=1810880000000, fee_rate="0")
    assert diagnostic.status == "watch"
    assert "stale_quote" in diagnostic.reject_reasons
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_execution_diagnostics.py -v
```

Expected: import or function-not-found failure.

- [ ] **Step 3: Implement dataclasses and minimal unsupported fallback**

In `execution_diagnostics.py`, add:

```python
@dataclass(frozen=True)
class ExecutionDiagnosticConfig:
    min_execution_net_profit: str = "20"
    min_dte_hours: str = "12"
    max_dte_hours: str = "72"
    max_moneyness: str = "0.20"
    quote_max_age_seconds: str = "30"
    min_depth_ratio: str = "0.2"
    maker_price_aggression: str = "0.8"
    settlement_fee_rate: str = "0"

@dataclass(frozen=True)
class ExecutionDiagnostic:
    status: str
    strategy_type: str | None
    anchor_leg: str | None
    all_taker_net_profit: str | None
    maker_anchor_net_profit: str | None
    estimated_open_fees: str
    estimated_settlement_cost: str
    estimated_funding_impact: str
    dte_hours: str | None
    moneyness: str | None
    depth_ok: bool | None
    quote_fresh: bool | None
    reject_reasons: list[str]
    risk_tags: list[str]
```

Add `diagnose_execution(opportunity, batch, config, observed_at_ms, fee_rate, taker_fee_rates_by_exchange_market=None, funding_holding_hours=None, funding_interval_hours="8")`.

- [ ] **Step 4: Implement PCP leg/quote extraction**

Use opportunity legs by `role`:

- `call`
- `put`
- `hedge` or `actual_future`

Resolve each leg's `instrument_key` against `batch.quotes_by_instrument_key` and `batch.hedge_quotes_by_underlying` values. Return `blocked` with `missing_execution_quote` if any required quote is absent.

- [ ] **Step 5: Implement status checks**

Implement:

- Spot sell hedge -> `blocked`, `spot_short_not_supported`.
- Non-PCP class -> `watch`, `execution_diagnostic_not_supported`.
- DTE from `expiry_time_ms - observed_at_ms`.
- Moneyness from `abs(strike - hedge_mid) / hedge_mid`.
- Freshness from quote `source_updated_at_ms` or `received_at_ms`.
- Depth from side-specific bid/ask sizes.

Use `watch` for uncertainty, `blocked` only for impossible/unsafe cases.

- [ ] **Step 6: Implement Maker/Taker profit estimates**

Map strategy:

- `long_synthetic_short_hedge` -> `sell_future_buy_synthetic`
- `short_synthetic_long_hedge` -> `buy_future_sell_synthetic`

Choose anchor by wider option spread. Compute all-taker and maker-anchor gross profit, subtract estimated fees and settlement cost.

- [ ] **Step 7: Run diagnostic tests**

Run:

```bash
python3 -m pytest tests/test_execution_diagnostics.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/option_taoli/execution_diagnostics.py tests/test_execution_diagnostics.py
git commit -m "feat: add execution diagnostics model"
```

## Task 2: Integrate Diagnostics Into Monitor

**Files:**
- Modify: `src/option_taoli/monitor.py`
- Test: `tests/test_monitor.py`

- [ ] **Step 1: Write failing monitor tests**

Add/adjust tests:

```python
def test_cross_exchange_pcp_keeps_perpetual_buy_hedge_direction():
    result = monitor.scan_once(batch_with_short_synthetic_and_perp_buy, observed_at_ms=1810880000000)
    assert any(o.direction == "short_synthetic_long_hedge" for o in result.opportunities)

def test_cross_exchange_pcp_still_rejects_spot_sell_hedge():
    result = monitor.scan_once(batch_with_long_synthetic_and_spot_sell, observed_at_ms=1810880000000)
    assert result.opportunities == []

def test_monitor_attaches_execution_diagnostic():
    result = monitor.scan_once(batch, observed_at_ms=1810880000000)
    assert result.opportunities[0].execution_diagnostic.status in {"ready", "watch", "blocked"}
```

- [ ] **Step 2: Run monitor tests and verify failure**

```bash
python3 -m pytest tests/test_monitor.py -v
```

Expected: failure because diagnostics field/config and perpetual buy behavior are not implemented.

- [ ] **Step 3: Modify `MonitorConfig` and `MonitoredOpportunity`**

Add:

```python
execution_diagnostic_config: ExecutionDiagnosticConfig | None = None
```

and:

```python
execution_diagnostic: ExecutionDiagnostic | None
```

- [ ] **Step 4: Pass batch into candidate monitoring**

Change `_monitor_candidate()` to accept `batch` and call `diagnose_execution()` after adjustments. Use config fee settings.

- [ ] **Step 5: Fix hedge executability filter**

Update `_has_executable_hedge_legs()`:

- Keep rejecting `market_type == "spot"` and `side == "sell"`.
- Stop rejecting `market_type == "perpetual"` and `side == "buy"`.
- Also allow `future` buy/sell.

- [ ] **Step 6: Run monitor tests**

```bash
python3 -m pytest tests/test_monitor.py tests/test_execution_diagnostics.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/option_taoli/monitor.py tests/test_monitor.py
git commit -m "feat: attach execution diagnostics to monitored opportunities"
```

## Task 3: Serialize Diagnostics in Dashboard API

**Files:**
- Modify: `dashboard_server.py`
- Test: `tests/test_dashboard_server.py`

- [ ] **Step 1: Write failing API serialization test**

Add an assertion that serialized opportunities include:

```python
assert opp["execution"]["status"] == "ready"
assert "maker_anchor_net_profit" in opp["execution"]
assert "reject_reasons" in opp["execution"]
```

For existing tests with fixture opportunity dicts, add backward-compatible handling so missing `execution` does not break rendering.

- [ ] **Step 2: Run dashboard server tests and verify failure**

```bash
python3 -m pytest tests/test_dashboard_server.py -v
```

- [ ] **Step 3: Add serializer helper**

In `dashboard_server.py`, add a small `_execution_json(diagnostic)` helper returning `None` or a dict with all diagnostic fields.

- [ ] **Step 4: Wire config**

Instantiate `MonitorConfig(execution_diagnostic_config=ExecutionDiagnosticConfig(...))` using defaults. Keep existing fee rate parsing.

- [ ] **Step 5: Run tests**

```bash
python3 -m pytest tests/test_dashboard_server.py tests/test_monitor.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard_server.py tests/test_dashboard_server.py
git commit -m "feat: expose execution diagnostics in scan api"
```

## Task 4: Render Diagnostics in Static and Live Dashboard

**Files:**
- Modify: `src/option_taoli/dashboard.py`
- Modify: `src/dashboard_client.js`
- Modify: `public/dashboard.bundle.js`
- Test: `tests/test_dashboard_list.py`, `tests/test_dashboard_detail.py`, `tests/test_dashboard_server.py`

- [ ] **Step 1: Write failing rendering tests**

Assert static HTML and live table rendering sources include:

- `Exec`
- `Maker Net`
- `Taker Net`
- status value such as `Ready`
- reject reason text for `Watch`/`Blocked`

- [ ] **Step 2: Run rendering tests and verify failure**

```bash
python3 -m pytest tests/test_dashboard_list.py tests/test_dashboard_detail.py tests/test_dashboard_server.py -v
```

- [ ] **Step 3: Update Python static dashboard**

Add diagnostic columns with safe fallback:

- Missing diagnostic -> `-`
- Status normalized to title case.
- Reason joins first few reject reasons.

- [ ] **Step 4: Update JS dashboard source**

In `src/dashboard_client.js`, update table header/body/detail rendering to read `o.execution`.

Keep layout compact:

- `Exec` as status text.
- `Maker Net` and `Taker Net` formatted with existing money formatter.
- `Reason` truncated if current code already truncates long fields; otherwise show first reason.

- [ ] **Step 5: Rebuild generated bundle**

Check `package.json` for scripts. Prefer:

```bash
npm run build
```

If no build script updates `public/dashboard.bundle.js`, apply equivalent manual generated change and document why in final output.

- [ ] **Step 6: Run rendering tests**

```bash
python3 -m pytest tests/test_dashboard_list.py tests/test_dashboard_detail.py tests/test_dashboard_server.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/option_taoli/dashboard.py src/dashboard_client.js public/dashboard.bundle.js tests/test_dashboard_list.py tests/test_dashboard_detail.py tests/test_dashboard_server.py
git commit -m "feat: render execution diagnostics on dashboard"
```

## Task 5: End-to-End Verification

**Files:**
- No new files unless tests reveal a gap.

- [ ] **Step 1: Run focused tests**

```bash
python3 -m pytest tests/test_execution_diagnostics.py tests/test_monitor.py tests/test_dashboard_server.py tests/test_dashboard_list.py tests/test_dashboard_detail.py tests/test_scan_multi.py -v
```

Expected: PASS.

- [ ] **Step 2: Run compile check**

```bash
python3 -m compileall -q src tests
```

Expected: no output and exit 0.

- [ ] **Step 3: Optional full test run if time permits**

```bash
python3 -m pytest
```

Expected: PASS or document unrelated failures.

- [ ] **Step 4: Inspect git diff**

```bash
git status --short
git diff --stat HEAD
```

Expected: only intended files changed since the last task commit; pre-existing dirty files may remain but should not be reverted.

- [ ] **Step 5: Final commit if needed**

If verification fixes were made:

```bash
git add <changed-files>
git commit -m "test: verify execution diagnostics dashboard"
```

## Notes for Implementation

- Do not add trading, private API keys, Redis, order placement, or rollback code.
- Keep `ExecutionDiagnostic` immutable and string-based for numeric values, matching project model conventions.
- Use `Decimal` for all calculations.
- Prefer `watch` when data is missing or uncertain; use `blocked` only for structurally impossible or unsafe execution.
- Do not revert existing dirty files that predate this work.
