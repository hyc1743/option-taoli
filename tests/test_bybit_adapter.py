from option_taoli.adapters.bybit import BybitAdapter


def test_normalizes_bybit_option_instrument_and_parses_symbol():
    adapter = BybitAdapter(normalized_at_ms=1780210000000)

    instrument = adapter.normalize_instrument(
        {
            "symbol": "BTC-26MAR27-78000-P-USDT",
            "status": "Trading",
            "baseCoin": "BTC",
            "quoteCoin": "USDT",
            "settleCoin": "USDT",
            "optionsType": "Put",
            "deliveryTime": "1806048000000",
            "priceFilter": {"tickSize": "5"},
            "lotSizeFilter": {"minOrderQty": "0.01", "qtyStep": "0.01"},
        },
        category="option",
    )

    assert instrument.instrument_key == "bybit:option:BTC-26MAR27-78000-P-USDT"
    assert instrument.exchange == "bybit"
    assert instrument.market_type == "option"
    assert instrument.instrument_id == "BTC-26MAR27-78000-P-USDT"
    assert instrument.base_asset == "BTC"
    assert instrument.quote_asset == "USDT"
    assert instrument.settlement_asset == "USDT"
    assert instrument.underlying_id == "BTC"
    assert instrument.expiry_time_ms == 1806048000000
    assert instrument.strike == "78000"
    assert instrument.option_type == "put"
    assert instrument.contract_type == "linear"
    assert instrument.contract_size == "1"
    assert instrument.tick_size == "5"
    assert instrument.min_order_size == "0.01"
    assert instrument.qty_step == "0.01"
    assert instrument.status == "trading"


def test_normalizes_bybit_spot_instrument_to_internal_model():
    adapter = BybitAdapter(normalized_at_ms=1780210000000)

    instrument = adapter.normalize_instrument(
        {
            "symbol": "BTCUSDT",
            "baseCoin": "BTC",
            "quoteCoin": "USDT",
            "status": "Trading",
            "lotSizeFilter": {
                "basePrecision": "0.000001",
                "minOrderQty": "0.000001",
                "minOrderAmt": "5",
            },
            "priceFilter": {"tickSize": "0.1"},
        },
        category="spot",
    )

    assert instrument.instrument_key == "bybit:spot:BTCUSDT"
    assert instrument.market_type == "spot"
    assert instrument.base_asset == "BTC"
    assert instrument.quote_asset == "USDT"
    assert instrument.contract_type == "spot"
    assert instrument.contract_size == "1"
    assert instrument.tick_size == "0.1"
    assert instrument.min_order_size == "0.000001"
    assert instrument.qty_step == "0.000001"


def test_normalizes_bybit_linear_perpetual_instrument():
    adapter = BybitAdapter(normalized_at_ms=1780210000000)

    instrument = adapter.normalize_instrument(
        {
            "symbol": "BTCUSDT",
            "baseCoin": "BTC",
            "quoteCoin": "USDT",
            "settleCoin": "USDT",
            "status": "Trading",
            "contractType": "LinearPerpetual",
            "deliveryTime": "0",
            "priceFilter": {"tickSize": "0.1"},
            "lotSizeFilter": {"minOrderQty": "0.001", "qtyStep": "0.001"},
        },
        category="linear",
    )

    assert instrument.instrument_key == "bybit:perpetual:BTCUSDT"
    assert instrument.market_type == "perpetual"
    assert instrument.base_asset == "BTC"
    assert instrument.quote_asset == "USDT"
    assert instrument.settlement_asset == "USDT"
    assert instrument.underlying_id == "BTCUSDT"
    assert instrument.expiry_time_ms is None
    assert instrument.contract_type == "linear"
    assert instrument.contract_size == "1"


def test_normalizes_bybit_linear_dated_future_instrument():
    adapter = BybitAdapter(normalized_at_ms=1780210000000)

    instrument = adapter.normalize_instrument(
        {
            "symbol": "BTCUSDT-27JUN25",
            "baseCoin": "BTC",
            "quoteCoin": "USDT",
            "settleCoin": "USDT",
            "status": "PreLaunch",
            "contractType": "LinearFutures",
            "deliveryTime": "1751011200000",
            "priceFilter": {"tickSize": "0.1"},
            "lotSizeFilter": {"minOrderQty": "0.001", "qtyStep": "0.001"},
        },
        category="linear",
    )

    assert instrument.instrument_key == "bybit:future:BTCUSDT-27JUN25"
    assert instrument.market_type == "future"
    assert instrument.base_asset == "BTC"
    assert instrument.quote_asset == "USDT"
    assert instrument.underlying_id == "BTCUSDT"
    assert instrument.expiry_time_ms == 1751011200000
    assert instrument.contract_type == "linear"
    assert instrument.status == "pre_launch"


def test_normalizes_bybit_option_ticker_to_quote():
    adapter = BybitAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)

    quote = adapter.normalize_ticker(
        {
            "symbol": "BTC-26MAR27-78000-P-USDT",
            "bid1Price": "20",
            "bid1Size": "12.36",
            "ask1Price": "25",
            "ask1Size": "27.49",
            "lastPrice": "20",
            "markPrice": "25.25265668",
            "indexPrice": "73891.54301089",
            "underlyingPrice": "73896.65382701",
            "markIv": "0.321",
            "delta": "-0.04894665",
            "gamma": "0.00008134",
            "vega": "3.93894914",
            "theta": "-62.66226984",
        },
        category="option",
    )

    assert quote.instrument_key == "bybit:option:BTC-26MAR27-78000-P-USDT"
    assert quote.bid_price == "20"
    assert quote.ask_price == "25"
    assert quote.mid_price == "22.5"
    assert quote.mark_price == "25.25265668"
    assert quote.index_price == "73891.54301089"
    assert quote.underlying_price == "73896.65382701"
    assert quote.mark_iv == "0.321"
    assert quote.delta == "-0.04894665"


def test_normalizes_bybit_linear_ticker_to_quote_and_funding():
    adapter = BybitAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)
    raw = {
        "symbol": "BTCUSDT",
        "lastPrice": "73869.20",
        "indexPrice": "73891.56",
        "markPrice": "73870.31",
        "fundingRate": "0.00004472",
        "nextFundingTime": "1780214400000",
        "fundingIntervalHour": "8",
        "ask1Size": "7.348",
        "bid1Price": "73869.10",
        "ask1Price": "73869.20",
        "bid1Size": "0.240",
    }

    quote = adapter.normalize_ticker(raw, category="linear")
    funding_rate = adapter.normalize_funding_rate_from_ticker(raw, category="linear")

    assert quote.instrument_key == "bybit:perpetual:BTCUSDT"
    assert quote.bid_price == "73869.10"
    assert quote.ask_price == "73869.20"
    assert quote.mid_price == "73869.15"
    assert quote.mark_price == "73870.31"
    assert quote.index_price == "73891.56"
    assert funding_rate.instrument_key == "bybit:perpetual:BTCUSDT"
    assert funding_rate.funding_rate_current == "0.00004472"
    assert funding_rate.next_funding_time_ms == 1780214400000
    assert funding_rate.funding_interval_hours == "8"


def test_normalizes_bybit_order_book_snapshot():
    adapter = BybitAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)

    order_book = adapter.normalize_order_book(
        {
            "s": "BTCUSDT",
            "a": [["73896.9", "1.299089"], ["73897.0", "2"]],
            "b": [["73896.8", "0.442845"], ["73896.7", "3"]],
            "ts": 1780213645353,
            "u": 4071936,
            "seq": 108220804018,
            "cts": 1780213645348,
        },
        category="spot",
    )

    assert order_book.instrument_key == "bybit:spot:BTCUSDT"
    assert order_book.depth == 2
    assert [level.price for level in order_book.bids] == ["73896.8", "73896.7"]
    assert [level.size for level in order_book.asks] == ["1.299089", "2"]
    assert order_book.sequence == "4071936"
    assert order_book.checksum == "108220804018"
    assert order_book.event_time_ms == 1780213645353
    assert order_book.transaction_time_ms == 1780213645348


def test_normalizes_bybit_funding_history_row():
    adapter = BybitAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)

    funding_rate = adapter.normalize_funding_history_row(
        {
            "symbol": "BTCUSDT",
            "fundingRate": "0.00007356",
            "fundingRateTimestamp": "1780185600000",
        },
        category="linear",
    )

    assert funding_rate.instrument_key == "bybit:perpetual:BTCUSDT"
    assert funding_rate.funding_rate_current == "0.00007356"
    assert funding_rate.funding_time_ms == 1780185600000
    assert funding_rate.source_updated_at_ms == 1780185600000
