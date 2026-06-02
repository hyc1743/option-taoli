from types import SimpleNamespace

from option_taoli.opportunity_sorting import OpportunitySort, sort_opportunities


def candidate(
    name: str,
    *,
    gross_profit: str = "100",
    net_profit: str,
    annualized_net_return: str | None,
    total_slippage: str = "1",
    min_depth: str = "10",
    expiry_time_ms: int = 1811744000000,
    is_executable: bool = True,
):
    return SimpleNamespace(
        name=name,
        gross_profit=gross_profit,
        net_profit=net_profit,
        annualized_net_return=annualized_net_return,
        total_slippage=total_slippage,
        min_depth=min_depth,
        expiry_time_ms=expiry_time_ms,
        is_executable=is_executable,
    )


def wrapped_candidate(name: str, *, net_profit: str, annualized_net_return: str):
    return SimpleNamespace(
        name=name,
        opportunity=SimpleNamespace(gross_profit="200", expiry_time_ms=1811830400000),
        adjustments=SimpleNamespace(
            net_profit=net_profit,
            annualized_net_return=annualized_net_return,
            total_slippage="2",
            is_executable=True,
        ),
        min_depth="8",
    )


def test_default_sort_prioritizes_executable_gross_profit_return_depth_and_nearer_expiry():
    opportunities = [
        candidate("not-executable-high-profit", gross_profit="1000", net_profit="10", annualized_net_return="1", is_executable=False),
        candidate("lower-profit", gross_profit="90", net_profit="900", annualized_net_return="3"),
        candidate("higher-return", gross_profit="100", net_profit="1", annualized_net_return="0.8"),
        candidate("deeper-book", gross_profit="100", net_profit="1", annualized_net_return="0.7", min_depth="20"),
        candidate("nearer-expiry", gross_profit="100", net_profit="1", annualized_net_return="0.7", expiry_time_ms=1810880000000),
    ]

    sorted_opportunities = sort_opportunities(opportunities)

    assert [opportunity.name for opportunity in sorted_opportunities] == [
        "higher-return",
        "deeper-book",
        "nearer-expiry",
        "lower-profit",
        "not-executable-high-profit",
    ]


def test_custom_sort_orders_wrapped_candidates_by_selected_metric():
    opportunities = [
        wrapped_candidate("best-net", net_profit="200", annualized_net_return="0.2"),
        wrapped_candidate("best-return", net_profit="80", annualized_net_return="0.9"),
        wrapped_candidate("middle", net_profit="120", annualized_net_return="0.4"),
    ]

    sorted_opportunities = sort_opportunities(
        opportunities,
        OpportunitySort(primary="gross_profit", descending=True),
    )

    assert [opportunity.name for opportunity in sorted_opportunities] == ["best-net", "best-return", "middle"]
