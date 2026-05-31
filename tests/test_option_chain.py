from option_taoli.models import Instrument
from option_taoli.option_chain import build_option_chain


def option_instrument(
    *,
    instrument_key: str,
    exchange: str,
    underlying_id: str | None,
    expiry_time_ms: int | None,
    strike: str | None,
    option_type: str | None,
    status: str = "trading",
) -> Instrument:
    return Instrument(
        instrument_key=instrument_key,
        exchange=exchange,
        market_type="option",
        instrument_id=instrument_key.rsplit(":", 1)[-1],
        base_asset="BTC",
        quote_asset="USD",
        contract_type="inverse",
        contract_size="1",
        status=status,
        normalized_at_ms=1780210000000,
        underlying_id=underlying_id,
        expiry_time_ms=expiry_time_ms,
        strike=strike,
        option_type=option_type,
    )


def test_builds_exchange_separated_call_put_pairs_for_pcp():
    instruments = [
        option_instrument(
            instrument_key="deribit:option:BTC-27JUN25-100000-C",
            exchange="deribit",
            underlying_id="btc_usd",
            expiry_time_ms=1751011200000,
            strike="100000",
            option_type="call",
        ),
        option_instrument(
            instrument_key="deribit:option:BTC-27JUN25-100000-P",
            exchange="deribit",
            underlying_id="btc_usd",
            expiry_time_ms=1751011200000,
            strike="100000",
            option_type="put",
        ),
        option_instrument(
            instrument_key="okx:option:BTC-USD-250627-100000-C",
            exchange="okx",
            underlying_id="BTC-USD",
            expiry_time_ms=1751011200000,
            strike="100000",
            option_type="call",
        ),
        option_instrument(
            instrument_key="okx:option:BTC-USD-250627-100000-P",
            exchange="okx",
            underlying_id="BTC-USD",
            expiry_time_ms=1751011200000,
            strike="100000",
            option_type="put",
        ),
    ]

    chain = build_option_chain(instruments)

    pairs = chain.complete_pairs()

    assert [(pair.exchange, pair.underlying_id, pair.strike) for pair in pairs] == [
        ("deribit", "btc_usd", "100000"),
        ("okx", "BTC-USD", "100000"),
    ]
    assert pairs[0].call.instrument_key == "deribit:option:BTC-27JUN25-100000-C"
    assert pairs[0].put.instrument_key == "deribit:option:BTC-27JUN25-100000-P"


def test_groups_expiries_and_sorts_strikes_for_box_spread_enumeration():
    instruments = [
        option_instrument(
            instrument_key="binance:option:BTC-260626-140000-C",
            exchange="binance",
            underlying_id="BTCUSDT",
            expiry_time_ms=1782432000000,
            strike="140000",
            option_type="call",
        ),
        option_instrument(
            instrument_key="binance:option:BTC-260626-90000-P",
            exchange="binance",
            underlying_id="BTCUSDT",
            expiry_time_ms=1782432000000,
            strike="90000",
            option_type="put",
        ),
        option_instrument(
            instrument_key="binance:option:BTC-260626-90000-C",
            exchange="binance",
            underlying_id="BTCUSDT",
            expiry_time_ms=1782432000000,
            strike="90000",
            option_type="call",
        ),
        option_instrument(
            instrument_key="binance:option:BTC-260626-140000-P",
            exchange="binance",
            underlying_id="BTCUSDT",
            expiry_time_ms=1782432000000,
            strike="140000",
            option_type="put",
        ),
    ]

    chain = build_option_chain(instruments)
    expiry = chain.expiries[("binance", "BTCUSDT", 1782432000000)]

    assert expiry.strikes == ["90000", "140000"]
    assert expiry.pairs_by_strike["90000"].call.instrument_key == "binance:option:BTC-260626-90000-C"
    assert expiry.pairs_by_strike["90000"].put.instrument_key == "binance:option:BTC-260626-90000-P"
    assert expiry.pairs_by_strike["140000"].call.instrument_key == "binance:option:BTC-260626-140000-C"
    assert expiry.pairs_by_strike["140000"].put.instrument_key == "binance:option:BTC-260626-140000-P"


def test_skips_non_trading_non_option_and_incomplete_option_instruments_by_default():
    valid_call = option_instrument(
        instrument_key="bybit:option:BTC-26MAR27-78000-C-USDT",
        exchange="bybit",
        underlying_id="BTC",
        expiry_time_ms=1806048000000,
        strike="78000",
        option_type="call",
    )
    expired_put = option_instrument(
        instrument_key="bybit:option:BTC-26MAR27-78000-P-USDT",
        exchange="bybit",
        underlying_id="BTC",
        expiry_time_ms=1806048000000,
        strike="78000",
        option_type="put",
        status="expired",
    )
    missing_underlying = option_instrument(
        instrument_key="deribit:option:BTC-27JUN25-100000-C",
        exchange="deribit",
        underlying_id=None,
        expiry_time_ms=1751011200000,
        strike="100000",
        option_type="call",
    )
    spot = Instrument(
        instrument_key="binance:spot:BTCUSDT",
        exchange="binance",
        market_type="spot",
        instrument_id="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        contract_type="spot",
        contract_size="1",
        status="trading",
        normalized_at_ms=1780210000000,
    )

    chain = build_option_chain([valid_call, expired_put, missing_underlying, spot])

    assert chain.complete_pairs() == []
    expiry = chain.expiries[("bybit", "BTC", 1806048000000)]
    assert expiry.strikes == ["78000"]
    assert expiry.pairs_by_strike["78000"].call == valid_call
    assert expiry.pairs_by_strike["78000"].put is None
