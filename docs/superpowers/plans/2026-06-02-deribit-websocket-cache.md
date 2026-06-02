# Deribit WebSocket Cache Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace slow Deribit per-option REST ticker polling with a WebSocket/cache path and external hedge selection.

**Architecture:** Add a focused Deribit cache module for planning, caching, and optional WebSocket consumption. Update `scan_multi` to consume cache or summary fallback, and normalize non-Deribit perpetual hedges into a shared BTC hedge group.

**Tech Stack:** Python stdlib, optional `websockets` runtime dependency, pytest.

---

### Task 1: Lock Deribit Fetcher Behavior

**Files:**
- Modify: `tests/test_scan_multi.py`

- [ ] Write failing tests for Deribit summary fallback, no Deribit hedge, and hedge group normalization.
- [ ] Run `python3 -m pytest tests/test_scan_multi.py -q` and confirm failures.

### Task 2: Add Deribit Cache Unit

**Files:**
- Create: `src/option_taoli/deribit_ws_cache.py`
- Create: `tests/test_deribit_ws_cache.py`

- [ ] Write failing tests for subscription planning and TTL cache snapshots.
- [ ] Implement planner/cache.
- [ ] Run `python3 -m pytest tests/test_deribit_ws_cache.py -q`.

### Task 3: Integrate Scanner

**Files:**
- Modify: `scan_multi.py`
- Modify: `requirements.txt`

- [ ] Replace Deribit per-option REST ticker loop with cache-or-summary path.
- [ ] Return no Deribit hedge from `_fetch_deribit`.
- [ ] Normalize Binance/OKX/Bybit hedge keys to shared group.
- [ ] Run `python3 -m pytest tests/test_scan_multi.py -q`.

### Task 4: Verify

**Files:**
- All touched files.

- [ ] Run `python3 -m pytest tests/test_deribit_ws_cache.py tests/test_scan_multi.py tests/test_monitor.py -q`.
- [ ] Run `python3 -m pytest -q`.
- [ ] Run a one-off Deribit fetch timing check.
