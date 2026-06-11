#!/usr/bin/env python3
"""多交易所套利扫描 — 连接 Deribit / Binance / OKX / Bybit / Gate 实盘 API。

用法:
    python3 scan_multi.py                    # 扫描所有交易所
    python3 scan_multi.py --exchange deribit # 仅扫描指定交易所
    python3 scan_multi.py --exchange binance,okx
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from threading import Thread
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).parent / "src"))

from option_taoli.adapters.binance import BinanceAdapter
from option_taoli.adapters.bybit import BybitAdapter
from option_taoli.adapters.deribit import DeribitAdapter
from option_taoli.adapters.gate import GateAdapter
from option_taoli.adapters.okx import OkxAdapter
from option_taoli.deribit_ws_cache import DeribitMarketDataCache, plan_deribit_option_subscriptions
from option_taoli.market_depth import ExecutableQuote, StandardizedOrderBook, standardize_order_book, standardize_quote
from option_taoli.models import Instrument, Quote
from option_taoli.monitor import ArbitrageMonitor, MarketDataBatch, MonitorConfig
from option_taoli.opportunity_history import OpportunityHistoryStore

# ═══════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════

MAX_EXPIRIES = 4
STRIKE_RANGE_PCT = 12
FEE_RATE = "0.0005"
CAPITAL_RATE = "0.1"
CURRENCY = "BTC"
DERIBIT_OPTION_CURRENCY = "USDC"
DERIBIT_USDC_UNDERLYING = "btc_usdc"
DERIBIT_SPOT_INSTRUMENT = "BTC_USDC"
BTC_USD_HEDGE_GROUP = "btc_usd_hedge"
OUT_DIR = Path("public")
OUT_DIR.mkdir(exist_ok=True)
_DERIBIT_CACHE: DeribitMarketDataCache | None = None

# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _http_get(url: str, timeout: int = 15) -> dict[str, Any]:
    from urllib.request import Request
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _fmt_usd(v: str | None) -> str:
    if v is None:
        return "—"
    try:
        d = Decimal(v)
        if abs(d) >= 1000: return f"${d:,.2f}"
        if abs(d) >= 1: return f"${d:.2f}"
        return f"${d:.4f}"
    except Exception:
        return str(v)


def _fmt_apy(v: str | None) -> str:
    if v is None: return "—"
    try:
        d = Decimal(v)
        if abs(d) >= 0.01: return f"{d:.2%}"
        return f"{d:.4%}"
    except Exception:
        return str(v)


# ═══════════════════════════════════════════════════════════════
# Exchange-specific fetchers
# ═══════════════════════════════════════════════════════════════

@dataclass
class ExchangeSnapshot:
    exchange: str
    instruments: list[Instrument]
    quotes_by_key: dict[str, ExecutableQuote]
    hedge_quote: ExecutableQuote | None
    hedge_key: tuple[str, str] | None
    atm_price: float
    errors: list[str]
    extra_hedges: list[tuple[tuple[str, str], ExecutableQuote]] = field(default_factory=list)


def _fetch_deribit(now_ms: int) -> ExchangeSnapshot:
    """Deribit: USDC-settled BTC options. Hedge legs are supplied by other exchanges."""
    errors: list[str] = []
    adapter = DeribitAdapter(normalized_at_ms=now_ms, received_at_ms=now_ms)
    base = "https://www.deribit.com/api/v2"

    if _DERIBIT_CACHE is not None:
        cached = _DERIBIT_CACHE.snapshot(now_ms=now_ms)
        if isinstance(cached, ExchangeSnapshot):
            return cached
        if cached:
            return _deribit_snapshot_from_cached_tickers(adapter, cached)

    # instruments
    insts_raw = _http_get(
        f"{base}/public/get_instruments?currency={DERIBIT_OPTION_CURRENCY}&kind=option&expired=false"
    )["result"]
    insts_raw = [raw for raw in insts_raw if _is_deribit_btc_usdc_option(raw)]

    # spot hedge
    spot = _http_get(f"{base}/public/ticker?instrument_name={DERIBIT_SPOT_INSTRUMENT}")["result"]
    spot_q = standardize_quote(adapter.normalize_quote(spot, market_type="spot"))
    atm = float(spot_q.mid_price)

    # filter
    lo, hi = atm * (1 - STRIKE_RANGE_PCT / 100), atm * (1 + STRIKE_RANGE_PCT / 100)
    all_exps = sorted({i["expiration_timestamp"] for i in insts_raw if i.get("expiration_timestamp")})
    target = set(all_exps[:MAX_EXPIRIES])

    selected = [i for i in insts_raw
                if i.get("strike") and i.get("expiration_timestamp") in target
                and lo <= float(str(i["strike"])) <= hi]
    _configure_deribit_cache(insts_raw, atm_price=atm)

    summaries = _http_get(
        f"{base}/public/get_book_summary_by_currency?currency={DERIBIT_OPTION_CURRENCY}&kind=option"
    )["result"]
    summaries_by_name = {raw.get("instrument_name"): raw for raw in summaries}

    insts, quotes = [], {}
    for raw in selected:
        name = raw["instrument_name"]
        summary = summaries_by_name.get(name)
        if summary is None:
            continue
        try:
            inst = _with_btc_hedge_group(adapter.normalize_instrument(raw))
            q = _standardize_deribit_summary_quote(summary, now_ms=now_ms)
            insts.append(inst)
            quotes[q.instrument_key] = q
        except Exception as e:
            errors.append(f"{name}: {e}")

    print(f"    Deribit: {len(insts)} USDC options, external hedge only, atm={atm:.0f}")
    return ExchangeSnapshot("deribit", insts, quotes, None, None, atm, errors)


def _is_deribit_btc_usdc_option(raw: dict[str, Any]) -> bool:
    return (
        str(raw.get("price_index", "")).lower() == DERIBIT_USDC_UNDERLYING
        or str(raw.get("instrument_name", "")).startswith(f"{DERIBIT_SPOT_INSTRUMENT}-")
    )


def _configure_deribit_cache(instruments: list[dict[str, Any]], *, atm_price: float) -> None:
    global _DERIBIT_CACHE
    channels = plan_deribit_option_subscriptions(
        instruments,
        atm_price=atm_price,
        max_expiries=MAX_EXPIRIES,
        strike_range_pct=STRIKE_RANGE_PCT,
    )
    if not channels:
        return
    if _DERIBIT_CACHE is None:
        _DERIBIT_CACHE = DeribitMarketDataCache()
    _DERIBIT_CACHE.configure(channels, instruments=instruments)
    _DERIBIT_CACHE.start_background()


def _deribit_snapshot_from_cached_tickers(
    adapter: DeribitAdapter,
    cached: dict[str, dict[str, Any]],
) -> ExchangeSnapshot:
    insts, quotes, errors = [], {}, []
    for raw in cached.values():
        name = str(raw.get("instrument_name", "unknown"))
        try:
            inst_raw = raw.get("instrument") if isinstance(raw.get("instrument"), dict) else _instrument_from_deribit_name(raw)
            inst = _with_btc_hedge_group(adapter.normalize_instrument(inst_raw))
            q = standardize_quote(adapter.normalize_quote(raw, market_type="option"))
            insts.append(inst)
            quotes[q.instrument_key] = q
        except Exception as e:
            errors.append(f"{name}: {e}")
    return ExchangeSnapshot("deribit", insts, quotes, None, None, 0, errors)


def _instrument_from_deribit_name(raw: dict[str, Any]) -> dict[str, Any]:
    name = str(raw["instrument_name"])
    parts = name.split("-")
    option_code = parts[-1] if parts else ""
    return {
        "instrument_name": name,
        "kind": "option",
        "base_currency": "BTC",
        "quote_currency": "USDC",
        "settlement_currency": "USDC",
        "expiration_timestamp": int(raw.get("expiration_timestamp") or 0),
        "strike": parts[-2] if len(parts) >= 2 else raw.get("strike"),
        "option_type": "call" if option_code == "C" else "put",
        "instrument_type": "linear",
        "settlement_period": "month",
        "contract_size": "1",
        "tick_size": "0.5",
        "price_index": DERIBIT_USDC_UNDERLYING,
        "state": "open",
    }


def _with_btc_hedge_group(instrument: Instrument) -> Instrument:
    return replace(instrument, underlying_id=BTC_USD_HEDGE_GROUP)


def _standardize_deribit_summary_quote(raw: dict[str, Any], *, now_ms: int) -> ExecutableQuote:
    bid = raw.get("bid_price")
    ask = raw.get("ask_price")
    quote = Quote(
        instrument_key=f"deribit:option:{raw['instrument_name']}",
        exchange="deribit",
        market_type="option",
        instrument_id=str(raw["instrument_name"]),
        bid_price=None if bid is None else str(bid),
        ask_price=None if ask is None else str(ask),
        bid_size="1" if bid is not None else None,
        ask_size="1" if ask is not None else None,
        mark_price=None if raw.get("mark_price") is None else str(raw.get("mark_price")),
        underlying_price=None if raw.get("underlying_price") is None else str(raw.get("underlying_price")),
        mark_iv=None if raw.get("mark_iv") is None else str(raw.get("mark_iv")),
        source_updated_at_ms=int(raw.get("creation_timestamp") or now_ms),
        received_at_ms=now_ms,
        normalized_at_ms=now_ms,
        raw=raw,
    )
    return standardize_quote(quote)


def _fetch_binance(now_ms: int) -> ExchangeSnapshot:
    """Binance: batch ticker for all options in one call, spot primary hedge plus perp sell hedge."""
    errors: list[str] = []
    adapter = BinanceAdapter(normalized_at_ms=now_ms, received_at_ms=now_ms)
    base_opt = "https://eapi.binance.com"
    base_spot = "https://api.binance.com"
    base_usdm = "https://fapi.binance.com"

    # exchange info
    info = _http_get(f"{base_opt}/eapi/v1/exchangeInfo")
    option_symbols = info.get("optionSymbols", [])
    option_contracts = {c.get("underlying", ""): c for c in info.get("optionContracts", [])}

    # hedge: spot BTCUSDT. Short spot hedge legs are filtered by the monitor.
    try:
        btc_spot = _http_get(f"{base_spot}/api/v3/ticker/bookTicker?symbol=BTCUSDT")
        hedge_q = standardize_quote(adapter.normalize_spot_book_ticker(btc_spot))
        atm = float(hedge_q.mid_price)
    except Exception as e:
        errors.append(f"spot hedge: {e}")
        hedge_q = None
        atm = 0

    extra_hedges: list[tuple[tuple[str, str], ExecutableQuote]] = []
    try:
        btc_perp = _http_get(f"{base_usdm}/fapi/v1/ticker/bookTicker?symbol=BTCUSDT")
        perp_q = standardize_quote(adapter.normalize_usdm_book_ticker(btc_perp))
        extra_hedges.append((("binance:perpetual", BTC_USD_HEDGE_GROUP), perp_q))
    except Exception as e:
        errors.append(f"perp hedge: {e}")

    if atm <= 0:
        print(f"    Binance: hedge unavailable")
        return ExchangeSnapshot("binance", [], {}, None, None, 0, errors)

    # filter expiries
    all_exps = sorted({s["expiryDate"] for s in option_symbols if s.get("expiryDate")})
    target = set(all_exps[:MAX_EXPIRIES])

    # fetch all option tickers in one batch call (no symbol param = all)
    try:
        tickers_list = _http_get(f"{base_opt}/eapi/v1/ticker")
    except Exception as e:
        errors.append(f"option_ticker: {e}")
        tickers_list = []

    tickers_by_symbol = {t["symbol"]: t for t in tickers_list}

    insts, quotes = [], {}
    lo, hi = atm * (1 - STRIKE_RANGE_PCT / 100), atm * (1 + STRIKE_RANGE_PCT / 100)
    for raw in option_symbols:
        sid = raw["symbol"]
        tkr = tickers_by_symbol.get(sid)
        if tkr is None:
            continue
        exp = raw.get("expiryDate")
        if exp not in target:
            continue
        strike = raw.get("strikePrice")
        if strike is None:
            continue
        try:
            sv = float(str(strike))
        except (ValueError, TypeError):
            continue
        if not (lo <= sv <= hi):
            continue

        # skip instruments with zero bid AND zero ask (untradeable)
        b_str = str(tkr.get("bidPrice", "") or "")
        a_str = str(tkr.get("askPrice", "") or "")
        try:
            if float(b_str) <= 0 and float(a_str) <= 0:
                continue
        except ValueError:
            pass

        try:
            cid = str(raw.get("underlying", ""))
            ctr = option_contracts.get(cid, {})
            inst = _with_btc_hedge_group(adapter.normalize_option_instrument(raw, option_contract=ctr))
            q_raw = adapter.normalize_option_mark_quote(tkr)
            # ticker endpoint lacks bidQty/askQty, and some quotes have crossed bid/ask
            if q_raw.bid_price is not None and q_raw.ask_price is not None:
                from decimal import Decimal
                if Decimal(q_raw.bid_price) > Decimal(q_raw.ask_price):
                    # crossed book, skip (can't compute mid)
                    continue
            from dataclasses import replace
            if q_raw.bid_size is None:
                q_raw = replace(q_raw, bid_size="1")
            if q_raw.ask_size is None:
                q_raw = replace(q_raw, ask_size="1")
            q = standardize_quote(q_raw)
            insts.append(inst)
            quotes[q.instrument_key] = q
        except Exception as e:
            errors.append(f"{sid}: {e}")

    print(f"    Binance: {len(insts)} options, hedge={atm:.0f}")
    hedge_key = ("binance", BTC_USD_HEDGE_GROUP) if hedge_q else None
    return ExchangeSnapshot("binance", insts, quotes, hedge_q, hedge_key, atm, errors, extra_hedges)


def _fetch_okx(now_ms: int) -> ExchangeSnapshot:
    """OKX: single tickers batch call."""
    errors: list[str] = []
    adapter = OkxAdapter(normalized_at_ms=now_ms, received_at_ms=now_ms)
    base = "https://www.okx.com"
    family = f"{CURRENCY}-USD"

    # instruments & tickers in parallel
    insts_raw = _http_get(f"{base}/api/v5/public/instruments?instType=OPTION&instFamily={family}")["data"]
    tickers_raw = _http_get(f"{base}/api/v5/market/tickers?instType=OPTION&instFamily={family}")["data"]
    tkrs_by_id = {t["instId"]: t for t in tickers_raw}

    # hedge: spot BTC-USDT. Short spot hedge legs are filtered by the monitor.
    try:
        hedge_raw = _http_get(f"{base}/api/v5/market/ticker?instId=BTC-USDT")["data"]
        btc_list = [t for t in hedge_raw if t.get("instId") == "BTC-USDT"]
        if btc_list:
            hq = adapter.normalize_ticker(btc_list[0])
            hedge_q = standardize_quote(hq)
            atm = float(hedge_q.mid_price)
        else:
            raise ValueError("BTC-USDT not found in spot ticker")
    except Exception as e:
        errors.append(f"spot hedge: {e}")
        hedge_q = None
        atm = 0

    extra_hedges: list[tuple[tuple[str, str], ExecutableQuote]] = []
    try:
        hedge_raw = _http_get(f"{base}/api/v5/market/tickers?instType=SWAP&instFamily={family}")["data"]
        btc_list = [t for t in hedge_raw if t.get("instId") == f"{family}-SWAP"]
        if btc_list:
            perp_q = standardize_quote(adapter.normalize_ticker(btc_list[0]))
            extra_hedges.append((("okx:perpetual", BTC_USD_HEDGE_GROUP), perp_q))
        else:
            raise ValueError(f"{family}-SWAP not found in swap tickers")
    except Exception as e:
        errors.append(f"perp hedge: {e}")

    insts, quotes = [], {}
    lo, hi = atm * (1 - STRIKE_RANGE_PCT / 100), atm * (1 + STRIKE_RANGE_PCT / 100) if atm else (0, 1e9)
    all_exps = sorted({i["expTime"] for i in insts_raw if i.get("expTime")})
    target = set(all_exps[:MAX_EXPIRIES])

    for raw in insts_raw:
        iid = raw.get("instId", "")
        exp = raw.get("expTime")
        if exp not in target or iid not in tkrs_by_id:
            continue
        strike = raw.get("stk")
        if strike is None:
            continue
        try:
            sv = float(str(strike))
        except (ValueError, TypeError):
            continue
        if not (lo <= sv <= hi):
            continue
        try:
            inst = _with_btc_hedge_group(adapter.normalize_instrument(raw))
            tkr = tkrs_by_id[iid]
            q = standardize_quote(adapter.normalize_ticker(tkr))
            insts.append(inst)
            quotes[q.instrument_key] = q
        except Exception as e:
            errors.append(f"{iid}: {e}")

    print(f"    OKX:     {len(insts)} options, hedge={atm:.0f}")
    hedge_key = ("okx", BTC_USD_HEDGE_GROUP) if hedge_q else None
    return ExchangeSnapshot("okx", insts, quotes, hedge_q, hedge_key, atm, errors, extra_hedges)


def _fetch_bybit(now_ms: int) -> ExchangeSnapshot:
    """Bybit: tickers per base_coin per expiry (paginated)."""
    errors: list[str] = []
    adapter = BybitAdapter(normalized_at_ms=now_ms, received_at_ms=now_ms)
    base = "https://api.bybit.com"
    coin = CURRENCY

    # instruments (paginated)
    insts_raw: list[dict] = []
    cursor = None
    while True:
        params = {"category": "option", "baseCoin": coin, "status": "Trading", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        resp = _http_get(f"{base}/v5/market/instruments-info?{urlencode(params)}")
        items = resp.get("result", {}).get("list", [])
        insts_raw.extend(items)
        cursor = resp.get("result", {}).get("nextPageCursor", "")
        if not cursor or not items:
            break

    # tickers: batch by baseCoin, but may need pagination too
    tickers_raw: list[dict] = []
    cursor = None
    while True:
        params = {"category": "option", "baseCoin": coin, "limit": 200}
        if cursor:
            params["cursor"] = cursor
        resp = _http_get(f"{base}/v5/market/tickers?{urlencode(params)}")
        items = resp.get("result", {}).get("list", [])
        tickers_raw.extend(items)
        cursor = resp.get("result", {}).get("nextPageCursor", "")
        if not cursor or not items:
            break
    tkrs_by_sym = {t["symbol"]: t for t in tickers_raw}

    # hedge: spot BTCUSDT. Short spot hedge legs are filtered by the monitor.
    try:
        hedge_raw = _http_get(f"{base}/v5/market/tickers?category=spot&symbol=BTCUSDT")
        hlist = hedge_raw.get("result", {}).get("list", [])
        if hlist:
            hq = adapter.normalize_ticker(hlist[0], category="spot")
            hedge_q = standardize_quote(hq)
            atm = float(hedge_q.mid_price)
        else:
            raise ValueError("no spot ticker")
    except Exception as e:
        errors.append(f"spot hedge: {e}")
        hedge_q = None
        atm = 0

    extra_hedges: list[tuple[tuple[str, str], ExecutableQuote]] = []
    try:
        hedge_raw = _http_get(f"{base}/v5/market/tickers?category=linear&symbol=BTCUSDT")
        hlist = hedge_raw.get("result", {}).get("list", [])
        if hlist:
            perp_q = standardize_quote(adapter.normalize_ticker(hlist[0], category="linear"))
            extra_hedges.append((("bybit:perpetual", BTC_USD_HEDGE_GROUP), perp_q))
        else:
            raise ValueError("no perpetual ticker")
    except Exception as e:
        errors.append(f"perp hedge: {e}")

    insts, quotes = [], {}
    lo, hi = atm * (1 - STRIKE_RANGE_PCT / 100), atm * (1 + STRIKE_RANGE_PCT / 100) if atm else (0, 1e9)
    all_exps = sorted({i["deliveryTime"] for i in insts_raw if i.get("deliveryTime")})
    target = set(all_exps[:MAX_EXPIRIES])

    for raw in insts_raw:
        sid = raw.get("symbol", "")
        exp = raw.get("deliveryTime")
        if exp not in target or sid not in tkrs_by_sym:
            continue
        # extract strike from symbol for filter
        parts = sid.split("-")
        if len(parts) < 4:
            continue
        try:
            sv = float(parts[2])
        except (ValueError, TypeError):
            continue
        if not (lo <= sv <= hi):
            continue
        try:
            inst = _with_btc_hedge_group(adapter.normalize_instrument(raw, category="option"))
            tkr = tkrs_by_sym[sid]
            q = standardize_quote(adapter.normalize_ticker(tkr, category="option"))
            insts.append(inst)
            quotes[q.instrument_key] = q
        except Exception as e:
            errors.append(f"{sid}: {e}")

    print(f"    Bybit:   {len(insts)} options, hedge={atm:.0f}")
    hedge_key = ("bybit", BTC_USD_HEDGE_GROUP) if hedge_q else None
    return ExchangeSnapshot("bybit", insts, quotes, hedge_q, hedge_key, atm, errors, extra_hedges)


def _fetch_gate(now_ms: int) -> ExchangeSnapshot:
    """Gate: public BTC_USDT options plus index-price hedge."""
    errors: list[str] = []
    adapter = GateAdapter(normalized_at_ms=now_ms, received_at_ms=now_ms)
    base = "https://api.gateio.ws/api/v4"
    underlying = "BTC_USDT"

    try:
        underlying_ticker = _http_get(f"{base}/options/underlying/tickers/{underlying}")
        index_price = str(underlying_ticker["index_price"])
        hedge_q = standardize_quote(
            Quote(
                instrument_key="gate:spot:BTC_USDT",
                exchange="gate",
                market_type="spot",
                instrument_id="BTC_USDT",
                bid_price=index_price,
                ask_price=index_price,
                bid_size="1",
                ask_size="1",
                mid_price=index_price,
                index_price=index_price,
                received_at_ms=now_ms,
                normalized_at_ms=now_ms,
                raw=underlying_ticker,
            )
        )
        atm = float(hedge_q.mid_price)
    except Exception as e:
        errors.append(f"underlying hedge: {e}")
        hedge_q = None
        atm = 0

    try:
        insts_raw = _http_get(f"{base}/options/contracts?underlying={underlying}")
    except Exception as e:
        errors.append(f"contracts: {e}")
        insts_raw = []

    try:
        tickers_raw = _http_get(f"{base}/options/tickers?underlying={underlying}")
    except Exception as e:
        errors.append(f"tickers: {e}")
        tickers_raw = []

    tkrs_by_name = {t["name"]: t for t in tickers_raw if t.get("name")}
    all_exps = sorted({i["expiration_time"] for i in insts_raw if i.get("expiration_time")})
    target = set(all_exps[:MAX_EXPIRIES])
    if atm:
        lo, hi = atm * (1 - STRIKE_RANGE_PCT / 100), atm * (1 + STRIKE_RANGE_PCT / 100)
    else:
        lo, hi = 0, 1e12

    insts, quotes = [], {}
    for raw in insts_raw:
        name = raw.get("name", "")
        exp = raw.get("expiration_time")
        if exp not in target or name not in tkrs_by_name:
            continue
        strike = raw.get("strike_price")
        if strike is None:
            continue
        try:
            strike_value = float(str(strike))
        except (ValueError, TypeError):
            continue
        if not (lo <= strike_value <= hi):
            continue
        try:
            inst = _with_btc_hedge_group(adapter.normalize_contract(raw))
            book_raw = _http_get(
                f"{base}/options/order_book?{urlencode({'contract': name, 'limit': 5, 'with_id': 'true'})}"
            )
            q = _executable_quote_from_order_book(standardize_order_book(adapter.normalize_order_book(book_raw, contract=name)))
            insts.append(inst)
            quotes[q.instrument_key] = q
        except Exception as e:
            errors.append(f"{name}: {e}")

    print(f"    Gate:    {len(insts)} options, hedge={atm:.0f}")
    hedge_key = ("gate", BTC_USD_HEDGE_GROUP) if hedge_q else None
    return ExchangeSnapshot("gate", insts, quotes, hedge_q, hedge_key, atm, errors)


def _executable_quote_from_order_book(order_book: StandardizedOrderBook) -> ExecutableQuote:
    return ExecutableQuote(
        instrument_key=order_book.instrument_key,
        exchange=order_book.exchange,
        market_type=order_book.market_type,
        instrument_id=order_book.instrument_id,
        best_bid_price=order_book.best_bid_price,
        best_ask_price=order_book.best_ask_price,
        best_bid_size=order_book.best_bid_size,
        best_ask_size=order_book.best_ask_size,
        mid_price=order_book.mid_price,
        spread=order_book.spread,
        received_at_ms=order_book.received_at_ms,
        normalized_at_ms=order_book.normalized_at_ms,
        has_executable_quote=order_book.has_depth,
    )


# ═══════════════════════════════════════════════════════════════
# Scanner
# ═══════════════════════════════════════════════════════════════

FETCHERS: dict[str, Callable[[int], ExchangeSnapshot]] = {
    "deribit": _fetch_deribit,
    "binance": _fetch_binance,
    "okx": _fetch_okx,
    "bybit": _fetch_bybit,
    "gate": _fetch_gate,
}


def scan_all(exchanges: list[str] | None = None) -> dict[str, Any]:
    """Fetch data from all specified exchanges, run arbitrage scan, return combined results."""
    if exchanges is None:
        exchanges = list(FETCHERS)

    now_ms = int(time.time() * 1000)

    # Phase 1: parallel fetch (threads)
    print("=" * 72)
    print("  多交易所套利扫描")
    print("=" * 72)
    print(f"  目标: {', '.join(exchanges)}")
    print(f"  行权价范围: ±{STRIKE_RANGE_PCT}%  |  到期日: 前 {MAX_EXPIRIES} 个")
    print()

    snapshots: dict[str, ExchangeSnapshot] = {}
    threads: list[Thread] = []

    def _worker(exch: str, now_ms: int):
        try:
            snapshots[exch] = FETCHERS[exch](now_ms)
        except Exception as exc:
            print(f"    ✗ {exch}: {exc}")
            snapshots[exch] = ExchangeSnapshot(exch, [], {}, None, None, 0, [str(exc)])

    for ex in exchanges:
        t = Thread(target=_worker, args=(ex, now_ms), daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join(timeout=120)

    # Phase 2: build combined MarketDataBatch
    all_instruments: list[Instrument] = []
    all_quotes: dict[str, ExecutableQuote] = {}
    all_hedges: dict[tuple[str, str], ExecutableQuote] = {}

    for name, snap in snapshots.items():
        all_instruments.extend(snap.instruments)
        all_quotes.update(snap.quotes_by_key)
        if snap.hedge_quote and snap.hedge_key:
            all_hedges[snap.hedge_key] = snap.hedge_quote
            all_quotes[snap.hedge_quote.instrument_key] = snap.hedge_quote
        for hedge_key, hedge_quote in snap.extra_hedges:
            all_hedges[hedge_key] = hedge_quote
            all_quotes[hedge_quote.instrument_key] = hedge_quote

    if not all_instruments:
        print("\n  ✗ 无可用数据")
        return {"opportunities": [], "total": 0, "snapshots": snapshots, "error": "no instruments"}

    # Phase 3: scan
    batch = MarketDataBatch(
        instruments=all_instruments,
        quotes_by_instrument_key=all_quotes,
        hedge_quotes_by_underlying=all_hedges,
    )

    store = OpportunityHistoryStore(str(OUT_DIR / "opportunities.sqlite3"))
    monitor = ArbitrageMonitor(
        MonitorConfig(fee_rate=FEE_RATE, capital_requirement_rate=CAPITAL_RATE),
        history_store=store,
    )
    result = monitor.scan_once(batch, observed_at_ms=now_ms)

    # Phase 4: collect output
    opportunities = []
    for o in result.displayed_opportunities:
        d = {
            "id": o.opportunity_id,
            "type": o.opportunity_type,
            "exchange": o.exchange,
            "underlying": o.underlying_id,
            "expiry_ms": o.expiry_time_ms,
            "strike": o.strike,
            "lower_strike": o.lower_strike,
            "upper_strike": o.upper_strike,
            "direction": o.direction,
            "gross_profit": o.gross_profit,
            "annualized_return": o.annualized_net_return,
            "capital": o.capital_required,
            "executable": o.is_executable,
            "pcp_execution_mode": o.pcp_execution_mode,
            "risk_tags": o.risk_tags or [],
        }
        try:
            legs = getattr(o, "legs", [])
            if legs and not isinstance(legs, str):
                d["legs"] = [
                    {"instrument_key": getattr(l, "instrument_key", ""),
                     "side": getattr(l, "side", ""),
                     "price": getattr(l, "price", ""),
                     "size": getattr(l, "size", ""),
                     "role": getattr(l, "role", "")}
                    for l in legs
                ]
        except Exception:
            pass
        opportunities.append(d)


    return {
        "opportunities": opportunities,
        "total": len(opportunities),
        "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "scanned_at_ms": now_ms,
        "snapshots": snapshots,
    }


def print_results(data: dict[str, Any]) -> None:
    opps = data.get("opportunities", [])
    snaps = data.get("snapshots", {})

    print()
    print("=" * 72)
    print("  汇总")
    print("=" * 72)
    for name, snap in snaps.items():
        status = "✓" if snap.hedge_quote else "✗"
        print(f"  {status} {name:8s}  {len(snap.instruments):4d} options  |  errors: {len(snap.errors)}")

    print(f"\n  总机会: {len(opps)}")

    if not opps:
        print("  未发现套利机会。")
        return

    by_exch: dict[str, int] = {}
    by_type: dict[str, int] = {}
    exec_count = 0
    for o in opps:
        by_exch[o["exchange"]] = by_exch.get(o["exchange"], 0) + 1
        by_type[o["type"]] = by_type.get(o["type"], 0) + 1
        if o["executable"]:
            exec_count += 1

    print(f"  按交易所: {by_exch}")
    print(f"  按类型: {by_type}")
    print(f"  可执行: {exec_count}")

    # top 10
    print(f"\n{'─' * 72}")
    print(f"  前 10 条最佳机会:")
    print(f"{'─' * 72}")
    sorted_opps = sorted(opps, key=lambda o: float(o.get("gross_profit") or 0), reverse=True)
    for i, o in enumerate(sorted_opps[:10]):
        labels = {"put_call_parity": "PCP", "box_spread": "Box", "implied_futures_basis": "IFB"}
        s = o.get("strike") or f"{o.get('lower_strike','')}-{o.get('upper_strike','')}"
        print(f"\n  [{i+1}] [{labels.get(o['type'], o['type'])}] {o['exchange']} {s}")
        print(f"      方向: {o['direction']}")
        print(f"      毛收益: {_fmt_usd(o['gross_profit'])}")
        print(f"      年化: {_fmt_apy(o['annualized_return'])}")
        print(f"      可执行: {o['executable']}  {'| ' + ', '.join(str(t) for t in (o.get('risk_tags') or [])) if o.get('risk_tags') else ''}")

    # HTML
    html = _render_html(data)
    html_path = OUT_DIR / "index.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"\n  看板: file://{html_path.resolve()}  ({len(html):,} bytes)")


def _render_html(data: dict[str, Any]) -> str:
    """Minimal static report for quick verification."""
    opps = data.get("opportunities", [])
    snaps = data.get("snapshots", {})

    rows = ""
    for o in sorted(opps, key=lambda o: float(o.get("gross_profit") or 0), reverse=True):
        labels = {"put_call_parity": "PCP", "box_spread": "Box", "implied_futures_basis": "IFB"}
        s = o.get("strike") or f"{o.get('lower_strike','')}-{o.get('upper_strike','')}"
        rows += f"""<tr>
<td>{labels.get(o['type'], o['type'])}</td>
<td>{o['exchange']}</td>
<td>{s}</td>
<td>{o['direction']}</td>
<td style="text-align:right">{_fmt_usd(o['gross_profit'])}</td>
<td style="text-align:right">{_fmt_apy(o['annualized_return'])}</td>
<td>{'✓' if o['executable'] else '—'}</td>
</tr>"""

    snap_summary = "".join(
        f"<tr><td>{name}</td><td style='text-align:right'>{s.hedge_quote and '✓' or '✗'}</td>"
        f"<td style='text-align:right'>{len(s.instruments)}</td></tr>"
        for name, s in snaps.items()
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>套利扫描报告 · Arbitrage Scan</title>
<style>
body{{background:#0c0c0b;color:#c4c1b8;font-family:system-ui,sans-serif;padding:24px;max-width:1200px;margin:0 auto}}
h1{{font-size:20px;color:#e8e4da;margin-bottom:4px}}
h2{{font-size:14px;color:#706d64;font-weight:400;margin-bottom:20px}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1px;background:#2a2922;margin-bottom:20px}}
.summary>div{{background:#131310;padding:14px 18px}}
.summary .label{{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:#706d64}}
.summary .value{{font-size:22px;font-weight:700;color:#e8e4da;margin-top:4px}}
table{{width:100%;border-collapse:collapse;margin-top:12px}}
th{{text-align:left;padding:8px 10px;border-bottom:2px solid #2a2922;font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:#706d64}}
td{{padding:7px 10px;border-bottom:1px solid #2a2922;font-size:13px}}
tr:hover td{{background:#1a1a16}}
.section{{margin-top:28px}}
</style></head>
<body>
<h1>套利扫描报告</h1>
<h2>{data.get('scanned_at', '—')} · {len(opps)} 机会</h2>

<div class="summary">
<div><div class="label">总机会</div><div class="value">{len(opps)}</div></div>
<div><div class="label">交易所</div><div class="value">{len(snaps)}</div></div>
</div>

<div class="section"><h2>交易所状态</h2>
<table><tr><th>交易所</th><th>对冲</th><th>期权</th></tr>{snap_summary}</table></div>

<div class="section"><h2>套利机会</h2>
{'<p style="color:#706d64">未发现套利机会。</p>' if not opps else ''}
{"<table><tr><th>类型</th><th>交易所</th><th>行权价</th><th>方向</th><th>毛收益</th><th>年化</th><th>可执行</th></tr>" + rows + "</table>" if opps else ""}
</div>
</body></html>"""


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    exchanges = None
    for arg in sys.argv[1:]:
        if arg.startswith("--exchange="):
            exchanges = arg.split("=")[1].split(",")

    data = scan_all(exchanges)
    print_results(data)


if __name__ == "__main__":
    main()
