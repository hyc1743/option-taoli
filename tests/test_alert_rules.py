from types import SimpleNamespace

from option_taoli.alert_rules import AlertRule, select_alert_candidates


def opportunity(
    *,
    opportunity_id: str,
    opportunity_type: str = "put_call_parity",
    exchange: str = "deribit",
    underlying_id: str = "btc_usd",
    expiry_time_ms: int = 1811744000000,
    gross_profit: str = "120",
    net_profit: str = "120",
    annualized_net_return: str = "0.42",
    total_slippage: str = "3",
    min_depth: str = "2",
    is_executable: bool = True,
):
    return SimpleNamespace(
        opportunity_id=opportunity_id,
        opportunity_type=opportunity_type,
        exchange=exchange,
        underlying_id=underlying_id,
        expiry_time_ms=expiry_time_ms,
        gross_profit=gross_profit,
        net_profit=net_profit,
        annualized_net_return=annualized_net_return,
        total_slippage=total_slippage,
        min_depth=min_depth,
        is_executable=is_executable,
    )


def test_selects_alert_candidates_that_match_thresholds_and_scope():
    candidates = [
        opportunity(opportunity_id="pcp-1", gross_profit="120", net_profit="1", annualized_net_return="0.42"),
        opportunity(opportunity_id="pcp-low-profit", gross_profit="20", net_profit="900", annualized_net_return="0.42"),
        opportunity(opportunity_id="pcp-low-return", gross_profit="120", net_profit="1", annualized_net_return="0.05"),
        opportunity(opportunity_id="pcp-high-slippage", gross_profit="120", net_profit="1", annualized_net_return="0.42", total_slippage="9"),
        opportunity(opportunity_id="pcp-low-depth", gross_profit="120", net_profit="1", annualized_net_return="0.42", min_depth="0.2"),
        opportunity(opportunity_id="pcp-blocked", gross_profit="120", net_profit="1", annualized_net_return="0.42", is_executable=False),
        opportunity(opportunity_id="box-1", opportunity_type="box_spread", gross_profit="120", net_profit="1", annualized_net_return="0.42"),
    ]

    selected = select_alert_candidates(
        candidates,
        AlertRule(
            min_net_profit="100",
            min_annualized_return="0.10",
            max_slippage="5",
            min_depth="1",
            opportunity_types={"put_call_parity"},
            exchanges={"deribit"},
            underlying_ids={"btc_usd"},
            expiry_time_ms_values={1811744000000},
        ),
    )

    assert [candidate.opportunity_id for candidate in selected] == ["pcp-1", "pcp-high-slippage"]


def test_suppresses_previously_alerted_opportunities_by_id():
    selected = select_alert_candidates(
        [
            opportunity(opportunity_id="pcp-1"),
            opportunity(opportunity_id="pcp-2"),
        ],
        AlertRule(min_net_profit="100"),
        suppressed_opportunity_ids={"pcp-1"},
    )

    assert [candidate.opportunity_id for candidate in selected] == ["pcp-2"]


def test_alert_rule_accepts_wrapped_opportunities_and_adjustments():
    raw = opportunity(opportunity_id="wrapped-1", gross_profit="140", net_profit="20")
    adjustments = SimpleNamespace(
        net_profit="140",
        annualized_net_return="0.35",
        total_slippage="2",
        min_depth="3",
        is_executable=True,
    )
    wrapped = SimpleNamespace(opportunity=raw, adjustments=adjustments)

    selected = select_alert_candidates(
        [wrapped],
        AlertRule(min_net_profit="100", min_annualized_return="0.10", max_slippage="5", min_depth="1"),
    )

    assert selected == [wrapped]
