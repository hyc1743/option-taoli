from types import SimpleNamespace

import pytest

from option_taoli.opportunity_history import OpportunityHistoryStore
from option_taoli.telegram_alerts import TelegramAlertConfig, TelegramAlerter


def opportunity():
    return SimpleNamespace(
        name="pcp-btc",
        opportunity_type="put_call_parity",
        exchange="deribit",
        underlying_id="btc_usd",
        expiry_time_ms=1811744000000,
        strike="100000",
        direction="long_synthetic_short_hedge",
        gross_profit="150",
        net_profit="120",
        annualized_net_return="0.42",
        total_slippage="3",
        capital_required="25000",
        is_executable=True,
        risk_tags=["funding_cost_assumed"],
    )


class FakeTelegramHTTP:
    def __init__(self, response: dict | None = None):
        self.calls = []
        self.response = response or {"ok": True, "result": {"message_id": 42}}

    def __call__(self, url: str, payload: dict, timeout_seconds: int) -> dict:
        self.calls.append((url, payload, timeout_seconds))
        return self.response


def test_sends_telegram_message_with_official_send_message_payload():
    http = FakeTelegramHTTP()
    alerter = TelegramAlerter(
        TelegramAlertConfig(bot_token="123:token", chat_id="-1001", timeout_seconds=7),
        http_post=http,
    )

    result = alerter.send_opportunity_alert(opportunity(), sent_at_ms=1810880000000)

    assert result.status == "sent"
    assert result.message_id == "42"
    assert len(http.calls) == 1
    url, payload, timeout = http.calls[0]
    assert url == "https://api.telegram.org/bot123:token/sendMessage"
    assert timeout == 7
    assert payload["chat_id"] == "-1001"
    assert payload["disable_web_page_preview"] is True
    assert payload["parse_mode"] == "HTML"
    assert "put_call_parity" in payload["text"]
    assert "deribit" in payload["text"]
    assert "btc_usd" in payload["text"]
    assert "Gross profit: 150" in payload["text"]
    assert "Net profit" not in payload["text"]
    assert "Slippage" not in payload["text"]
    assert "Annualized return: 42.00%" in payload["text"]
    assert "funding_cost_assumed" in payload["text"]


def test_records_successful_telegram_alert_in_history_store(tmp_path):
    store = OpportunityHistoryStore(tmp_path / "history.sqlite3")
    event = store.record_observations([opportunity()], observed_at_ms=1810880000000)[0]
    http = FakeTelegramHTTP()
    alerter = TelegramAlerter(
        TelegramAlertConfig(bot_token="123:token", chat_id="-1001"),
        http_post=http,
        history_store=store,
    )

    result = alerter.send_opportunity_alert(event.snapshot, sent_at_ms=1810880010000)

    alerts = store.alerts(event.opportunity_id)
    assert result.status == "sent"
    assert len(alerts) == 1
    assert alerts[0].channel == "telegram"
    assert alerts[0].sent_at_ms == 1810880010000
    assert alerts[0].status == "sent"
    assert "Gross profit: 150" in alerts[0].message
    assert "Net profit" not in alerts[0].message


def test_records_failed_telegram_alert_and_exposes_error(tmp_path):
    store = OpportunityHistoryStore(tmp_path / "history.sqlite3")
    event = store.record_observations([opportunity()], observed_at_ms=1810880000000)[0]
    http = FakeTelegramHTTP({"ok": False, "description": "Bad Request: chat not found"})
    alerter = TelegramAlerter(
        TelegramAlertConfig(bot_token="123:token", chat_id="-1001"),
        http_post=http,
        history_store=store,
    )

    result = alerter.send_opportunity_alert(event.snapshot, sent_at_ms=1810880010000)

    assert result.status == "failed"
    assert result.error == "Bad Request: chat not found"
    alerts = store.alerts(event.opportunity_id)
    assert alerts[0].status == "failed"
    assert "Bad Request: chat not found" in alerts[0].message


def test_rejects_missing_telegram_configuration():
    with pytest.raises(ValueError, match="bot_token is required"):
        TelegramAlertConfig(bot_token="", chat_id="-1001")

    with pytest.raises(ValueError, match="chat_id is required"):
        TelegramAlertConfig(bot_token="123:token", chat_id="")
