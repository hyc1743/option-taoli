from option_taoli.execution_diagnostics import ExecutionDiagnosticConfig, diagnose_execution
from option_taoli.market_depth import ExecutableQuote
from option_taoli.monitor import MarketDataBatch
from option_taoli.put_call_parity import ArbitrageLeg, PutCallParityOpportunity


OBSERVED_AT_MS = 1810880000000
EXPIRY_24H_MS = OBSERVED_AT_MS + 86_400_000


def quote(
    key: str,
    *,
    market_type: str,
    bid: str,
    ask: str,
    bid_size: str = "3",
    ask_size: str = "3",
    received_at_ms: int = OBSERVED_AT_MS,
) -> ExecutableQuote:
    exchange, _, instrument_id = key.split(":", 2)
    return ExecutableQuote(
        instrument_key=key,
        exchange=exchange,
        market_type=market_type,  # type: ignore[arg-type]
        instrument_id=instrument_id,
        best_bid_price=bid,
        best_ask_price=ask,
        best_bid_size=bid_size,
        best_ask_size=ask_size,
        mid_price=str((float(bid) + float(ask)) / 2),
        spread=str(float(ask) - float(bid)),
        received_at_ms=received_at_ms,
        normalized_at_ms=received_at_ms,
    )


def pcp_opportunity(
    *,
    direction: str = "long_synthetic_short_hedge",
    hedge_key: str = "binance:perpetual:BTCUSDT",
    hedge_side: str = "sell",
) -> PutCallParityOpportunity:
    if direction == "long_synthetic_short_hedge":
        legs = [
            ArbitrageLeg("deribit:option:BTC-C", "buy", "6000", "1", "call"),
            ArbitrageLeg("deribit:option:BTC-P", "sell", "5200", "1", "put"),
            ArbitrageLeg(hedge_key, hedge_side, "100900", "1", "hedge"),  # type: ignore[arg-type]
        ]
        return PutCallParityOpportunity(
            exchange="cross_exchange",
            underlying_id="btc_usd",
            expiry_time_ms=EXPIRY_24H_MS,
            strike="100000",
            direction="long_synthetic_short_hedge",
            synthetic_forward_price="100800",
            hedge_price="100900",
            deviation="100",
            gross_profit="100",
            legs=legs,
            explanation="test",
        )
    return PutCallParityOpportunity(
        exchange="cross_exchange",
        underlying_id="btc_usd",
        expiry_time_ms=EXPIRY_24H_MS,
        strike="100000",
        direction="short_synthetic_long_hedge",
        synthetic_forward_price="101100",
        hedge_price="100900",
        deviation="200",
        gross_profit="200",
        legs=[
            ArbitrageLeg("deribit:option:BTC-C", "sell", "6100", "1", "call"),
            ArbitrageLeg("deribit:option:BTC-P", "buy", "5000", "1", "put"),
            ArbitrageLeg(hedge_key, hedge_side, "100900", "1", "hedge"),  # type: ignore[arg-type]
        ],
        explanation="test",
    )


def batch(
    *,
    hedge_key: str = "binance:perpetual:BTCUSDT",
    hedge_market: str = "perpetual",
    stale: bool = False,
    call_bid: str = "5900",
    call_ask: str = "6000",
    put_bid: str = "5200",
    put_ask: str = "5210",
) -> MarketDataBatch:
    received_at_ms = OBSERVED_AT_MS - 31_000 if stale else OBSERVED_AT_MS
    call = quote("deribit:option:BTC-C", market_type="option", bid=call_bid, ask=call_ask, received_at_ms=received_at_ms)
    put = quote("deribit:option:BTC-P", market_type="option", bid=put_bid, ask=put_ask, received_at_ms=received_at_ms)
    hedge = quote(hedge_key, market_type=hedge_market, bid="100900", ask="100910", received_at_ms=received_at_ms)
    return MarketDataBatch(
        instruments=[],
        quotes_by_instrument_key={
            call.instrument_key: call,
            put.instrument_key: put,
            hedge.instrument_key: hedge,
        },
        hedge_quotes_by_underlying={(hedge.exchange, "btc_usd"): hedge},
    )


def test_marks_profitable_fresh_liquid_cross_exchange_pcp_ready():
    diagnostic = diagnose_execution(
        pcp_opportunity(),
        batch(),
        ExecutionDiagnosticConfig(min_execution_net_profit="20"),
        observed_at_ms=OBSERVED_AT_MS,
        fee_rate="0",
    )

    assert diagnostic.status == "ready"
    assert diagnostic.strategy_type == "sell_future_buy_synthetic"
    assert diagnostic.anchor_leg == "call"
    assert diagnostic.maker_anchor_net_profit == "120.0"
    assert diagnostic.reject_reasons == []


def test_maps_short_synthetic_long_perpetual_to_buy_future_sell_synthetic():
    diagnostic = diagnose_execution(
        pcp_opportunity(direction="short_synthetic_long_hedge", hedge_side="buy"),
        batch(call_bid="6100", call_ask="6200", put_bid="4990", put_ask="5000"),
        ExecutionDiagnosticConfig(min_execution_net_profit="20"),
        observed_at_ms=OBSERVED_AT_MS,
        fee_rate="0",
    )

    assert diagnostic.status == "ready"
    assert diagnostic.strategy_type == "buy_future_sell_synthetic"


def test_marks_sell_spot_hedge_blocked():
    diagnostic = diagnose_execution(
        pcp_opportunity(hedge_key="binance:spot:BTCUSDT", hedge_side="sell"),
        batch(hedge_key="binance:spot:BTCUSDT", hedge_market="spot"),
        ExecutionDiagnosticConfig(min_execution_net_profit="20"),
        observed_at_ms=OBSERVED_AT_MS,
        fee_rate="0",
    )

    assert diagnostic.status == "blocked"
    assert "spot_short_not_supported" in diagnostic.reject_reasons


def test_marks_stale_quote_watch():
    diagnostic = diagnose_execution(
        pcp_opportunity(),
        batch(stale=True),
        ExecutionDiagnosticConfig(min_execution_net_profit="20", quote_max_age_seconds="30"),
        observed_at_ms=OBSERVED_AT_MS,
        fee_rate="0",
    )

    assert diagnostic.status == "watch"
    assert diagnostic.quote_fresh is False
    assert "stale_quote" in diagnostic.reject_reasons


def test_marks_placeholder_depth_watch():
    shallow = batch()
    placeholder = {
        key: quote(
            value.instrument_key,
            market_type=value.market_type,
            bid=value.best_bid_price,
            ask=value.best_ask_price,
            bid_size="1",
            ask_size="1",
        )
        for key, value in shallow.quotes_by_instrument_key.items()
    }
    diagnostic = diagnose_execution(
        pcp_opportunity(),
        MarketDataBatch(instruments=[], quotes_by_instrument_key=placeholder, hedge_quotes_by_underlying=shallow.hedge_quotes_by_underlying),
        ExecutionDiagnosticConfig(min_execution_net_profit="20"),
        observed_at_ms=OBSERVED_AT_MS,
        fee_rate="0",
    )

    assert diagnostic.status == "watch"
    assert "placeholder_depth" in diagnostic.reject_reasons
