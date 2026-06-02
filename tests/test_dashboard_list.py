from types import SimpleNamespace

from option_taoli.dashboard import render_opportunity_list_html
from option_taoli.opportunity_filters import OpportunityFilter
from option_taoli.opportunity_sorting import OpportunitySort


def candidate(
    name: str,
    *,
    opportunity_type: str,
    exchange: str,
    underlying_id: str,
    expiry_time_ms: int,
    strike: str = "100000",
    direction: str = "long_synthetic_short_hedge",
    gross_profit: str = "150",
    net_profit: str = "120",
    annualized_net_return: str = "0.42",
    total_slippage: str = "3",
    min_depth: str = "5",
    capital_required: str = "25000",
    is_executable: bool = True,
    risk_tags: list[str] | None = None,
):
    return SimpleNamespace(
        name=name,
        opportunity_type=opportunity_type,
        exchange=exchange,
        underlying_id=underlying_id,
        expiry_time_ms=expiry_time_ms,
        strike=strike,
        direction=direction,
        gross_profit=gross_profit,
        net_profit=net_profit,
        annualized_net_return=annualized_net_return,
        total_slippage=total_slippage,
        min_depth=min_depth,
        capital_required=capital_required,
        is_executable=is_executable,
        risk_tags=risk_tags or [],
    )


def test_renders_opportunity_list_with_filters_metrics_and_risk_tags():
    opportunities = [
        candidate(
            "pcp",
            opportunity_type="put_call_parity",
            exchange="deribit",
            underlying_id="btc_usd",
            expiry_time_ms=1811744000000,
            risk_tags=["funding_cost_assumed"],
        ),
        candidate(
            "box",
            opportunity_type="box_spread",
            exchange="okx",
            underlying_id="BTC-USD",
            expiry_time_ms=1811830400000,
            is_executable=False,
            risk_tags=["insufficient_depth"],
        ),
    ]

    html = render_opportunity_list_html(opportunities, generated_at_ms=1810880000000)

    assert "<!doctype html>" in html
    assert "Option Arbitrage Monitor" in html
    assert "Arbitrage type" in html
    assert "Exchange" in html
    assert "PCP mode" in html
    assert "Underlying" in html
    assert "Expiry" in html
    assert "Direction" not in html
    assert "Gross profit" not in html
    assert "Profit" in html
    assert "Min gross profit" in html
    assert "Max slippage" not in html
    assert "put_call_parity" in html
    assert "box_spread" in html
    assert "deribit" in html
    assert "okx" in html
    assert "btc_usd" in html
    assert "BTC-USD" in html
    assert "2027-05-31" in html
    assert "150" in html
    assert "42.00%" in html
    assert "25000" in html
    assert "Executable" in html
    assert "Blocked" in html
    assert "funding_cost_assumed" in html
    assert "insufficient_depth" in html
    assert "font-family: \"IBM Plex Mono\", \"JetBrains Mono\", monospace" in html
    assert "background: #0B0C0A" in html
    assert "border: 1px solid" in html


def test_dashboard_applies_filters_and_sorting_before_rendering_rows():
    opportunities = [
        candidate(
            "low-profit",
            opportunity_type="put_call_parity",
            exchange="deribit",
            underlying_id="btc_usd",
            expiry_time_ms=1811744000000,
            gross_profit="60",
            net_profit="60",
            annualized_net_return="0.1",
        ),
        candidate(
            "best-return",
            opportunity_type="box_spread",
            exchange="deribit",
            underlying_id="btc_usd",
            expiry_time_ms=1811744000000,
            gross_profit="150",
            net_profit="150",
            annualized_net_return="0.8",
        ),
        candidate(
            "middle-return",
            opportunity_type="implied_futures_basis",
            exchange="deribit",
            underlying_id="btc_usd",
            expiry_time_ms=1811744000000,
            gross_profit="180",
            net_profit="180",
            annualized_net_return="0.4",
        ),
    ]

    html = render_opportunity_list_html(
        opportunities,
        filters=OpportunityFilter(min_net_profit="100"),
        sort=OpportunitySort(primary="annualized_net_return", descending=True),
    )

    assert "low-profit" not in html
    assert html.index("best-return") < html.index("middle-return")


def test_dashboard_escapes_dynamic_values():
    html = render_opportunity_list_html(
        [
            candidate(
                "<script>",
                opportunity_type="put_call_parity",
                exchange="bad<exchange>",
                underlying_id="BTC<USD>",
                expiry_time_ms=1811744000000,
                risk_tags=["tag<script>"],
            )
        ]
    )

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "bad&lt;exchange&gt;" in html
    assert "BTC&lt;USD&gt;" in html
    assert "tag&lt;script&gt;" in html


def test_dashboard_formats_integral_strikes_without_decimal_suffix():
    html = render_opportunity_list_html(
        [
            candidate(
                "pcp",
                opportunity_type="put_call_parity",
                exchange="deribit",
                underlying_id="btc_usd",
                expiry_time_ms=1811744000000,
                strike="100000.000",
            )
        ]
    )

    assert ">100000<" in html
    assert "100000.000" not in html
