from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from option_taoli.opportunity_filters import OpportunityFilter, filter_opportunities


@dataclass(frozen=True)
class AlertRule:
    min_net_profit: str | None = None
    min_annualized_return: str | None = None
    max_slippage: str | None = None
    min_depth: str | None = None
    exchanges: set[str] | None = None
    underlying_ids: set[str] | None = None
    expiry_time_ms_values: set[int] | None = None
    opportunity_types: set[str] | None = None
    require_executable: bool = True

    def as_opportunity_filter(self) -> OpportunityFilter:
        return OpportunityFilter(
            min_net_profit=self.min_net_profit,
            min_annualized_return=self.min_annualized_return,
            max_slippage=self.max_slippage,
            min_depth=self.min_depth,
            exchanges=self.exchanges,
            underlying_ids=self.underlying_ids,
            expiry_time_ms_values=self.expiry_time_ms_values,
            opportunity_types=self.opportunity_types,
            require_executable=self.require_executable,
        )


def select_alert_candidates(
    opportunities: Iterable[object],
    rule: AlertRule,
    *,
    suppressed_opportunity_ids: set[str] | None = None,
) -> list[object]:
    matched = filter_opportunities(opportunities, rule.as_opportunity_filter())
    suppressed = suppressed_opportunity_ids or set()
    return [candidate for candidate in matched if _opportunity_id(candidate) not in suppressed]


def _opportunity_id(candidate: object) -> str | None:
    value = _value(candidate, "opportunity_id")
    if value is None:
        return None
    return str(value)


def _value(candidate: object, field_name: str) -> object | None:
    if hasattr(candidate, field_name):
        return getattr(candidate, field_name)

    opportunity = getattr(candidate, "opportunity", None)
    if opportunity is not None and hasattr(opportunity, field_name):
        return getattr(opportunity, field_name)

    adjustments = getattr(candidate, "adjustments", None)
    if adjustments is not None and hasattr(adjustments, field_name):
        return getattr(adjustments, field_name)

    return None
