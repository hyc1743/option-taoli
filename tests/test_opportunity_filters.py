from types import SimpleNamespace

from option_taoli.opportunity_filters import OpportunityFilter, filter_opportunities


def candidate(
    *,
    opportunity_type: str,
    exchange: str = "deribit",
    underlying_id: str = "btc_usd",
    expiry_time_ms: int = 1811744000000,
    net_profit: str = "100",
    annualized_net_return: str | None = "0.25",
    total_slippage: str = "3",
    min_depth: str = "2",
    is_executable: bool = True,
):
    return SimpleNamespace(
        opportunity_type=opportunity_type,
        exchange=exchange,
        underlying_id=underlying_id,
        expiry_time_ms=expiry_time_ms,
        net_profit=net_profit,
        annualized_net_return=annualized_net_return,
        total_slippage=total_slippage,
        min_depth=min_depth,
        is_executable=is_executable,
    )


def wrapped_candidate(
    *,
    opportunity_type: str = "put_call_parity",
    net_profit: str = "80",
    annualized_net_return: str = "0.18",
    total_slippage: str = "4",
):
    return SimpleNamespace(
        opportunity=SimpleNamespace(
            exchange="okx",
            underlying_id="BTC-USD",
            expiry_time_ms=1811744000000,
            gross_profit="100",
        ),
        adjustments=SimpleNamespace(
            net_profit=net_profit,
            annualized_net_return=annualized_net_return,
            total_slippage=total_slippage,
            is_executable=True,
        ),
        opportunity_type=opportunity_type,
        min_depth="5",
    )


def test_filters_by_profit_return_slippage_depth_and_executable_status():
    opportunities = [
        candidate(opportunity_type="put_call_parity", net_profit="120", annualized_net_return="0.4"),
        candidate(opportunity_type="box_spread", net_profit="90", annualized_net_return="0.4"),
        candidate(opportunity_type="box_spread", net_profit="120", annualized_net_return="0.05"),
        candidate(opportunity_type="box_spread", net_profit="120", annualized_net_return="0.4", total_slippage="11"),
        candidate(opportunity_type="box_spread", net_profit="120", annualized_net_return="0.4", min_depth="0.5"),
        candidate(opportunity_type="box_spread", net_profit="120", annualized_net_return="0.4", is_executable=False),
    ]

    filtered = filter_opportunities(
        opportunities,
        OpportunityFilter(
            min_net_profit="100",
            min_annualized_return="0.1",
            max_slippage="10",
            min_depth="1",
            opportunity_types={"put_call_parity", "box_spread"},
        ),
    )

    assert filtered == [opportunities[0]]


def test_filters_by_exchange_underlying_expiry_and_type_on_wrapped_candidates():
    opportunities = [
        wrapped_candidate(opportunity_type="put_call_parity"),
        wrapped_candidate(opportunity_type="box_spread"),
        candidate(
            opportunity_type="put_call_parity",
            exchange="deribit",
            underlying_id="btc_usd",
            expiry_time_ms=1811830400000,
        ),
    ]

    filtered = filter_opportunities(
        opportunities,
        OpportunityFilter(
            exchanges={"okx"},
            underlying_ids={"BTC-USD"},
            expiry_time_ms_values={1811744000000},
            opportunity_types={"put_call_parity"},
        ),
    )

    assert filtered == [opportunities[0]]


def test_falls_back_to_gross_profit_and_keeps_unknown_optional_metrics():
    opportunities = [
        SimpleNamespace(
            opportunity_type="implied_futures_basis",
            exchange="bybit",
            underlying_id="BTC",
            expiry_time_ms=1811744000000,
            gross_profit="60",
        ),
        SimpleNamespace(
            opportunity_type="implied_futures_basis",
            exchange="bybit",
            underlying_id="BTC",
            expiry_time_ms=1811744000000,
            gross_profit="30",
        ),
    ]

    filtered = filter_opportunities(opportunities, OpportunityFilter(min_net_profit="50"))

    assert filtered == [opportunities[0]]
