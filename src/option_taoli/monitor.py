from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from time import sleep as default_sleep
from typing import Callable, Iterable, Literal, Protocol

from option_taoli.alert_rules import AlertRule, select_alert_candidates
from option_taoli.box_spread import calculate_box_spreads
from option_taoli.dashboard import render_opportunity_list_html
from option_taoli.execution_diagnostics import (
    ExecutionDiagnostic,
    ExecutionDiagnosticConfig,
    diagnose_execution,
)
from option_taoli.implied_futures_basis import calculate_implied_futures_basis
from option_taoli.market_depth import ExecutableQuote
from option_taoli.models import Instrument
from option_taoli.opportunity_adjustments import AdjustedOpportunity, apply_opportunity_adjustments
from option_taoli.opportunity_filters import OpportunityFilter, filter_opportunities
from option_taoli.opportunity_history import OpportunityHistoryStore, OpportunityTimelineEvent
from option_taoli.opportunity_sorting import OpportunitySort, sort_opportunities
from option_taoli.option_chain import OptionPair, build_option_chain
from option_taoli.perpetual_market import PerpetualMarketState
from option_taoli.put_call_parity import calculate_put_call_parity


HedgeKey = tuple[str, str]
PcpExecutionMode = Literal["same_exchange", "cross_exchange"]


class OpportunityAlerter(Protocol):
    def send_opportunity_alert(self, opportunity: object, *, sent_at_ms: int) -> object:
        ...


@dataclass(frozen=True)
class MarketDataBatch:
    instruments: list[Instrument]
    quotes_by_instrument_key: dict[str, ExecutableQuote]
    hedge_quotes_by_underlying: dict[HedgeKey, ExecutableQuote]
    perpetual_states_by_instrument_key: dict[str, PerpetualMarketState] | None = None


@dataclass(frozen=True)
class MonitorConfig:
    fee_rate: str = "0"
    taker_fee_rates_by_exchange_market: Mapping[str, str] | None = None
    capital_requirement_rate: str = "1"
    funding_holding_hours: str | None = None
    funding_interval_hours: str = "8"
    opportunity_filter: OpportunityFilter | None = None
    opportunity_sort: OpportunitySort | None = None
    alert_rule: AlertRule | None = None
    alert_once_per_opportunity: bool = True
    execution_diagnostic_config: ExecutionDiagnosticConfig | None = None


@dataclass(frozen=True)
class MonitoredOpportunity:
    opportunity_id: str
    name: str
    opportunity_type: str
    exchange: str
    underlying_id: str
    expiry_time_ms: int
    strike: str | None
    lower_strike: str | None
    upper_strike: str | None
    direction: str
    gross_profit: str
    net_profit: str
    annualized_net_return: str | None
    total_slippage: str
    capital_required: str
    is_executable: bool
    risk_tags: list[str]
    pcp_execution_mode: PcpExecutionMode | None
    execution_diagnostic: ExecutionDiagnostic | None
    opportunity: object
    adjustments: AdjustedOpportunity

    @property
    def legs(self) -> object:
        return getattr(self.opportunity, "legs")

    @property
    def synthetic_forward_price(self) -> object | None:
        return getattr(self.opportunity, "synthetic_forward_price", None)

    @property
    def hedge_price(self) -> object | None:
        return getattr(self.opportunity, "hedge_price", None)

    @property
    def deviation(self) -> object | None:
        return getattr(self.opportunity, "deviation", None)

    @property
    def fixed_cashflow(self) -> object | None:
        return getattr(self.opportunity, "fixed_cashflow", None)

    @property
    def entry_value(self) -> object | None:
        return getattr(self.opportunity, "entry_value", None)

    @property
    def implied_futures_price(self) -> object | None:
        return getattr(self.opportunity, "implied_futures_price", None)

    @property
    def actual_futures_price(self) -> object | None:
        return getattr(self.opportunity, "actual_futures_price", None)

    @property
    def basis(self) -> object | None:
        return getattr(self.opportunity, "basis", None)


@dataclass(frozen=True)
class MonitorScanResult:
    opportunities: list[MonitoredOpportunity]
    displayed_opportunities: list[MonitoredOpportunity]
    alert_candidates: list[MonitoredOpportunity]
    dashboard_html: str
    history_events: list[OpportunityTimelineEvent]
    alert_results: list[object]


class ArbitrageMonitor:
    def __init__(
        self,
        config: MonitorConfig | None = None,
        *,
        history_store: OpportunityHistoryStore | None = None,
        alerters: Iterable[OpportunityAlerter] | None = None,
        sleep: Callable[[float], None] = default_sleep,
    ):
        self._config = config or MonitorConfig()
        self._history_store = history_store
        self._alerters = list(alerters or [])
        self._sleep = sleep
        self._alerted_opportunity_ids: set[str] = set()

    def scan_once(self, batch: MarketDataBatch, *, observed_at_ms: int) -> MonitorScanResult:
        raw_opportunities = self._calculate_opportunities(batch, observed_at_ms=observed_at_ms)
        opportunities = [
            self._monitor_candidate(opportunity, batch=batch, observed_at_ms=observed_at_ms)
            for opportunity in raw_opportunities
        ]

        displayed = opportunities
        if self._config.opportunity_filter is not None:
            displayed = filter_opportunities(displayed, self._config.opportunity_filter)
        displayed = sort_opportunities(displayed, self._config.opportunity_sort)

        history_events: list[OpportunityTimelineEvent] = []
        if self._history_store is not None:
            history_events = self._history_store.record_observations(displayed, observed_at_ms=observed_at_ms)

        dashboard_html = render_opportunity_list_html(displayed, generated_at_ms=observed_at_ms)
        alert_candidates = self._select_alert_candidates(displayed)
        alert_results = self._send_alerts(alert_candidates, sent_at_ms=observed_at_ms)

        return MonitorScanResult(
            opportunities=opportunities,
            displayed_opportunities=displayed,
            alert_candidates=alert_candidates,
            dashboard_html=dashboard_html,
            history_events=history_events,
            alert_results=alert_results,
        )

    def run_polling(
        self,
        fetch_batch: Callable[[], MarketDataBatch],
        *,
        interval_seconds: float,
        max_cycles: int | None = None,
        start_observed_at_ms: int = 0,
    ) -> list[MonitorScanResult]:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero")
        if max_cycles is not None and max_cycles <= 0:
            raise ValueError("max_cycles must be greater than zero")

        results: list[MonitorScanResult] = []
        cycle = 0
        while max_cycles is None or cycle < max_cycles:
            observed_at_ms = start_observed_at_ms + int(cycle * interval_seconds * 1000)
            results.append(self.scan_once(fetch_batch(), observed_at_ms=observed_at_ms))
            cycle += 1
            if max_cycles is not None and cycle >= max_cycles:
                break
            self._sleep(interval_seconds)
        return results

    def _calculate_opportunities(self, batch: MarketDataBatch, *, observed_at_ms: int) -> list[object]:
        chain = build_option_chain(batch.instruments)
        opportunities: list[object] = _calculate_cross_exchange_put_call_parity(batch)

        for pair in chain.complete_pairs():
            assert pair.call is not None
            assert pair.put is not None
            call_quote = batch.quotes_by_instrument_key.get(pair.call.instrument_key)
            put_quote = batch.quotes_by_instrument_key.get(pair.put.instrument_key)
            hedge_quote = batch.hedge_quotes_by_underlying.get((pair.exchange, pair.underlying_id))
            if call_quote is None or put_quote is None or hedge_quote is None:
                continue

            contract_type = pair.call.contract_type

            market_state = (batch.perpetual_states_by_instrument_key or {}).get(hedge_quote.instrument_key)
            basis = calculate_implied_futures_basis(
                pair,
                call_quote,
                put_quote,
                hedge_quote,
                actual_market_state=market_state,
                contract_type=contract_type,
            )
            if basis is not None and _has_executable_hedge_legs(basis):
                opportunities.append(basis)

        for expiry in chain.expiries.values():
            hedge_quote_for_underlying = batch.hedge_quotes_by_underlying.get(
                (expiry.exchange, expiry.underlying_id)
            )
            hedge_price = (
                hedge_quote_for_underlying.best_ask_price if hedge_quote_for_underlying else None
            )
            contract_type = _expiry_contract_type(expiry)
            opportunities.extend(
                calculate_box_spreads(
                    expiry,
                    batch.quotes_by_instrument_key,
                    now_ms=observed_at_ms,
                    contract_type=contract_type,
                    hedge_price=hedge_price,
                )
            )

        return opportunities

    def _monitor_candidate(
        self,
        opportunity: object,
        *,
        batch: MarketDataBatch,
        observed_at_ms: int,
    ) -> MonitoredOpportunity:
        adjustments = apply_opportunity_adjustments(
            opportunity,
            fee_rate=self._config.fee_rate,
            capital_requirement_rate=self._config.capital_requirement_rate,
            funding_holding_hours=self._config.funding_holding_hours,
            funding_interval_hours=self._config.funding_interval_hours,
            now_ms=observed_at_ms,
        )
        opportunity_type = _opportunity_type(opportunity)
        execution_diagnostic = None
        if self._config.execution_diagnostic_config is not None:
            execution_diagnostic = diagnose_execution(
                opportunity,
                batch,
                self._config.execution_diagnostic_config,
                observed_at_ms=observed_at_ms,
                fee_rate=self._config.fee_rate,
                taker_fee_rates_by_exchange_market=self._config.taker_fee_rates_by_exchange_market,
                funding_holding_hours=self._config.funding_holding_hours,
                funding_interval_hours=self._config.funding_interval_hours,
            )
        strike = _optional_str(getattr(opportunity, "strike", None))
        lower_strike = _optional_str(getattr(opportunity, "lower_strike", None))
        upper_strike = _optional_str(getattr(opportunity, "upper_strike", None))
        strike_label = strike or f"{lower_strike}-{upper_strike}"
        opportunity_id = _opportunity_id(opportunity, opportunity_type, strike_label)

        return MonitoredOpportunity(
            opportunity_id=opportunity_id,
            name=opportunity_id,
            opportunity_type=opportunity_type,
            exchange=str(getattr(opportunity, "exchange")),
            underlying_id=str(getattr(opportunity, "underlying_id")),
            expiry_time_ms=int(getattr(opportunity, "expiry_time_ms")),
            strike=strike,
            lower_strike=lower_strike,
            upper_strike=upper_strike,
            direction=str(getattr(opportunity, "direction")),
            gross_profit=str(getattr(opportunity, "gross_profit")),
            net_profit=adjustments.net_profit,
            annualized_net_return=adjustments.annualized_net_return
            or _optional_str(getattr(opportunity, "annualized_return", None)),
            total_slippage=adjustments.total_slippage,
            capital_required=adjustments.capital_required,
            is_executable=adjustments.is_executable,
            risk_tags=_merged_risk_tags(getattr(opportunity, "risk_tags", []), adjustments.risk_tags),
            pcp_execution_mode=_pcp_execution_mode(opportunity, opportunity_type),
            execution_diagnostic=execution_diagnostic,
            opportunity=opportunity,
            adjustments=adjustments,
        )

    def _select_alert_candidates(self, displayed: list[MonitoredOpportunity]) -> list[MonitoredOpportunity]:
        if self._config.alert_rule is None:
            return []
        suppressed = self._alerted_opportunity_ids if self._config.alert_once_per_opportunity else set()
        return select_alert_candidates(displayed, self._config.alert_rule, suppressed_opportunity_ids=suppressed)

    def _send_alerts(self, candidates: list[MonitoredOpportunity], *, sent_at_ms: int) -> list[object]:
        results: list[object] = []
        for candidate in candidates:
            for alerter in self._alerters:
                results.append(alerter.send_opportunity_alert(candidate, sent_at_ms=sent_at_ms))
            if self._config.alert_once_per_opportunity:
                self._alerted_opportunity_ids.add(candidate.opportunity_id)
        return results


def _opportunity_type(opportunity: object) -> str:
    class_name = opportunity.__class__.__name__
    if class_name == "PutCallParityOpportunity":
        return "put_call_parity"
    if class_name == "BoxSpreadOpportunity":
        return "box_spread"
    if class_name == "ImpliedFuturesBasisOpportunity":
        return "implied_futures_basis"
    raise ValueError(f"unsupported opportunity type: {class_name}")


PcpGroupKey = tuple[str, int, str]


def _calculate_cross_exchange_put_call_parity(batch: MarketDataBatch) -> list[object]:
    groups: dict[PcpGroupKey, dict[str, list[Instrument]]] = {}
    for instrument in batch.instruments:
        if not _is_pcp_option(instrument):
            continue
        assert instrument.underlying_id is not None
        assert instrument.expiry_time_ms is not None
        assert instrument.strike is not None
        assert instrument.option_type is not None
        key = (instrument.underlying_id, instrument.expiry_time_ms, instrument.strike)
        side = "calls" if instrument.option_type == "call" else "puts"
        groups.setdefault(key, {"calls": [], "puts": []})[side].append(instrument)

    hedges_by_underlying: dict[str, list[ExecutableQuote]] = {}
    for (_, underlying_id), hedge_quote in batch.hedge_quotes_by_underlying.items():
        hedges_by_underlying.setdefault(underlying_id, []).append(hedge_quote)

    opportunities: list[object] = []
    for (underlying_id, expiry_time_ms, strike), group in groups.items():
        candidates: list[object] = []
        for call in group["calls"]:
            call_quote = batch.quotes_by_instrument_key.get(call.instrument_key)
            if call_quote is None:
                continue
            for put in group["puts"]:
                if call.contract_type != put.contract_type:
                    continue
                put_quote = batch.quotes_by_instrument_key.get(put.instrument_key)
                if put_quote is None:
                    continue
                for hedge_quote in hedges_by_underlying.get(underlying_id, []):
                    pair = OptionPair(
                        exchange=_pcp_exchange(call, put, hedge_quote),
                        underlying_id=underlying_id,
                        expiry_time_ms=expiry_time_ms,
                        strike=strike,
                        call=call,
                        put=put,
                    )
                    opportunity = calculate_put_call_parity(
                        pair,
                        call_quote,
                        put_quote,
                        hedge_quote,
                        contract_type=call.contract_type,
                    )
                    if opportunity is None or not _has_executable_hedge_legs(opportunity):
                        continue
                    if _is_cross_exchange(call, put, hedge_quote):
                        opportunity = _with_risk_tag(opportunity, "cross_exchange_execution")
                    candidates.append(opportunity)
        opportunities.extend(_best_pcp_candidates_by_direction(candidates))
    return opportunities


def _is_pcp_option(instrument: Instrument) -> bool:
    return (
        instrument.market_type == "option"
        and instrument.status == "trading"
        and instrument.underlying_id is not None
        and instrument.expiry_time_ms is not None
        and instrument.strike is not None
        and instrument.option_type in {"call", "put"}
    )


def _pcp_exchange(call: Instrument, put: Instrument, hedge_quote: ExecutableQuote) -> str:
    return call.exchange if not _is_cross_exchange(call, put, hedge_quote) else "cross_exchange"


def _is_cross_exchange(call: Instrument, put: Instrument, hedge_quote: ExecutableQuote) -> bool:
    return len({call.exchange, put.exchange, hedge_quote.exchange}) > 1


def _with_risk_tag(opportunity: object, tag: str) -> object:
    risk_tags = list(getattr(opportunity, "risk_tags", None) or [])
    if tag not in risk_tags:
        risk_tags.append(tag)
    return replace(opportunity, risk_tags=risk_tags)


def _best_pcp_candidates_by_direction(candidates: list[object]) -> list[object]:
    best_by_direction: dict[str, object] = {}
    for candidate in candidates:
        key = str(getattr(candidate, "direction"))
        current = best_by_direction.get(key)
        candidate_profit = Decimal(str(getattr(candidate, "gross_profit")))
        current_profit = Decimal(str(getattr(current, "gross_profit"))) if current is not None else None
        if current_profit is None or candidate_profit > current_profit:
            best_by_direction[key] = candidate
    return list(best_by_direction.values())


def _opportunity_id(opportunity: object, opportunity_type: str, strike_label: str) -> str:
    base = (
        f"{getattr(opportunity, 'exchange')}:{opportunity_type}:{getattr(opportunity, 'underlying_id')}:"
        f"{getattr(opportunity, 'expiry_time_ms')}:{strike_label}:{getattr(opportunity, 'direction')}"
    )
    if opportunity_type != "put_call_parity" or getattr(opportunity, "exchange", None) != "cross_exchange":
        return base
    leg_keys = ":".join(str(getattr(leg, "instrument_key")) for leg in getattr(opportunity, "legs", []))
    return f"{base}:{leg_keys}"


def _pcp_execution_mode(opportunity: object, opportunity_type: str) -> PcpExecutionMode | None:
    if opportunity_type != "put_call_parity":
        return None
    return _raw_pcp_execution_mode(opportunity)  # type: ignore[return-value]


def _raw_pcp_execution_mode(opportunity: object) -> str:
    return "cross_exchange" if getattr(opportunity, "exchange", None) == "cross_exchange" else "same_exchange"


def _has_executable_hedge_legs(opportunity: object) -> bool:
    for leg in getattr(opportunity, "legs", []):
        parts = str(getattr(leg, "instrument_key", "")).split(":", 2)
        market_type = parts[1] if len(parts) > 1 else ""
        if market_type == "spot" and getattr(leg, "side", None) == "sell":
            return False
    return True


def _optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _merged_risk_tags(*tag_lists: object) -> list[str]:
    tags: list[str] = []
    for tag_list in tag_lists:
        for tag in tag_list or []:
            text = str(tag)
            if text not in tags:
                tags.append(text)
    return tags


def _expiry_contract_type(expiry: object) -> str:
    """Extract contract_type from any complete pair in an OptionExpiry."""
    for strike in getattr(expiry, "strikes", []):
        pair = getattr(expiry, "pairs_by_strike", {}).get(strike)
        if pair is not None and getattr(pair, "call", None) is not None:
            return str(getattr(pair.call, "contract_type", "linear"))
        if pair is not None and getattr(pair, "put", None) is not None:
            return str(getattr(pair.put, "contract_type", "linear"))
    return "linear"
