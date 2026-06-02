# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
python3 -m pytest

# Run a single test file
python3 -m pytest tests/test_end_to_end_integration.py

# Run a single test by name
python3 -m pytest -k "test_deribit_put_call_parity_opportunity_flows_to_dashboard_and_webhook_alert"

# Verify all source compiles
python3 -m compileall -q src tests

# Install deps (runtime uses only stdlib, pytest needed for development)
pip install pytest
```

Test config: `pyproject.toml` sets `pythonpath = ["src"]` so imports resolve correctly.

## Architecture

Cryptocurrency options arbitrage monitoring system. Pure Python, zero runtime dependencies (stdlib only).

### Data Flow (top to bottom)

```
Exchange WebSocket/REST  →  Public Clients  →  Adapters  →  Standardization  →  ArbitrageMonitor
```

1. **Public Clients** (`public_clients.py`) — REST fetchers for Deribit/Binance/OKX/Bybit public market data. Injectable `get_json` for testing/proxy.

2. **Adapters** (`adapters/{deribit,binance,bybit,okx}.py`) — Normalize exchange-specific JSON payloads into unified `models.py` dataclasses (`Instrument`, `Quote`, `OrderBook`, `FundingRate`).

3. **Standardization** (`market_depth.py`, `option_chain.py`, `perpetual_market.py`) — Build `ExecutableQuote` (bid/ask with depth), `OptionChain` (pair call/put by strike), `PerpetualMarketState` from normalized data.

4. **ArbitrageMonitor** (`monitor.py`) — Orchestrator. Accepts a `MarketDataBatch`, runs three calculation strategies, applies adjustments, filtering, sorting, renders dashboard, records history, sends alerts.

### Calculation Strategies (3 types)

- **Put-Call Parity** (`put_call_parity.py`) — Detect synthetic vs. hedge price deviation
- **Box Spread** (`box_spread.py`) — Vertical call/put spread combinations
- **Implied Futures Basis** (`implied_futures_basis.py`) — Futures basis from option prices vs. actual perpetual/future price

### Post-Processing Pipeline (in order)

1. **Adjustments** (`opportunity_adjustments.py`) — Fee, slippage, funding cost, capital requirement, executable flag, risk tags
2. **Filtering** (`opportunity_filters.py`) — Optional filter by type, exchange, direction, etc.
3. **Sorting** (`opportunity_sorting.py`) — Sort by net_profit, annualized_return, etc.
4. **Dashboard** (`dashboard.py`) — Static HTML list and detail page rendering
5. **History** (`opportunity_history.py`) — SQLite-backed opportunity timeline
6. **Alerts** (`alert_rules.py`, `telegram_alerts.py`, `webhook_alerts.py`) — Rule-based threshold filtering, Telegram/Webhook delivery

### Key Models (`models.py`)

- `Instrument` — Market metadata (exchange, type, strike, expiry, contract specs, fees)
- `Quote` — Top-of-book bid/ask/IV/Greeks
- `OrderBook` — Full L2 order book with bids/asks
- `FundingRate` — Perpetual funding state

### Key Design Decisions

- **Runtime zero-dependency**: Everything uses Python stdlib. No requests, no pandas, no third-party deps.
- **Strings for numeric values**: Decimal strings in models to avoid float precision issues. Consumers parse via `Decimal`.
- **Immutable dataclasses**: All model types are frozen dataclasses.
- **Injectable time/HTTP**: Adapters accept `normalized_at_ms`/`received_at_ms`; `PublicClient` accepts `get_json`; `ArbitrageMonitor` accepts `sleep` — all for testability.
- **No built-in daemon**: This is a library, not a service. Deployment wraps it with WebSocket collector + static file server.
