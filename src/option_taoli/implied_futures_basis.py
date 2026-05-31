from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from option_taoli.market_depth import ExecutableQuote
from option_taoli.option_chain import OptionPair
from option_taoli.perpetual_market import PerpetualMarketState
from option_taoli.put_call_parity import ArbitrageLeg


BasisDirection = Literal["buy_implied_sell_actual", "sell_implied_buy_actual"]


@dataclass(frozen=True)
class ImpliedFuturesBasisOpportunity:
    exchange: str
    underlying_id: str
    expiry_time_ms: int
    strike: str
    direction: BasisDirection
    implied_futures_price: str
    actual_futures_price: str
    basis: str
    gross_profit: str
    funding_rate_current: str | None
    funding_rate_8h: str | None
    funding_rate_annualized: str | None
    risk_tags: list[str]
    legs: list[ArbitrageLeg]
    explanation: str


def calculate_implied_futures_basis(
    option_pair: OptionPair,
    call_quote: ExecutableQuote,
    put_quote: ExecutableQuote,
    actual_quote: ExecutableQuote,
    *,
    actual_market_state: PerpetualMarketState | None = None,
    discount_factor: str = "1",
    size: str = "1",
) -> ImpliedFuturesBasisOpportunity | None:
    _validate_inputs(option_pair, call_quote, put_quote, actual_quote, actual_market_state)

    strike = Decimal(option_pair.strike)
    discounted_strike = strike * Decimal(discount_factor)
    trade_size = _positive_decimal(size, "size")

    implied_ask = Decimal(call_quote.best_ask_price) - Decimal(put_quote.best_bid_price) + discounted_strike
    buy_implied_profit = Decimal(actual_quote.best_bid_price) - implied_ask

    implied_bid = Decimal(call_quote.best_bid_price) - Decimal(put_quote.best_ask_price) + discounted_strike
    sell_implied_profit = implied_bid - Decimal(actual_quote.best_ask_price)

    if buy_implied_profit <= 0 and sell_implied_profit <= 0:
        return None

    risk_tags = _risk_tags(actual_quote, actual_market_state)
    if buy_implied_profit >= sell_implied_profit:
        return ImpliedFuturesBasisOpportunity(
            exchange=option_pair.exchange,
            underlying_id=option_pair.underlying_id,
            expiry_time_ms=option_pair.expiry_time_ms,
            strike=option_pair.strike,
            direction="buy_implied_sell_actual",
            implied_futures_price=str(implied_ask),
            actual_futures_price=actual_quote.best_bid_price,
            basis=str(buy_implied_profit),
            gross_profit=str(buy_implied_profit * trade_size),
            funding_rate_current=None if actual_market_state is None else actual_market_state.funding_rate_current,
            funding_rate_8h=None if actual_market_state is None else actual_market_state.funding_rate_8h,
            funding_rate_annualized=None if actual_market_state is None else actual_market_state.funding_rate_annualized,
            risk_tags=risk_tags,
            legs=[
                ArbitrageLeg(call_quote.instrument_key, "buy", call_quote.best_ask_price, str(trade_size), "call"),
                ArbitrageLeg(put_quote.instrument_key, "sell", put_quote.best_bid_price, str(trade_size), "put"),
                ArbitrageLeg(
                    actual_quote.instrument_key,
                    "sell",
                    actual_quote.best_bid_price,
                    str(trade_size),
                    "actual_future",
                ),
            ],
            explanation="Implied futures ask is below actual futures bid; buy implied future and sell actual future.",
        )

    return ImpliedFuturesBasisOpportunity(
        exchange=option_pair.exchange,
        underlying_id=option_pair.underlying_id,
        expiry_time_ms=option_pair.expiry_time_ms,
        strike=option_pair.strike,
        direction="sell_implied_buy_actual",
        implied_futures_price=str(implied_bid),
        actual_futures_price=actual_quote.best_ask_price,
        basis=str(sell_implied_profit),
        gross_profit=str(sell_implied_profit * trade_size),
        funding_rate_current=None if actual_market_state is None else actual_market_state.funding_rate_current,
        funding_rate_8h=None if actual_market_state is None else actual_market_state.funding_rate_8h,
        funding_rate_annualized=None if actual_market_state is None else actual_market_state.funding_rate_annualized,
        risk_tags=risk_tags,
        legs=[
            ArbitrageLeg(call_quote.instrument_key, "sell", call_quote.best_bid_price, str(trade_size), "call"),
            ArbitrageLeg(put_quote.instrument_key, "buy", put_quote.best_ask_price, str(trade_size), "put"),
            ArbitrageLeg(
                actual_quote.instrument_key,
                "buy",
                actual_quote.best_ask_price,
                str(trade_size),
                "actual_future",
            ),
        ],
        explanation="Implied futures bid is above actual futures ask; sell implied future and buy actual future.",
    )


def _validate_inputs(
    option_pair: OptionPair,
    call_quote: ExecutableQuote,
    put_quote: ExecutableQuote,
    actual_quote: ExecutableQuote,
    actual_market_state: PerpetualMarketState | None,
) -> None:
    if option_pair.call is None or option_pair.put is None:
        raise ValueError("option pair must include call and put")
    if call_quote.instrument_key != option_pair.call.instrument_key:
        raise ValueError("call quote does not match call instrument")
    if put_quote.instrument_key != option_pair.put.instrument_key:
        raise ValueError("put quote does not match put instrument")
    if actual_quote.market_type not in {"perpetual", "future"}:
        raise ValueError("actual quote market_type must be perpetual or future")
    if actual_market_state is not None and actual_market_state.instrument_key != actual_quote.instrument_key:
        raise ValueError("actual market state does not match actual quote")


def _risk_tags(
    actual_quote: ExecutableQuote,
    actual_market_state: PerpetualMarketState | None,
) -> list[str]:
    tags: list[str] = []
    if actual_quote.market_type == "perpetual":
        if actual_market_state and (
            actual_market_state.funding_rate_current is not None or actual_market_state.funding_rate_8h is not None
        ):
            tags.append("funding_rate_present")
        else:
            tags.append("missing_funding_rate")
    else:
        tags.append("no_funding_rate")
    return tags


def _positive_decimal(value: str, field_name: str) -> Decimal:
    decimal = Decimal(value)
    if decimal <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return decimal
