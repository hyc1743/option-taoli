from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


ExchangeId = Literal["deribit", "binance", "okx", "bybit", "gate"]
MarketType = Literal["spot", "option", "perpetual", "future"]
OptionType = Literal["call", "put"]
ContractType = Literal["linear", "inverse", "quanto", "spot", "unknown"]
InstrumentStatus = Literal[
    "trading",
    "pre_launch",
    "delivering",
    "expired",
    "suspended",
    "unknown",
]
FeeSource = Literal["public_metadata", "authenticated_account", "static_config"]


@dataclass(frozen=True)
class Instrument:
    instrument_key: str
    exchange: ExchangeId
    market_type: MarketType
    instrument_id: str
    base_asset: str
    quote_asset: str
    contract_type: ContractType
    contract_size: str
    status: InstrumentStatus
    normalized_at_ms: int
    settlement_asset: str | None = None
    underlying_id: str | None = None
    instrument_family: str | None = None
    expiry_time_ms: int | None = None
    strike: str | None = None
    option_type: OptionType | None = None
    contract_value_currency: str | None = None
    tick_size: str | None = None
    min_order_size: str | None = None
    qty_step: str | None = None
    price_precision: int | None = None
    size_precision: int | None = None
    maker_fee_rate: str | None = None
    taker_fee_rate: str | None = None
    fee_source: FeeSource | None = None
    raw_symbol: str | None = None
    source_updated_at_ms: int | None = None
    raw: Any | None = None


@dataclass(frozen=True)
class Quote:
    instrument_key: str
    exchange: ExchangeId
    market_type: MarketType
    instrument_id: str
    received_at_ms: int
    normalized_at_ms: int
    bid_price: str | None = None
    ask_price: str | None = None
    bid_size: str | None = None
    ask_size: str | None = None
    mid_price: str | None = None
    last_price: str | None = None
    mark_price: str | None = None
    index_price: str | None = None
    underlying_price: str | None = None
    bid_iv: str | None = None
    ask_iv: str | None = None
    mark_iv: str | None = None
    delta: str | None = None
    gamma: str | None = None
    vega: str | None = None
    theta: str | None = None
    source_updated_at_ms: int | None = None
    raw: Any | None = None


@dataclass(frozen=True)
class OrderBookLevel:
    price: str
    size: str


@dataclass(frozen=True)
class OrderBook:
    instrument_key: str
    exchange: ExchangeId
    market_type: MarketType
    instrument_id: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    depth: int
    is_snapshot: bool
    received_at_ms: int
    normalized_at_ms: int
    sequence: str | None = None
    previous_sequence: str | None = None
    checksum: str | None = None
    event_time_ms: int | None = None
    transaction_time_ms: int | None = None
    raw: Any | None = None


@dataclass(frozen=True)
class FundingRate:
    instrument_key: str
    exchange: ExchangeId
    instrument_id: str
    received_at_ms: int
    normalized_at_ms: int
    funding_rate_current: str | None = None
    funding_rate_8h: str | None = None
    funding_time_ms: int | None = None
    next_funding_time_ms: int | None = None
    funding_interval_hours: str | None = None
    interest_rate: str | None = None
    premium: str | None = None
    source_updated_at_ms: int | None = None
    raw: Any | None = None
