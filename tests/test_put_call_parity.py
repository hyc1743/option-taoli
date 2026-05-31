import pytest

from option_taoli.market_depth import ExecutableQuote
from option_taoli.models import Instrument
from option_taoli.option_chain import OptionPair
from option_taoli.put_call_parity import calculate_put_call_parity


def option_instrument(instrument_id: str, option_type: str) -> Instrument:
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
        normalized_at_ms=1780210000000,
        underlying_id="btc_usd",
        expiry_time_ms=1751011200000,
        strike="100000",
        option_type=option_type,
    )


def executable_quote(
    *,
    instrument_key: str,
    instrument_id: str,
    market_type: str,
    bid: str,
    ask: str,
) -> ExecutableQuote:
    return ExecutableQuote(
        instrument_key=instrument_key,
        exchange="deribit",
        market_type=market_type,
        instrument_id=instrument_id,
        best_bid_price=bid,
        best_ask_price=ask,
        best_bid_size="10",
        best_ask_size="10",
        mid_price=str((float(bid) + float(ask)) / 2),
        spread=str(float(ask) - float(bid)),
        received_at_ms=1780210000100,
        normalized_at_ms=1780210000200,
    )


def complete_pair() -> OptionPair:
    return OptionPair(
        exchange="deribit",
        underlying_id="btc_usd",
        expiry_time_ms=1751011200000,
        strike="100000",
        call=option_instrument("BTC-27JUN25-100000-C", "call"),
        put=option_instrument("BTC-27JUN25-100000-P", "put"),
    )


def test_detects_long_synthetic_short_hedge_put_call_parity_opportunity():
    pair = complete_pair()
    call_quote = executable_quote(
        instrument_key="deribit:option:BTC-27JUN25-100000-C",
        instrument_id="BTC-27JUN25-100000-C",
        market_type="option",
        bid="4900",
        ask="5000",
    )
    put_quote = executable_quote(
        instrument_key="deribit:option:BTC-27JUN25-100000-P",
        instrument_id="BTC-27JUN25-100000-P",
        market_type="option",
        bid="9950",
        ask="10050",
    )
    hedge_quote = executable_quote(
        instrument_key="deribit:perpetual:BTC-PERPETUAL",
        instrument_id="BTC-PERPETUAL",
        market_type="perpetual",
        bid="95100",
        ask="95200",
    )

    opportunity = calculate_put_call_parity(pair, call_quote, put_quote, hedge_quote)

    assert opportunity is not None
    assert opportunity.direction == "long_synthetic_short_hedge"
    assert opportunity.synthetic_forward_price == "95050"
    assert opportunity.hedge_price == "95100"
    assert opportunity.gross_profit == "50"
    assert opportunity.deviation == "50"
    assert [(leg.instrument_key, leg.side, leg.price) for leg in opportunity.legs] == [
        ("deribit:option:BTC-27JUN25-100000-C", "buy", "5000"),
        ("deribit:option:BTC-27JUN25-100000-P", "sell", "9950"),
        ("deribit:perpetual:BTC-PERPETUAL", "sell", "95100"),
    ]
    assert "C - P + K is below hedge bid" in opportunity.explanation


def test_detects_short_synthetic_long_hedge_put_call_parity_opportunity():
    pair = complete_pair()
    call_quote = executable_quote(
        instrument_key="deribit:option:BTC-27JUN25-100000-C",
        instrument_id="BTC-27JUN25-100000-C",
        market_type="option",
        bid="6200",
        ask="6300",
    )
    put_quote = executable_quote(
        instrument_key="deribit:option:BTC-27JUN25-100000-P",
        instrument_id="BTC-27JUN25-100000-P",
        market_type="option",
        bid="9950",
        ask="10000",
    )
    hedge_quote = executable_quote(
        instrument_key="deribit:perpetual:BTC-PERPETUAL",
        instrument_id="BTC-PERPETUAL",
        market_type="perpetual",
        bid="95500",
        ask="96000",
    )

    opportunity = calculate_put_call_parity(pair, call_quote, put_quote, hedge_quote)

    assert opportunity is not None
    assert opportunity.direction == "short_synthetic_long_hedge"
    assert opportunity.synthetic_forward_price == "96200"
    assert opportunity.hedge_price == "96000"
    assert opportunity.gross_profit == "200"
    assert [(leg.instrument_key, leg.side, leg.price) for leg in opportunity.legs] == [
        ("deribit:option:BTC-27JUN25-100000-C", "sell", "6200"),
        ("deribit:option:BTC-27JUN25-100000-P", "buy", "10000"),
        ("deribit:perpetual:BTC-PERPETUAL", "buy", "96000"),
    ]


def test_returns_none_when_executable_edges_do_not_cross_parity():
    opportunity = calculate_put_call_parity(
        complete_pair(),
        executable_quote(
            instrument_key="deribit:option:BTC-27JUN25-100000-C",
            instrument_id="BTC-27JUN25-100000-C",
            market_type="option",
            bid="5000",
            ask="5100",
        ),
        executable_quote(
            instrument_key="deribit:option:BTC-27JUN25-100000-P",
            instrument_id="BTC-27JUN25-100000-P",
            market_type="option",
            bid="10000",
            ask="10100",
        ),
        executable_quote(
            instrument_key="deribit:spot:BTC_USDC",
            instrument_id="BTC_USDC",
            market_type="spot",
            bid="95000",
            ask="95100",
        ),
    )

    assert opportunity is None


def test_rejects_incomplete_pair_and_quote_mismatch():
    pair = OptionPair(
        exchange="deribit",
        underlying_id="btc_usd",
        expiry_time_ms=1751011200000,
        strike="100000",
        call=option_instrument("BTC-27JUN25-100000-C", "call"),
    )
    quote = executable_quote(
        instrument_key="deribit:option:BTC-27JUN25-100000-C",
        instrument_id="BTC-27JUN25-100000-C",
        market_type="option",
        bid="5000",
        ask="5100",
    )
    wrong_put_quote = executable_quote(
        instrument_key="deribit:option:BTC-27JUN25-90000-P",
        instrument_id="BTC-27JUN25-90000-P",
        market_type="option",
        bid="10000",
        ask="10100",
    )
    hedge_quote = executable_quote(
        instrument_key="deribit:perpetual:BTC-PERPETUAL",
        instrument_id="BTC-PERPETUAL",
        market_type="perpetual",
        bid="95000",
        ask="95100",
    )

    with pytest.raises(ValueError, match="option pair must include call and put"):
        calculate_put_call_parity(pair, quote, wrong_put_quote, hedge_quote)

    with pytest.raises(ValueError, match="put quote does not match put instrument"):
        calculate_put_call_parity(complete_pair(), quote, wrong_put_quote, hedge_quote)
