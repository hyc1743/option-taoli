from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Iterable


DERIBIT_WS_URL = "wss://www.deribit.com/ws/api/v2"


def plan_deribit_option_subscriptions(
    instruments: Iterable[dict[str, Any]],
    *,
    atm_price: float,
    max_expiries: int,
    strike_range_pct: float,
) -> list[str]:
    lo = atm_price * (1 - strike_range_pct / 100)
    hi = atm_price * (1 + strike_range_pct / 100)
    btc_usdc = [raw for raw in instruments if _is_btc_usdc_option(raw)]
    expiries = sorted({raw["expiration_timestamp"] for raw in btc_usdc if raw.get("expiration_timestamp")})
    target_expiries = set(expiries[:max_expiries])

    selected: list[tuple[int, float, str]] = []
    for raw in btc_usdc:
        if raw.get("expiration_timestamp") not in target_expiries:
            continue
        try:
            strike = float(str(raw.get("strike")))
        except (TypeError, ValueError):
            continue
        if lo <= strike <= hi:
            selected.append((int(raw["expiration_timestamp"]), strike, str(raw["instrument_name"])))
    return [f"ticker.{name}.raw" for _, _, name in sorted(selected)]


@dataclass
class DeribitTickerCache:
    ttl_ms: int = 10_000
    _tickers: dict[str, tuple[dict[str, Any], int]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def update(self, raw: dict[str, Any], *, received_at_ms: int | None = None) -> None:
        instrument_name = raw.get("instrument_name")
        if not instrument_name:
            return
        timestamp = received_at_ms if received_at_ms is not None else int(time.time() * 1000)
        with self._lock:
            self._tickers[str(instrument_name)] = (dict(raw), timestamp)

    def snapshot(self, *, now_ms: int | None = None) -> dict[str, dict[str, Any]]:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        fresh: dict[str, dict[str, Any]] = {}
        with self._lock:
            for instrument_name, (raw, received_at_ms) in self._tickers.items():
                if now - received_at_ms > self.ttl_ms:
                    continue
                if not _has_two_sided_quote(raw):
                    continue
                fresh[instrument_name] = dict(raw)
        return fresh

    def is_warm(self, *, minimum_quotes: int = 1, now_ms: int | None = None) -> bool:
        return len(self.snapshot(now_ms=now_ms)) >= minimum_quotes


class DeribitMarketDataCache:
    def __init__(
        self,
        *,
        channels: Iterable[str] | None = None,
        ws_url: str = DERIBIT_WS_URL,
        ttl_ms: int = 10_000,
    ) -> None:
        self._channels = list(channels or [])
        self._ws_url = ws_url
        self._ticker_cache = DeribitTickerCache(ttl_ms=ttl_ms)
        self._instruments_by_name: dict[str, dict[str, Any]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def configure(
        self,
        channels: Iterable[str],
        *,
        instruments: Iterable[dict[str, Any]] | None = None,
    ) -> None:
        self._channels = list(channels)
        if instruments is not None:
            self._instruments_by_name = {
                str(raw["instrument_name"]): dict(raw)
                for raw in instruments
                if raw.get("instrument_name")
            }

    def update(self, raw: dict[str, Any], *, received_at_ms: int | None = None) -> None:
        self._ticker_cache.update(raw, received_at_ms=received_at_ms)

    def snapshot(self, *, now_ms: int | None = None) -> dict[str, dict[str, Any]]:
        tickers = self._ticker_cache.snapshot(now_ms=now_ms)
        for instrument_name, raw in tickers.items():
            instrument = self._instruments_by_name.get(instrument_name)
            if instrument is not None:
                raw["instrument"] = dict(instrument)
        return tickers

    def is_warm(self, *, minimum_quotes: int = 1, now_ms: int | None = None) -> bool:
        return self._ticker_cache.is_warm(minimum_quotes=minimum_quotes, now_ms=now_ms)

    def start_background(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=lambda: asyncio.run(self.run_forever()), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                await self._run_once()
            except Exception:
                await asyncio.sleep(1)

    async def _run_once(self) -> None:
        if not self._channels:
            await asyncio.sleep(1)
            return
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("websockets dependency is required for Deribit WebSocket cache") from exc

        async with websockets.connect(self._ws_url, ping_interval=20, ping_timeout=20) as ws:
            await ws.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "public/subscribe",
                        "params": {"channels": self._channels},
                    }
                )
            )
            while not self._stop.is_set():
                message = json.loads(await ws.recv())
                data = message.get("params", {}).get("data")
                if isinstance(data, dict):
                    self.update(data)


def _is_btc_usdc_option(raw: dict[str, Any]) -> bool:
    return str(raw.get("instrument_name", "")).startswith("BTC_USDC-")


def _has_two_sided_quote(raw: dict[str, Any]) -> bool:
    return (
        raw.get("best_bid_price") is not None
        and raw.get("best_ask_price") is not None
        and raw.get("best_bid_amount") is not None
        and raw.get("best_ask_amount") is not None
    )
