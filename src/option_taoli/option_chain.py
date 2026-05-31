from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from option_taoli.models import Instrument


ExpiryKey = tuple[str, str, int]
StrikeKey = tuple[str, str, int, str]


@dataclass(frozen=True)
class OptionPair:
    exchange: str
    underlying_id: str
    expiry_time_ms: int
    strike: str
    call: Instrument | None = None
    put: Instrument | None = None

    @property
    def is_complete(self) -> bool:
        return self.call is not None and self.put is not None


@dataclass(frozen=True)
class OptionExpiry:
    exchange: str
    underlying_id: str
    expiry_time_ms: int
    strikes: list[str]
    pairs_by_strike: dict[str, OptionPair]

    def complete_pairs(self) -> list[OptionPair]:
        return [self.pairs_by_strike[strike] for strike in self.strikes if self.pairs_by_strike[strike].is_complete]


@dataclass(frozen=True)
class OptionChain:
    expiries: dict[ExpiryKey, OptionExpiry]

    def complete_pairs(self) -> list[OptionPair]:
        pairs: list[OptionPair] = []
        for key in sorted(self.expiries):
            pairs.extend(self.expiries[key].complete_pairs())
        return pairs


def build_option_chain(
    instruments: Iterable[Instrument],
    *,
    include_non_trading: bool = False,
) -> OptionChain:
    pairs: dict[StrikeKey, OptionPair] = {}

    for instrument in instruments:
        if not _is_eligible_option(instrument, include_non_trading=include_non_trading):
            continue

        assert instrument.underlying_id is not None
        assert instrument.expiry_time_ms is not None
        assert instrument.strike is not None
        assert instrument.option_type is not None

        key = (instrument.exchange, instrument.underlying_id, instrument.expiry_time_ms, instrument.strike)
        current = pairs.get(key) or OptionPair(
            exchange=instrument.exchange,
            underlying_id=instrument.underlying_id,
            expiry_time_ms=instrument.expiry_time_ms,
            strike=instrument.strike,
        )

        if instrument.option_type == "call":
            current = OptionPair(
                exchange=current.exchange,
                underlying_id=current.underlying_id,
                expiry_time_ms=current.expiry_time_ms,
                strike=current.strike,
                call=instrument,
                put=current.put,
            )
        else:
            current = OptionPair(
                exchange=current.exchange,
                underlying_id=current.underlying_id,
                expiry_time_ms=current.expiry_time_ms,
                strike=current.strike,
                call=current.call,
                put=instrument,
            )
        pairs[key] = current

    pairs_by_expiry: dict[ExpiryKey, dict[str, OptionPair]] = {}
    for (exchange, underlying_id, expiry_time_ms, strike), pair in pairs.items():
        expiry_key = (exchange, underlying_id, expiry_time_ms)
        pairs_by_expiry.setdefault(expiry_key, {})[strike] = pair

    expiries: dict[ExpiryKey, OptionExpiry] = {}
    for (exchange, underlying_id, expiry_time_ms), expiry_pairs in pairs_by_expiry.items():
        strikes = sorted(expiry_pairs, key=Decimal)
        expiries[(exchange, underlying_id, expiry_time_ms)] = OptionExpiry(
            exchange=exchange,
            underlying_id=underlying_id,
            expiry_time_ms=expiry_time_ms,
            strikes=strikes,
            pairs_by_strike={strike: expiry_pairs[strike] for strike in strikes},
        )

    return OptionChain(expiries={key: expiries[key] for key in sorted(expiries)})


def _is_eligible_option(instrument: Instrument, *, include_non_trading: bool) -> bool:
    if instrument.market_type != "option":
        return False
    if not include_non_trading and instrument.status != "trading":
        return False
    return (
        instrument.underlying_id is not None
        and instrument.expiry_time_ms is not None
        and instrument.strike is not None
        and instrument.option_type in {"call", "put"}
    )
