from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from option_taoli.market_depth import DepthFill
from option_taoli.put_call_parity import ArbitrageLeg


MILLISECONDS_PER_YEAR = Decimal("31536000000")


@dataclass(frozen=True)
class AdjustedOpportunity:
    gross_profit: str
    total_fees: str
    total_slippage: str
    funding_impact: str
    capital_required: str
    net_profit: str
    net_return: str | None
    annualized_net_return: str | None
    is_executable: bool
    risk_tags: list[str]


def apply_opportunity_adjustments(
    opportunity: object,
    *,
    fee_rate: str = "0",
    slippage_costs_by_instrument_key: Mapping[str, str] | None = None,
    depth_fills_by_instrument_key: Mapping[str, DepthFill] | None = None,
    funding_rates_by_instrument_key: Mapping[str, str] | None = None,
    funding_holding_hours: str | None = None,
    funding_interval_hours: str = "8",
    capital_requirement_rate: str = "1",
    now_ms: int | None = None,
) -> AdjustedOpportunity:
    legs = _legs(opportunity)
    gross_profit = _decimal(str(getattr(opportunity, "gross_profit")), "gross_profit")
    rate = _non_negative_decimal(fee_rate, "fee_rate")
    capital_rate = _non_negative_decimal(capital_requirement_rate, "capital_requirement_rate")

    leg_notionals = [_leg_notional(leg) for leg in legs]
    total_fees = sum((notional * rate for notional in leg_notionals), Decimal("0"))
    _, depth_is_executable = _slippage_cost(
        legs,
        {},
        depth_fills_by_instrument_key or {},
    )
    funding_impact, funding_tags = _funding_impact(
        legs,
        funding_rates_by_instrument_key or {},
        funding_holding_hours=funding_holding_hours,
        funding_interval_hours=funding_interval_hours,
    )
    capital_required = sum((notional * capital_rate for notional in leg_notionals), Decimal("0"))
    total_slippage = Decimal("0")
    net_profit = gross_profit
    net_return = None if capital_required <= 0 else str(net_profit / capital_required)

    annualized_net_return = None
    expiry_time_ms = getattr(opportunity, "expiry_time_ms", None)
    if now_ms is not None and expiry_time_ms is not None and capital_required > 0:
        time_to_expiry_ms = Decimal(int(expiry_time_ms) - now_ms)
        if time_to_expiry_ms > 0:
            annualized_net_return = str((net_profit / capital_required) * (MILLISECONDS_PER_YEAR / time_to_expiry_ms))

    risk_tags: list[str] = []
    if not depth_is_executable:
        risk_tags.append("insufficient_depth")
    risk_tags.extend(funding_tags)
    if gross_profit <= 0:
        risk_tags.append("not_profitable")

    return AdjustedOpportunity(
        gross_profit=str(gross_profit),
        total_fees=str(total_fees),
        total_slippage=str(total_slippage),
        funding_impact=str(funding_impact),
        capital_required=str(capital_required),
        net_profit=str(net_profit),
        net_return=net_return,
        annualized_net_return=annualized_net_return,
        is_executable=depth_is_executable and gross_profit > 0,
        risk_tags=risk_tags,
    )


def _legs(opportunity: object) -> list[ArbitrageLeg]:
    legs = getattr(opportunity, "legs", None)
    if not legs:
        raise ValueError("opportunity must include at least one leg")
    return list(legs)


def _slippage_cost(
    legs: list[ArbitrageLeg],
    explicit_costs: Mapping[str, str],
    depth_fills: Mapping[str, DepthFill],
) -> tuple[Decimal, bool]:
    total = Decimal("0")
    is_executable = True
    for leg in legs:
        if leg.instrument_key in explicit_costs:
            total += _non_negative_decimal(explicit_costs[leg.instrument_key], "slippage cost")

        fill = depth_fills.get(leg.instrument_key)
        if fill is None:
            continue
        if not fill.fully_filled:
            is_executable = False
        if fill.average_price is None:
            continue
        expected_price = _positive_decimal(leg.price, "leg price")
        fill_price = _positive_decimal(fill.average_price, "fill average price")
        size = _positive_decimal(fill.filled_size, "fill filled_size")
        if leg.side == "buy":
            total += (fill_price - expected_price) * size
        else:
            total += (expected_price - fill_price) * size
    return total, is_executable


def _funding_impact(
    legs: list[ArbitrageLeg],
    rates_by_instrument_key: Mapping[str, str],
    *,
    funding_holding_hours: str | None,
    funding_interval_hours: str,
) -> tuple[Decimal, list[str]]:
    if not rates_by_instrument_key:
        return Decimal("0"), []
    if funding_holding_hours is None:
        raise ValueError("funding_holding_hours is required when funding rates are provided")

    holding_hours = _non_negative_decimal(funding_holding_hours, "funding_holding_hours")
    interval_hours = _positive_decimal(funding_interval_hours, "funding_interval_hours")
    intervals = holding_hours / interval_hours
    total = Decimal("0")
    tags: list[str] = []

    for leg in legs:
        rate_text = rates_by_instrument_key.get(leg.instrument_key)
        if rate_text is None:
            continue
        notional = _leg_notional(leg)
        rate = _decimal(rate_text, "funding rate")
        directional_multiplier = Decimal("1") if leg.side == "buy" else Decimal("-1")
        impact = notional * rate * intervals * directional_multiplier
        total += impact
        if impact < 0:
            tags.append("funding_credit_assumed")
        elif impact > 0:
            tags.append("funding_cost_assumed")

    return total, tags


def _leg_notional(leg: ArbitrageLeg) -> Decimal:
    return _positive_decimal(leg.price, "leg price") * _positive_decimal(leg.size, "leg size")


def _positive_decimal(value: str, field_name: str) -> Decimal:
    decimal = _decimal(value, field_name)
    if decimal <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return decimal


def _non_negative_decimal(value: str, field_name: str) -> Decimal:
    decimal = _decimal(value, field_name)
    if decimal < 0:
        raise ValueError(f"{field_name} must be greater than or equal to zero")
    return decimal


def _decimal(value: str, field_name: str) -> Decimal:
    try:
        return Decimal(value)
    except Exception as exc:
        raise ValueError(f"{field_name} must be a decimal string") from exc
