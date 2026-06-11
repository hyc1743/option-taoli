# Execution Diagnostics Dashboard Design

## Goal

Improve the local arbitrage dashboard so it distinguishes theoretical arbitrage from execution-ready opportunities, using the Binance-Deribit project's scanner logic as the reference for execution diagnostics while keeping this project non-trading and read-only.

## Context

The current project scans normalized multi-exchange market data, calculates put-call parity, box spread, and implied futures basis opportunities, applies generic adjustments, and renders a dashboard. It is intentionally a scanner/dashboard library.

The referenced Binance-Deribit project is an automatic trading engine. Its scanner is narrower but more execution-aware: it targets Deribit options plus Binance perpetual hedges, applies DTE, moneyness, spread, depth, stale quote, funding, settlement fee, and minimum profit gates, and estimates mixed Maker/Taker entry pricing before sending candidates to execution.

This design imports the execution-readiness concepts, not the order placement engine.

## Scope

In scope:

- Add execution diagnostics to monitored opportunities.
- Allow both perpetual hedge directions for PCP scanning so the local scanner can detect the two Binance-Deribit strategy directions.
- Keep spot short hedge legs blocked.
- Add configurable execution thresholds for diagnostics.
- Surface execution status, profit basis, anchor leg, DTE, funding estimate, and reject reasons on the dashboard/API.
- Add tests covering scanner direction, diagnostics, and dashboard serialization/rendering.

Out of scope:

- Real order placement.
- API key handling.
- Redis state recovery.
- Position monitoring.
- Automatic rollback.
- Exchange-specific private account or commission APIs.

## Strategy Mapping

The referenced project uses two strategy directions:

- `sell_future_buy_synthetic`: buy call, sell put, sell Binance perpetual.
- `buy_future_sell_synthetic`: sell call, buy put, buy Binance perpetual.

Local mapping:

- `PutCallParityOpportunity.direction == "long_synthetic_short_hedge"` maps to `sell_future_buy_synthetic`.
- `PutCallParityOpportunity.direction == "short_synthetic_long_hedge"` maps to `buy_future_sell_synthetic` when the hedge leg is a perpetual/future buy.

The current scanner blocks `perpetual buy` hedge legs. That should change: perpetual/future buy legs are executable; spot sell legs remain blocked because spot cannot be sold unless inventory or margin is explicitly modeled.

## Execution Diagnostic Model

Create a new focused module:

`src/option_taoli/execution_diagnostics.py`

Primary dataclasses/functions:

- `ExecutionDiagnosticConfig`
- `ExecutionDiagnostic`
- `diagnose_execution(opportunity, batch, config, observed_at_ms, fee_config)`

Suggested fields:

- `status`: `ready | watch | blocked`
- `strategy_type`: `sell_future_buy_synthetic | buy_future_sell_synthetic | None`
- `anchor_leg`: `call | put | None`
- `all_taker_net_profit`
- `maker_anchor_net_profit`
- `estimated_open_fees`
- `estimated_settlement_cost`
- `estimated_funding_impact`
- `dte_hours`
- `moneyness`
- `depth_ok`
- `quote_fresh`
- `reject_reasons`
- `risk_tags`

Default config:

- `min_execution_net_profit = "20"`
- `min_dte_hours = "12"`
- `max_dte_hours = "72"`
- `max_moneyness = "0.20"`
- `quote_max_age_seconds = "30"`
- `min_depth_ratio = "0.2"`
- `maker_price_aggression = "0.8"`
- `settlement_fee_rate = "0"`

The diagnostic function must receive the original `MarketDataBatch`, not only `MonitoredOpportunity`, because depth, quote freshness, bid/ask spreads, and current hedge prices live in `ExecutableQuote` objects keyed by instrument. The first implementation can estimate open fees from existing `taker_fee_rates_by_exchange_market` plus default `fee_rate`. Settlement fee remains configurable and defaults to zero until exchange-specific settlement fee modeling is added.

## Diagnostic Rules

Apply diagnostics primarily to PCP opportunities because they map cleanly to the Binance-Deribit execution model. Box spread and implied futures basis should get a simple `watch` diagnostic with a reason such as `execution_diagnostic_not_supported` unless a future implementation adds specific models.

Rules:

- `blocked` if the opportunity has a sell spot hedge leg.
- `blocked` if required call, put, or hedge leg data cannot be identified.
- `watch` if DTE is outside the configured execution window.
- `watch` if moneyness exceeds the configured limit.
- `watch` if quote timestamps are stale or missing enough data to verify freshness.
- `watch` if depth is known and below the configured threshold.
- `watch` if an exchange snapshot supplies placeholder depth rather than real depth.
- `watch` if maker-anchor net profit is below the configured minimum but theoretical gross profit is positive.
- `ready` only when no blocking/watch reasons remain and maker-anchor net profit meets the threshold.

For missing optional data, prefer `watch` over `blocked` unless execution is clearly impossible. The dashboard should explain uncertainty rather than hiding the opportunity.

## Maker/Taker Pricing

For PCP opportunities:

1. Identify call, put, and hedge legs from the opportunity legs.
2. Choose the anchor option leg by comparing option bid-ask spread. The wider spread becomes the Maker anchor.
3. Estimate Maker anchor price using `maker_price_aggression`:
   - Buy anchor: `bid + (ask - bid) * aggression`
   - Sell anchor: `ask - (ask - bid) * aggression`
4. Use Taker prices for the other option leg and hedge leg.
5. Compute all-taker net profit and maker-anchor net profit.

This is an approximation of the reference project's execution scanner, not a fill guarantee. The dashboard must label it as an execution diagnostic.

## Integration

Modify:

- `src/option_taoli/monitor.py`
  - Add optional diagnostics config to `MonitorConfig`.
  - Add `execution_diagnostic` to `MonitoredOpportunity`.
  - Compute diagnostics during `scan_once` while both the raw opportunity and `MarketDataBatch` are still available.
  - Allow perpetual/future buy hedge legs in `_has_executable_hedge_legs`; keep spot sell blocked.

- `dashboard_server.py`
  - Include diagnostic fields in `/api/scan` opportunity JSON.
  - Add defaults for execution diagnostic config.
  - Keep existing fee rate controls; diagnostics should consume the same fee settings where possible.

- `src/dashboard_client.js` and generated `public/dashboard.bundle.js`
  - Add columns for execution status, anchor, all-taker net, maker net, DTE, funding, and reason.
  - Add filtering by execution status if it fits existing UI patterns without large redesign.

- `src/option_taoli/dashboard.py`
  - Include diagnostic fields in static HTML rendering.

## Dashboard UX

Use three statuses:

- `Ready`: execution-style checks pass and maker-anchor net profit meets the threshold.
- `Watch`: theoretical opportunity exists but execution checks are incomplete or below threshold.
- `Blocked`: execution is structurally impossible or unsafe under the current model.

Suggested table columns:

- `Exec`
- `Type`
- `Exchange`
- `Direction`
- `Strike`
- `Net`
- `Maker Net`
- `Taker Net`
- `Anchor`
- `DTE`
- `Funding`
- `Reason`

Details should show:

- The original theoretical calculation.
- Execution pricing assumptions.
- Fee/funding/settlement breakdown.
- DTE, moneyness, depth, freshness checks.
- Reject reasons.

## Testing

Add focused unit tests:

- PCP scanner keeps `short_synthetic_long_hedge` opportunities with a perpetual buy hedge.
- PCP scanner still rejects spot sell hedge opportunities.
- Diagnostics mark a profitable, fresh, liquid PCP opportunity as `ready`.
- Diagnostics mark stale quotes as `watch`.
- Diagnostics mark sell spot hedge as `blocked`.
- Diagnostics chooses the wider-spread option as the Maker anchor.
- Dashboard/API serialization includes diagnostic fields.
- Client rendering handles missing diagnostics without breaking.

Run at minimum:

```bash
python3 -m pytest tests/test_monitor.py tests/test_opportunity_adjustments.py tests/test_dashboard_server.py tests/test_dashboard_detail.py tests/test_scan_multi.py
python3 -m compileall -q src tests
```

## Risks

- The Maker/Taker diagnostic may look more precise than it is. Mitigation: label it as an estimate and preserve both all-taker and maker-anchor profit.
- Missing depth data from public ticker endpoints can produce false `watch` statuses. Mitigation: treat missing data as uncertainty, not a hard block.
- Some fetchers currently synthesize bid/ask size as `1` when the exchange ticker endpoint omits depth. Mitigation: include a depth-source/placeholder check in diagnostics and avoid marking such rows `Ready` solely from synthetic size.
- Adding columns could clutter the dashboard. Mitigation: keep key status columns visible and move detailed breakdown to the detail view.
- Static bundle updates can drift from source JS. Mitigation: update source and rebuild/check generated bundle as part of implementation.

## Acceptance Criteria

- The dashboard can show whether each opportunity is `Ready`, `Watch`, or `Blocked`.
- Cross-exchange PCP opportunities in both synthetic directions can be detected when using perpetual hedges.
- The API response includes diagnostic fields for each opportunity.
- Tests cover the new scanner direction and diagnostic status logic.
- No trading, order placement, API key, Redis, or private-account code is introduced.
