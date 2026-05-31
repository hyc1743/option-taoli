from option_taoli.adapters.deribit import DeribitAdapter


def test_normalizes_deribit_option_instrument_to_internal_model():
    adapter = DeribitAdapter(normalized_at_ms=1780210000000)

    instrument = adapter.normalize_instrument(
        {
            "instrument_name": "BTC-27JUN25-100000-C",
            "kind": "option",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "BTC",
            "expiration_timestamp": 1751011200000,
            "strike": 100000,
            "option_type": "call",
            "instrument_type": "reversed",
            "settlement_period": "month",
            "contract_size": 1,
            "tick_size": 0.0005,
            "maker_commission": 0.0003,
            "taker_commission": 0.0003,
            "price_index": "btc_usd",
            "state": "open",
        }
    )

    assert instrument.instrument_key == "deribit:option:BTC-27JUN25-100000-C"
    assert instrument.exchange == "deribit"
    assert instrument.market_type == "option"
    assert instrument.instrument_id == "BTC-27JUN25-100000-C"
    assert instrument.base_asset == "BTC"
    assert instrument.quote_asset == "USD"
    assert instrument.settlement_asset == "BTC"
    assert instrument.underlying_id == "btc_usd"
    assert instrument.expiry_time_ms == 1751011200000
    assert instrument.strike == "100000"
    assert instrument.option_type == "call"
    assert instrument.contract_type == "inverse"
    assert instrument.contract_size == "1"
    assert instrument.tick_size == "0.0005"
    assert instrument.maker_fee_rate == "0.0003"
    assert instrument.taker_fee_rate == "0.0003"
    assert instrument.fee_source == "public_metadata"
    assert instrument.status == "trading"
    assert instrument.normalized_at_ms == 1780210000000


def test_normalizes_deribit_perpetual_instrument_market_type():
    adapter = DeribitAdapter(normalized_at_ms=1780210000000)

    instrument = adapter.normalize_instrument(
        {
            "instrument_name": "BTC-PERPETUAL",
            "kind": "future",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "BTC",
            "expiration_timestamp": 32503708800000,
            "instrument_type": "reversed",
            "settlement_period": "perpetual",
            "contract_size": 10,
            "tick_size": 0.5,
            "maker_commission": 0.0,
            "taker_commission": 0.0005,
            "price_index": "btc_usd",
            "state": "open",
        }
    )

    assert instrument.instrument_key == "deribit:perpetual:BTC-PERPETUAL"
    assert instrument.market_type == "perpetual"
    assert instrument.expiry_time_ms is None
    assert instrument.contract_type == "inverse"
    assert instrument.contract_size == "10"


def test_normalizes_deribit_ticker_to_quote_with_mid_price():
    adapter = DeribitAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)

    quote = adapter.normalize_quote(
        {
            "instrument_name": "BTC-PERPETUAL",
            "best_bid_price": 73800.5,
            "best_ask_price": 73801.5,
            "best_bid_amount": 120,
            "best_ask_amount": 80,
            "last_price": 73801,
            "mark_price": 73802.25,
            "index_price": 73810.75,
            "current_funding": 0.00001234,
            "funding_8h": 0.00009876,
            "timestamp": 1780210000000,
        },
        market_type="perpetual",
    )

    assert quote.instrument_key == "deribit:perpetual:BTC-PERPETUAL"
    assert quote.bid_price == "73800.5"
    assert quote.ask_price == "73801.5"
    assert quote.bid_size == "120"
    assert quote.ask_size == "80"
    assert quote.mid_price == "73801.0"
    assert quote.mark_price == "73802.25"
    assert quote.index_price == "73810.75"
    assert quote.source_updated_at_ms == 1780210000000
    assert quote.received_at_ms == 1780210000123


def test_normalizes_deribit_order_book_snapshot():
    adapter = DeribitAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)

    order_book = adapter.normalize_order_book(
        {
            "instrument_name": "BTC-PERPETUAL",
            "bids": [[73800.5, 2], [73799.5, 3]],
            "asks": [[73801.5, 4], [73802.5, 5]],
            "change_id": 12345,
            "prev_change_id": 12344,
            "timestamp": 1780210000000,
        },
        market_type="perpetual",
    )

    assert order_book.instrument_key == "deribit:perpetual:BTC-PERPETUAL"
    assert order_book.depth == 2
    assert [level.price for level in order_book.bids] == ["73800.5", "73799.5"]
    assert [level.size for level in order_book.bids] == ["2", "3"]
    assert [level.price for level in order_book.asks] == ["73801.5", "73802.5"]
    assert order_book.sequence == "12345"
    assert order_book.previous_sequence == "12344"
    assert order_book.is_snapshot is True
    assert order_book.event_time_ms == 1780210000000


def test_normalizes_deribit_websocket_order_book_level_shape():
    adapter = DeribitAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)

    order_book = adapter.normalize_order_book(
        {
            "instrument_name": "BTC-PERPETUAL",
            "bids": [["new", 73800.5, 2], ["change", 73799.5, 3], ["delete", 73798.5, 0]],
            "asks": [["new", 73801.5, 4], ["change", 73802.5, 5], ["delete", 73803.5, 0]],
            "change_id": 12345,
            "prev_change_id": 12344,
            "timestamp": 1780210000000,
        },
        market_type="perpetual",
    )

    assert [level.price for level in order_book.bids] == ["73800.5", "73799.5"]
    assert [level.size for level in order_book.bids] == ["2", "3"]
    assert [level.price for level in order_book.asks] == ["73801.5", "73802.5"]
    assert [level.size for level in order_book.asks] == ["4", "5"]


def test_extracts_deribit_perpetual_funding_rate_from_ticker():
    adapter = DeribitAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)

    funding_rate = adapter.normalize_funding_rate(
        {
            "instrument_name": "BTC-PERPETUAL",
            "current_funding": 0.00001234,
            "funding_8h": 0.00009876,
            "interest_rate": 0.0,
            "timestamp": 1780210000000,
        }
    )

    assert funding_rate.instrument_key == "deribit:perpetual:BTC-PERPETUAL"
    assert funding_rate.exchange == "deribit"
    assert funding_rate.instrument_id == "BTC-PERPETUAL"
    assert funding_rate.funding_rate_current == "0.00001234"
    assert funding_rate.funding_rate_8h == "0.00009876"
    assert funding_rate.interest_rate == "0.0"
    assert funding_rate.source_updated_at_ms == 1780210000000
