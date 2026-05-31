from types import SimpleNamespace

from option_taoli.box_spread import calculate_box_spreads
from option_taoli.implied_futures_basis import calculate_implied_futures_basis
from option_taoli.market_depth import ExecutableQuote
from option_taoli.models import Instrument
from option_taoli.opportunity_adjustments import apply_opportunity_adjustments
from option_taoli.opportunity_filters import OpportunityFilter, filter_opportunities
from option_taoli.opportunity_sorting import sort_opportunities
from option_taoli.option_chain import OptionPair, build_option_chain
from option_taoli.put_call_parity import calculate_put_call_parity


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


def quote(instrument_key: str, instrument_id: str, market_type: str, *, bid: str, ask: str) -> ExecutableQuote:
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
        received_at_ms=NOW_MS,
        normalized_at_ms=NOW_MS,
    )


def option_quote(instrument: Instrument, *, bid: str, ask: str) -> ExecutableQuote:
    return quote(instrument.instrument_key, instrument.instrument_id, "option", bid=bid, ask=ask)


def option_pair(strike: str = "100000") -> OptionPair:
    call = option_instrument(strike, "call")
    put = option_instrument(strike, "put")
    return OptionPair(
        exchange="deribit",
        underlying_id="btc_usd",
        expiry_time_ms=EXPIRY_MS,
        strike=strike,
        call=call,
        put=put,
    )


def test_put_call_parity_applies_discount_factor_and_trade_size_to_profit():
    pair = option_pair()
    assert pair.call is not None
    assert pair.put is not None

    opportunity = calculate_put_call_parity(
        pair,
        option_quote(pair.call, bid="6900", ask="7000"),
        option_quote(pair.put, bid="11500", ask="11600"),
        quote("deribit:perpetual:BTC-PERPETUAL", "BTC-PERPETUAL", "perpetual", bid="95000", ask="95100"),
        discount_factor="0.99",
        size="2",
    )

    assert opportunity is not None
    assert opportunity.direction == "long_synthetic_short_hedge"
    assert opportunity.synthetic_forward_price == "94500.00"
    assert opportunity.deviation == "500.00"
    assert opportunity.gross_profit == "1000.00"
    assert [leg.size for leg in opportunity.legs] == ["2", "2", "2"]


def test_box_spread_scales_cashflow_entry_value_and_profit_by_size():
    instruments = [
        option_instrument("90000", "call"),
        option_instrument("90000", "put"),
        option_instrument("100000", "call"),
        option_instrument("100000", "put"),
    ]
    expiry = build_option_chain(instruments).expiries[("deribit", "btc_usd", EXPIRY_MS)]

    opportunities = calculate_box_spreads(
        expiry,
        {
            instruments[0].instrument_key: option_quote(instruments[0], bid="6900", ask="7000"),
            instruments[1].instrument_key: option_quote(instruments[1], bid="400", ask="500"),
            instruments[2].instrument_key: option_quote(instruments[2], bid="2500", ask="2600"),
            instruments[3].instrument_key: option_quote(instruments[3], bid="4900", ask="5000"),
        },
        now_ms=NOW_MS,
        size="3",
    )

    opportunity = opportunities[0]
    assert opportunity.fixed_cashflow == "30000"
    assert opportunity.entry_value == "27300"
    assert opportunity.gross_profit == "2700"
    assert [leg.size for leg in opportunity.legs] == ["3", "3", "3", "3"]


def test_implied_futures_basis_applies_discount_factor_and_size_to_basis_profit():
    pair = option_pair()
    assert pair.call is not None
    assert pair.put is not None

    opportunity = calculate_implied_futures_basis(
        pair,
        option_quote(pair.call, bid="6900", ask="7000"),
        option_quote(pair.put, bid="11500", ask="11600"),
        quote("deribit:future:BTC-27JUN25", "BTC-27JUN25", "future", bid="95000", ask="95100"),
        discount_factor="0.99",
        size="2",
    )

    assert opportunity is not None
    assert opportunity.direction == "buy_implied_sell_actual"
    assert opportunity.implied_futures_price == "94500.00"
    assert opportunity.actual_futures_price == "95000"
    assert opportunity.basis == "500.00"
    assert opportunity.gross_profit == "1000.00"
    assert [leg.size for leg in opportunity.legs] == ["2", "2", "2"]


def test_adjusted_core_opportunities_can_be_filtered_and_sorted_by_net_metrics():
    high_gross = SimpleNamespace(
        name="high-gross",
        opportunity_type="put_call_parity",
        gross_profit="300",
        annualized_net_return="0.10",
        total_slippage="1",
        min_depth="5",
        is_executable=True,
        legs=[
            SimpleNamespace(instrument_key="call", side="buy", price="100", size="1", role="call"),
            SimpleNamespace(instrument_key="hedge", side="sell", price="1000", size="1", role="hedge"),
        ],
    )
    high_net = SimpleNamespace(
        name="high-net",
        opportunity_type="box_spread",
        gross_profit="150",
        annualized_net_return="0.20",
        total_slippage="1",
        min_depth="5",
        is_executable=True,
        legs=[
            SimpleNamespace(instrument_key="lower_call", side="buy", price="100", size="1", role="lower_call"),
            SimpleNamespace(instrument_key="upper_call", side="sell", price="100", size="1", role="upper_call"),
        ],
    )

    adjusted_high_gross = SimpleNamespace(
        name=high_gross.name,
        opportunity=high_gross,
        adjustments=apply_opportunity_adjustments(high_gross, fee_rate="0", slippage_costs_by_instrument_key={"call": "250"}),
        annualized_net_return="0.10",
        total_slippage="250",
        min_depth="5",
        opportunity_type=high_gross.opportunity_type,
    )
    adjusted_high_net = SimpleNamespace(
        name=high_net.name,
        opportunity=high_net,
        adjustments=apply_opportunity_adjustments(high_net, fee_rate="0"),
        annualized_net_return="0.20",
        total_slippage="1",
        min_depth="5",
        opportunity_type=high_net.opportunity_type,
    )

    filtered = filter_opportunities(
        [adjusted_high_gross, adjusted_high_net],
        OpportunityFilter(min_net_profit="100", max_slippage="10"),
    )
    sorted_opportunities = sort_opportunities(filtered)

    assert [opportunity.name for opportunity in sorted_opportunities] == ["high-net"]
    assert sorted_opportunities[0].adjustments.net_profit == "150"
