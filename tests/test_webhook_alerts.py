from types import SimpleNamespace

import pytest

from option_taoli.opportunity_history import OpportunityHistoryStore
from option_taoli.webhook_alerts import WebhookAlertConfig, WebhookAlerter


def opportunity():
    return SimpleNamespace(
        name="basis-btc",
        opportunity_type="implied_futures_basis",
        exchange="okx",
        underlying_id="BTC-USD",
        expiry_time_ms=1811744000000,
        strike="90000",
        direction="buy_implied_sell_actual",
        gross_profit="150",
        net_profit="120",
        annualized_net_return="0.42",
        total_slippage="3",
        capital_required="25000",
        is_executable=True,
        risk_tags=["funding_rate_present"],
    )


class FakeWebhookHTTP:
    def __init__(self, response: dict | None = None):
        self.calls = []
        self.response = response or {"status_code": 204, "body": ""}

    def __call__(self, url: str, payload: dict, headers: dict[str, str], timeout_seconds: int) -> dict:
        self.calls.append((url, payload, headers, timeout_seconds))
        return self.response


def test_posts_structured_webhook_payload_with_headers():
    http = FakeWebhookHTTP()
    alerter = WebhookAlerter(
        WebhookAlertConfig(
            url="https://alerts.example.test/hook",
            secret="shared-secret",
            timeout_seconds=6,
        ),
        http_post=http,
    )

    result = alerter.send_opportunity_alert(opportunity(), sent_at_ms=1810880000000)

    assert result.status == "sent"
    assert len(http.calls) == 1
    url, payload, headers, timeout = http.calls[0]
    assert url == "https://alerts.example.test/hook"
    assert timeout == 6
    assert headers["Content-Type"] == "application/json"
    assert headers["X-Option-Taoli-Secret"] == "shared-secret"
    assert payload["event"] == "option_arbitrage_opportunity"
    assert payload["sent_at_ms"] == 1810880000000
    assert payload["opportunity"]["type"] == "implied_futures_basis"
    assert payload["opportunity"]["exchange"] == "okx"
    assert payload["opportunity"]["underlying_id"] == "BTC-USD"
    assert payload["opportunity"]["gross_profit"] == "150"
    assert "net_profit" not in payload["opportunity"]
    assert "total_slippage" not in payload["opportunity"]
    assert payload["opportunity"]["annualized_net_return"] == "0.42"
    assert payload["opportunity"]["is_executable"] is True
    assert payload["opportunity"]["risk_tags"] == ["funding_rate_present"]


def test_records_successful_webhook_alert_in_history_store(tmp_path):
    store = OpportunityHistoryStore(tmp_path / "history.sqlite3")
    event = store.record_observations([opportunity()], observed_at_ms=1810880000000)[0]
    http = FakeWebhookHTTP()
    alerter = WebhookAlerter(
        WebhookAlertConfig(url="https://alerts.example.test/hook"),
        http_post=http,
        history_store=store,
    )

    result = alerter.send_opportunity_alert(event.snapshot, sent_at_ms=1810880010000)

    alerts = store.alerts(event.opportunity_id)
    assert result.status == "sent"
    assert len(alerts) == 1
    assert alerts[0].channel == "webhook"
    assert alerts[0].sent_at_ms == 1810880010000
    assert alerts[0].status == "sent"
    assert "implied_futures_basis" in alerts[0].message


def test_records_failed_webhook_alert_and_error(tmp_path):
    store = OpportunityHistoryStore(tmp_path / "history.sqlite3")
    event = store.record_observations([opportunity()], observed_at_ms=1810880000000)[0]
    http = FakeWebhookHTTP({"status_code": 500, "body": "server error"})
    alerter = WebhookAlerter(
        WebhookAlertConfig(url="https://alerts.example.test/hook"),
        http_post=http,
        history_store=store,
    )

    result = alerter.send_opportunity_alert(event.snapshot, sent_at_ms=1810880010000)

    assert result.status == "failed"
    assert result.error == "HTTP 500: server error"
    alerts = store.alerts(event.opportunity_id)
    assert alerts[0].status == "failed"
    assert "HTTP 500: server error" in alerts[0].message


def test_rejects_invalid_webhook_configuration():
    with pytest.raises(ValueError, match="url is required"):
        WebhookAlertConfig(url="")

    with pytest.raises(ValueError, match="timeout_seconds must be greater than zero"):
        WebhookAlertConfig(url="https://alerts.example.test/hook", timeout_seconds=0)
