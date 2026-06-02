from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


@dataclass(frozen=True)
class OpportunityFilter:
    min_net_profit: str | None = None
    min_annualized_return: str | None = None
    # Deprecated: slippage is no longer used as an opportunity filter.
    max_slippage: str | None = None
    min_depth: str | None = None
    exchanges: set[str] | None = None
    underlying_ids: set[str] | None = None
    expiry_time_ms_values: set[int] | None = None
    opportunity_types: set[str] | None = None
    pcp_execution_modes: set[str] | None = None
    require_executable: bool = True


def filter_opportunities(opportunities: Iterable[object], filters: OpportunityFilter) -> list[object]:
    return [opportunity for opportunity in opportunities if _matches(opportunity, filters)]


def _matches(candidate: object, filters: OpportunityFilter) -> bool:
    if filters.exchanges is not None and _value(candidate, "exchange") not in filters.exchanges:
        return False
    if filters.underlying_ids is not None and _value(candidate, "underlying_id") not in filters.underlying_ids:
        return False
    if filters.expiry_time_ms_values is not None and _value(candidate, "expiry_time_ms") not in filters.expiry_time_ms_values:
        return False
    if filters.opportunity_types is not None and _opportunity_type(candidate) not in filters.opportunity_types:
        return False
    if (
        filters.pcp_execution_modes is not None
        and _opportunity_type(candidate) == "put_call_parity"
        and _value(candidate, "pcp_execution_mode") not in filters.pcp_execution_modes
    ):
        return False

    if filters.require_executable and _value(candidate, "is_executable") is False:
        return False

    profit = _decimal_metric(candidate, "gross_profit")
    if filters.min_net_profit is not None and profit is not None and profit < _decimal(filters.min_net_profit):
        return False

    annualized_return = _decimal_metric(candidate, "annualized_net_return", fallback_field="annualized_return")
    if (
        filters.min_annualized_return is not None
        and annualized_return is not None
        and annualized_return < _decimal(filters.min_annualized_return)
    ):
        return False

    depth = _decimal_metric(candidate, "min_depth")
    if filters.min_depth is not None and depth is not None and depth < _decimal(filters.min_depth):
        return False

    return True


def _opportunity_type(candidate: object) -> str | None:
    explicit = _value(candidate, "opportunity_type")
    if explicit is not None:
        return str(explicit)

    source = getattr(candidate, "opportunity", candidate)
    class_name = source.__class__.__name__
    if class_name == "PutCallParityOpportunity":
        return "put_call_parity"
    if class_name == "BoxSpreadOpportunity":
        return "box_spread"
    if class_name == "ImpliedFuturesBasisOpportunity":
        return "implied_futures_basis"
    return None


def _decimal_metric(candidate: object, field_name: str, *, fallback_field: str | None = None) -> Decimal | None:
    value = _value(candidate, field_name)
    if value is None and fallback_field is not None:
        value = _value(candidate, fallback_field)
    if value is None:
        return None
    return _decimal(str(value))


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


def _decimal(value: str) -> Decimal:
    return Decimal(value)
