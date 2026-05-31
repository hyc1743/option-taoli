from types import SimpleNamespace

from option_taoli.market_depth import DepthFill
from option_taoli.opportunity_adjustments import apply_opportunity_adjustments
from option_taoli.put_call_parity import ArbitrageLeg


def opportunity(*, gross_profit: str = "50", expiry_time_ms: int = 1811744000000):
    return SimpleNamespace(
        gross_profit=gross_profit,
        expiry_time_ms=expiry_time_ms,
        legs=[
            ArbitrageLeg("deribit:option:BTC-C", "buy", "5000", "1", "call"),
            ArbitrageLeg("deribit:option:BTC-P", "sell", "9950", "1", "put"),
            ArbitrageLeg("deribit:perpetual:BTC-PERPETUAL", "sell", "95100", "1", "actual_future"),
        ],
    )


def test_adjusts_gross_profit_for_fees_slippage_and_capital_usage():
    adjusted = apply_opportunity_adjustments(
        opportunity(gross_profit="200"),
        fee_rate="0.0001",
        slippage_costs_by_instrument_key={
            "deribit:option:BTC-C": "2.5",
            "deribit:option:BTC-P": "1.5",
        },
        capital_requirement_rate="0.1",
    )

    assert adjusted.gross_profit == "200"
    assert adjusted.total_fees == "11.0050"
    assert adjusted.total_slippage == "4.0"
    assert adjusted.funding_impact == "0"
    assert adjusted.capital_required == "11005.0"
    assert adjusted.net_profit == "184.9950"
    assert adjusted.net_return == "0.01681008632439800090867787369"
    assert adjusted.is_executable is True
    assert adjusted.risk_tags == []


def test_uses_depth_fill_for_slippage_and_marks_incomplete_fill_not_executable():
    adjusted = apply_opportunity_adjustments(
        opportunity(gross_profit="100"),
        fee_rate="0",
        depth_fills_by_instrument_key={
            "deribit:option:BTC-C": DepthFill(
                side="buy",
                requested_size="1",
                filled_size="1",
                notional="5003",
                average_price="5003",
                worst_price="5003",
                fully_filled=True,
            ),
            "deribit:perpetual:BTC-PERPETUAL": DepthFill(
                side="sell",
                requested_size="1",
                filled_size="0.5",
                notional="47540",
                average_price="95080",
                worst_price="95080",
                fully_filled=False,
            ),
        },
    )

    assert adjusted.total_slippage == "13.0"
    assert adjusted.net_profit == "87.0"
    assert adjusted.is_executable is False
    assert "insufficient_depth" in adjusted.risk_tags


def test_applies_perpetual_funding_impact_and_annualized_net_return():
    adjusted = apply_opportunity_adjustments(
        opportunity(gross_profit="120", expiry_time_ms=1811744000000),
        fee_rate="0",
        funding_rates_by_instrument_key={"deribit:perpetual:BTC-PERPETUAL": "0.0001"},
        funding_holding_hours="16",
        funding_interval_hours="8",
        capital_requirement_rate="0.2",
        now_ms=1810880000000,
    )

    assert adjusted.funding_impact == "-19.0200"
    assert adjusted.net_profit == "139.0200"
    assert adjusted.capital_required == "22010.0"
    assert adjusted.net_return == "0.006316219900045433893684688778"
    assert adjusted.annualized_net_return == "0.2305420263516583371194911404"
    assert "funding_credit_assumed" in adjusted.risk_tags
