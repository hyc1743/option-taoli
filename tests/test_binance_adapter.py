from option_taoli.adapters.binance import BinanceAdapter


def test_normalizes_binance_option_instrument_from_exchange_info():
    adapter = BinanceAdapter(normalized_at_ms=1780210000000)

    instrument = adapter.normalize_option_instrument(
        {
            "symbol": "BTC-260626-140000-C",
            "underlying": "BTCUSDT",
            "expiryDate": 1782432000000,
            "side": "CALL",
            "strikePrice": "140000",
            "unit": 1,
            "quoteAsset": "USDT",
            "settleAsset": "USDT",
            "status": "TRADING",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.1"},
                {"filterType": "LOT_SIZE", "minQty": "0.01", "stepSize": "0.01"},
            ],
        },
        option_contract={"baseAsset": "BTC"},
    )

    assert instrument.instrument_key == "binance:option:BTC-260626-140000-C"
    assert instrument.exchange == "binance"
    assert instrument.market_type == "option"
    assert instrument.instrument_id == "BTC-260626-140000-C"
    assert instrument.base_asset == "BTC"
    assert instrument.quote_asset == "USDT"
    assert instrument.settlement_asset == "USDT"
    assert instrument.underlying_id == "BTCUSDT"
    assert instrument.expiry_time_ms == 1782432000000
    assert instrument.strike == "140000"
    assert instrument.option_type == "call"
    assert instrument.contract_type == "linear"
    assert instrument.contract_size == "1"
    assert instrument.tick_size == "0.1"
    assert instrument.min_order_size == "0.01"
    assert instrument.qty_step == "0.01"
    assert instrument.status == "trading"


def test_normalizes_binance_spot_book_ticker_to_quote():
    adapter = BinanceAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)

    quote = adapter.normalize_spot_book_ticker(
        {
            "symbol": "BTCUSDT",
            "bidPrice": "73800.10",
            "bidQty": "0.25",
            "askPrice": "73800.20",
            "askQty": "0.5",
        }
    )

    assert quote.instrument_key == "binance:spot:BTCUSDT"
    assert quote.exchange == "binance"
    assert quote.market_type == "spot"
    assert quote.instrument_id == "BTCUSDT"
    assert quote.bid_price == "73800.10"
    assert quote.ask_price == "73800.20"
    assert quote.bid_size == "0.25"
    assert quote.ask_size == "0.5"
    assert quote.mid_price == "73800.15"
    assert quote.received_at_ms == 1780210000123


def test_normalizes_binance_usdm_perpetual_instrument():
    adapter = BinanceAdapter(normalized_at_ms=1780210000000)

    instrument = adapter.normalize_usdm_instrument(
        {
            "symbol": "BTCUSDT",
            "pair": "BTCUSDT",
            "contractType": "PERPETUAL",
            "deliveryDate": 4133404800000,
            "status": "TRADING",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "marginAsset": "USDT",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.1"},
                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
            ],
        }
    )

    assert instrument.instrument_key == "binance:perpetual:BTCUSDT"
    assert instrument.market_type == "perpetual"
    assert instrument.instrument_id == "BTCUSDT"
    assert instrument.base_asset == "BTC"
    assert instrument.quote_asset == "USDT"
    assert instrument.settlement_asset == "USDT"
    assert instrument.underlying_id == "BTCUSDT"
    assert instrument.expiry_time_ms is None
    assert instrument.contract_type == "linear"
    assert instrument.contract_size == "1"
    assert instrument.tick_size == "0.1"
    assert instrument.min_order_size == "0.001"
    assert instrument.qty_step == "0.001"


def test_normalizes_binance_usdm_premium_index_to_quote_and_funding():
    adapter = BinanceAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)
    raw = {
        "symbol": "BTCUSDT",
        "markPrice": "73802.25",
        "indexPrice": "73810.75",
        "lastFundingRate": "0.00001234",
        "interestRate": "0.0001",
        "nextFundingTime": 1780214400000,
        "time": 1780210000000,
    }

    quote = adapter.normalize_usdm_premium_index_quote(raw)
    funding_rate = adapter.normalize_usdm_funding_rate(raw)

    assert quote.instrument_key == "binance:perpetual:BTCUSDT"
    assert quote.mark_price == "73802.25"
    assert quote.index_price == "73810.75"
    assert quote.source_updated_at_ms == 1780210000000
    assert funding_rate.instrument_key == "binance:perpetual:BTCUSDT"
    assert funding_rate.funding_rate_current == "0.00001234"
    assert funding_rate.interest_rate == "0.0001"
    assert funding_rate.next_funding_time_ms == 1780214400000
    assert funding_rate.source_updated_at_ms == 1780210000000


def test_normalizes_binance_option_mark_quote_from_websocket_short_fields():
    adapter = BinanceAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)

    quote = adapter.normalize_option_mark_quote(
        {
            "s": "BTC-260626-140000-C",
            "bo": "100.1",
            "ao": "100.5",
            "bq": "1.2",
            "aq": "0.8",
            "mp": "100.3",
            "i": "73810.75",
            "E": 1780210000000,
        }
    )

    assert quote.instrument_key == "binance:option:BTC-260626-140000-C"
    assert quote.bid_price == "100.1"
    assert quote.ask_price == "100.5"
    assert quote.bid_size == "1.2"
    assert quote.ask_size == "0.8"
    assert quote.mid_price == "100.3"
    assert quote.mark_price == "100.3"
    assert quote.index_price == "73810.75"
    assert quote.source_updated_at_ms == 1780210000000


def test_normalizes_binance_usdm_mark_price_stream_to_quote_and_funding():
    adapter = BinanceAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)
    raw = {
        "s": "BTCUSDT",
        "p": "73802.25",
        "i": "73810.75",
        "r": "0.00001234",
        "T": 1780214400000,
        "E": 1780210000000,
    }

    quote = adapter.normalize_usdm_premium_index_quote(raw)
    funding_rate = adapter.normalize_usdm_funding_rate(raw)

    assert quote.instrument_key == "binance:perpetual:BTCUSDT"
    assert quote.mark_price == "73802.25"
    assert quote.index_price == "73810.75"
    assert quote.source_updated_at_ms == 1780210000000
    assert funding_rate.instrument_key == "binance:perpetual:BTCUSDT"
    assert funding_rate.funding_rate_current == "0.00001234"
    assert funding_rate.next_funding_time_ms == 1780214400000
    assert funding_rate.source_updated_at_ms == 1780210000000


def test_normalizes_binance_depth_snapshot_for_options_or_futures():
    adapter = BinanceAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)

    order_book = adapter.normalize_depth_snapshot(
        {
            "lastUpdateId": 12345,
            "T": 1780210000000,
            "bids": [["10.5", "2"], ["10.4", "3"]],
            "asks": [["10.6", "4"], ["10.7", "5"]],
        },
        market_type="option",
        instrument_id="BTC-260626-140000-C",
    )

    assert order_book.instrument_key == "binance:option:BTC-260626-140000-C"
    assert order_book.depth == 2
    assert [level.price for level in order_book.bids] == ["10.5", "10.4"]
    assert [level.size for level in order_book.asks] == ["4", "5"]
    assert order_book.sequence == "12345"
    assert order_book.transaction_time_ms == 1780210000000
    assert order_book.is_snapshot is True
