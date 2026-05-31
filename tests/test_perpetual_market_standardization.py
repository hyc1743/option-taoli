import pytest

from option_taoli.models import FundingRate, Quote
from option_taoli.perpetual_market import standardize_perpetual_state


def test_standardizes_perpetual_price_mark_index_and_funding_snapshot():
    quote = Quote(
        instrument_key="binance:perpetual:BTCUSDT",
        exchange="binance",
        market_type="perpetual",
        instrument_id="BTCUSDT",
        bid_price="73799",
        ask_price="73801",
        mid_price="73800",
        last_price="73805",
        mark_price="73802.25",
        index_price="73810.75",
        received_at_ms=1780210000123,
        normalized_at_ms=1780210000456,
        source_updated_at_ms=1780210000000,
    )
    funding = FundingRate(
        instrument_key="binance:perpetual:BTCUSDT",
        exchange="binance",
        instrument_id="BTCUSDT",
        funding_rate_current="0.00001234",
        interest_rate="0.0001",
        next_funding_time_ms=1780214400000,
        funding_interval_hours="8",
        received_at_ms=1780210000124,
        normalized_at_ms=1780210000457,
        source_updated_at_ms=1780210000000,
    )

    state = standardize_perpetual_state(quote, funding)

    assert state.instrument_key == "binance:perpetual:BTCUSDT"
    assert state.exchange == "binance"
    assert state.perpetual_price == "73800"
    assert state.mark_price == "73802.25"
    assert state.index_price == "73810.75"
    assert state.mark_index_basis == "-8.50"
    assert state.mark_index_basis_rate == "-0.0001151593771909918270712599452"
    assert state.funding_rate_current == "0.00001234"
    assert state.funding_interval_hours == "8"
    assert state.funding_rate_annualized == "0.01351230"
    assert state.next_funding_time_ms == 1780214400000
    assert state.price_source_updated_at_ms == 1780210000000
    assert state.funding_source_updated_at_ms == 1780210000000


def test_uses_last_price_when_mid_price_is_absent():
    quote = Quote(
        instrument_key="deribit:perpetual:BTC-PERPETUAL",
        exchange="deribit",
        market_type="perpetual",
        instrument_id="BTC-PERPETUAL",
        last_price="73805",
        mark_price="73802.25",
        index_price="73810.75",
        received_at_ms=1780210000123,
        normalized_at_ms=1780210000456,
    )
    funding = FundingRate(
        instrument_key="deribit:perpetual:BTC-PERPETUAL",
        exchange="deribit",
        instrument_id="BTC-PERPETUAL",
        funding_rate_current="0.00001234",
        funding_rate_8h="0.00009876",
        received_at_ms=1780210000124,
        normalized_at_ms=1780210000457,
    )

    state = standardize_perpetual_state(quote, funding)

    assert state.perpetual_price == "73805"
    assert state.funding_rate_current == "0.00001234"
    assert state.funding_rate_8h == "0.00009876"
    assert state.funding_rate_annualized is None


def test_rejects_mismatched_funding_and_non_perpetual_quote():
    spot_quote = Quote(
        instrument_key="okx:spot:BTC-USDT",
        exchange="okx",
        market_type="spot",
        instrument_id="BTC-USDT",
        mark_price="73802.25",
        index_price="73810.75",
        received_at_ms=1780210000123,
        normalized_at_ms=1780210000456,
    )
    perpetual_quote = Quote(
        instrument_key="okx:perpetual:BTC-USDT-SWAP",
        exchange="okx",
        market_type="perpetual",
        instrument_id="BTC-USDT-SWAP",
        mid_price="73800",
        mark_price="73802.25",
        index_price="73810.75",
        received_at_ms=1780210000123,
        normalized_at_ms=1780210000456,
    )
    mismatched_funding = FundingRate(
        instrument_key="okx:perpetual:ETH-USDT-SWAP",
        exchange="okx",
        instrument_id="ETH-USDT-SWAP",
        funding_rate_current="0.00001234",
        received_at_ms=1780210000124,
        normalized_at_ms=1780210000457,
    )

    with pytest.raises(ValueError, match="quote market_type must be perpetual"):
        standardize_perpetual_state(spot_quote)

    with pytest.raises(ValueError, match="funding instrument_key does not match quote"):
        standardize_perpetual_state(perpetual_quote, mismatched_funding)


def test_rejects_missing_or_non_positive_mark_and_index_prices():
    missing_mark = Quote(
        instrument_key="bybit:perpetual:BTCUSDT",
        exchange="bybit",
        market_type="perpetual",
        instrument_id="BTCUSDT",
        mid_price="73800",
        index_price="73810.75",
        received_at_ms=1780210000123,
        normalized_at_ms=1780210000456,
    )
    zero_index = Quote(
        instrument_key="bybit:perpetual:BTCUSDT",
        exchange="bybit",
        market_type="perpetual",
        instrument_id="BTCUSDT",
        mid_price="73800",
        mark_price="73802.25",
        index_price="0",
        received_at_ms=1780210000123,
        normalized_at_ms=1780210000456,
    )

    with pytest.raises(ValueError, match="mark price is required"):
        standardize_perpetual_state(missing_mark)

    with pytest.raises(ValueError, match="index price must be greater than zero"):
        standardize_perpetual_state(zero_index)
