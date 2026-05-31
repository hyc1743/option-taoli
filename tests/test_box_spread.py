from option_taoli.box_spread import calculate_box_spreads
from option_taoli.market_depth import ExecutableQuote
from option_taoli.models import Instrument
from option_taoli.option_chain import build_option_chain


NOW_MS = 1748419200000
EXPIRY_MS = 1751011200000


def option_instrument(strike: str, option_type: str) -> Instrument:
    suffix = "C" if option_type == "call" else "P"
    instrument_id = f"BTC-27JUN25-{strike}-{suffix}"
    return Instrument(
        instrument_key=f"deribit:option:{instrument_id}",
        exchange="deribit",
        market_type="option",
        instrument_id=instrument_id,
        base_asset="BTC",
        quote_asset="USD",
        contract_type="inverse",
        contract_size="1",
        status="trading",
        normalized_at_ms=NOW_MS,
        underlying_id="btc_usd",
        expiry_time_ms=EXPIRY_MS,
        strike=strike,
        option_type=option_type,
    )


def quote(instrument: Instrument, *, bid: str, ask: str) -> ExecutableQuote:
    return ExecutableQuote(
        instrument_key=instrument.instrument_key,
        exchange=instrument.exchange,
        market_type=instrument.market_type,
        instrument_id=instrument.instrument_id,
        best_bid_price=bid,
        best_ask_price=ask,
        best_bid_size="5",
        best_ask_size="5",
        mid_price=str((float(bid) + float(ask)) / 2),
        spread=str(float(ask) - float(bid)),
        received_at_ms=NOW_MS,
        normalized_at_ms=NOW_MS,
    )


def expiry_and_instruments():
    instruments = [
        option_instrument("90000", "call"),
        option_instrument("90000", "put"),
        option_instrument("100000", "call"),
        option_instrument("100000", "put"),
    ]
    chain = build_option_chain(instruments)
    return chain.expiries[("deribit", "btc_usd", EXPIRY_MS)], instruments


def test_enumerates_profitable_long_box_spread_from_two_strikes():
    expiry, instruments = expiry_and_instruments()
    quotes = {
        instruments[0].instrument_key: quote(instruments[0], bid="6900", ask="7000"),
        instruments[1].instrument_key: quote(instruments[1], bid="400", ask="500"),
        instruments[2].instrument_key: quote(instruments[2], bid="2500", ask="2600"),
        instruments[3].instrument_key: quote(instruments[3], bid="4900", ask="5000"),
    }

    opportunities = calculate_box_spreads(expiry, quotes, now_ms=NOW_MS)

    assert len(opportunities) == 1
    opportunity = opportunities[0]
    assert opportunity.direction == "long_box"
    assert opportunity.lower_strike == "90000"
    assert opportunity.upper_strike == "100000"
    assert opportunity.fixed_cashflow == "10000"
    assert opportunity.entry_value == "9100"
    assert opportunity.gross_profit == "900"
    assert opportunity.annualized_return == "1.203296703296703296703296704"
    assert [(leg.instrument_key, leg.side, leg.price, leg.role) for leg in opportunity.legs] == [
        ("deribit:option:BTC-27JUN25-90000-C", "buy", "7000", "lower_call"),
        ("deribit:option:BTC-27JUN25-100000-C", "sell", "2500", "upper_call"),
        ("deribit:option:BTC-27JUN25-100000-P", "buy", "5000", "upper_put"),
        ("deribit:option:BTC-27JUN25-90000-P", "sell", "400", "lower_put"),
    ]
    assert "fixed expiry cashflow exceeds entry cost" in opportunity.explanation


def test_enumerates_profitable_short_box_spread_when_credit_exceeds_cashflow():
    expiry, instruments = expiry_and_instruments()
    quotes = {
        instruments[0].instrument_key: quote(instruments[0], bid="8000", ask="8100"),
        instruments[1].instrument_key: quote(instruments[1], bid="300", ask="400"),
        instruments[2].instrument_key: quote(instruments[2], bid="1900", ask="2000"),
        instruments[3].instrument_key: quote(instruments[3], bid="5600", ask="5700"),
    }

    opportunities = calculate_box_spreads(expiry, quotes, now_ms=NOW_MS)

    assert len(opportunities) == 1
    opportunity = opportunities[0]
    assert opportunity.direction == "short_box"
    assert opportunity.fixed_cashflow == "10000"
    assert opportunity.entry_value == "11200"
    assert opportunity.gross_profit == "1200"
    assert [(leg.instrument_key, leg.side, leg.price, leg.role) for leg in opportunity.legs] == [
        ("deribit:option:BTC-27JUN25-90000-C", "sell", "8000", "lower_call"),
        ("deribit:option:BTC-27JUN25-100000-C", "buy", "2000", "upper_call"),
        ("deribit:option:BTC-27JUN25-100000-P", "sell", "5600", "upper_put"),
        ("deribit:option:BTC-27JUN25-90000-P", "buy", "400", "lower_put"),
    ]


def test_skips_incomplete_strikes_and_missing_quotes():
    low_call = option_instrument("90000", "call")
    low_put = option_instrument("90000", "put")
    high_call = option_instrument("100000", "call")
    chain = build_option_chain([low_call, low_put, high_call])
    expiry = chain.expiries[("deribit", "btc_usd", EXPIRY_MS)]

    opportunities = calculate_box_spreads(
        expiry,
        {
            low_call.instrument_key: quote(low_call, bid="6900", ask="7000"),
            low_put.instrument_key: quote(low_put, bid="400", ask="500"),
            high_call.instrument_key: quote(high_call, bid="2500", ask="2600"),
        },
        now_ms=NOW_MS,
    )

    assert opportunities == []


def test_sorts_multiple_box_opportunities_by_gross_profit_descending():
    instruments = [
        option_instrument("90000", "call"),
        option_instrument("90000", "put"),
        option_instrument("100000", "call"),
        option_instrument("100000", "put"),
        option_instrument("110000", "call"),
        option_instrument("110000", "put"),
    ]
    expiry = build_option_chain(instruments).expiries[("deribit", "btc_usd", EXPIRY_MS)]
    quotes = {
        instruments[0].instrument_key: quote(instruments[0], bid="6900", ask="7000"),
        instruments[1].instrument_key: quote(instruments[1], bid="400", ask="500"),
        instruments[2].instrument_key: quote(instruments[2], bid="2500", ask="2600"),
        instruments[3].instrument_key: quote(instruments[3], bid="4900", ask="5000"),
        instruments[4].instrument_key: quote(instruments[4], bid="900", ask="1000"),
        instruments[5].instrument_key: quote(instruments[5], bid="9800", ask="9900"),
    }

    opportunities = calculate_box_spreads(expiry, quotes, now_ms=NOW_MS)

    assert [opportunity.gross_profit for opportunity in opportunities] == ["4400", "3300", "900"]
    assert [(opportunity.lower_strike, opportunity.upper_strike) for opportunity in opportunities] == [
        ("90000", "110000"),
        ("100000", "110000"),
        ("90000", "100000"),
    ]
