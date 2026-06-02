from __future__ import annotations

from decimal import Decimal, InvalidOperation
from time import time
from typing import Any

from option_taoli.models import Instrument, OrderBook, OrderBookLevel, Quote


class GateAdapter:
    exchange = "gate"

    def __init__(self, normalized_at_ms: int | None = None, received_at_ms: int | None = None) -> None:
        now_ms = int(time() * 1000)
        self._normalized_at_ms = normalized_at_ms if normalized_at_ms is not None else now_ms
        self._received_at_ms = received_at_ms if received_at_ms is not None else self._normalized_at_ms

    def normalize_contract(self, raw: dict[str, Any]) -> Instrument:
        instrument_id = self._required_str(raw, "name")
        underlying = self._required_str(raw, "underlying")
        base_asset, quote_asset = self._assets(underlying)

        return Instrument(
            instrument_key=self._instrument_key(instrument_id),
            exchange="gate",
            market_type="option",
            instrument_id=instrument_id,
            base_asset=base_asset,
            quote_asset=quote_asset,
            settlement_asset=quote_asset,
            underlying_id=underlying,
            instrument_family=underlying,
            expiry_time_ms=self._seconds_to_ms(raw.get("expiration_time")),
            strike=self._decimal_string(raw.get("strike_price")),
            option_type=self._option_type(raw.get("is_call"), instrument_id),
            contract_type="linear",
            contract_size=self._decimal_string(raw.get("multiplier")) or "1",
            contract_value_currency=base_asset,
            tick_size=self._decimal_string(raw.get("order_price_round") or raw.get("mark_price_round")),
            min_order_size=self._decimal_string(raw.get("order_size_min")),
            qty_step="1",
            maker_fee_rate=self._decimal_string(raw.get("maker_fee_rate")),
            taker_fee_rate=self._decimal_string(raw.get("taker_fee_rate")),
            fee_source="public_metadata",
            status="trading",
            raw_symbol=instrument_id,
            normalized_at_ms=self._normalized_at_ms,
            source_updated_at_ms=self._seconds_to_ms(raw.get("create_time")),
            raw=raw,
        )

    def normalize_ticker(self, raw: dict[str, Any]) -> Quote:
        instrument_id = self._required_str(raw, "name")
        bid_price = self._positive_decimal_string(raw.get("bid1_price"))
        ask_price = self._positive_decimal_string(raw.get("ask1_price"))

        return Quote(
            instrument_key=self._instrument_key(instrument_id),
            exchange="gate",
            market_type="option",
            instrument_id=instrument_id,
            bid_price=bid_price,
            ask_price=ask_price,
            bid_size=self._positive_decimal_string(raw.get("bid1_size")),
            ask_size=self._positive_decimal_string(raw.get("ask1_size")),
            mid_price=self._mid_price(bid_price, ask_price),
            last_price=self._decimal_string(raw.get("last_price")),
            mark_price=self._decimal_string(raw.get("mark_price")),
            index_price=self._decimal_string(raw.get("index_price")),
            bid_iv=self._decimal_string(raw.get("bid_iv")),
            ask_iv=self._decimal_string(raw.get("ask_iv")),
            mark_iv=self._decimal_string(raw.get("mark_iv")),
            delta=self._decimal_string(raw.get("delta")),
            gamma=self._decimal_string(raw.get("gamma")),
            vega=self._decimal_string(raw.get("vega")),
            theta=self._decimal_string(raw.get("theta")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_order_book(self, raw: dict[str, Any], *, contract: str) -> OrderBook:
        bids = self._levels(raw.get("bids", []), reverse=True)
        asks = self._levels(raw.get("asks", []), reverse=False)
        self._validate_crossed_book(bids, asks)

        return OrderBook(
            instrument_key=self._instrument_key(contract),
            exchange="gate",
            market_type="option",
            instrument_id=contract,
            bids=bids,
            asks=asks,
            depth=min(len(bids), len(asks)),
            sequence=self._optional_str(raw.get("id")),
            is_snapshot=True,
            event_time_ms=self._seconds_float_to_ms(raw.get("update")),
            transaction_time_ms=self._seconds_float_to_ms(raw.get("current")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def _instrument_key(self, instrument_id: str) -> str:
        return f"gate:option:{instrument_id}"

    def _assets(self, underlying: str) -> tuple[str, str]:
        if "_" in underlying:
            base, quote = underlying.split("_", 1)
            return base, quote
        raise ValueError(f"cannot derive Gate base/quote assets for {underlying}")

    def _option_type(self, is_call: Any, instrument_id: str) -> str:
        if isinstance(is_call, bool):
            return "call" if is_call else "put"
        suffix = instrument_id.rsplit("-", 1)[-1].upper()
        if suffix == "C":
            return "call"
        if suffix == "P":
            return "put"
        raise ValueError(f"unsupported Gate option type for {instrument_id}")

    def _levels(self, raw_levels: list[Any], reverse: bool) -> list[OrderBookLevel]:
        levels: list[OrderBookLevel] = []
        for raw_level in raw_levels:
            price_value = raw_level.get("p") if isinstance(raw_level, dict) else raw_level[0] if len(raw_level) > 0 else None
            size_value = raw_level.get("s") if isinstance(raw_level, dict) else raw_level[1] if len(raw_level) > 1 else None
            price = self._decimal_string(price_value)
            size = self._decimal_string(size_value)
            if price is None or size is None:
                raise ValueError(f"invalid Gate order book level: {raw_level!r}")
            if Decimal(price) <= 0 or Decimal(size) <= 0:
                continue
            levels.append(OrderBookLevel(price=price, size=size))
        return sorted(levels, key=lambda level: Decimal(level.price), reverse=reverse)

    def _validate_crossed_book(self, bids: list[OrderBookLevel], asks: list[OrderBookLevel]) -> None:
        if bids and asks and Decimal(bids[0].price) > Decimal(asks[0].price):
            raise ValueError("invalid Gate order book: best bid is greater than best ask")

    def _mid_price(self, bid_price: str | None, ask_price: str | None) -> str | None:
        if bid_price is None or ask_price is None:
            return None
        bid = Decimal(bid_price)
        ask = Decimal(ask_price)
        if bid > ask:
            raise ValueError("invalid Gate quote: bid price is greater than ask price")
        return str((bid + ask) / Decimal("2"))

    def _positive_decimal_string(self, value: Any) -> str | None:
        decimal_string = self._decimal_string(value)
        if decimal_string is None or Decimal(decimal_string) <= 0:
            return None
        return decimal_string

    def _decimal_string(self, value: Any) -> str | None:
        if value is None or value == "":
            return None
        try:
            decimal = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"invalid decimal value: {value!r}") from exc
        return format(decimal, "f")

    def _seconds_to_ms(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        return int(Decimal(str(value)) * Decimal("1000"))

    def _seconds_float_to_ms(self, value: Any) -> int | None:
        return self._seconds_to_ms(value)

    def _optional_str(self, value: Any) -> str | None:
        if value is None or value == "":
            return None
        return str(value)

    def _required_str(self, raw: dict[str, Any], field: str) -> str:
        value = raw.get(field)
        if value is None or value == "":
            raise ValueError(f"missing required Gate field: {field}")
        return str(value)
