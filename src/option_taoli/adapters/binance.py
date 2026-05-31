from __future__ import annotations

from decimal import Decimal, InvalidOperation
from time import time
from typing import Any

from option_taoli.models import FundingRate, Instrument, MarketType, OrderBook, OrderBookLevel, Quote


class BinanceAdapter:
    exchange = "binance"

    def __init__(self, normalized_at_ms: int | None = None, received_at_ms: int | None = None) -> None:
        now_ms = int(time() * 1000)
        self._normalized_at_ms = normalized_at_ms if normalized_at_ms is not None else now_ms
        self._received_at_ms = received_at_ms if received_at_ms is not None else self._normalized_at_ms

    def normalize_option_instrument(
        self,
        raw: dict[str, Any],
        option_contract: dict[str, Any] | None = None,
    ) -> Instrument:
        instrument_id = self._required_str(raw, "symbol")
        filters = self._filters_by_type(raw.get("filters", []))
        lot_size = filters.get("LOT_SIZE", {})
        price_filter = filters.get("PRICE_FILTER", {})
        base_asset = (option_contract or {}).get("baseAsset") or self._base_from_underlying(raw.get("underlying"))

        return Instrument(
            instrument_key=self._instrument_key("option", instrument_id),
            exchange="binance",
            market_type="option",
            instrument_id=instrument_id,
            base_asset=self._required_value_as_str(base_asset, "baseAsset"),
            quote_asset=self._required_str(raw, "quoteAsset"),
            settlement_asset=self._optional_str(raw.get("settleAsset")),
            underlying_id=self._optional_str(raw.get("underlying")),
            instrument_family=self._optional_str(raw.get("underlying")),
            expiry_time_ms=self._optional_int(raw.get("expiryDate")),
            strike=self._decimal_string(raw.get("strikePrice")),
            option_type=self._option_type(raw.get("side")),
            contract_type="linear",
            contract_size=self._decimal_string(raw.get("unit")) or "1",
            contract_value_currency=self._optional_str(raw.get("quoteAsset")),
            tick_size=self._decimal_string(price_filter.get("tickSize")),
            min_order_size=self._decimal_string(lot_size.get("minQty")),
            qty_step=self._decimal_string(lot_size.get("stepSize")),
            status=self._status(raw.get("status")),
            raw_symbol=instrument_id,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_spot_instrument(self, raw: dict[str, Any]) -> Instrument:
        instrument_id = self._required_str(raw, "symbol")
        filters = self._filters_by_type(raw.get("filters", []))
        lot_size = filters.get("LOT_SIZE", {})
        price_filter = filters.get("PRICE_FILTER", {})

        return Instrument(
            instrument_key=self._instrument_key("spot", instrument_id),
            exchange="binance",
            market_type="spot",
            instrument_id=instrument_id,
            base_asset=self._required_str(raw, "baseAsset"),
            quote_asset=self._required_str(raw, "quoteAsset"),
            contract_type="spot",
            contract_size="1",
            tick_size=self._decimal_string(price_filter.get("tickSize")),
            min_order_size=self._decimal_string(lot_size.get("minQty")),
            qty_step=self._decimal_string(lot_size.get("stepSize")),
            status=self._status(raw.get("status")),
            raw_symbol=instrument_id,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_usdm_instrument(self, raw: dict[str, Any]) -> Instrument:
        instrument_id = self._required_str(raw, "symbol")
        market_type = "perpetual" if raw.get("contractType") == "PERPETUAL" else "future"
        filters = self._filters_by_type(raw.get("filters", []))
        lot_size = filters.get("LOT_SIZE", {})
        price_filter = filters.get("PRICE_FILTER", {})
        expiry_time_ms = None if market_type == "perpetual" else self._optional_int(raw.get("deliveryDate"))

        return Instrument(
            instrument_key=self._instrument_key(market_type, instrument_id),
            exchange="binance",
            market_type=market_type,
            instrument_id=instrument_id,
            base_asset=self._required_str(raw, "baseAsset"),
            quote_asset=self._required_str(raw, "quoteAsset"),
            settlement_asset=self._optional_str(raw.get("marginAsset")),
            underlying_id=self._optional_str(raw.get("pair")),
            instrument_family=self._optional_str(raw.get("pair")),
            expiry_time_ms=expiry_time_ms,
            contract_type="linear",
            contract_size="1",
            contract_value_currency=self._optional_str(raw.get("quoteAsset")),
            tick_size=self._decimal_string(price_filter.get("tickSize")),
            min_order_size=self._decimal_string(lot_size.get("minQty")),
            qty_step=self._decimal_string(lot_size.get("stepSize")),
            status=self._status(raw.get("status")),
            raw_symbol=instrument_id,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_spot_book_ticker(self, raw: dict[str, Any]) -> Quote:
        instrument_id = self._required_str(raw, "symbol")
        bid_price = self._decimal_string(raw.get("bidPrice"))
        ask_price = self._decimal_string(raw.get("askPrice"))

        return Quote(
            instrument_key=self._instrument_key("spot", instrument_id),
            exchange="binance",
            market_type="spot",
            instrument_id=instrument_id,
            bid_price=bid_price,
            ask_price=ask_price,
            bid_size=self._decimal_string(raw.get("bidQty")),
            ask_size=self._decimal_string(raw.get("askQty")),
            mid_price=self._mid_price(bid_price, ask_price),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_option_mark_quote(self, raw: dict[str, Any]) -> Quote:
        instrument_id = self._required_value_as_str(self._first_present(raw, "symbol", "s"), "symbol")
        bid_price = self._decimal_string(self._first_present(raw, "bidPrice", "bo"))
        ask_price = self._decimal_string(self._first_present(raw, "askPrice", "ao"))

        return Quote(
            instrument_key=self._instrument_key("option", instrument_id),
            exchange="binance",
            market_type="option",
            instrument_id=instrument_id,
            bid_price=bid_price,
            ask_price=ask_price,
            bid_size=self._decimal_string(self._first_present(raw, "bidQty", "bq")),
            ask_size=self._decimal_string(self._first_present(raw, "askQty", "aq")),
            mid_price=self._mid_price(bid_price, ask_price),
            mark_price=self._decimal_string(self._first_present(raw, "markPrice", "mp")),
            index_price=self._decimal_string(self._first_present(raw, "indexPrice", "i")),
            bid_iv=self._decimal_string(raw.get("bidIV")),
            ask_iv=self._decimal_string(raw.get("askIV")),
            mark_iv=self._decimal_string(raw.get("markIV")),
            delta=self._decimal_string(raw.get("delta")),
            gamma=self._decimal_string(raw.get("gamma")),
            vega=self._decimal_string(raw.get("vega")),
            theta=self._decimal_string(raw.get("theta")),
            source_updated_at_ms=self._optional_int(self._first_present(raw, "time", "T", "E")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_usdm_premium_index_quote(self, raw: dict[str, Any]) -> Quote:
        instrument_id = self._required_value_as_str(self._first_present(raw, "symbol", "s"), "symbol")
        return Quote(
            instrument_key=self._instrument_key("perpetual", instrument_id),
            exchange="binance",
            market_type="perpetual",
            instrument_id=instrument_id,
            mark_price=self._decimal_string(self._first_present(raw, "markPrice", "p")),
            index_price=self._decimal_string(self._first_present(raw, "indexPrice", "i")),
            source_updated_at_ms=self._optional_int(self._first_present(raw, "time", "E")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_depth_snapshot(
        self,
        raw: dict[str, Any],
        market_type: MarketType,
        instrument_id: str,
    ) -> OrderBook:
        bids = self._levels(raw.get("bids", []), reverse=True)
        asks = self._levels(raw.get("asks", []), reverse=False)
        self._validate_crossed_book(bids, asks)

        return OrderBook(
            instrument_key=self._instrument_key(market_type, instrument_id),
            exchange="binance",
            market_type=market_type,
            instrument_id=instrument_id,
            bids=bids,
            asks=asks,
            depth=min(len(bids), len(asks)),
            sequence=self._optional_str(raw.get("lastUpdateId")),
            is_snapshot=True,
            event_time_ms=self._optional_int(raw.get("E")),
            transaction_time_ms=self._optional_int(raw.get("T")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_usdm_funding_rate(self, raw: dict[str, Any]) -> FundingRate:
        instrument_id = self._required_value_as_str(self._first_present(raw, "symbol", "s"), "symbol")
        return FundingRate(
            instrument_key=self._instrument_key("perpetual", instrument_id),
            exchange="binance",
            instrument_id=instrument_id,
            funding_rate_current=self._decimal_string(self._first_present(raw, "lastFundingRate", "fundingRate", "r")),
            funding_time_ms=self._optional_int(raw.get("fundingTime")),
            next_funding_time_ms=self._optional_int(self._first_present(raw, "nextFundingTime", "T")),
            interest_rate=self._decimal_string(raw.get("interestRate")),
            source_updated_at_ms=self._optional_int(self._first_present(raw, "time", "E", "fundingTime")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def _instrument_key(self, market_type: MarketType, instrument_id: str) -> str:
        return f"binance:{market_type}:{instrument_id}"

    def _filters_by_type(self, filters: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {str(item.get("filterType")): item for item in filters if isinstance(item, dict)}

    def _base_from_underlying(self, underlying: Any) -> str | None:
        if underlying is None:
            return None
        value = str(underlying)
        for suffix in ("USDT", "USDC", "USD", "BTC", "ETH"):
            if value.endswith(suffix) and len(value) > len(suffix):
                return value[: -len(suffix)]
        return value

    def _status(self, status: Any) -> str:
        value = str(status or "").upper()
        if value == "TRADING":
            return "trading"
        if value in {"PRE_TRADING", "PENDING_TRADING"}:
            return "pre_launch"
        if value in {"EXPIRED", "DELIVERED"}:
            return "expired"
        if value in {"BREAK", "HALT", "SUSPEND"}:
            return "suspended"
        return "unknown"

    def _option_type(self, side: Any) -> str | None:
        if side is None:
            return None
        value = str(side).upper()
        if value in {"CALL", "C"}:
            return "call"
        if value in {"PUT", "P"}:
            return "put"
        raise ValueError(f"unsupported Binance option side: {side}")

    def _levels(self, raw_levels: list[Any], reverse: bool) -> list[OrderBookLevel]:
        levels: list[OrderBookLevel] = []
        for raw_level in raw_levels:
            if len(raw_level) < 2:
                raise ValueError(f"invalid Binance order book level: {raw_level!r}")
            price = self._decimal_string(raw_level[0])
            size = self._decimal_string(raw_level[1])
            if price is None or size is None:
                raise ValueError(f"invalid Binance order book level: {raw_level!r}")
            if Decimal(price) <= 0 or Decimal(size) <= 0:
                continue
            levels.append(OrderBookLevel(price=price, size=size))
        return sorted(levels, key=lambda level: Decimal(level.price), reverse=reverse)

    def _validate_crossed_book(self, bids: list[OrderBookLevel], asks: list[OrderBookLevel]) -> None:
        if bids and asks and Decimal(bids[0].price) > Decimal(asks[0].price):
            raise ValueError("invalid Binance order book: best bid is greater than best ask")

    def _mid_price(self, bid_price: str | None, ask_price: str | None) -> str | None:
        if bid_price is None or ask_price is None:
            return None
        bid = Decimal(bid_price)
        ask = Decimal(ask_price)
        if bid > ask:
            raise ValueError("invalid Binance quote: bid price is greater than ask price")
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
        return self._required_value_as_str(raw.get(field), field)

    def _first_present(self, raw: dict[str, Any], *fields: str) -> Any:
        for field in fields:
            value = raw.get(field)
            if value is not None:
                return value
        return None

    def _required_value_as_str(self, value: Any, field: str) -> str:
        if value is None:
            raise ValueError(f"missing required Binance field: {field}")
        return str(value)
