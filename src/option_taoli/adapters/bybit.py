from __future__ import annotations

from decimal import Decimal, InvalidOperation
from time import time
from typing import Any

from option_taoli.models import FundingRate, Instrument, MarketType, OrderBook, OrderBookLevel, Quote


class BybitAdapter:
    exchange = "bybit"

    def __init__(self, normalized_at_ms: int | None = None, received_at_ms: int | None = None) -> None:
        now_ms = int(time() * 1000)
        self._normalized_at_ms = normalized_at_ms if normalized_at_ms is not None else now_ms
        self._received_at_ms = received_at_ms if received_at_ms is not None else self._normalized_at_ms

    def normalize_instrument(self, raw: dict[str, Any], category: str) -> Instrument:
        instrument_id = self._required_str(raw, "symbol")
        market_type = self._market_type(category, raw)
        lot_size = raw.get("lotSizeFilter", {}) if isinstance(raw.get("lotSizeFilter"), dict) else {}
        price_filter = raw.get("priceFilter", {}) if isinstance(raw.get("priceFilter"), dict) else {}
        expiry_time_ms = self._optional_int(raw.get("deliveryTime"))
        if market_type == "perpetual":
            expiry_time_ms = None

        parsed_option = self._parse_option_symbol(instrument_id) if market_type == "option" else {}

        return Instrument(
            instrument_key=self._instrument_key(market_type, instrument_id),
            exchange="bybit",
            market_type=market_type,
            instrument_id=instrument_id,
            base_asset=self._required_str(raw, "baseCoin"),
            quote_asset=self._required_str(raw, "quoteCoin"),
            settlement_asset=self._optional_str(raw.get("settleCoin")),
            underlying_id=self._underlying_id(raw, category, market_type),
            instrument_family=self._instrument_family(raw, category, market_type),
            expiry_time_ms=expiry_time_ms,
            strike=self._decimal_string(parsed_option.get("strike")),
            option_type=self._option_type(raw.get("optionsType") or parsed_option.get("option_type")),
            contract_type=self._contract_type(raw.get("contractType"), category, market_type),
            contract_size="1",
            contract_value_currency=self._optional_str(raw.get("quoteCoin")),
            tick_size=self._decimal_string(price_filter.get("tickSize")),
            min_order_size=self._decimal_string(lot_size.get("minOrderQty") or lot_size.get("minOrderAmt")),
            qty_step=self._decimal_string(lot_size.get("qtyStep") or lot_size.get("basePrecision")),
            status=self._status(raw.get("status")),
            raw_symbol=instrument_id,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_ticker(self, raw: dict[str, Any], category: str) -> Quote:
        instrument_id = self._required_str(raw, "symbol")
        market_type = self._market_type(category, raw)
        bid_price = self._decimal_string(raw.get("bid1Price"))
        ask_price = self._decimal_string(raw.get("ask1Price"))

        return Quote(
            instrument_key=self._instrument_key(market_type, instrument_id),
            exchange="bybit",
            market_type=market_type,
            instrument_id=instrument_id,
            bid_price=bid_price,
            ask_price=ask_price,
            bid_size=self._decimal_string(raw.get("bid1Size")),
            ask_size=self._decimal_string(raw.get("ask1Size")),
            mid_price=self._mid_price(bid_price, ask_price),
            last_price=self._decimal_string(raw.get("lastPrice")),
            mark_price=self._decimal_string(raw.get("markPrice")),
            index_price=self._decimal_string(raw.get("indexPrice")),
            underlying_price=self._decimal_string(raw.get("underlyingPrice")),
            bid_iv=self._decimal_string(raw.get("bid1Iv")),
            ask_iv=self._decimal_string(raw.get("ask1Iv")),
            mark_iv=self._decimal_string(raw.get("markIv")),
            delta=self._decimal_string(raw.get("delta")),
            gamma=self._decimal_string(raw.get("gamma")),
            vega=self._decimal_string(raw.get("vega")),
            theta=self._decimal_string(raw.get("theta")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_order_book(self, raw: dict[str, Any], category: str) -> OrderBook:
        instrument_id = self._required_str(raw, "s")
        market_type = self._market_type(category, {"symbol": instrument_id})
        bids = self._levels(raw.get("b", []), reverse=True)
        asks = self._levels(raw.get("a", []), reverse=False)
        self._validate_crossed_book(bids, asks)

        return OrderBook(
            instrument_key=self._instrument_key(market_type, instrument_id),
            exchange="bybit",
            market_type=market_type,
            instrument_id=instrument_id,
            bids=bids,
            asks=asks,
            depth=min(len(bids), len(asks)),
            sequence=self._optional_str(raw.get("u")),
            checksum=self._optional_str(raw.get("seq")),
            is_snapshot=True,
            event_time_ms=self._optional_int(raw.get("ts")),
            transaction_time_ms=self._optional_int(raw.get("cts")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_funding_rate_from_ticker(self, raw: dict[str, Any], category: str) -> FundingRate:
        instrument_id = self._required_str(raw, "symbol")
        market_type = self._market_type(category, raw)
        return FundingRate(
            instrument_key=self._instrument_key(market_type, instrument_id),
            exchange="bybit",
            instrument_id=instrument_id,
            funding_rate_current=self._decimal_string(raw.get("fundingRate")),
            next_funding_time_ms=self._optional_int(raw.get("nextFundingTime")),
            funding_interval_hours=self._decimal_string(raw.get("fundingIntervalHour")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_funding_history_row(self, raw: dict[str, Any], category: str) -> FundingRate:
        instrument_id = self._required_str(raw, "symbol")
        market_type = self._market_type(category, raw)
        funding_time_ms = self._optional_int(raw.get("fundingRateTimestamp"))
        return FundingRate(
            instrument_key=self._instrument_key(market_type, instrument_id),
            exchange="bybit",
            instrument_id=instrument_id,
            funding_rate_current=self._decimal_string(raw.get("fundingRate")),
            funding_time_ms=funding_time_ms,
            source_updated_at_ms=funding_time_ms,
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def _instrument_key(self, market_type: MarketType, instrument_id: str) -> str:
        return f"bybit:{market_type}:{instrument_id}"

    def _market_type(self, category: str, raw: dict[str, Any]) -> MarketType:
        value = category.lower()
        if value == "spot":
            return "spot"
        if value == "option":
            return "option"
        if value in {"linear", "inverse"}:
            contract_type = str(raw.get("contractType") or "").lower()
            delivery_time = str(raw.get("deliveryTime") or "0")
            if "future" in contract_type or (delivery_time not in {"", "0"} and "perpetual" not in contract_type):
                return "future"
            return "perpetual"
        raise ValueError(f"unsupported Bybit category: {category}")

    def _underlying_id(self, raw: dict[str, Any], category: str, market_type: MarketType) -> str | None:
        if market_type == "option":
            return self._optional_str(raw.get("baseCoin"))
        if market_type in {"perpetual", "future"}:
            return self._optional_str(raw.get("baseCoin") + raw.get("quoteCoin") if raw.get("baseCoin") and raw.get("quoteCoin") else raw.get("symbol"))
        return None

    def _instrument_family(self, raw: dict[str, Any], category: str, market_type: MarketType) -> str | None:
        if market_type == "option":
            return self._optional_str(raw.get("baseCoin"))
        if market_type in {"perpetual", "future"}:
            return self._underlying_id(raw, category, market_type)
        return None

    def _parse_option_symbol(self, symbol: str) -> dict[str, str]:
        parts = symbol.split("-")
        if len(parts) < 4:
            raise ValueError(f"invalid Bybit option symbol: {symbol}")
        option_part = parts[3]
        if option_part not in {"C", "P"}:
            raise ValueError(f"invalid Bybit option type in symbol: {symbol}")
        return {"strike": parts[2], "option_type": option_part}

    def _contract_type(self, contract_type: Any, category: str, market_type: MarketType) -> str:
        if market_type == "spot":
            return "spot"
        if market_type == "option":
            return "linear"
        value = str(contract_type or category).lower()
        if "inverse" in value:
            return "inverse"
        if "linear" in value or category.lower() == "linear":
            return "linear"
        return "unknown"

    def _option_type(self, option_type: Any) -> str | None:
        if option_type is None:
            return None
        value = str(option_type).lower()
        if value in {"call", "c"}:
            return "call"
        if value in {"put", "p"}:
            return "put"
        raise ValueError(f"unsupported Bybit option type: {option_type}")

    def _status(self, status: Any) -> str:
        value = str(status or "").lower()
        if value == "trading":
            return "trading"
        if value == "prelaunch":
            return "pre_launch"
        if value == "delivering":
            return "delivering"
        if value in {"closed", "settled"}:
            return "expired"
        return "unknown"

    def _levels(self, raw_levels: list[Any], reverse: bool) -> list[OrderBookLevel]:
        levels: list[OrderBookLevel] = []
        for raw_level in raw_levels:
            if len(raw_level) < 2:
                raise ValueError(f"invalid Bybit order book level: {raw_level!r}")
            price = self._decimal_string(raw_level[0])
            size = self._decimal_string(raw_level[1])
            if price is None or size is None:
                raise ValueError(f"invalid Bybit order book level: {raw_level!r}")
            if Decimal(price) <= 0 or Decimal(size) <= 0:
                continue
            levels.append(OrderBookLevel(price=price, size=size))
        return sorted(levels, key=lambda level: Decimal(level.price), reverse=reverse)

    def _validate_crossed_book(self, bids: list[OrderBookLevel], asks: list[OrderBookLevel]) -> None:
        if bids and asks and Decimal(bids[0].price) > Decimal(asks[0].price):
            raise ValueError("invalid Bybit order book: best bid is greater than best ask")

    def _mid_price(self, bid_price: str | None, ask_price: str | None) -> str | None:
        if bid_price is None or ask_price is None:
            return None
        bid = Decimal(bid_price)
        ask = Decimal(ask_price)
        if bid > ask:
            raise ValueError("invalid Bybit quote: bid price is greater than ask price")
        return str((bid + ask) / Decimal("2"))

    def _decimal_string(self, value: Any) -> str | None:
        if value is None or value == "":
            return None
        try:
            decimal = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"invalid decimal value: {value!r}") from exc
        return format(decimal, "f")

    def _optional_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    def _optional_str(self, value: Any) -> str | None:
        if value is None or value == "":
            return None
        return str(value)

    def _required_str(self, raw: dict[str, Any], field: str) -> str:
        value = raw.get(field)
        if value is None or value == "":
            raise ValueError(f"missing required Bybit field: {field}")
        return str(value)
