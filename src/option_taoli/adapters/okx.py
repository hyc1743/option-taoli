from __future__ import annotations

from decimal import Decimal, InvalidOperation
from time import time
from typing import Any

from option_taoli.models import FundingRate, Instrument, MarketType, OrderBook, OrderBookLevel, Quote


class OkxAdapter:
    exchange = "okx"

    def __init__(self, normalized_at_ms: int | None = None, received_at_ms: int | None = None) -> None:
        now_ms = int(time() * 1000)
        self._normalized_at_ms = normalized_at_ms if normalized_at_ms is not None else now_ms
        self._received_at_ms = received_at_ms if received_at_ms is not None else self._normalized_at_ms

    def normalize_instrument(self, raw: dict[str, Any]) -> Instrument:
        instrument_id = self._required_str(raw, "instId")
        instrument_type = self._required_str(raw, "instType")
        market_type = self._market_type(instrument_type)
        underlying_id = self._optional_str(raw.get("uly"))
        base_asset, quote_asset = self._assets(raw, underlying_id)

        return Instrument(
            instrument_key=self._instrument_key(market_type, instrument_id),
            exchange="okx",
            market_type=market_type,
            instrument_id=instrument_id,
            base_asset=base_asset,
            quote_asset=quote_asset,
            settlement_asset=self._optional_str(raw.get("settleCcy")),
            underlying_id=underlying_id,
            instrument_family=self._optional_str(raw.get("instFamily")),
            expiry_time_ms=self._optional_int(raw.get("expTime")),
            strike=self._decimal_string(raw.get("stk")),
            option_type=self._option_type(raw.get("optType")),
            contract_type=self._contract_type(raw.get("ctType"), market_type),
            contract_size=self._contract_size(raw),
            contract_value_currency=self._optional_str(raw.get("ctValCcy")),
            tick_size=self._decimal_string(raw.get("tickSz")),
            min_order_size=self._decimal_string(raw.get("minSz")),
            qty_step=self._decimal_string(raw.get("lotSz")),
            status=self._status(raw.get("state")),
            raw_symbol=instrument_id,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_ticker(self, raw: dict[str, Any]) -> Quote:
        instrument_id = self._required_str(raw, "instId")
        market_type = self._market_type(self._required_str(raw, "instType"))
        bid_price = self._decimal_string(raw.get("bidPx"))
        ask_price = self._decimal_string(raw.get("askPx"))

        return Quote(
            instrument_key=self._instrument_key(market_type, instrument_id),
            exchange="okx",
            market_type=market_type,
            instrument_id=instrument_id,
            bid_price=bid_price,
            ask_price=ask_price,
            bid_size=self._decimal_string(raw.get("bidSz")),
            ask_size=self._decimal_string(raw.get("askSz")),
            mid_price=self._mid_price(bid_price, ask_price),
            last_price=self._decimal_string(raw.get("last")),
            source_updated_at_ms=self._optional_int(raw.get("ts")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_order_book(self, raw: dict[str, Any], market_type: MarketType) -> OrderBook:
        instrument_id = self._required_str(raw, "instId")
        bids = self._levels(raw.get("bids", []), reverse=True)
        asks = self._levels(raw.get("asks", []), reverse=False)
        self._validate_crossed_book(bids, asks)

        return OrderBook(
            instrument_key=self._instrument_key(market_type, instrument_id),
            exchange="okx",
            market_type=market_type,
            instrument_id=instrument_id,
            bids=bids,
            asks=asks,
            depth=min(len(bids), len(asks)),
            sequence=self._optional_str(raw.get("seqId")),
            previous_sequence=self._optional_str(raw.get("prevSeqId")),
            checksum=self._optional_str(raw.get("checksum")),
            is_snapshot=str(raw.get("action", "snapshot")) == "snapshot",
            event_time_ms=self._optional_int(raw.get("ts")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_mark_price(self, raw: dict[str, Any]) -> Quote:
        instrument_id = self._required_str(raw, "instId")
        market_type = self._market_type(self._required_str(raw, "instType"))
        return Quote(
            instrument_key=self._instrument_key(market_type, instrument_id),
            exchange="okx",
            market_type=market_type,
            instrument_id=instrument_id,
            mark_price=self._decimal_string(raw.get("markPx")),
            source_updated_at_ms=self._optional_int(raw.get("ts")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_index_ticker(self, raw: dict[str, Any]) -> Quote:
        instrument_id = self._required_str(raw, "instId")
        return Quote(
            instrument_key=self._instrument_key("spot", instrument_id),
            exchange="okx",
            market_type="spot",
            instrument_id=instrument_id,
            index_price=self._decimal_string(raw.get("idxPx")),
            source_updated_at_ms=self._optional_int(raw.get("ts")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def normalize_funding_rate(self, raw: dict[str, Any]) -> FundingRate:
        instrument_id = self._required_str(raw, "instId")
        return FundingRate(
            instrument_key=self._instrument_key("perpetual", instrument_id),
            exchange="okx",
            instrument_id=instrument_id,
            funding_rate_current=self._decimal_string(raw.get("fundingRate")),
            funding_time_ms=self._optional_int(raw.get("fundingTime")),
            next_funding_time_ms=self._optional_int(raw.get("nextFundingTime")),
            interest_rate=self._decimal_string(raw.get("interestRate")),
            premium=self._decimal_string(raw.get("premium")),
            source_updated_at_ms=self._optional_int(raw.get("ts")),
            received_at_ms=self._received_at_ms,
            normalized_at_ms=self._normalized_at_ms,
            raw=raw,
        )

    def _instrument_key(self, market_type: MarketType, instrument_id: str) -> str:
        return f"okx:{market_type}:{instrument_id}"

    def _market_type(self, instrument_type: str) -> MarketType:
        value = instrument_type.upper()
        if value == "SPOT":
            return "spot"
        if value == "OPTION":
            return "option"
        if value == "SWAP":
            return "perpetual"
        if value == "FUTURES":
            return "future"
        raise ValueError(f"unsupported OKX instType: {instrument_type}")

    def _assets(self, raw: dict[str, Any], underlying_id: str | None) -> tuple[str, str]:
        base = self._optional_str(raw.get("baseCcy"))
        quote = self._optional_str(raw.get("quoteCcy"))
        if base and quote:
            return base, quote
        if underlying_id and "-" in underlying_id:
            base_from_underlying, quote_from_underlying = underlying_id.split("-", 1)
            return base or base_from_underlying, quote or quote_from_underlying
        instrument_id = self._required_str(raw, "instId")
        parts = instrument_id.split("-")
        if len(parts) >= 2:
            return base or parts[0], quote or parts[1]
        raise ValueError(f"cannot derive OKX base/quote assets for {instrument_id}")

    def _contract_size(self, raw: dict[str, Any]) -> str:
        ct_val = self._decimal_string(raw.get("ctVal"))
        ct_mult = self._decimal_string(raw.get("ctMult"))
        if ct_val is None:
            return "1"
        if ct_mult is None:
            return ct_val
        return format(Decimal(ct_val) * Decimal(ct_mult), "f")

    def _contract_type(self, contract_type: Any, market_type: MarketType) -> str:
        if market_type == "spot":
            return "spot"
        value = str(contract_type or "").lower()
        if value in {"linear", "inverse"}:
            return value
        return "unknown"

    def _option_type(self, option_type: Any) -> str | None:
        if option_type is None:
            return None
        value = str(option_type).upper()
        if value in {"C", "CALL"}:
            return "call"
        if value in {"P", "PUT"}:
            return "put"
        raise ValueError(f"unsupported OKX optType: {option_type}")

    def _status(self, status: Any) -> str:
        value = str(status or "").lower()
        if value == "live":
            return "trading"
        if value in {"suspend", "suspended"}:
            return "suspended"
        if value in {"expired", "settlement"}:
            return "expired"
        if value in {"preopen", "test"}:
            return "pre_launch"
        return "unknown"

    def _levels(self, raw_levels: list[Any], reverse: bool) -> list[OrderBookLevel]:
        levels: list[OrderBookLevel] = []
        for raw_level in raw_levels:
            if len(raw_level) < 2:
                raise ValueError(f"invalid OKX order book level: {raw_level!r}")
            price = self._decimal_string(raw_level[0])
            size = self._decimal_string(raw_level[1])
            if price is None or size is None:
                raise ValueError(f"invalid OKX order book level: {raw_level!r}")
            if Decimal(price) <= 0 or Decimal(size) <= 0:
                continue
            levels.append(OrderBookLevel(price=price, size=size))
        return sorted(levels, key=lambda level: Decimal(level.price), reverse=reverse)

    def _validate_crossed_book(self, bids: list[OrderBookLevel], asks: list[OrderBookLevel]) -> None:
        if bids and asks and Decimal(bids[0].price) > Decimal(asks[0].price):
            raise ValueError("invalid OKX order book: best bid is greater than best ask")

    def _mid_price(self, bid_price: str | None, ask_price: str | None) -> str | None:
        if bid_price is None or ask_price is None:
            return None
        bid = Decimal(bid_price)
        ask = Decimal(ask_price)
        if bid > ask:
            raise ValueError("invalid OKX quote: bid price is greater than ask price")
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
            raise ValueError(f"missing required OKX field: {field}")
        return str(value)
