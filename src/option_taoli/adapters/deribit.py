from __future__ import annotations

from decimal import Decimal, InvalidOperation
from time import time
from typing import Any

from option_taoli.models import FundingRate, Instrument, MarketType, OrderBook, OrderBookLevel, Quote


class DeribitAdapter:
    exchange = "deribit"

    def __init__(self, normalized_at_ms: int | None = None, received_at_ms: int | None = None) -> None:
        now_ms = int(time() * 1000)
        self._normalized_at_ms = normalized_at_ms if normalized_at_ms is not None else now_ms
        self._received_at_ms = received_at_ms if received_at_ms is not None else self._normalized_at_ms

    def normalize_instrument(self, raw: dict[str, Any]) -> Instrument:
        instrument_id = self._required_str(raw, "instrument_name")
        kind = self._required_str(raw, "kind")
        settlement_period = raw.get("settlement_period")
        market_type = self._market_type(kind, settlement_period)
        expiry_time_ms = raw.get("expiration_timestamp")

        if market_type == "perpetual":
            expiry_time_ms = None

        option_type = raw.get("option_type")
        if option_type is not None:
            option_type = self._normalize_option_type(str(option_type))

        return Instrument(
            instrument_key=self._instrument_key(market_type, instrument_id),
            exchange="deribit",
            market_type=market_type,
            instrument_id=instrument_id,
            base_asset=self._required_str(raw, "base_currency"),
            quote_asset=self._required_str(raw, "quote_currency"),
            settlement_asset=self._optional_str(raw.get("settlement_currency")),
            underlying_id=self._optional_str(raw.get("price_index")),
            expiry_time_ms=self._optional_int(expiry_time_ms),
            strike=self._decimal_string(raw.get("strike")),
            option_type=option_type,
            contract_type=self._contract_type(raw.get("instrument_type"), market_type),
            contract_size=self._decimal_string(raw.get("contract_size")) or "1",
            contract_value_currency=self._optional_str(raw.get("quote_currency")),
            tick_size=self._decimal_string(raw.get("tick_size")),
            maker_fee_rate=self._decimal_string(raw.get("maker_commission")),
            taker_fee_rate=self._decimal_string(raw.get("taker_commission")),
            fee_source="public_metadata"
            if raw.get("maker_commission") is not None or raw.get("taker_commission") is not None
            else None,
            status=self._status(raw.get("state")),
            raw_symbol=instrument_id,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_quote(self, raw: dict[str, Any], market_type: MarketType) -> Quote:
        instrument_id = self._required_str(raw, "instrument_name")
        bid_price = self._decimal_string(raw.get("best_bid_price"))
        ask_price = self._decimal_string(raw.get("best_ask_price"))

        return Quote(
            instrument_key=self._instrument_key(market_type, instrument_id),
            exchange="deribit",
            market_type=market_type,
            instrument_id=instrument_id,
            bid_price=bid_price,
            ask_price=ask_price,
            bid_size=self._decimal_string(raw.get("best_bid_amount")),
            ask_size=self._decimal_string(raw.get("best_ask_amount")),
            mid_price=self._mid_price(bid_price, ask_price),
            last_price=self._decimal_string(raw.get("last_price")),
            mark_price=self._decimal_string(raw.get("mark_price")),
            index_price=self._decimal_string(raw.get("index_price")),
            underlying_price=self._decimal_string(raw.get("underlying_price")),
            bid_iv=self._decimal_string(raw.get("bid_iv")),
            ask_iv=self._decimal_string(raw.get("ask_iv")),
            mark_iv=self._decimal_string(raw.get("mark_iv")),
            delta=self._decimal_string(raw.get("greeks", {}).get("delta") if isinstance(raw.get("greeks"), dict) else raw.get("delta")),
            gamma=self._decimal_string(raw.get("greeks", {}).get("gamma") if isinstance(raw.get("greeks"), dict) else raw.get("gamma")),
            vega=self._decimal_string(raw.get("greeks", {}).get("vega") if isinstance(raw.get("greeks"), dict) else raw.get("vega")),
            theta=self._decimal_string(raw.get("greeks", {}).get("theta") if isinstance(raw.get("greeks"), dict) else raw.get("theta")),
            source_updated_at_ms=self._optional_int(raw.get("timestamp")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_order_book(self, raw: dict[str, Any], market_type: MarketType) -> OrderBook:
        instrument_id = self._required_str(raw, "instrument_name")
        bids = self._levels(raw.get("bids", []), reverse=True)
        asks = self._levels(raw.get("asks", []), reverse=False)
        self._validate_crossed_book(bids, asks)

        return OrderBook(
            instrument_key=self._instrument_key(market_type, instrument_id),
            exchange="deribit",
            market_type=market_type,
            instrument_id=instrument_id,
            bids=bids,
            asks=asks,
            depth=min(len(bids), len(asks)),
            sequence=self._optional_str(raw.get("change_id")),
            previous_sequence=self._optional_str(raw.get("prev_change_id")),
            is_snapshot=True,
            event_time_ms=self._optional_int(raw.get("timestamp")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_funding_rate(self, raw: dict[str, Any]) -> FundingRate:
        instrument_id = self._required_str(raw, "instrument_name")
        return FundingRate(
            instrument_key=self._instrument_key("perpetual", instrument_id),
            exchange="deribit",
            instrument_id=instrument_id,
            funding_rate_current=self._decimal_string(raw.get("current_funding")),
            funding_rate_8h=self._decimal_string(raw.get("funding_8h")),
            interest_rate=self._decimal_string(raw.get("interest_rate") if raw.get("interest_rate") is not None else raw.get("interest")),
            source_updated_at_ms=self._optional_int(raw.get("timestamp")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def _instrument_key(self, market_type: MarketType, instrument_id: str) -> str:
        return f"deribit:{market_type}:{instrument_id}"

    def _market_type(self, kind: str, settlement_period: Any) -> MarketType:
        if kind == "option":
            return "option"
        if kind == "spot":
            return "spot"
        if kind == "future":
            return "perpetual" if settlement_period == "perpetual" else "future"
        raise ValueError(f"unsupported Deribit kind: {kind}")

    def _contract_type(self, instrument_type: Any, market_type: MarketType) -> str:
        if market_type == "spot":
            return "spot"
        value = str(instrument_type or "").lower()
        if value in {"reversed", "inverse"}:
            return "inverse"
        if value in {"linear"}:
            return "linear"
        return "unknown"

    def _status(self, state: Any) -> str:
        value = str(state or "").lower()
        if value == "open":
            return "trading"
        if value in {"closed", "settled"}:
            return "expired"
        if value in {"suspended", "inactive"}:
            return "suspended"
        return "unknown"

    def _normalize_option_type(self, option_type: str) -> str:
        value = option_type.lower()
        if value in {"call", "c"}:
            return "call"
        if value in {"put", "p"}:
            return "put"
        raise ValueError(f"unsupported Deribit option type: {option_type}")

    def _levels(self, raw_levels: list[Any], reverse: bool) -> list[OrderBookLevel]:
        levels: list[OrderBookLevel] = []
        for raw_level in raw_levels:
            if len(raw_level) < 2:
                raise ValueError(f"invalid Deribit order book level: {raw_level!r}")
            price = self._decimal_string(raw_level[-2] if isinstance(raw_level[0], str) and len(raw_level) >= 3 else raw_level[0])
            size = self._decimal_string(raw_level[-1] if isinstance(raw_level[0], str) and len(raw_level) >= 3 else raw_level[1])
            if price is None or size is None:
                raise ValueError(f"invalid Deribit order book level: {raw_level!r}")
            if Decimal(price) <= 0 or Decimal(size) <= 0:
                continue
            levels.append(OrderBookLevel(price=price, size=size))
        return sorted(levels, key=lambda level: Decimal(level.price), reverse=reverse)

    def _validate_crossed_book(self, bids: list[OrderBookLevel], asks: list[OrderBookLevel]) -> None:
        if bids and asks and Decimal(bids[0].price) > Decimal(asks[0].price):
            raise ValueError("invalid Deribit order book: best bid is greater than best ask")

    def _mid_price(self, bid_price: str | None, ask_price: str | None) -> str | None:
        if bid_price is None or ask_price is None:
            return None
        bid = Decimal(bid_price)
        ask = Decimal(ask_price)
        if bid > ask:
            raise ValueError("invalid Deribit quote: bid price is greater than ask price")
        return str((bid + ask) / Decimal("2"))

    def _decimal_string(self, value: Any) -> str | None:
        if value is None:
            return None
        try:
            decimal = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"invalid decimal value: {value!r}") from exc
        return format(decimal, "f")

    def _optional_int(self, value: Any) -> int | None:
        if value is None:
            return None
        return int(value)

    def _optional_str(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    def _required_str(self, raw: dict[str, Any], field: str) -> str:
        value = raw.get(field)
        if value is None:
            raise ValueError(f"missing required Deribit field: {field}")
        return str(value)
