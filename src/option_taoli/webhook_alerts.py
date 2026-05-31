from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable
from urllib import request

from option_taoli.opportunity_history import OpportunityHistoryStore


WebhookPost = Callable[[str, dict, dict[str, str], int], dict]


@dataclass(frozen=True)
class WebhookAlertConfig:
    url: str
    secret: str | None = None
    timeout_seconds: int = 10

    def __post_init__(self) -> None:
        if not self.url:
            raise ValueError("url is required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")


@dataclass(frozen=True)
class WebhookAlertResult:
    status: str
    message: str
    status_code: int | None = None
    error: str | None = None


class WebhookAlerter:
    def __init__(
        self,
        config: WebhookAlertConfig,
        *,
        http_post: WebhookPost | None = None,
        history_store: OpportunityHistoryStore | None = None,
    ):
        self._config = config
        self._http_post = http_post or _webhook_http_post
        self._history_store = history_store

    def send_opportunity_alert(self, opportunity: object, *, sent_at_ms: int) -> WebhookAlertResult:
        payload = build_webhook_payload(opportunity, sent_at_ms=sent_at_ms)
        response = self._http_post(
            self._config.url,
            payload,
            self._headers(),
            self._config.timeout_seconds,
        )
        status_code = int(response.get("status_code", 0))
        message = json.dumps(payload, sort_keys=True, separators=(",", ":"))

        if 200 <= status_code < 300:
            result = WebhookAlertResult(status="sent", message=message, status_code=status_code)
        else:
            error = f"HTTP {status_code}: {response.get('body', '')}"
            result = WebhookAlertResult(status="failed", message=f"{message}\nError: {error}", status_code=status_code, error=error)

        if self._history_store is not None:
            self._history_store.record_alert(
                _opportunity_id(opportunity),
                channel="webhook",
                sent_at_ms=sent_at_ms,
                status=result.status,
                message=result.message,
            )

        return result

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._config.secret:
            headers["X-Option-Taoli-Secret"] = self._config.secret
        return headers


def build_webhook_payload(opportunity: object, *, sent_at_ms: int) -> dict:
    return {
        "event": "option_arbitrage_opportunity",
        "sent_at_ms": sent_at_ms,
        "opportunity": {
            "id": _value(opportunity, "opportunity_id"),
            "type": _opportunity_type(opportunity),
            "exchange": _value(opportunity, "exchange"),
            "underlying_id": _value(opportunity, "underlying_id"),
            "expiry_time_ms": _value(opportunity, "expiry_time_ms"),
            "strike": _value(opportunity, "strike") or _strike_range(opportunity),
            "direction": _value(opportunity, "direction"),
            "gross_profit": _value(opportunity, "gross_profit"),
            "net_profit": _value(opportunity, "net_profit") or _value(opportunity, "gross_profit"),
            "annualized_net_return": _value(opportunity, "annualized_net_return")
            or _value(opportunity, "annualized_return"),
            "total_slippage": _value(opportunity, "total_slippage"),
            "capital_required": _value(opportunity, "capital_required"),
            "is_executable": _value(opportunity, "is_executable"),
            "risk_tags": _risk_tags(opportunity),
        },
    }


def _webhook_http_post(url: str, payload: dict, headers: dict[str, str], timeout_seconds: int) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_seconds) as response:
        return {"status_code": response.status, "body": response.read().decode("utf-8")}


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
    raise ValueError("opportunity_id is required when recording Webhook alert history")


def _strike_range(candidate: object) -> str | None:
    lower = _value(candidate, "lower_strike")
    upper = _value(candidate, "upper_strike")
    if lower is None or upper is None:
        return None
    return f"{lower}-{upper}"


def _risk_tags(candidate: object) -> list[str]:
    value = _value(candidate, "risk_tags")
    if value is None:
        return []
    return [str(tag) for tag in value]
