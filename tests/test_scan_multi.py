import scan_multi


def test_deribit_fetcher_uses_usdc_settled_btc_options_without_deribit_hedge(monkeypatch):
    seen_urls = []

    def fake_http_get(url: str, timeout: int = 15):
        seen_urls.append(url)
        if "public/get_instruments?currency=USDC&kind=option&expired=false" in url:
            return {
                "result": [
                    {
                        "instrument_name": "BTC_USDC-27JUN25-100000-C",
                        "kind": "option",
                        "base_currency": "BTC",
                        "quote_currency": "USDC",
                        "settlement_currency": "USDC",
                        "expiration_timestamp": 1751011200000,
                        "strike": "100000",
                        "option_type": "call",
                        "instrument_type": "linear",
                        "settlement_period": "month",
                        "contract_size": "1",
                        "tick_size": "0.5",
                        "price_index": "btc_usdc",
                        "state": "open",
                    }
                ]
            }
        if url.endswith("public/ticker?instrument_name=BTC_USDC"):
            return {
                "result": {
                    "instrument_name": "BTC_USDC",
                    "best_bid_price": "100000",
                    "best_ask_price": "100010",
                    "best_bid_amount": "2",
                    "best_ask_amount": "2",
                    "timestamp": 1810880000000,
                }
            }
        if "public/get_book_summary_by_currency?currency=USDC&kind=option" in url:
            return {
                "result": [
                    {
                        "instrument_name": "BTC_USDC-27JUN25-100000-C",
                        "bid_price": "5000",
                        "ask_price": "5010",
                        "mark_price": "5005",
                        "underlying_price": "100005",
                        "creation_timestamp": 1810880000000,
                    }
                ]
            }
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(scan_multi, "_http_get", fake_http_get)
    monkeypatch.setattr(scan_multi.time, "sleep", lambda _: None)
    monkeypatch.setattr(scan_multi, "_DERIBIT_CACHE", None)

    snapshot = scan_multi._fetch_deribit(1810880000000)

    assert snapshot.hedge_quote is None
    assert snapshot.hedge_key is None
    assert [instrument.instrument_key for instrument in snapshot.instruments] == [
        "deribit:option:BTC_USDC-27JUN25-100000-C"
    ]
    assert snapshot.instruments[0].settlement_asset == "USDC"
    assert snapshot.instruments[0].contract_type == "linear"
    assert snapshot.instruments[0].underlying_id == scan_multi.BTC_USD_HEDGE_GROUP
    assert list(snapshot.quotes_by_key) == ["deribit:option:BTC_USDC-27JUN25-100000-C"]
    assert not any("BTC-PERPETUAL" in url or "currency=BTC" in url for url in seen_urls)
    assert not any("public/ticker?instrument_name=BTC_USDC-27JUN25-100000-C" in url for url in seen_urls)


def test_deribit_fetcher_prefers_warm_cache(monkeypatch):
    class FakeCache:
        def snapshot(self, *, now_ms):
            return scan_multi.ExchangeSnapshot("deribit", [], {}, None, None, 0, [])

    def fail_http_get(url: str, timeout: int = 15):
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(scan_multi, "_DERIBIT_CACHE", FakeCache())
    monkeypatch.setattr(scan_multi, "_http_get", fail_http_get)

    snapshot = scan_multi._fetch_deribit(1810880000000)

    assert snapshot.exchange == "deribit"
    assert snapshot.hedge_quote is None


def test_binance_fetcher_uses_spot_for_hedge(monkeypatch):
    def fake_http_get(url: str, timeout: int = 15):
        if "eapi/v1/exchangeInfo" in url:
            return {
                "optionContracts": [{"underlying": "BTCUSDT", "baseAsset": "BTC"}],
                "optionSymbols": [
                    {
                        "symbol": "BTC-260626-100000-C",
                        "underlying": "BTCUSDT",
                        "quoteAsset": "USDT",
                        "settleAsset": "USDT",
                        "expiryDate": 1782432000000,
                        "strikePrice": "100000",
                        "side": "CALL",
                        "unit": "1",
                        "status": "TRADING",
                        "filters": [],
                    }
                ],
            }
        if "api/v3/ticker/bookTicker" in url:
            return {"symbol": "BTCUSDT", "bidPrice": "100000", "askPrice": "100010", "bidQty": "2", "askQty": "2"}
        if "fapi/v1/ticker/bookTicker" in url:
            return {"symbol": "BTCUSDT", "bidPrice": "100020", "askPrice": "100030", "bidQty": "2", "askQty": "2"}
        if "eapi/v1/ticker" in url:
            return [
                {
                    "symbol": "BTC-260626-100000-C",
                    "bidPrice": "5000",
                    "askPrice": "5010",
                }
            ]
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(scan_multi, "_http_get", fake_http_get)

    snapshot = scan_multi._fetch_binance(1810880000000)

    assert snapshot.hedge_quote is not None
    assert snapshot.hedge_quote.market_type == "spot"
    assert snapshot.hedge_quote.instrument_key == "binance:spot:BTCUSDT"
    assert snapshot.hedge_key == ("binance", scan_multi.BTC_USD_HEDGE_GROUP)
    assert snapshot.extra_hedges[0][0] == ("binance:perpetual", scan_multi.BTC_USD_HEDGE_GROUP)
    assert snapshot.extra_hedges[0][1].instrument_key == "binance:perpetual:BTCUSDT"
    assert snapshot.instruments[0].underlying_id == scan_multi.BTC_USD_HEDGE_GROUP


def test_okx_fetcher_uses_spot_for_hedge(monkeypatch):
    def fake_http_get(url: str, timeout: int = 15):
        if "public/instruments?instType=OPTION" in url:
            return {
                "data": [
                    {
                        "instType": "OPTION",
                        "instId": "BTC-USD-260626-100000-C",
                        "uly": "BTC-USD",
                        "instFamily": "BTC-USD",
                        "expTime": "1782432000000",
                        "stk": "100000",
                        "optType": "C",
                        "ctType": "linear",
                        "ctVal": "1",
                        "ctValCcy": "USD",
                        "settleCcy": "USD",
                        "tickSz": "0.1",
                        "minSz": "1",
                        "lotSz": "1",
                        "state": "live",
                    }
                ]
            }
        if "market/tickers?instType=OPTION" in url:
            return {
                "data": [
                    {
                        "instType": "OPTION",
                        "instId": "BTC-USD-260626-100000-C",
                        "bidPx": "5000",
                        "askPx": "5010",
                        "bidSz": "1",
                        "askSz": "1",
                        "ts": "1810880000000",
                    }
                ]
            }
        if "market/ticker?instId=BTC-USDT" in url:
            return {
                "data": [
                    {
                        "instType": "SPOT",
                        "instId": "BTC-USDT",
                        "bidPx": "100000",
                        "askPx": "100010",
                        "bidSz": "2",
                        "askSz": "2",
                        "ts": "1810880000000",
                    }
                ]
            }
        if "market/tickers?instType=SWAP" in url:
            return {
                "data": [
                    {
                        "instType": "SWAP",
                        "instId": "BTC-USD-SWAP",
                        "bidPx": "100020",
                        "askPx": "100030",
                        "bidSz": "2",
                        "askSz": "2",
                        "ts": "1810880000000",
                    }
                ]
            }
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(scan_multi, "_http_get", fake_http_get)

    snapshot = scan_multi._fetch_okx(1810880000000)

    assert snapshot.hedge_quote is not None
    assert snapshot.hedge_quote.market_type == "spot"
    assert snapshot.hedge_quote.instrument_key == "okx:spot:BTC-USDT"
    assert snapshot.hedge_key == ("okx", scan_multi.BTC_USD_HEDGE_GROUP)
    assert snapshot.extra_hedges[0][0] == ("okx:perpetual", scan_multi.BTC_USD_HEDGE_GROUP)
    assert snapshot.extra_hedges[0][1].instrument_key == "okx:perpetual:BTC-USD-SWAP"
    assert snapshot.instruments[0].underlying_id == scan_multi.BTC_USD_HEDGE_GROUP


def test_bybit_fetcher_uses_shared_btc_hedge_group(monkeypatch):
    def fake_http_get(url: str, timeout: int = 15):
        if "instruments-info" in url:
            return {
                "result": {
                    "list": [
                        {
                            "symbol": "BTC-26JUN26-100000-C",
                            "baseCoin": "BTC",
                            "quoteCoin": "USDT",
                            "settleCoin": "USDT",
                            "deliveryTime": "1782432000000",
                            "optionsType": "Call",
                            "status": "Trading",
                            "priceFilter": {"tickSize": "0.1"},
                            "lotSizeFilter": {"minOrderQty": "1", "qtyStep": "1"},
                        }
                    ],
                    "nextPageCursor": "",
                }
            }
        if "market/tickers?category=option" in url:
            return {
                "result": {
                    "list": [
                        {
                            "symbol": "BTC-26JUN26-100000-C",
                            "bid1Price": "5000",
                            "ask1Price": "5010",
                            "bid1Size": "1",
                            "ask1Size": "1",
                            "markPrice": "5005",
                        }
                    ],
                    "nextPageCursor": "",
                }
            }
        if "market/tickers?category=spot&symbol=BTCUSDT" in url:
            return {
                "result": {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "bid1Price": "100000",
                            "ask1Price": "100010",
                            "bid1Size": "2",
                            "ask1Size": "2",
                            "markPrice": "100005",
                        }
                    ]
                }
            }
        if "market/tickers?category=linear&symbol=BTCUSDT" in url:
            return {
                "result": {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "bid1Price": "100020",
                            "ask1Price": "100030",
                            "bid1Size": "2",
                            "ask1Size": "2",
                            "markPrice": "100025",
                        }
                    ]
                }
            }
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(scan_multi, "_http_get", fake_http_get)

    snapshot = scan_multi._fetch_bybit(1810880000000)

    assert snapshot.hedge_quote is not None
    assert snapshot.hedge_quote.market_type == "spot"
    assert snapshot.hedge_quote.instrument_key == "bybit:spot:BTCUSDT"
    assert snapshot.extra_hedges[0][0] == ("bybit:perpetual", scan_multi.BTC_USD_HEDGE_GROUP)
    assert snapshot.extra_hedges[0][1].instrument_key == "bybit:perpetual:BTCUSDT"
    assert snapshot.hedge_key == ("bybit", scan_multi.BTC_USD_HEDGE_GROUP)
    assert snapshot.instruments[0].underlying_id == scan_multi.BTC_USD_HEDGE_GROUP


def test_gate_fetcher_uses_shared_btc_hedge_group(monkeypatch):
    def fake_http_get(url: str, timeout: int = 15):
        if "/options/underlying/tickers/BTC_USDT" in url:
            return {"index_price": "100005", "trade_put": 1, "trade_call": 1}
        if "/options/contracts?underlying=BTC_USDT" in url:
            return [
                {
                    "name": "BTC_USDT-20260626-100000-C",
                    "expiration_time": 1782432000,
                    "is_call": True,
                    "strike_price": "100000",
                    "underlying": "BTC_USDT",
                    "underlying_price": "100005",
                    "multiplier": "0.0001",
                    "order_price_round": "0.1",
                    "order_size_min": 1,
                }
            ]
        if "/options/tickers?underlying=BTC_USDT" in url:
            return [
                {
                    "name": "BTC_USDT-20260626-100000-C",
                    "bid1_price": "4990",
                    "ask1_price": "5020",
                    "bid1_size": 1,
                    "ask1_size": 1,
                    "mark_price": "5005",
                    "index_price": "100005",
                }
            ]
        if "/options/order_book?contract=BTC_USDT-20260626-100000-C" in url:
            return {
                "id": 11,
                "current": 1810880000.123,
                "update": 1810880000.111,
                "bids": [{"p": "5000", "s": 2}],
                "asks": [{"p": "5010", "s": 3}],
            }
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(scan_multi, "_http_get", fake_http_get)

    snapshot = scan_multi._fetch_gate(1810880000000)

    assert snapshot.hedge_quote is not None
    assert snapshot.hedge_quote.instrument_key == "gate:spot:BTC_USDT"
    assert snapshot.hedge_key == ("gate", scan_multi.BTC_USD_HEDGE_GROUP)
    assert snapshot.instruments[0].instrument_key == "gate:option:BTC_USDT-20260626-100000-C"
    assert snapshot.instruments[0].underlying_id == scan_multi.BTC_USD_HEDGE_GROUP
    assert list(snapshot.quotes_by_key) == ["gate:option:BTC_USDT-20260626-100000-C"]
    quote = snapshot.quotes_by_key["gate:option:BTC_USDT-20260626-100000-C"]
    assert quote.best_bid_price == "5000"
    assert quote.best_ask_price == "5010"
    assert quote.best_bid_size == "2"
    assert quote.best_ask_size == "3"
