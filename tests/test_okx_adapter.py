from option_taoli.adapters.okx import OkxAdapter


def test_normalizes_okx_option_instrument_to_internal_model():
    adapter = OkxAdapter(normalized_at_ms=1780210000000)

    instrument = adapter.normalize_instrument(
        {
            "instType": "OPTION",
            "instId": "BTC-USD-250627-100000-C",
            "uly": "BTC-USD",
            "instFamily": "BTC-USD",
            "baseCcy": "",
            "quoteCcy": "",
            "settleCcy": "BTC",
            "ctVal": "1",
            "ctMult": "1",
            "ctValCcy": "BTC",
            "ctType": "inverse",
            "optType": "C",
            "stk": "100000",
            "expTime": "1751011200000",
            "tickSz": "0.0005",
            "lotSz": "0.1",
            "minSz": "0.1",
            "state": "live",
        }
    )

    assert instrument.instrument_key == "okx:option:BTC-USD-250627-100000-C"
    assert instrument.exchange == "okx"
    assert instrument.market_type == "option"
    assert instrument.instrument_id == "BTC-USD-250627-100000-C"
    assert instrument.base_asset == "BTC"
    assert instrument.quote_asset == "USD"
    assert instrument.settlement_asset == "BTC"
    assert instrument.underlying_id == "BTC-USD"
    assert instrument.instrument_family == "BTC-USD"
    assert instrument.expiry_time_ms == 1751011200000
    assert instrument.strike == "100000"
    assert instrument.option_type == "call"
    assert instrument.contract_type == "inverse"
    assert instrument.contract_size == "1"
    assert instrument.contract_value_currency == "BTC"
    assert instrument.tick_size == "0.0005"
    assert instrument.min_order_size == "0.1"
    assert instrument.qty_step == "0.1"
    assert instrument.status == "trading"


def test_normalizes_okx_spot_instrument_to_internal_model():
    adapter = OkxAdapter(normalized_at_ms=1780210000000)

    instrument = adapter.normalize_instrument(
        {
            "instType": "SPOT",
            "instId": "BTC-USDT",
            "baseCcy": "BTC",
            "quoteCcy": "USDT",
            "tickSz": "0.1",
            "lotSz": "0.00000001",
            "minSz": "0.00001",
            "state": "live",
        }
    )

    assert instrument.instrument_key == "okx:spot:BTC-USDT"
    assert instrument.market_type == "spot"
    assert instrument.base_asset == "BTC"
    assert instrument.quote_asset == "USDT"
    assert instrument.contract_type == "spot"
    assert instrument.contract_size == "1"
    assert instrument.tick_size == "0.1"
    assert instrument.min_order_size == "0.00001"
    assert instrument.qty_step == "0.00000001"


def test_normalizes_okx_swap_instrument_to_perpetual():
    adapter = OkxAdapter(normalized_at_ms=1780210000000)

    instrument = adapter.normalize_instrument(
        {
            "instType": "SWAP",
            "instId": "BTC-USDT-SWAP",
            "uly": "BTC-USDT",
            "instFamily": "BTC-USDT",
            "settleCcy": "USDT",
            "ctVal": "0.01",
            "ctMult": "1",
            "ctValCcy": "BTC",
            "ctType": "linear",
            "tickSz": "0.1",
            "lotSz": "0.01",
            "minSz": "0.01",
            "state": "live",
        }
    )

    assert instrument.instrument_key == "okx:perpetual:BTC-USDT-SWAP"
    assert instrument.market_type == "perpetual"
    assert instrument.base_asset == "BTC"
    assert instrument.quote_asset == "USDT"
    assert instrument.settlement_asset == "USDT"
    assert instrument.underlying_id == "BTC-USDT"
    assert instrument.contract_type == "linear"
    assert instrument.contract_size == "0.01"


def test_normalizes_okx_futures_instrument_to_delivery_future():
    adapter = OkxAdapter(normalized_at_ms=1780210000000)

    instrument = adapter.normalize_instrument(
        {
            "instType": "FUTURES",
            "instId": "BTC-USDT-250627",
            "uly": "BTC-USDT",
            "instFamily": "BTC-USDT",
            "settleCcy": "USDT",
            "ctVal": "0.01",
            "ctMult": "10",
            "ctValCcy": "BTC",
            "ctType": "linear",
            "expTime": "1751011200000",
            "tickSz": "0.1",
            "lotSz": "0.01",
            "minSz": "0.01",
            "state": "preopen",
        }
    )

    assert instrument.instrument_key == "okx:future:BTC-USDT-250627"
    assert instrument.market_type == "future"
    assert instrument.base_asset == "BTC"
    assert instrument.quote_asset == "USDT"
    assert instrument.expiry_time_ms == 1751011200000
    assert instrument.contract_type == "linear"
    assert instrument.contract_size == "0.10"
    assert instrument.status == "pre_launch"


def test_normalizes_okx_ticker_to_quote_with_mid_price():
    adapter = OkxAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)

    quote = adapter.normalize_ticker(
        {
            "instType": "SWAP",
            "instId": "BTC-USDT-SWAP",
            "last": "73801.1",
            "lastSz": "2",
            "askPx": "73801.5",
            "askSz": "4",
            "bidPx": "73800.5",
            "bidSz": "3",
            "ts": "1780210000000",
        }
    )

    assert quote.instrument_key == "okx:perpetual:BTC-USDT-SWAP"
    assert quote.bid_price == "73800.5"
    assert quote.ask_price == "73801.5"
    assert quote.bid_size == "3"
    assert quote.ask_size == "4"
    assert quote.mid_price == "73801.0"
    assert quote.last_price == "73801.1"
    assert quote.source_updated_at_ms == 1780210000000


def test_normalizes_okx_books_snapshot():
    adapter = OkxAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)

    order_book = adapter.normalize_order_book(
        {
            "instId": "BTC-USDT",
            "asks": [["73801.5", "4", "0", "2"], ["73802.5", "5", "0", "1"]],
            "bids": [["73800.5", "2", "0", "3"], ["73799.5", "3", "0", "1"]],
            "ts": "1780210000000",
            "seqId": 12345,
        },
        market_type="spot",
    )

    assert order_book.instrument_key == "okx:spot:BTC-USDT"
    assert order_book.depth == 2
    assert [level.price for level in order_book.bids] == ["73800.5", "73799.5"]
    assert [level.size for level in order_book.asks] == ["4", "5"]
    assert order_book.sequence == "12345"
    assert order_book.event_time_ms == 1780210000000
    assert order_book.is_snapshot is True


def test_normalizes_okx_mark_index_and_funding_data():
    adapter = OkxAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)

    mark_quote = adapter.normalize_mark_price(
        {
            "instType": "SWAP",
            "instId": "BTC-USDT-SWAP",
            "markPx": "73802.25",
            "ts": "1780210000000",
        }
    )
    index_quote = adapter.normalize_index_ticker(
        {
            "instId": "BTC-USDT",
            "idxPx": "73810.75",
            "ts": "1780210000001",
        }
    )
    funding_rate = adapter.normalize_funding_rate(
        {
            "instId": "BTC-USDT-SWAP",
            "fundingRate": "0.00001234",
            "fundingTime": "1780214400000",
            "nextFundingTime": "1780243200000",
            "settFundingRate": "0.00001",
            "interestRate": "0.0001",
            "premium": "0.0002",
            "ts": "1780210000002",
        }
    )

    assert mark_quote.instrument_key == "okx:perpetual:BTC-USDT-SWAP"
    assert mark_quote.mark_price == "73802.25"
    assert mark_quote.source_updated_at_ms == 1780210000000
    assert index_quote.instrument_key == "okx:spot:BTC-USDT"
    assert index_quote.index_price == "73810.75"
    assert index_quote.source_updated_at_ms == 1780210000001
    assert funding_rate.instrument_key == "okx:perpetual:BTC-USDT-SWAP"
    assert funding_rate.funding_rate_current == "0.00001234"
    assert funding_rate.funding_time_ms == 1780214400000
    assert funding_rate.next_funding_time_ms == 1780243200000
    assert funding_rate.interest_rate == "0.0001"
    assert funding_rate.premium == "0.0002"
    assert funding_rate.source_updated_at_ms == 1780210000002
