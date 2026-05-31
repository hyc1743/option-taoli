from types import SimpleNamespace

from option_taoli.dashboard import render_opportunity_detail_html
from option_taoli.put_call_parity import ArbitrageLeg


def opportunity_detail():
    return SimpleNamespace(
        name="pcp-btc-jun",
        opportunity_type="put_call_parity",
        exchange="deribit",
        underlying_id="btc_usd",
        expiry_time_ms=1811744000000,
        strike="100000",
        direction="long_synthetic_short_hedge",
        synthetic_forward_price="95050",
        hedge_price="95100",
        deviation="50",
        gross_profit="50",
        net_profit="37.5",
        annualized_net_return="0.31",
        total_fees="8",
        total_slippage="4.5",
        funding_impact="0",
        capital_required="12000",
        is_executable=True,
        risk_tags=["funding_cost_assumed", "legs_3"],
        explanation="C - P + K is below hedge bid; buy call, sell put, and sell hedge.",
        legs=[
            ArbitrageLeg("deribit:option:BTC-C", "buy", "5000", "1", "call"),
            ArbitrageLeg("deribit:option:BTC-P", "sell", "9950", "1", "put"),
            ArbitrageLeg("deribit:perpetual:BTC-PERPETUAL", "sell", "95100", "1", "hedge"),
        ],
    )


def test_renders_detail_page_with_logic_metrics_legs_and_risks():
    html = render_opportunity_detail_html(opportunity_detail(), generated_at_ms=1810880000000)

    assert "<!doctype html>" in html
    assert "Opportunity Detail" in html
    assert "pcp-btc-jun" in html
    assert "put_call_parity" in html
    assert "deribit" in html
    assert "btc_usd" in html
    assert "2027-05-31" in html
    assert "long_synthetic_short_hedge" in html
    assert "C - P + K is below hedge bid" in html
    assert "Synthetic forward price" in html
    assert "95050" in html
    assert "Hedge price" in html
    assert "95100" in html
    assert "Deviation" in html
    assert "Gross profit" in html
    assert "Net profit" in html
    assert "37.5" in html
    assert "Annualized net return" in html
    assert "31.00%" in html
    assert "Total fees" in html
    assert "Total slippage" in html
    assert "Funding impact" in html
    assert "Capital required" in html
    assert "Executable" in html
    assert "funding_cost_assumed" in html
    assert "legs_3" in html
    assert "deribit:option:BTC-C" in html
    assert "buy" in html
    assert "sell" in html
    assert "hedge" in html
    assert "font-family: \"IBM Plex Mono\", \"JetBrains Mono\", monospace" in html
    assert "background: #0B0C0A" in html


def test_renders_wrapped_detail_with_adjustments_and_basis_fields():
    wrapped = SimpleNamespace(
        name="basis-btc",
        opportunity_type="implied_futures_basis",
        opportunity=SimpleNamespace(
            exchange="okx",
            underlying_id="BTC-USD",
            expiry_time_ms=1811830400000,
            strike="90000",
            direction="buy_implied_sell_actual",
            implied_futures_price="95050",
            actual_futures_price="95100",
            basis="50",
            gross_profit="50",
            funding_rate_current="0.0001",
            funding_rate_8h="0.0008",
            explanation="Implied futures ask is below actual futures bid.",
            legs=[ArbitrageLeg("okx:option:BTC-C", "buy", "5000", "1", "call")],
        ),
        adjustments=SimpleNamespace(
            net_profit="41",
            annualized_net_return="0.22",
            total_fees="5",
            total_slippage="2",
            funding_impact="2",
            capital_required="10000",
            is_executable=False,
            risk_tags=["insufficient_depth"],
        ),
    )

    html = render_opportunity_detail_html(wrapped)

    assert "basis-btc" in html
    assert "implied_futures_basis" in html
    assert "Implied futures price" in html
    assert "Actual futures price" in html
    assert "Basis" in html
    assert "Funding rate current" in html
    assert "0.0001" in html
    assert "Funding rate 8h" in html
    assert "Blocked" in html
    assert "insufficient_depth" in html
    assert "okx:option:BTC-C" in html


def test_detail_page_escapes_dynamic_values():
    bad = opportunity_detail()
    bad.name = "<script>"
    bad.exchange = "bad<exchange>"
    bad.explanation = "logic <script>"
    bad.risk_tags = ["risk<script>"]
    bad.legs = [ArbitrageLeg("leg<script>", "buy", "1", "1", "call<script>")]

    html = render_opportunity_detail_html(bad)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "bad&lt;exchange&gt;" in html
    assert "logic &lt;script&gt;" in html
    assert "risk&lt;script&gt;" in html
    assert "leg&lt;script&gt;" in html
    assert "call&lt;script&gt;" in html
