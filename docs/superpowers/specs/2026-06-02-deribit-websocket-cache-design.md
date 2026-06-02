# Deribit WebSocket Cache Design

## Goal

Reduce Deribit scan latency by replacing per-option REST ticker polling with a warm WebSocket-backed market data cache, while ensuring Deribit option opportunities use hedge legs from non-Deribit exchanges.

## Architecture

Deribit option metadata still starts from REST `public/get_instruments`. Live option quotes are maintained in a background WebSocket cache that subscribes to selected Deribit ticker channels. When the cache is not warm, Deribit falls back to `public/get_book_summary_by_currency` instead of per-instrument ticker polling.

The Deribit snapshot contributes only option instruments and option quotes. It does not contribute a Deribit spot or perpetual hedge quote. Binance, OKX, and Bybit perpetual hedges are keyed into a shared hedge group so the existing cross-exchange PCP logic can evaluate Deribit option pairs against external hedge legs and select the best candidate by profit.

## Components

- `option_taoli.deribit_ws_cache`
  - Plans Deribit option subscriptions from instrument metadata and spot/underlying price.
  - Stores raw ticker payloads with timestamps and TTL filtering.
  - Builds `ExchangeSnapshot`-compatible payloads from cached tickers.
  - Provides an async WebSocket runner using the optional `websockets` dependency.

- `scan_multi`
  - Uses the global Deribit cache if warm.
  - Falls back to Deribit book summary if the cache is cold.
  - Normalizes hedge keys for Binance, OKX, and Bybit to a shared BTC hedge group.
  - Prevents Deribit from returning its own hedge quote.

## Error Handling

The WebSocket runner reconnects after failures. Cache reads are non-blocking; stale quotes are excluded by TTL. REST summary fallback records quote normalization errors per instrument and still returns any usable option quotes.

## Testing

Tests cover subscription planning, cache TTL behavior, summary fallback, avoiding per-option ticker calls, Deribit no-hedge output, and cross-exchange hedge grouping.
