from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from option_taoli.market_depth import ExecutableQuote
from option_taoli.put_call_parity import ArbitrageLeg


MILLISECONDS_PER_HOUR = Decimal("3600000")


@dataclass(frozen=True)
class ExecutionDiagnosticConfig:
    min_execution_net_profit: str = "20"
    min_dte_hours: str = "12"
    max_dte_hours: str = "72"
    max_moneyness: str = "0.20"
    quote_max_age_seconds: str = "30"
    min_depth_ratio: str = "0.2"
    maker_price_aggression: str = "0.8"
    settlement_fee_rate: str = "0"


@dataclass(frozen=True)
class ExecutionDiagnostic:
    status: str
    strategy_type: str | None
    anchor_leg: str | None
    all_taker_net_profit: str | None
    maker_anchor_net_profit: str | None
    estimated_open_fees: str
    estimated_settlement_cost: str
    estimated_funding_impact: str
    dte_hours: str | None
    moneyness: str | None
    depth_ok: bool | None
    quote_fresh: bool | None
    reject_reasons: list[str]
    risk_tags: list[str]


def diagnose_execution(
    opportunity: object,
    batch: object,
    config: ExecutionDiagnosticConfig | None,
    *,
    observed_at_ms: int,
    fee_rate: str,
    taker_fee_rates_by_exchange_market: Mapping[str, str] | None = None,
    funding_holding_hours: str | None = None,
    funding_interval_hours: str = "8",
) -> ExecutionDiagnostic:
    del taker_fee_rates_by_exchange_market, funding_holding_hours, funding_interval_hours
    cfg = config or ExecutionDiagnosticConfig()
    if opportunity.__class__.__name__ != "PutCallParityOpportunity":
        return _diagnostic(
            status="watch",
            reason="execution_diagnostic_not_supported",
            risk_tags=_risk_tags(opportunity),
        )

    legs = list(getattr(opportunity, "legs", []) or [])
    leg_by_role = {str(leg.role): leg for leg in legs}
    call_leg = leg_by_role.get("call")
    put_leg = leg_by_role.get("put")
    hedge_leg = leg_by_role.get("hedge") or leg_by_role.get("actual_future")
    if call_leg is None or put_leg is None or hedge_leg is None:
        return _diagnostic(
            status="blocked",
            reason="missing_execution_leg",
            risk_tags=_risk_tags(opportunity),
        )

    quotes = getattr(batch, "quotes_by_instrument_key", {})
    call_quote = quotes.get(call_leg.instrument_key)
    put_quote = quotes.get(put_leg.instrument_key)
    hedge_quote = quotes.get(hedge_leg.instrument_key)
    if call_quote is None or put_quote is None or hedge_quote is None:
        return _diagnostic(
            status="blocked",
            reason="missing_execution_quote",
            risk_tags=_risk_tags(opportunity),
        )

    blocked: list[str] = []
    watch: list[str] = []
    if hedge_quote.market_type == "spot" and hedge_leg.side == "sell":
        blocked.append("spot_short_not_supported")

    dte_hours = _dte_hours(opportunity, observed_at_ms)
    if dte_hours is None:
        watch.append("missing_dte")
    elif dte_hours < Decimal(cfg.min_dte_hours):
        watch.append("dte_too_short")
    elif dte_hours > Decimal(cfg.max_dte_hours):
        watch.append("dte_too_long")

    moneyness = _moneyness(opportunity, hedge_quote)
    if moneyness is None:
        watch.append("missing_moneyness")
    elif moneyness > Decimal(cfg.max_moneyness):
        watch.append("moneyness_out_of_range")

    quote_fresh = _quotes_are_fresh([call_quote, put_quote, hedge_quote], observed_at_ms, cfg)
    if quote_fresh is False:
        watch.append("stale_quote")

    depth_ok = _depth_ok([call_leg, put_leg, hedge_leg], [call_quote, put_quote, hedge_quote], cfg)
    if depth_ok is False:
        watch.append("insufficient_depth")
    if _has_placeholder_depth([call_quote, put_quote, hedge_quote]):
        watch.append("placeholder_depth")

    anchor_leg = _anchor_leg(call_quote, put_quote)
    strategy_type = _strategy_type(opportunity)
    all_taker_gross = _all_taker_gross(opportunity, call_quote, put_quote, hedge_quote)
    maker_gross = _maker_anchor_gross(opportunity, call_quote, put_quote, hedge_quote, anchor_leg, cfg)
    open_fees = _estimated_open_fees([call_leg, put_leg, hedge_leg], [call_quote, put_quote, hedge_quote], fee_rate)
    settlement_cost = _settlement_cost([call_leg, put_leg, hedge_leg], [call_quote, put_quote, hedge_quote], cfg)
    funding_impact = Decimal("0")
    all_taker_net = all_taker_gross - open_fees - settlement_cost - funding_impact
    maker_net = maker_gross - open_fees - settlement_cost - funding_impact

    if maker_net < Decimal(cfg.min_execution_net_profit):
        watch.append("min_execution_net_profit_not_met")

    reasons = _dedupe(blocked + watch)
    status = "blocked" if blocked else "watch" if watch else "ready"
    return ExecutionDiagnostic(
        status=status,
        strategy_type=strategy_type,
        anchor_leg=anchor_leg,
        all_taker_net_profit=str(all_taker_net),
        maker_anchor_net_profit=str(maker_net),
        estimated_open_fees=str(open_fees),
        estimated_settlement_cost=str(settlement_cost),
        estimated_funding_impact=str(funding_impact),
        dte_hours=None if dte_hours is None else str(dte_hours),
        moneyness=None if moneyness is None else str(moneyness),
        depth_ok=depth_ok,
        quote_fresh=quote_fresh,
        reject_reasons=reasons,
        risk_tags=_risk_tags(opportunity) + reasons,
    )


def _diagnostic(*, status: str, reason: str, risk_tags: list[str]) -> ExecutionDiagnostic:
    return ExecutionDiagnostic(
        status=status,
        strategy_type=None,
        anchor_leg=None,
        all_taker_net_profit=None,
        maker_anchor_net_profit=None,
        estimated_open_fees="0",
        estimated_settlement_cost="0",
        estimated_funding_impact="0",
        dte_hours=None,
        moneyness=None,
        depth_ok=None,
        quote_fresh=None,
        reject_reasons=[reason],
        risk_tags=risk_tags + [reason],
    )


def _risk_tags(opportunity: object) -> list[str]:
    return [str(tag) for tag in (getattr(opportunity, "risk_tags", None) or [])]


def _strategy_type(opportunity: object) -> str | None:
    direction = getattr(opportunity, "direction", None)
    if direction == "long_synthetic_short_hedge":
        return "sell_future_buy_synthetic"
    if direction == "short_synthetic_long_hedge":
        return "buy_future_sell_synthetic"
    return None


def _dte_hours(opportunity: object, observed_at_ms: int) -> Decimal | None:
    expiry = getattr(opportunity, "expiry_time_ms", None)
    if expiry is None:
        return None
    return (Decimal(int(expiry)) - Decimal(observed_at_ms)) / MILLISECONDS_PER_HOUR


def _moneyness(opportunity: object, hedge_quote: ExecutableQuote) -> Decimal | None:
    strike = getattr(opportunity, "strike", None)
    if strike is None:
        return None
    hedge_mid = Decimal(hedge_quote.mid_price)
    if hedge_mid <= 0:
        return None
    return abs(Decimal(str(strike)) - hedge_mid) / hedge_mid


def _quotes_are_fresh(
    quotes: list[ExecutableQuote],
    observed_at_ms: int,
    config: ExecutionDiagnosticConfig,
) -> bool | None:
    max_age_ms = Decimal(config.quote_max_age_seconds) * Decimal("1000")
    fresh = True
    for quote in quotes:
        timestamp = quote.received_at_ms or quote.normalized_at_ms
        if timestamp is None:
            return None
        if Decimal(observed_at_ms - int(timestamp)) > max_age_ms:
            fresh = False
    return fresh


def _depth_ok(
    legs: list[ArbitrageLeg],
    quotes: list[ExecutableQuote],
    config: ExecutionDiagnosticConfig,
) -> bool | None:
    required_multiplier = Decimal(config.min_depth_ratio)
    ok = True
    for leg, quote in zip(legs, quotes):
        required = Decimal(leg.size) * required_multiplier
        available = Decimal(quote.best_ask_size if leg.side == "buy" else quote.best_bid_size)
        if available < required:
            ok = False
    return ok


def _has_placeholder_depth(quotes: list[ExecutableQuote]) -> bool:
    return all(
        Decimal(quote.best_bid_size) == Decimal("1") and Decimal(quote.best_ask_size) == Decimal("1")
        for quote in quotes
    )


def _anchor_leg(call_quote: ExecutableQuote, put_quote: ExecutableQuote) -> str:
    call_spread = Decimal(call_quote.best_ask_price) - Decimal(call_quote.best_bid_price)
    put_spread = Decimal(put_quote.best_ask_price) - Decimal(put_quote.best_bid_price)
    return "call" if call_spread >= put_spread else "put"


def _all_taker_gross(
    opportunity: object,
    call_quote: ExecutableQuote,
    put_quote: ExecutableQuote,
    hedge_quote: ExecutableQuote,
) -> Decimal:
    strike = Decimal(str(getattr(opportunity, "strike")))
    if getattr(opportunity, "direction") == "long_synthetic_short_hedge":
        synthetic = Decimal(call_quote.best_ask_price) - Decimal(put_quote.best_bid_price) + strike
        return Decimal(hedge_quote.best_bid_price) - synthetic
    synthetic = Decimal(call_quote.best_bid_price) - Decimal(put_quote.best_ask_price) + strike
    return synthetic - Decimal(hedge_quote.best_ask_price)


def _maker_anchor_gross(
    opportunity: object,
    call_quote: ExecutableQuote,
    put_quote: ExecutableQuote,
    hedge_quote: ExecutableQuote,
    anchor_leg: str,
    config: ExecutionDiagnosticConfig,
) -> Decimal:
    strike = Decimal(str(getattr(opportunity, "strike")))
    direction = getattr(opportunity, "direction")
    call_price = _maker_price(call_quote, side="buy" if direction == "long_synthetic_short_hedge" else "sell", config=config) if anchor_leg == "call" else _taker_price(call_quote, side="buy" if direction == "long_synthetic_short_hedge" else "sell")
    put_price = _maker_price(put_quote, side="sell" if direction == "long_synthetic_short_hedge" else "buy", config=config) if anchor_leg == "put" else _taker_price(put_quote, side="sell" if direction == "long_synthetic_short_hedge" else "buy")
    if direction == "long_synthetic_short_hedge":
        synthetic = call_price - put_price + strike
        return Decimal(hedge_quote.best_bid_price) - synthetic
    synthetic = call_price - put_price + strike
    return synthetic - Decimal(hedge_quote.best_ask_price)


def _maker_price(quote: ExecutableQuote, *, side: str, config: ExecutionDiagnosticConfig) -> Decimal:
    bid = Decimal(quote.best_bid_price)
    ask = Decimal(quote.best_ask_price)
    spread = ask - bid
    aggression = Decimal(config.maker_price_aggression)
    if side == "buy":
        return bid + spread * aggression
    return ask - spread * aggression


def _taker_price(quote: ExecutableQuote, *, side: str) -> Decimal:
    return Decimal(quote.best_ask_price if side == "buy" else quote.best_bid_price)


def _estimated_open_fees(
    legs: list[ArbitrageLeg],
    quotes: list[ExecutableQuote],
    fee_rate: str,
) -> Decimal:
    rate = Decimal(fee_rate)
    return sum((Decimal(leg.size) * _taker_price(quote, side=leg.side) * rate for leg, quote in zip(legs, quotes)), Decimal("0"))


def _settlement_cost(
    legs: list[ArbitrageLeg],
    quotes: list[ExecutableQuote],
    config: ExecutionDiagnosticConfig,
) -> Decimal:
    rate = Decimal(config.settlement_fee_rate)
    return sum((Decimal(leg.size) * _taker_price(quote, side=leg.side) * rate for leg, quote in zip(legs, quotes)), Decimal("0"))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
