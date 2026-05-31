from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from option_taoli.models import FundingRate, Quote


@dataclass(frozen=True)
class PerpetualMarketState:
    instrument_key: str
    exchange: str
    instrument_id: str
    perpetual_price: str
    mark_price: str
    index_price: str
    mark_index_basis: str
    mark_index_basis_rate: str
    received_at_ms: int
    normalized_at_ms: int
    price_source_updated_at_ms: int | None = None
    funding_rate_current: str | None = None
    funding_rate_8h: str | None = None
    funding_rate_annualized: str | None = None
    funding_time_ms: int | None = None
    next_funding_time_ms: int | None = None
    funding_interval_hours: str | None = None
    interest_rate: str | None = None
    premium: str | None = None
    funding_source_updated_at_ms: int | None = None


def standardize_perpetual_state(quote: Quote, funding_rate: FundingRate | None = None) -> PerpetualMarketState:
    if quote.market_type != "perpetual":
        raise ValueError("quote market_type must be perpetual")
    if funding_rate is not None and funding_rate.instrument_key != quote.instrument_key:
        raise ValueError("funding instrument_key does not match quote")

    perpetual_price = _first_decimal(
        ("mid price", quote.mid_price),
        ("last price", quote.last_price),
        ("mark price", quote.mark_price),
    )
    mark_price = _required_positive_decimal(quote.mark_price, "mark price")
    index_price = _required_positive_decimal(quote.index_price, "index price")
    basis = mark_price - index_price

    funding_rate_current = _optional_decimal_string(None if funding_rate is None else funding_rate.funding_rate_current)
    funding_interval_hours = None if funding_rate is None else funding_rate.funding_interval_hours

    return PerpetualMarketState(
        instrument_key=quote.instrument_key,
        exchange=quote.exchange,
        instrument_id=quote.instrument_id,
        perpetual_price=str(perpetual_price),
        mark_price=str(mark_price),
        index_price=str(index_price),
        mark_index_basis=str(basis),
        mark_index_basis_rate=str(basis / index_price),
        received_at_ms=quote.received_at_ms,
        normalized_at_ms=quote.normalized_at_ms,
        price_source_updated_at_ms=quote.source_updated_at_ms,
        funding_rate_current=funding_rate_current,
        funding_rate_8h=None if funding_rate is None else _optional_decimal_string(funding_rate.funding_rate_8h),
        funding_rate_annualized=_annualized_funding_rate(funding_rate_current, funding_interval_hours),
        funding_time_ms=None if funding_rate is None else funding_rate.funding_time_ms,
        next_funding_time_ms=None if funding_rate is None else funding_rate.next_funding_time_ms,
        funding_interval_hours=funding_interval_hours,
        interest_rate=None if funding_rate is None else _optional_decimal_string(funding_rate.interest_rate),
        premium=None if funding_rate is None else _optional_decimal_string(funding_rate.premium),
        funding_source_updated_at_ms=None if funding_rate is None else funding_rate.source_updated_at_ms,
    )


def _first_decimal(*candidates: tuple[str, str | None]) -> Decimal:
    for field_name, value in candidates:
        if value is not None:
            return _required_positive_decimal(value, field_name)
    raise ValueError("perpetual price is required")


def _required_positive_decimal(value: str | None, field_name: str) -> Decimal:
    if value is None:
        raise ValueError(f"{field_name} is required")
    decimal = Decimal(value)
    if decimal <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return decimal


def _optional_decimal_string(value: str | None) -> str | None:
    if value is None:
        return None
    return str(Decimal(value))


def _annualized_funding_rate(funding_rate_current: str | None, funding_interval_hours: str | None) -> str | None:
    if funding_rate_current is None or funding_interval_hours is None:
        return None
    interval_hours = Decimal(funding_interval_hours)
    if interval_hours <= 0:
        raise ValueError("funding interval hours must be greater than zero")
    funding_rate = Decimal(funding_rate_current)
    return str(funding_rate * (Decimal("24") / interval_hours) * Decimal("365"))
