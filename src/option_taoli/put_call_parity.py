from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from option_taoli.market_depth import ExecutableQuote
from option_taoli.option_chain import OptionPair


ArbitrageDirection = Literal["long_synthetic_short_hedge", "short_synthetic_long_hedge"]
LegSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class ArbitrageLeg:
    instrument_key: str
    side: LegSide
    price: str
    size: str
    role: str


@dataclass(frozen=True)
class PutCallParityOpportunity:
    exchange: str
    underlying_id: str
    expiry_time_ms: int
    strike: str
    direction: ArbitrageDirection
    synthetic_forward_price: str
    hedge_price: str
    deviation: str
    gross_profit: str
    legs: list[ArbitrageLeg]
    explanation: str


def calculate_put_call_parity(
    option_pair: OptionPair,
    call_quote: ExecutableQuote,
    put_quote: ExecutableQuote,
    hedge_quote: ExecutableQuote,
    *,
    discount_factor: str = "1",
    size: str = "1",
) -> PutCallParityOpportunity | None:
    _validate_inputs(option_pair, call_quote, put_quote)

    strike = Decimal(option_pair.strike)
    discounted_strike = strike * Decimal(discount_factor)
    trade_size = _positive_decimal(size, "size")

    long_synthetic_price = Decimal(call_quote.best_ask_price) - Decimal(put_quote.best_bid_price) + discounted_strike
    long_synthetic_profit = Decimal(hedge_quote.best_bid_price) - long_synthetic_price

    short_synthetic_price = Decimal(call_quote.best_bid_price) - Decimal(put_quote.best_ask_price) + discounted_strike
    short_synthetic_profit = short_synthetic_price - Decimal(hedge_quote.best_ask_price)

    if long_synthetic_profit <= 0 and short_synthetic_profit <= 0:
        return None

    if long_synthetic_profit >= short_synthetic_profit:
        return PutCallParityOpportunity(
            exchange=option_pair.exchange,
            underlying_id=option_pair.underlying_id,
            expiry_time_ms=option_pair.expiry_time_ms,
            strike=option_pair.strike,
            direction="long_synthetic_short_hedge",
            synthetic_forward_price=str(long_synthetic_price),
            hedge_price=hedge_quote.best_bid_price,
            deviation=str(long_synthetic_profit),
            gross_profit=str(long_synthetic_profit * trade_size),
            legs=[
                ArbitrageLeg(call_quote.instrument_key, "buy", call_quote.best_ask_price, str(trade_size), "call"),
                ArbitrageLeg(put_quote.instrument_key, "sell", put_quote.best_bid_price, str(trade_size), "put"),
                ArbitrageLeg(hedge_quote.instrument_key, "sell", hedge_quote.best_bid_price, str(trade_size), "hedge"),
            ],
            explanation="C - P + K is below hedge bid; buy call, sell put, and sell hedge.",
        )

    return PutCallParityOpportunity(
        exchange=option_pair.exchange,
        underlying_id=option_pair.underlying_id,
        expiry_time_ms=option_pair.expiry_time_ms,
        strike=option_pair.strike,
        direction="short_synthetic_long_hedge",
        synthetic_forward_price=str(short_synthetic_price),
        hedge_price=hedge_quote.best_ask_price,
        deviation=str(short_synthetic_profit),
        gross_profit=str(short_synthetic_profit * trade_size),
        legs=[
            ArbitrageLeg(call_quote.instrument_key, "sell", call_quote.best_bid_price, str(trade_size), "call"),
            ArbitrageLeg(put_quote.instrument_key, "buy", put_quote.best_ask_price, str(trade_size), "put"),
            ArbitrageLeg(hedge_quote.instrument_key, "buy", hedge_quote.best_ask_price, str(trade_size), "hedge"),
        ],
        explanation="C - P + K is above hedge ask; sell call, buy put, and buy hedge.",
    )


def _validate_inputs(option_pair: OptionPair, call_quote: ExecutableQuote, put_quote: ExecutableQuote) -> None:
    if option_pair.call is None or option_pair.put is None:
        raise ValueError("option pair must include call and put")
    if call_quote.instrument_key != option_pair.call.instrument_key:
        raise ValueError("call quote does not match call instrument")
    if put_quote.instrument_key != option_pair.put.instrument_key:
        raise ValueError("put quote does not match put instrument")


def _positive_decimal(value: str, field_name: str) -> Decimal:
    decimal = Decimal(value)
    if decimal <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return decimal
