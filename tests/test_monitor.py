from option_taoli.adapters.deribit import DeribitAdapter
from option_taoli.alert_rules import AlertRule
from option_taoli.market_depth import standardize_quote
from option_taoli.monitor import ArbitrageMonitor, MarketDataBatch, MonitorConfig
from option_taoli.opportunity_history import OpportunityHistoryStore
from option_taoli.webhook_alerts import WebhookAlertConfig, WebhookAlerter


class FakeWebhookHTTP:
    def __init__(self):
        self.calls = []

    def __call__(self, url: str, payload: dict, headers: dict[str, str], timeout_seconds: int) -> dict:
        self.calls.append((url, payload, headers, timeout_seconds))
        return {"status_code": 204, "body": ""}


class FakeSleeper:
    def __init__(self):
        self.intervals = []

    def __call__(self, interval_seconds: float) -> None:
        self.intervals.append(interval_seconds)


def deribit_pcp_batch() -> MarketDataBatch:
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
            "instrument_type": "reversed",
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
            "settlement_currency": "BTC",
            "expiration_timestamp": 1811744000000,
            "strike": "100000",
            "option_type": "put",
            "instrument_type": "reversed",
            "settlement_period": "month",
            "contract_size": "1",
            "tick_size": "0.5",
            "price_index": "btc_usd",
            "state": "open",
        }
    )
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
    return MarketDataBatch(
        instruments=[call, put],
        quotes_by_instrument_key={
            call_quote.instrument_key: call_quote,
            put_quote.instrument_key: put_quote,
            hedge_quote.instrument_key: hedge_quote,
        },
        hedge_quotes_by_underlying={("deribit", "btc_usd"): hedge_quote},
    )


def test_scan_once_generates_opportunities_records_history_renders_dashboard_and_sends_alert(tmp_path):
    http = FakeWebhookHTTP()
    store = OpportunityHistoryStore(tmp_path / "history.sqlite3")
    monitor = ArbitrageMonitor(
        MonitorConfig(
            fee_rate="0.0001",
            capital_requirement_rate="0.1",
            alert_rule=AlertRule(
                min_net_profit="50",
                min_annualized_return="0.1",
                opportunity_types={"put_call_parity"},
            ),
        ),
        history_store=store,
        alerters=[
            WebhookAlerter(
                WebhookAlertConfig(url="https://alerts.example.test/hook"),
                http_post=http,
                history_store=store,
            )
        ],
    )

    result = monitor.scan_once(deribit_pcp_batch(), observed_at_ms=1810880000000)

    assert len(result.opportunities) == 2
    assert result.displayed_opportunities[0].opportunity_type == "put_call_parity"
    assert result.alert_candidates == [result.displayed_opportunities[0]]
    assert "put_call_parity" in result.dashboard_html
    assert "deribit" in result.dashboard_html
    assert [event.event_type for event in result.history_events] == ["created", "created"]
    assert http.calls[0][1]["opportunity"]["type"] == "put_call_parity"
    assert store.alerts(result.alert_candidates[0].opportunity_id)[0].status == "sent"


def test_polling_loop_fetches_batches_and_sleeps_between_cycles(tmp_path):
    calls = []
    sleeper = FakeSleeper()
    monitor = ArbitrageMonitor(
        MonitorConfig(alert_rule=AlertRule(min_net_profit="50")),
        history_store=OpportunityHistoryStore(tmp_path / "history.sqlite3"),
        sleep=sleeper,
    )

    def fetch_batch() -> MarketDataBatch:
        calls.append("fetch")
        return deribit_pcp_batch()

    results = monitor.run_polling(fetch_batch, interval_seconds=3, max_cycles=2, start_observed_at_ms=1810880000000)

    assert len(results) == 2
    assert calls == ["fetch", "fetch"]
    assert sleeper.intervals == [3]
    assert all(result.displayed_opportunities for result in results)
