from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Literal


SortMetric = Literal[
    "net_profit",
    "annualized_net_return",
    "total_slippage",
    "min_depth",
    "expiry_time_ms",
    "capital_required",
]


@dataclass(frozen=True)
class OpportunitySort:
    primary: SortMetric = "net_profit"
    descending: bool = True


def sort_opportunities(opportunities: Iterable[object], sort: OpportunitySort | None = None) -> list[object]:
    candidates = list(opportunities)
    if sort is not None:
        return sorted(
            candidates,
            key=lambda candidate: _custom_sort_key(candidate, sort.primary, sort.descending),
        )

    return sorted(candidates, key=_default_sort_key)


def _default_sort_key(candidate: object) -> tuple[object, ...]:
    return (
        _value(candidate, "is_executable") is False,
        -_decimal_metric(candidate, "net_profit", fallback_field="gross_profit", default=Decimal("0")),
        -_decimal_metric(candidate, "annualized_net_return", fallback_field="annualized_return", default=Decimal("0")),
        _decimal_metric(candidate, "total_slippage", default=Decimal("0")),
        -_decimal_metric(candidate, "min_depth", default=Decimal("0")),
        _integer_metric(candidate, "expiry_time_ms", default=0),
    )


def _custom_sort_key(candidate: object, metric: SortMetric, descending: bool) -> tuple[bool, Decimal | int]:
    if metric == "expiry_time_ms":
        value: Decimal | int = _integer_metric(candidate, metric, default=0)
    elif metric == "annualized_net_return":
        value = _decimal_metric(candidate, metric, fallback_field="annualized_return", default=Decimal("0"))
    elif metric == "net_profit":
        value = _decimal_metric(candidate, metric, fallback_field="gross_profit", default=Decimal("0"))
    else:
        value = _decimal_metric(candidate, metric, default=Decimal("0"))

    adjusted_value = -value if descending else value
    return (_value(candidate, metric) is None, adjusted_value)


def _decimal_metric(
    candidate: object,
    field_name: str,
    *,
    fallback_field: str | None = None,
    default: Decimal,
) -> Decimal:
    value = _value(candidate, field_name)
    if value is None and fallback_field is not None:
        value = _value(candidate, fallback_field)
    if value is None:
        return default
    return Decimal(str(value))


def _integer_metric(candidate: object, field_name: str, *, default: int) -> int:
    value = _value(candidate, field_name)
    if value is None:
        return default
    return int(value)


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
