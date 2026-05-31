from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from option_taoli.models import MarketType, OrderBook, OrderBookLevel, Quote


Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class ExecutableQuote:
    instrument_key: str
    exchange: str
    market_type: MarketType
    instrument_id: str
    best_bid_price: str
    best_ask_price: str
    best_bid_size: str
    best_ask_size: str
    mid_price: str
    spread: str
    received_at_ms: int
    normalized_at_ms: int
    has_executable_quote: bool = True


@dataclass(frozen=True)
class StandardizedOrderBook:
    instrument_key: str
    exchange: str
    market_type: MarketType
    instrument_id: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    depth: int
    best_bid_price: str
    best_ask_price: str
    best_bid_size: str
    best_ask_size: str
    mid_price: str
    spread: str
    received_at_ms: int
    normalized_at_ms: int
    has_depth: bool = True


@dataclass(frozen=True)
class DepthFill:
    side: Side
    requested_size: str
    filled_size: str
    notional: str
    average_price: str | None
    worst_price: str | None
    fully_filled: bool


def standardize_quote(quote: Quote) -> ExecutableQuote:
    bid_price = _required_decimal(quote.bid_price, "bid price")
    ask_price = _required_decimal(quote.ask_price, "ask price")
    bid_size = _required_decimal(quote.bid_size, "bid size")
    ask_size = _required_decimal(quote.ask_size, "ask size")

    if bid_size <= 0:
        raise ValueError("bid size must be greater than zero")
    if ask_size <= 0:
        raise ValueError("ask size must be greater than zero")
    _validate_bid_ask(bid_price, ask_price)

    return ExecutableQuote(
        instrument_key=quote.instrument_key,
        exchange=quote.exchange,
        market_type=quote.market_type,
        instrument_id=quote.instrument_id,
        best_bid_price=str(bid_price),
        best_ask_price=str(ask_price),
        best_bid_size=str(bid_size),
        best_ask_size=str(ask_size),
        mid_price=str((bid_price + ask_price) / Decimal("2")),
        spread=str(ask_price - bid_price),
        received_at_ms=quote.received_at_ms,
        normalized_at_ms=quote.normalized_at_ms,
    )


def standardize_order_book(order_book: OrderBook) -> StandardizedOrderBook:
    bids = _standardize_levels(order_book.bids, side="bid")
    asks = _standardize_levels(order_book.asks, side="ask")
    if not bids or not asks:
        raise ValueError("order book must contain at least one bid and one ask")

    bid_price = Decimal(bids[0].price)
    ask_price = Decimal(asks[0].price)
    _validate_bid_ask(bid_price, ask_price)

    return StandardizedOrderBook(
        instrument_key=order_book.instrument_key,
        exchange=order_book.exchange,
        market_type=order_book.market_type,
        instrument_id=order_book.instrument_id,
        bids=bids,
        asks=asks,
        depth=min(len(bids), len(asks)),
        best_bid_price=bids[0].price,
        best_ask_price=asks[0].price,
        best_bid_size=bids[0].size,
        best_ask_size=asks[0].size,
        mid_price=str((bid_price + ask_price) / Decimal("2")),
        spread=str(ask_price - bid_price),
        received_at_ms=order_book.received_at_ms,
        normalized_at_ms=order_book.normalized_at_ms,
    )


def estimate_fill(book: StandardizedOrderBook, *, side: Side, quantity: str) -> DepthFill:
    requested_size = _required_decimal(quantity, "quantity")
    if requested_size <= 0:
        raise ValueError("quantity must be greater than zero")

    remaining = requested_size
    filled = Decimal("0")
    notional = Decimal("0")
    worst_price: Decimal | None = None
    levels = book.asks if side == "buy" else book.bids

    for level in levels:
        if remaining <= 0:
            break
        level_price = Decimal(level.price)
        level_size = Decimal(level.size)
        take_size = min(remaining, level_size)
        filled += take_size
        notional += take_size * level_price
        remaining -= take_size
        worst_price = level_price

    average_price = None if filled == 0 else str(notional / filled)
    return DepthFill(
        side=side,
        requested_size=str(requested_size),
        filled_size=str(filled),
        notional=str(notional),
        average_price=average_price,
        worst_price=None if worst_price is None else str(worst_price),
        fully_filled=filled == requested_size,
    )


def _standardize_levels(levels: list[OrderBookLevel], *, side: Literal["bid", "ask"]) -> list[OrderBookLevel]:
    normalized: list[OrderBookLevel] = []
    for level in levels:
        price = _required_decimal(level.price, "level price")
        size = _required_decimal(level.size, "level size")
        if price <= 0:
            raise ValueError("level price must be greater than zero")
        if size <= 0:
            raise ValueError("level size must be greater than zero")
        normalized.append(OrderBookLevel(price=str(price), size=str(size)))

    return sorted(normalized, key=lambda level: Decimal(level.price), reverse=side == "bid")


def _required_decimal(value: str | None, field_name: str) -> Decimal:
    if value is None:
        raise ValueError(f"{field_name} is required")
    return Decimal(value)


def _validate_bid_ask(bid_price: Decimal, ask_price: Decimal) -> None:
    if bid_price <= 0:
        raise ValueError("bid price must be greater than zero")
    if ask_price <= 0:
        raise ValueError("ask price must be greater than zero")
    if bid_price > ask_price:
        raise ValueError("bid price is greater than ask price")
