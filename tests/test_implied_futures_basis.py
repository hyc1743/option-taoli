import pytest

from option_taoli.implied_futures_basis import calculate_implied_futures_basis
from option_taoli.market_depth import ExecutableQuote
from option_taoli.models import Instrument
from option_taoli.option_chain import OptionPair
from option_taoli.perpetual_market import PerpetualMarketState


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


def complete_pair() -> OptionPair:
    return OptionPair(
        exchange="deribit",
        underlying_id="btc_usd",
        expiry_time_ms=1751011200000,
        strike="100000",
        call=option_instrument("BTC-27JUN25-100000-C", "call"),
        put=option_instrument("BTC-27JUN25-100000-P", "put"),
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


def perpetual_state() -> PerpetualMarketState:
    return PerpetualMarketState(
        instrument_key="deribit:perpetual:BTC-PERPETUAL",
        exchange="deribit",
        instrument_id="BTC-PERPETUAL",
        perpetual_price="95150",
        mark_price="95120",
        index_price="95080",
        mark_index_basis="40",
        mark_index_basis_rate="0.0004206973075305006310475399663",
        funding_rate_current="0.00001234",
        funding_rate_8h="0.00009876",
        funding_rate_annualized=None,
        funding_interval_hours="8",
        received_at_ms=1780210000100,
        normalized_at_ms=1780210000200,
    )


def test_detects_buy_implied_sell_actual_futures_basis_opportunity():
    opportunity = calculate_implied_futures_basis(
        complete_pair(),
        executable_quote(
            instrument_key="deribit:option:BTC-27JUN25-100000-C",
            instrument_id="BTC-27JUN25-100000-C",
            market_type="option",
            bid="4900",
            ask="5000",
        ),
        executable_quote(
            instrument_key="deribit:option:BTC-27JUN25-100000-P",
            instrument_id="BTC-27JUN25-100000-P",
            market_type="option",
            bid="9950",
            ask="10050",
        ),
        executable_quote(
            instrument_key="deribit:perpetual:BTC-PERPETUAL",
            instrument_id="BTC-PERPETUAL",
            market_type="perpetual",
            bid="95100",
            ask="95200",
        ),
        actual_market_state=perpetual_state(),
    )

    assert opportunity is not None
    assert opportunity.direction == "buy_implied_sell_actual"
    assert opportunity.implied_futures_price == "95050"
    assert opportunity.actual_futures_price == "95100"
    assert opportunity.basis == "50"
    assert opportunity.gross_profit == "50"
    assert opportunity.funding_rate_current == "0.00001234"
    assert "funding_rate_present" in opportunity.risk_tags
    assert [(leg.instrument_key, leg.side, leg.price, leg.role) for leg in opportunity.legs] == [
        ("deribit:option:BTC-27JUN25-100000-C", "buy", "5000", "call"),
        ("deribit:option:BTC-27JUN25-100000-P", "sell", "9950", "put"),
        ("deribit:perpetual:BTC-PERPETUAL", "sell", "95100", "actual_future"),
    ]


def test_detects_sell_implied_buy_actual_futures_basis_opportunity():
    opportunity = calculate_implied_futures_basis(
        complete_pair(),
        executable_quote(
            instrument_key="deribit:option:BTC-27JUN25-100000-C",
            instrument_id="BTC-27JUN25-100000-C",
            market_type="option",
            bid="6200",
            ask="6300",
        ),
        executable_quote(
            instrument_key="deribit:option:BTC-27JUN25-100000-P",
            instrument_id="BTC-27JUN25-100000-P",
            market_type="option",
            bid="9950",
            ask="10000",
        ),
        executable_quote(
            instrument_key="deribit:future:BTC-27JUN25",
            instrument_id="BTC-27JUN25",
            market_type="future",
            bid="95500",
            ask="96000",
        ),
    )

    assert opportunity is not None
    assert opportunity.direction == "sell_implied_buy_actual"
    assert opportunity.implied_futures_price == "96200"
    assert opportunity.actual_futures_price == "96000"
    assert opportunity.basis == "200"
    assert opportunity.funding_rate_current is None
    assert "no_funding_rate" in opportunity.risk_tags
    assert [(leg.instrument_key, leg.side, leg.price, leg.role) for leg in opportunity.legs] == [
        ("deribit:option:BTC-27JUN25-100000-C", "sell", "6200", "call"),
        ("deribit:option:BTC-27JUN25-100000-P", "buy", "10000", "put"),
        ("deribit:future:BTC-27JUN25", "buy", "96000", "actual_future"),
    ]


def test_returns_none_when_implied_and_actual_edges_do_not_cross():
    opportunity = calculate_implied_futures_basis(
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
            instrument_key="deribit:perpetual:BTC-PERPETUAL",
            instrument_id="BTC-PERPETUAL",
            market_type="perpetual",
            bid="95000",
            ask="95100",
        ),
    )

    assert opportunity is None


def test_rejects_mismatched_quotes_and_unsupported_actual_market_type():
    call_quote = executable_quote(
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
    put_quote = executable_quote(
        instrument_key="deribit:option:BTC-27JUN25-100000-P",
        instrument_id="BTC-27JUN25-100000-P",
        market_type="option",
        bid="10000",
        ask="10100",
    )
    spot_quote = executable_quote(
        instrument_key="deribit:spot:BTC_USDC",
        instrument_id="BTC_USDC",
        market_type="spot",
        bid="95000",
        ask="95100",
    )

    with pytest.raises(ValueError, match="put quote does not match put instrument"):
        calculate_implied_futures_basis(complete_pair(), call_quote, wrong_put_quote, spot_quote)

    with pytest.raises(ValueError, match="actual quote market_type must be perpetual, future, or spot"):
        index_q = executable_quote(
            instrument_key="deribit:index:BTC_USDC",
            instrument_id="BTC_USDC",
            market_type="index",
            bid="95000",
            ask="95100",
        )
        calculate_implied_futures_basis(complete_pair(), call_quote, put_quote, index_q)