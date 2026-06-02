from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from html import escape
from typing import Callable
from urllib import request

from option_taoli.opportunity_history import OpportunityHistoryStore


TelegramPost = Callable[[str, dict, int], dict]


@dataclass(frozen=True)
class TelegramAlertConfig:
    bot_token: str
    chat_id: str
    timeout_seconds: int = 10
    api_base_url: str = "https://api.telegram.org"

    def __post_init__(self) -> None:
        if not self.bot_token:
            raise ValueError("bot_token is required")
        if not self.chat_id:
            raise ValueError("chat_id is required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")


@dataclass(frozen=True)
class TelegramAlertResult:
    status: str
    message: str
    message_id: str | None = None
    error: str | None = None


class TelegramAlerter:
    def __init__(
        self,
        config: TelegramAlertConfig,
        *,
        http_post: TelegramPost | None = None,
        history_store: OpportunityHistoryStore | None = None,
    ):
        self._config = config
        self._http_post = http_post or _telegram_http_post
        self._history_store = history_store

    def send_opportunity_alert(self, opportunity: object, *, sent_at_ms: int) -> TelegramAlertResult:
        message = format_telegram_opportunity_message(opportunity)
        response = self._http_post(
            self._send_message_url(),
            {
                "chat_id": self._config.chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            self._config.timeout_seconds,
        )

        if response.get("ok") is True:
            message_id = response.get("result", {}).get("message_id")
            result = TelegramAlertResult(status="sent", message=message, message_id=None if message_id is None else str(message_id))
        else:
            error = str(response.get("description", "Telegram sendMessage failed"))
            result = TelegramAlertResult(status="failed", message=f"{message}\n\nError: {error}", error=error)

        if self._history_store is not None:
            self._history_store.record_alert(
                _opportunity_id(opportunity),
                channel="telegram",
                sent_at_ms=sent_at_ms,
                status=result.status,
                message=result.message,
            )

        return result

    def _send_message_url(self) -> str:
        return f"{self._config.api_base_url.rstrip('/')}/bot{self._config.bot_token}/sendMessage"


def format_telegram_opportunity_message(opportunity: object) -> str:
    lines = [
        "<b>Option arbitrage opportunity</b>",
        f"Type: {_html(_opportunity_type(opportunity))}",
        f"Exchange: {_html(_value(opportunity, 'exchange'))}",
        f"Underlying: {_html(_value(opportunity, 'underlying_id'))}",
        f"Expiry: {_html(_value(opportunity, 'expiry_time_ms'))}",
        f"Direction: {_html(_value(opportunity, 'direction'))}",
        f"Gross profit: {_html(_value(opportunity, 'gross_profit'))}",
        f"Annualized return: {_html(_percent(_value(opportunity, 'annualized_net_return') or _value(opportunity, 'annualized_return')))}",
        f"Capital required: {_html(_value(opportunity, 'capital_required'))}",
        f"Status: {'Executable' if _value(opportunity, 'is_executable') is not False else 'Blocked'}",
    ]
    risk_tags = _risk_tags(opportunity)
    if risk_tags:
        lines.append(f"Risk tags: {_html(', '.join(risk_tags))}")
    return "\n".join(lines)


def _telegram_http_post(url: str, payload: dict, timeout_seconds: int) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _value(candidate: object, field_name: str) -> object | None:
    if hasattr(candidate, field_name):
        return getattr(candidate, field_name)

    adjustments = getattr(candidate, "adjustments", None)
    if adjustments is not None and hasattr(adjustments, field_name):
        return getattr(adjustments, field_name)

    opportunity = getattr(candidate, "opportunity", None)
    if opportunity is not None and hasattr(opportunity, field_name):
        return getattr(opportunity, field_name)

    return None


def _opportunity_type(candidate: object) -> str | None:
    explicit = _value(candidate, "opportunity_type")
    if explicit is not None:
        return str(explicit)
    class_name = candidate.__class__.__name__
    if class_name == "PutCallParityOpportunity":
        return "put_call_parity"
    if class_name == "BoxSpreadOpportunity":
        return "box_spread"
    if class_name == "ImpliedFuturesBasisOpportunity":
        return "implied_futures_basis"
    return None


def _opportunity_id(candidate: object) -> str:
    explicit = _value(candidate, "opportunity_id")
    if explicit is not None:
        return str(explicit)
    # The history store snapshots expose opportunity_id; raw candidates should be recorded before alerting.
    raise ValueError("opportunity_id is required when recording Telegram alert history")


def _risk_tags(candidate: object) -> list[str]:
    value = _value(candidate, "risk_tags")
    if value is None:
        return []
    return [str(tag) for tag in value]


def _percent(value: object | None) -> str | None:
    if value is None:
        return None
    return f"{Decimal(str(value)) * Decimal('100'):.2f}%"


def _html(value: object | None) -> str:
    if value is None:
        return ""
    return escape(str(value))
