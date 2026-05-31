from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations
from typing import Literal

from option_taoli.market_depth import ExecutableQuote
from option_taoli.option_chain import OptionExpiry, OptionPair
from option_taoli.put_call_parity import ArbitrageLeg


BoxDirection = Literal["long_box", "short_box"]

MILLISECONDS_PER_YEAR = Decimal("31536000000")


@dataclass(frozen=True)
class BoxSpreadOpportunity:
    exchange: str
    underlying_id: str
    expiry_time_ms: int
    lower_strike: str
    upper_strike: str
    direction: BoxDirection
    fixed_cashflow: str
    entry_value: str
    gross_profit: str
    annualized_return: str | None
    legs: list[ArbitrageLeg]
    explanation: str


def calculate_box_spreads(
    expiry: OptionExpiry,
    quotes_by_instrument_key: dict[str, ExecutableQuote],
    *,
    now_ms: int | None = None,
    size: str = "1",
) -> list[BoxSpreadOpportunity]:
    trade_size = _positive_decimal(size, "size")
    opportunities: list[BoxSpreadOpportunity] = []

    for lower_strike, upper_strike in combinations(expiry.strikes, 2):
        lower_pair = expiry.pairs_by_strike[lower_strike]
        upper_pair = expiry.pairs_by_strike[upper_strike]
        if not lower_pair.is_complete or not upper_pair.is_complete:
            continue

        quotes = _quotes_for_box(lower_pair, upper_pair, quotes_by_instrument_key)
        if quotes is None:
            continue

        fixed_cashflow = Decimal(upper_strike) - Decimal(lower_strike)
        if fixed_cashflow <= 0:
            continue

        long_box = _calculate_long_box(
            expiry=expiry,
            lower_pair=lower_pair,
            upper_pair=upper_pair,
            quotes=quotes,
            fixed_cashflow=fixed_cashflow,
            trade_size=trade_size,
            now_ms=now_ms,
        )
        if long_box is not None:
            opportunities.append(long_box)

        short_box = _calculate_short_box(
            expiry=expiry,
            lower_pair=lower_pair,
            upper_pair=upper_pair,
            quotes=quotes,
            fixed_cashflow=fixed_cashflow,
            trade_size=trade_size,
            now_ms=now_ms,
        )
        if short_box is not None:
            opportunities.append(short_box)

    return sorted(opportunities, key=lambda opportunity: Decimal(opportunity.gross_profit), reverse=True)


def _calculate_long_box(
    *,
    expiry: OptionExpiry,
    lower_pair: OptionPair,
    upper_pair: OptionPair,
    quotes: dict[str, ExecutableQuote],
    fixed_cashflow: Decimal,
    trade_size: Decimal,
    now_ms: int | None,
) -> BoxSpreadOpportunity | None:
    lower_call = quotes["lower_call"]
    lower_put = quotes["lower_put"]
    upper_call = quotes["upper_call"]
    upper_put = quotes["upper_put"]

    entry_cost = (
        Decimal(lower_call.best_ask_price)
        - Decimal(upper_call.best_bid_price)
        + Decimal(upper_put.best_ask_price)
        - Decimal(lower_put.best_bid_price)
    )
    profit = (fixed_cashflow - entry_cost) * trade_size
    if profit <= 0:
        return None

    return BoxSpreadOpportunity(
        exchange=expiry.exchange,
        underlying_id=expiry.underlying_id,
        expiry_time_ms=expiry.expiry_time_ms,
        lower_strike=lower_pair.strike,
        upper_strike=upper_pair.strike,
        direction="long_box",
        fixed_cashflow=str(fixed_cashflow * trade_size),
        entry_value=str(entry_cost * trade_size),
        gross_profit=str(profit),
        annualized_return=_annualized_return(profit, entry_cost * trade_size, expiry.expiry_time_ms, now_ms),
        legs=[
            ArbitrageLeg(lower_call.instrument_key, "buy", lower_call.best_ask_price, str(trade_size), "lower_call"),
            ArbitrageLeg(upper_call.instrument_key, "sell", upper_call.best_bid_price, str(trade_size), "upper_call"),
            ArbitrageLeg(upper_put.instrument_key, "buy", upper_put.best_ask_price, str(trade_size), "upper_put"),
            ArbitrageLeg(lower_put.instrument_key, "sell", lower_put.best_bid_price, str(trade_size), "lower_put"),
        ],
        explanation="Long box: fixed expiry cashflow exceeds entry cost.",
    )


def _calculate_short_box(
    *,
    expiry: OptionExpiry,
    lower_pair: OptionPair,
    upper_pair: OptionPair,
    quotes: dict[str, ExecutableQuote],
    fixed_cashflow: Decimal,
    trade_size: Decimal,
    now_ms: int | None,
) -> BoxSpreadOpportunity | None:
    lower_call = quotes["lower_call"]
    lower_put = quotes["lower_put"]
    upper_call = quotes["upper_call"]
    upper_put = quotes["upper_put"]

    entry_credit = (
        Decimal(lower_call.best_bid_price)
        - Decimal(upper_call.best_ask_price)
        + Decimal(upper_put.best_bid_price)
        - Decimal(lower_put.best_ask_price)
    )
    profit = (entry_credit - fixed_cashflow) * trade_size
    if profit <= 0:
        return None

    return BoxSpreadOpportunity(
        exchange=expiry.exchange,
        underlying_id=expiry.underlying_id,
        expiry_time_ms=expiry.expiry_time_ms,
        lower_strike=lower_pair.strike,
        upper_strike=upper_pair.strike,
        direction="short_box",
        fixed_cashflow=str(fixed_cashflow * trade_size),
        entry_value=str(entry_credit * trade_size),
        gross_profit=str(profit),
        annualized_return=_annualized_return(profit, fixed_cashflow * trade_size, expiry.expiry_time_ms, now_ms),
        legs=[
            ArbitrageLeg(lower_call.instrument_key, "sell", lower_call.best_bid_price, str(trade_size), "lower_call"),
            ArbitrageLeg(upper_call.instrument_key, "buy", upper_call.best_ask_price, str(trade_size), "upper_call"),
            ArbitrageLeg(upper_put.instrument_key, "sell", upper_put.best_bid_price, str(trade_size), "upper_put"),
            ArbitrageLeg(lower_put.instrument_key, "buy", lower_put.best_ask_price, str(trade_size), "lower_put"),
        ],
        explanation="Short box: entry credit exceeds fixed expiry cashflow.",
    )


def _quotes_for_box(
    lower_pair: OptionPair,
    upper_pair: OptionPair,
    quotes_by_instrument_key: dict[str, ExecutableQuote],
) -> dict[str, ExecutableQuote] | None:
    assert lower_pair.call is not None
    assert lower_pair.put is not None
    assert upper_pair.call is not None
    assert upper_pair.put is not None

    quote_keys = {
        "lower_call": lower_pair.call.instrument_key,
        "lower_put": lower_pair.put.instrument_key,
        "upper_call": upper_pair.call.instrument_key,
        "upper_put": upper_pair.put.instrument_key,
    }
    if any(instrument_key not in quotes_by_instrument_key for instrument_key in quote_keys.values()):
        return None
    return {role: quotes_by_instrument_key[instrument_key] for role, instrument_key in quote_keys.items()}


def _annualized_return(
    profit: Decimal,
    capital_base: Decimal,
    expiry_time_ms: int,
    now_ms: int | None,
) -> str | None:
    if now_ms is None:
        return None
    if capital_base <= 0:
        return None
    time_to_expiry_ms = Decimal(expiry_time_ms - now_ms)
    if time_to_expiry_ms <= 0:
        return None
    return str((profit / capital_base) * (MILLISECONDS_PER_YEAR / time_to_expiry_ms))


def _positive_decimal(value: str, field_name: str) -> Decimal:
    decimal = Decimal(value)
    if decimal <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return decimal
