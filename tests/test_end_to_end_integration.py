from types import SimpleNamespace

from option_taoli.adapters.deribit import DeribitAdapter
from option_taoli.alert_rules import AlertRule, select_alert_candidates
from option_taoli.dashboard import render_opportunity_list_html
from option_taoli.market_depth import standardize_quote
from option_taoli.opportunity_adjustments import apply_opportunity_adjustments
from option_taoli.opportunity_filters import OpportunityFilter
from option_taoli.opportunity_sorting import OpportunitySort, sort_opportunities
from option_taoli.option_chain import build_option_chain
from option_taoli.put_call_parity import calculate_put_call_parity
from option_taoli.webhook_alerts import WebhookAlertConfig, WebhookAlerter


class FakeWebhookHTTP:
    def __init__(self):
        self.calls = []

    def __call__(self, url: str, payload: dict, headers: dict[str, str], timeout_seconds: int) -> dict:
        self.calls.append((url, payload, headers, timeout_seconds))
        return {"status_code": 204, "body": ""}


def test_deribit_put_call_parity_opportunity_flows_to_dashboard_and_webhook_alert():
    adapter = DeribitAdapter(normalized_at_ms=1810880000000, received_at_ms=1810880000123)
    call = adapter.normalize_instrument(
        {
            "instrument_name": "BTC-27MAY27-100000-C",
            "kind": "option",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "BTC",
            "expiration_timestamp": 1811744000000,
            "strike": "100000",
            "option_type": "call",
            "instrument_type": "linear",
            "settlement_period": "month",
            "contract_size": "1",
            "tick_size": "0.5",
            "price_index": "btc_usd",
            "state": "open",
        }
    )
    put = adapter.normalize_instrument(
        {
            "instrument_name": "BTC-27MAY27-100000-P",
            "kind": "option",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "USD",
            "expiration_timestamp": 1811744000000,
            "strike": "100000",
            "option_type": "put",
            "instrument_type": "linear",
            "settlement_period": "month",
            "contract_size": "1",
            "tick_size": "0.5",
            "price_index": "btc_usd",
            "state": "open",
        }
    )
    chain = build_option_chain([call, put])
    option_pair = chain.complete_pairs()[0]

    call_quote = standardize_quote(
        adapter.normalize_quote(
            {
                "instrument_name": "BTC-27MAY27-100000-C",
                "best_bid_price": "5990",
                "best_ask_price": "6000",
                "best_bid_amount": "3",
                "best_ask_amount": "3",
                "timestamp": 1810880000000,
            },
            market_type="option",
        )
    )
    put_quote = standardize_quote(
        adapter.normalize_quote(
            {
                "instrument_name": "BTC-27MAY27-100000-P",
                "best_bid_price": "5000",
                "best_ask_price": "5010",
                "best_bid_amount": "3",
                "best_ask_amount": "3",
                "timestamp": 1810880000000,
            },
            market_type="option",
        )
    )
    hedge_quote = standardize_quote(
        adapter.normalize_quote(
            {
                "instrument_name": "BTC-PERPETUAL",
                "best_bid_price": "100900",
                "best_ask_price": "100910",
                "best_bid_amount": "2",
                "best_ask_amount": "2",
                "timestamp": 1810880000000,
            },
            market_type="perpetual",
        )
    )

    opportunity = calculate_put_call_parity(option_pair, call_quote, put_quote, hedge_quote)
    assert opportunity is not None
    adjusted = apply_opportunity_adjustments(
        opportunity,
        fee_rate="0.0001",
        capital_requirement_rate="0.1",
        now_ms=1810880000000,
    )
    candidate = SimpleNamespace(
        opportunity_id="deribit:pcp:btc_usd:1811744000000:100000",
        name="deribit-btc-pcp",
        opportunity_type="put_call_parity",
        exchange=opportunity.exchange,
        underlying_id=opportunity.underlying_id,
        expiry_time_ms=opportunity.expiry_time_ms,
        strike=opportunity.strike,
        direction=opportunity.direction,
        gross_profit=opportunity.gross_profit,
        net_profit=adjusted.net_profit,
        annualized_net_return=adjusted.annualized_net_return,
        total_slippage=adjusted.total_slippage,
        capital_required=adjusted.capital_required,
        is_executable=adjusted.is_executable,
        risk_tags=adjusted.risk_tags,
    )

    filtered = sort_opportunities(
        select_alert_candidates([candidate], AlertRule(min_net_profit="50", min_annualized_return="0.1")),
        OpportunitySort(primary="net_profit", descending=True),
    )
    html = render_opportunity_list_html(
        filtered,
        filters=OpportunityFilter(opportunity_types={"put_call_parity"}),
        generated_at_ms=1810880000000,
    )
    webhook_http = FakeWebhookHTTP()
    alerter = WebhookAlerter(
        WebhookAlertConfig(url="https://alerts.example.test/hook", secret="shared-secret"),
        http_post=webhook_http,
    )
    result = alerter.send_opportunity_alert(filtered[0], sent_at_ms=1810880010000)

    assert [item.opportunity_id for item in filtered] == ["deribit:pcp:btc_usd:1811744000000:100000"]
    assert "deribit-btc-pcp" in html
    assert "put_call_parity" in html
    assert result.status == "sent"
    assert webhook_http.calls[0][1]["opportunity"]["gross_profit"] == opportunity.gross_profit
    assert "net_profit" not in webhook_http.calls[0][1]["opportunity"]
    assert "total_slippage" not in webhook_http.calls[0][1]["opportunity"]
    assert webhook_http.calls[0][1]["opportunity"]["type"] == "put_call_parity"
