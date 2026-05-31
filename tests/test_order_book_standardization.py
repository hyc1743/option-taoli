import pytest

from option_taoli.market_depth import estimate_fill, standardize_order_book, standardize_quote
from option_taoli.models import OrderBook, OrderBookLevel, Quote


def test_standardizes_quote_bid_ask_mid_and_spread():
    quote = Quote(
        instrument_key="deribit:option:BTC-27JUN25-100000-C",
        exchange="deribit",
        market_type="option",
        instrument_id="BTC-27JUN25-100000-C",
        bid_price="10",
        ask_price="10.5",
        bid_size="2",
        ask_size="3",
        received_at_ms=1780210000000,
        normalized_at_ms=1780210000001,
    )

    executable_quote = standardize_quote(quote)

    assert executable_quote.instrument_key == quote.instrument_key
    assert executable_quote.best_bid_price == "10"
    assert executable_quote.best_ask_price == "10.5"
    assert executable_quote.best_bid_size == "2"
    assert executable_quote.best_ask_size == "3"
    assert executable_quote.mid_price == "10.25"
    assert executable_quote.spread == "0.5"
    assert executable_quote.has_executable_quote is True


def test_standardizes_order_book_sides_and_depth():
    order_book = OrderBook(
        instrument_key="binance:perpetual:BTCUSDT",
        exchange="binance",
        market_type="perpetual",
        instrument_id="BTCUSDT",
        bids=[OrderBookLevel(price="99", size="1"), OrderBookLevel(price="100", size="2")],
        asks=[OrderBookLevel(price="102", size="4"), OrderBookLevel(price="101", size="3")],
        depth=2,
        is_snapshot=True,
        received_at_ms=1780210000000,
        normalized_at_ms=1780210000001,
    )

    book = standardize_order_book(order_book)

    assert [level.price for level in book.bids] == ["100", "99"]
    assert [level.price for level in book.asks] == ["101", "102"]
    assert book.best_bid_price == "100"
    assert book.best_ask_price == "101"
    assert book.mid_price == "100.5"
    assert book.spread == "1"
    assert book.depth == 2
    assert book.has_depth is True


def test_estimates_buy_and_sell_fill_from_standardized_depth():
    order_book = OrderBook(
        instrument_key="okx:spot:BTC-USDT",
        exchange="okx",
        market_type="spot",
        instrument_id="BTC-USDT",
        bids=[OrderBookLevel(price="99", size="2"), OrderBookLevel(price="98", size="1")],
        asks=[OrderBookLevel(price="100", size="1"), OrderBookLevel(price="101", size="2")],
        depth=2,
        is_snapshot=True,
        received_at_ms=1780210000000,
        normalized_at_ms=1780210000001,
    )
    book = standardize_order_book(order_book)

    buy_fill = estimate_fill(book, side="buy", quantity="3")
    sell_fill = estimate_fill(book, side="sell", quantity="5")

    assert buy_fill.fully_filled is True
    assert buy_fill.filled_size == "3"
    assert buy_fill.notional == "302"
    assert buy_fill.worst_price == "101"
    assert sell_fill.fully_filled is False
    assert sell_fill.filled_size == "3"
    assert sell_fill.notional == "296"
    assert sell_fill.worst_price == "98"


def test_rejects_crossed_or_non_positive_bid_ask_and_depth_levels():
    crossed_quote = Quote(
        instrument_key="bybit:option:BTC-26MAR27-78000-C-USDT",
        exchange="bybit",
        market_type="option",
        instrument_id="BTC-26MAR27-78000-C-USDT",
        bid_price="11",
        ask_price="10",
        bid_size="1",
        ask_size="1",
        received_at_ms=1780210000000,
        normalized_at_ms=1780210000001,
    )
    bad_book = OrderBook(
        instrument_key="bybit:option:BTC-26MAR27-78000-C-USDT",
        exchange="bybit",
        market_type="option",
        instrument_id="BTC-26MAR27-78000-C-USDT",
        bids=[OrderBookLevel(price="10", size="0")],
        asks=[OrderBookLevel(price="11", size="1")],
        depth=1,
        is_snapshot=True,
        received_at_ms=1780210000000,
        normalized_at_ms=1780210000001,
    )

    with pytest.raises(ValueError, match="bid price is greater than ask price"):
        standardize_quote(crossed_quote)

    with pytest.raises(ValueError, match="level size must be greater than zero"):
        standardize_order_book(bad_book)
