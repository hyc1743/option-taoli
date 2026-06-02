from __future__ import annotations

from option_taoli.deribit_ws_cache import DeribitTickerCache, plan_deribit_option_subscriptions


def option(name: str, strike: str, expiry: int = 1751011200000):
    return {
        "instrument_name": name,
        "kind": "option",
        "base_currency": "BTC",
        "quote_currency": "USDC",
        "settlement_currency": "USDC",
        "expiration_timestamp": expiry,
        "strike": strike,
        "option_type": "call" if name.endswith("-C") else "put",
        "instrument_type": "linear",
        "settlement_period": "month",
        "contract_size": "1",
        "tick_size": "0.5",
        "price_index": "btc_usdc",
        "state": "open",
    }


def test_plans_subscriptions_for_nearby_deribit_usdc_options():
    instruments = [
        option("BTC_USDC-27JUN25-90000-C", "90000"),
        option("BTC_USDC-27JUN25-100000-P", "100000"),
        option("BTC_USDC-27JUN25-130000-C", "130000"),
        option("ETH_USDC-27JUN25-100000-C", "100000"),
    ]

    selected = plan_deribit_option_subscriptions(
        instruments,
        atm_price=100000,
        max_expiries=1,
        strike_range_pct=12,
    )

    assert selected == [
        "ticker.BTC_USDC-27JUN25-90000-C.raw",
        "ticker.BTC_USDC-27JUN25-100000-P.raw",
    ]


def test_ticker_cache_excludes_stale_or_one_sided_quotes():
    cache = DeribitTickerCache(ttl_ms=1000)
    cache.update(
        {
            "instrument_name": "BTC_USDC-27JUN25-90000-C",
            "best_bid_price": "100",
            "best_ask_price": "110",
            "best_bid_amount": "2",
            "best_ask_amount": "3",
            "timestamp": 1810880000000,
        },
        received_at_ms=1810880000000,
    )
    cache.update(
        {
            "instrument_name": "BTC_USDC-27JUN25-90000-P",
            "best_bid_price": "90",
            "best_bid_amount": "2",
            "timestamp": 1810880000000,
        },
        received_at_ms=1810880000000,
    )

    fresh = cache.snapshot(now_ms=1810880000500)
    stale = cache.snapshot(now_ms=1810880002001)

    assert list(fresh) == ["BTC_USDC-27JUN25-90000-C"]
    assert stale == {}
