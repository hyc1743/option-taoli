from dataclasses import replace

from option_taoli.adapters.deribit import DeribitAdapter
from option_taoli.alert_rules import AlertRule
from option_taoli.market_depth import standardize_quote
from option_taoli.monitor import ArbitrageMonitor, MarketDataBatch, MonitorConfig
from option_taoli.opportunity_history import OpportunityHistoryStore
from option_taoli.webhook_alerts import WebhookAlertConfig, WebhookAlerter


class FakeWebhookHTTP:
    def __init__(self):
        self.calls = []

    def __call__(self, url: str, payload: dict, headers: dict[str, str], timeout_seconds: int) -> dict:
        self.calls.append((url, payload, headers, timeout_seconds))
        return {"status_code": 204, "body": ""}


class FakeSleeper:
    def __init__(self):
        self.intervals = []

    def __call__(self, interval_seconds: float) -> None:
        self.intervals.append(interval_seconds)


def deribit_pcp_batch() -> MarketDataBatch:
    adapter = DeribitAdapter(normalized_at_ms=1810880000000, received_at_ms=1810880000123)
    call = adapter.normalize_instrument(
        {
            "instrument_name": "BTC-27MAY27-100000-C",
            "kind": "option",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "BTC",
            "expiration_timestamp": 1811744000000,
            "strike": "100000",
            "option_type": "call",
            "instrument_type": "linear",
            "settlement_period": "month",
            "contract_size": "1",
            "tick_size": "0.5",
            "price_index": "btc_usd",
            "state": "open",
        }
    )
    put = adapter.normalize_instrument(
        {
            "instrument_name": "BTC-27MAY27-100000-P",
            "kind": "option",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "USD",
            "expiration_timestamp": 1811744000000,
            "strike": "100000",
            "option_type": "put",
            "instrument_type": "linear",
            "settlement_period": "month",
            "contract_size": "1",
            "tick_size": "0.5",
            "price_index": "btc_usd",
            "state": "open",
        }
    )
    call_quote = standardize_quote(
        adapter.normalize_quote(
            {
                "instrument_name": "BTC-27MAY27-100000-C",
                "best_bid_price": "5990",
                "best_ask_price": "6000",
                "best_bid_amount": "3",
                "best_ask_amount": "3",
                "timestamp": 1810880000000,
            },
            market_type="option",
        )
    )
    put_quote = standardize_quote(
        adapter.normalize_quote(
            {
                "instrument_name": "BTC-27MAY27-100000-P",
                "best_bid_price": "5000",
                "best_ask_price": "5010",
                "best_bid_amount": "3",
                "best_ask_amount": "3",
                "timestamp": 1810880000000,
            },
            market_type="option",
        )
    )
    hedge_quote = standardize_quote(
        adapter.normalize_quote(
            {
                "instrument_name": "BTC_USDC",
                "best_bid_price": "100900",
                "best_ask_price": "100910",
                "best_bid_amount": "2",
                "best_ask_amount": "2",
                "timestamp": 1810880000000,
            },
            market_type="spot",
        )
    )
    return MarketDataBatch(
        instruments=[call, put],
        quotes_by_instrument_key={
            call_quote.instrument_key: call_quote,
            put_quote.instrument_key: put_quote,
            hedge_quote.instrument_key: hedge_quote,
        },
        hedge_quotes_by_underlying={("deribit", "btc_usd"): hedge_quote},
    )


def test_scan_once_generates_opportunities_records_history_renders_dashboard_and_sends_alert(tmp_path):
    http = FakeWebhookHTTP()
    store = OpportunityHistoryStore(tmp_path / "history.sqlite3")
    monitor = ArbitrageMonitor(
        MonitorConfig(
            fee_rate="0.0001",
            capital_requirement_rate="0.1",
            alert_rule=AlertRule(
                min_net_profit="50",
                min_annualized_return="0.1",
                opportunity_types={"put_call_parity"},
            ),
        ),
        history_store=store,
        alerters=[
            WebhookAlerter(
                WebhookAlertConfig(url="https://alerts.example.test/hook"),
                http_post=http,
                history_store=store,
            )
        ],
    )

    result = monitor.scan_once(deribit_pcp_batch(), observed_at_ms=1810880000000)

    assert len(result.opportunities) == 2
    assert result.displayed_opportunities[0].opportunity_type == "put_call_parity"
    assert result.alert_candidates == [result.displayed_opportunities[0]]
    assert "put_call_parity" in result.dashboard_html
    assert "deribit" in result.dashboard_html
    assert [event.event_type for event in result.history_events] == ["created", "created"]
    assert http.calls[0][1]["opportunity"]["type"] == "put_call_parity"
    assert store.alerts(result.alert_candidates[0].opportunity_id)[0].status == "sent"


def test_polling_loop_fetches_batches_and_sleeps_between_cycles(tmp_path):
    calls = []
    sleeper = FakeSleeper()
    monitor = ArbitrageMonitor(
        MonitorConfig(alert_rule=AlertRule(min_net_profit="50")),
        history_store=OpportunityHistoryStore(tmp_path / "history.sqlite3"),
        sleep=sleeper,
    )

    def fetch_batch() -> MarketDataBatch:
        calls.append("fetch")
        return deribit_pcp_batch()

    results = monitor.run_polling(fetch_batch, interval_seconds=3, max_cycles=2, start_observed_at_ms=1810880000000)

    assert len(results) == 2
    assert calls == ["fetch", "fetch"]
    assert sleeper.intervals == [3]
    assert all(result.displayed_opportunities for result in results)


def test_scan_once_does_not_generate_short_spot_hedge_legs():
    batch = deribit_pcp_batch()
    hedge = next(iter(batch.hedge_quotes_by_underlying.values()))
    spot_hedge = type(hedge)(
        instrument_key="deribit:spot:BTC_USDC",
        exchange=hedge.exchange,
        market_type="spot",
        instrument_id="BTC_USDC",
        best_bid_price="101100",
        best_ask_price="101110",
        best_bid_size=hedge.best_bid_size,
        best_ask_size=hedge.best_ask_size,
        mid_price="101105",
        spread="10",
        received_at_ms=hedge.received_at_ms,
        normalized_at_ms=hedge.normalized_at_ms,
    )
    spot_batch = MarketDataBatch(
        instruments=batch.instruments,
        quotes_by_instrument_key=batch.quotes_by_instrument_key | {spot_hedge.instrument_key: spot_hedge},
        hedge_quotes_by_underlying={("deribit", "btc_usd"): spot_hedge},
    )

    result = ArbitrageMonitor(MonitorConfig()).scan_once(spot_batch, observed_at_ms=1810880000000)

    assert not [
        leg
        for opportunity in result.opportunities
        for leg in opportunity.legs
        if leg.instrument_key == "deribit:spot:BTC_USDC" and leg.side == "sell"
    ]


def test_scan_once_does_not_generate_long_perpetual_hedge_legs_when_spot_buy_is_available():
    batch = deribit_pcp_batch()
    spot_hedge = next(iter(batch.hedge_quotes_by_underlying.values()))
    perpetual_hedge = replace(
        spot_hedge,
        instrument_key="deribit:perpetual:BTC-PERPETUAL",
        market_type="perpetual",
        instrument_id="BTC-PERPETUAL",
        best_bid_price="100900",
        best_ask_price="100905",
    )
    mixed_batch = MarketDataBatch(
        instruments=batch.instruments,
        quotes_by_instrument_key=batch.quotes_by_instrument_key | {
            perpetual_hedge.instrument_key: perpetual_hedge
        },
        hedge_quotes_by_underlying={
            ("deribit", "btc_usd"): spot_hedge,
            ("deribit:perpetual", "btc_usd"): perpetual_hedge,
        },
    )

    result = ArbitrageMonitor(MonitorConfig()).scan_once(mixed_batch, observed_at_ms=1810880000000)

    assert [
        leg
        for opportunity in result.opportunities
        for leg in opportunity.legs
        if leg.instrument_key == spot_hedge.instrument_key and leg.side == "buy"
    ]
    assert not [
        leg
        for opportunity in result.opportunities
        for leg in opportunity.legs
        if leg.instrument_key == perpetual_hedge.instrument_key and leg.side == "buy"
    ]


def test_scan_once_detects_put_call_parity_across_exchanges():
    batch = deribit_pcp_batch()
    deribit_call, deribit_put = batch.instruments
    deribit_call_quote = batch.quotes_by_instrument_key[deribit_call.instrument_key]
    deribit_put_quote = batch.quotes_by_instrument_key[deribit_put.instrument_key]
    deribit_hedge_quote = next(iter(batch.hedge_quotes_by_underlying.values()))

    okx_put = replace(
        deribit_put,
        instrument_key="okx:option:BTC-27MAY27-100000-P",
        exchange="okx",
        instrument_id="BTC-27MAY27-100000-P-OKX",
    )
    okx_put_quote = replace(
        deribit_put_quote,
        instrument_key=okx_put.instrument_key,
        exchange="okx",
        instrument_id=okx_put.instrument_id,
        best_bid_price="5100",
        best_ask_price="5110",
    )
    binance_hedge_quote = replace(
        deribit_hedge_quote,
        instrument_key="binance:perpetual:BTCUSDT",
        exchange="binance",
        instrument_id="BTCUSDT",
        best_bid_price="101050",
        best_ask_price="101060",
    )
    batch = MarketDataBatch(
        instruments=[deribit_call, okx_put],
        quotes_by_instrument_key={
            deribit_call_quote.instrument_key: deribit_call_quote,
            okx_put_quote.instrument_key: okx_put_quote,
            binance_hedge_quote.instrument_key: binance_hedge_quote,
        },
        hedge_quotes_by_underlying={("binance", "btc_usd"): binance_hedge_quote},
    )

    result = ArbitrageMonitor(MonitorConfig()).scan_once(batch, observed_at_ms=1810880000000)

    pcp = [item for item in result.opportunities if item.opportunity_type == "put_call_parity"]
    assert len(pcp) == 1
    assert pcp[0].exchange == "cross_exchange"
    assert pcp[0].pcp_execution_mode == "cross_exchange"
    assert pcp[0].direction == "long_synthetic_short_hedge"
    assert pcp[0].gross_profit == "150"
    assert "cross_exchange_execution" in pcp[0].risk_tags
    assert [leg.instrument_key for leg in pcp[0].legs] == [
        deribit_call.instrument_key,
        okx_put.instrument_key,
        binance_hedge_quote.instrument_key,
    ]
    assert deribit_call.instrument_key in pcp[0].opportunity_id
    assert okx_put.instrument_key in pcp[0].opportunity_id
    assert binance_hedge_quote.instrument_key in pcp[0].opportunity_id


def test_scan_once_selects_best_hedge_across_same_and_cross_exchange_candidates():
    batch = deribit_pcp_batch()
    deribit_call, deribit_put = batch.instruments
    deribit_call_quote = batch.quotes_by_instrument_key[deribit_call.instrument_key]
    deribit_put_quote = batch.quotes_by_instrument_key[deribit_put.instrument_key]
    deribit_hedge_quote = next(iter(batch.hedge_quotes_by_underlying.values()))

    binance_hedge_quote = replace(
        deribit_hedge_quote,
        instrument_key="binance:perpetual:BTCUSDT",
        exchange="binance",
        market_type="perpetual",
        instrument_id="BTCUSDT",
        best_bid_price="101080",
        best_ask_price="101090",
    )
    batch = MarketDataBatch(
        instruments=[deribit_call, deribit_put],
        quotes_by_instrument_key={
            deribit_call_quote.instrument_key: deribit_call_quote,
            deribit_put_quote.instrument_key: deribit_put_quote,
            deribit_hedge_quote.instrument_key: deribit_hedge_quote,
            binance_hedge_quote.instrument_key: binance_hedge_quote,
        },
        hedge_quotes_by_underlying={
            ("deribit", "btc_usd"): deribit_hedge_quote,
            ("binance", "btc_usd"): binance_hedge_quote,
        },
    )

    result = ArbitrageMonitor(MonitorConfig()).scan_once(batch, observed_at_ms=1810880000000)

    pcp = [item for item in result.opportunities if item.opportunity_type == "put_call_parity"]
    cross_exchange_pcp = [item for item in pcp if item.pcp_execution_mode == "cross_exchange"]
    assert len(cross_exchange_pcp) == 1
    assert cross_exchange_pcp[0].gross_profit == "80"
    assert cross_exchange_pcp[0].legs[-1].instrument_key == binance_hedge_quote.instrument_key


def test_scan_once_skips_cross_exchange_pcp_when_option_contract_types_differ():
    batch = deribit_pcp_batch()
    deribit_call, deribit_put = batch.instruments
    deribit_call_quote = batch.quotes_by_instrument_key[deribit_call.instrument_key]
    deribit_put_quote = batch.quotes_by_instrument_key[deribit_put.instrument_key]
    deribit_hedge_quote = next(iter(batch.hedge_quotes_by_underlying.values()))

    inverse_put = replace(
        deribit_put,
        instrument_key="okx:option:BTC-27MAY27-100000-P",
        exchange="okx",
        instrument_id="BTC-27MAY27-100000-P-OKX",
        contract_type="inverse",
    )
    inverse_put_quote = replace(
        deribit_put_quote,
        instrument_key=inverse_put.instrument_key,
        exchange="okx",
        instrument_id=inverse_put.instrument_id,
        best_bid_price="5100",
        best_ask_price="5110",
    )

    batch = MarketDataBatch(
        instruments=[deribit_call, inverse_put],
        quotes_by_instrument_key={
            deribit_call_quote.instrument_key: deribit_call_quote,
            inverse_put_quote.instrument_key: inverse_put_quote,
            deribit_hedge_quote.instrument_key: deribit_hedge_quote,
        },
        hedge_quotes_by_underlying={("deribit", "btc_usd"): deribit_hedge_quote},
    )

    result = ArbitrageMonitor(MonitorConfig()).scan_once(batch, observed_at_ms=1810880000000)

    assert not [item for item in result.opportunities if item.opportunity_type == "put_call_parity"]
