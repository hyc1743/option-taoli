from option_taoli.adapters.gate import GateAdapter


def test_normalizes_gate_option_contract_to_internal_model():
    adapter = GateAdapter(normalized_at_ms=1780210000000)

    instrument = adapter.normalize_contract(
        {
            "name": "BTC_USDT-20211130-65000-C",
            "expiration_time": 1637913600,
            "is_call": True,
            "strike_price": "65000",
            "underlying": "BTC_USDT",
            "underlying_price": "70000",
            "multiplier": "0.0001",
            "order_price_round": "0.1",
            "order_size_min": 1,
            "maker_fee_rate": "0.0004",
            "taker_fee_rate": "0.0005",
        }
    )

    assert instrument.instrument_key == "gate:option:BTC_USDT-20211130-65000-C"
    assert instrument.exchange == "gate"
    assert instrument.market_type == "option"
    assert instrument.instrument_id == "BTC_USDT-20211130-65000-C"
    assert instrument.base_asset == "BTC"
    assert instrument.quote_asset == "USDT"
    assert instrument.settlement_asset == "USDT"
    assert instrument.underlying_id == "BTC_USDT"
    assert instrument.instrument_family == "BTC_USDT"
    assert instrument.expiry_time_ms == 1637913600000
    assert instrument.strike == "65000"
    assert instrument.option_type == "call"
    assert instrument.contract_type == "linear"
    assert instrument.contract_size == "0.0001"
    assert instrument.contract_value_currency == "BTC"
    assert instrument.tick_size == "0.1"
    assert instrument.min_order_size == "1"
    assert instrument.qty_step == "1"
    assert instrument.maker_fee_rate == "0.0004"
    assert instrument.taker_fee_rate == "0.0005"
    assert instrument.status == "trading"


def test_normalizes_gate_option_ticker_to_quote():
    adapter = GateAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)

    quote = adapter.normalize_ticker(
        {
            "name": "BTC_USDT-20211130-65000-P",
            "last_price": "13000",
            "mark_price": "14010",
            "index_price": "70010",
            "ask1_size": 2,
            "ask1_price": "14020",
            "bid1_size": 1,
            "bid1_price": "14000",
            "mark_iv": "0.123",
            "bid_iv": "0.023",
            "ask_iv": "0.342",
            "delta": "-0.33505",
            "gamma": "0.00004",
            "vega": "41.41202",
            "theta": "-120.1506",
        }
    )

    assert quote.instrument_key == "gate:option:BTC_USDT-20211130-65000-P"
    assert quote.exchange == "gate"
    assert quote.market_type == "option"
    assert quote.bid_price == "14000"
    assert quote.ask_price == "14020"
    assert quote.bid_size == "1"
    assert quote.ask_size == "2"
    assert quote.mid_price == "14010"
    assert quote.mark_price == "14010"
    assert quote.index_price == "70010"
    assert quote.bid_iv == "0.023"
    assert quote.ask_iv == "0.342"
    assert quote.mark_iv == "0.123"
    assert quote.delta == "-0.33505"
    assert quote.gamma == "0.00004"
    assert quote.vega == "41.41202"
    assert quote.theta == "-120.1506"


def test_normalizes_gate_option_order_book_snapshot():
    adapter = GateAdapter(normalized_at_ms=1780210000000, received_at_ms=1780210000123)

    order_book = adapter.normalize_order_book(
        {
            "id": 9,
            "current": 1780213645.123,
            "update": 1780213644.456,
            "asks": [{"p": "14020", "s": 2}, {"p": "14030", "s": 3}],
            "bids": [{"p": "14000", "s": 1}, {"p": "13990", "s": 4}],
        },
        contract="BTC_USDT-20211130-65000-C",
    )

    assert order_book.instrument_key == "gate:option:BTC_USDT-20211130-65000-C"
    assert order_book.depth == 2
    assert [level.price for level in order_book.bids] == ["14000", "13990"]
    assert [level.size for level in order_book.asks] == ["2", "3"]
    assert order_book.sequence == "9"
    assert order_book.event_time_ms == 1780213644456
    assert order_book.transaction_time_ms == 1780213645123
