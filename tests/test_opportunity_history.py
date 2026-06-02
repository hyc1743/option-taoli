from types import SimpleNamespace

from option_taoli.opportunity_history import OpportunityHistoryStore
from option_taoli.put_call_parity import ArbitrageLeg


def opportunity(
    name: str = "pcp-btc",
    *,
    net_profit: str = "120",
    risk_tags: list[str] | None = None,
    is_executable: bool = True,
):
    return SimpleNamespace(
        name=name,
        opportunity_type="put_call_parity",
        exchange="deribit",
        underlying_id="btc_usd",
        expiry_time_ms=1811744000000,
        strike="100000",
        direction="long_synthetic_short_hedge",
        synthetic_forward_price="95050",
        hedge_price="95100",
        deviation="50",
        gross_profit="150",
        net_profit=net_profit,
        annualized_net_return="0.42",
        total_slippage="3",
        capital_required="25000",
        is_executable=is_executable,
        risk_tags=risk_tags or [],
        legs=[
            ArbitrageLeg("deribit:option:BTC-C", "buy", "5000", "1", "call"),
            ArbitrageLeg("deribit:option:BTC-P", "sell", "9950", "1", "put"),
        ],
    )


def wrapped_opportunity():
    return SimpleNamespace(
        opportunity_type="implied_futures_basis",
        opportunity=SimpleNamespace(
            exchange="okx",
            underlying_id="BTC-USD",
            expiry_time_ms=1811830400000,
            strike="90000",
            direction="buy_implied_sell_actual",
            implied_futures_price="95050",
            actual_futures_price="95100",
            basis="50",
            gross_profit="50",
            risk_tags=["funding_rate_present"],
            legs=[ArbitrageLeg("okx:option:BTC-C", "buy", "5000", "1", "call")],
        ),
        adjustments=SimpleNamespace(
            net_profit="41",
            annualized_net_return="0.22",
            total_slippage="2",
            capital_required="10000",
            is_executable=True,
            risk_tags=["funding_credit_assumed"],
        ),
    )


def test_records_created_updated_and_disappeared_timeline(tmp_path):
    store = OpportunityHistoryStore(tmp_path / "history.sqlite3")

    created = store.record_observations([opportunity(net_profit="120")], observed_at_ms=1810880000000)
    opportunity_id = created[0].opportunity_id
    updated = store.record_observations(
        [opportunity(net_profit="140", risk_tags=["funding_cost_assumed"])],
        observed_at_ms=1810880060000,
    )
    disappeared = store.record_observations([], observed_at_ms=1810880120000)

    assert [event.event_type for event in created] == ["created"]
    assert [event.event_type for event in updated] == ["updated"]
    assert [event.event_type for event in disappeared] == ["disappeared"]

    timeline = store.timeline(opportunity_id)
    assert [event.event_type for event in timeline] == ["created", "updated", "disappeared"]
    assert timeline[0].snapshot.net_profit is None
    assert timeline[1].snapshot.net_profit is None
    assert timeline[0].snapshot.total_slippage is None
    assert timeline[1].snapshot.risk_tags == ["funding_cost_assumed"]
    assert timeline[1].snapshot.legs[0]["instrument_key"] == "deribit:option:BTC-C"
    assert timeline[2].snapshot.is_active is False


def test_persists_wrapped_opportunity_snapshot_and_reopens_store(tmp_path):
    db_path = tmp_path / "history.sqlite3"
    store = OpportunityHistoryStore(db_path)

    events = store.record_observations([wrapped_opportunity()], observed_at_ms=1810880000000)
    opportunity_id = events[0].opportunity_id

    reopened = OpportunityHistoryStore(db_path)
    snapshot = reopened.latest_snapshot(opportunity_id)

    assert snapshot is not None
    assert snapshot.opportunity_type == "implied_futures_basis"
    assert snapshot.exchange == "okx"
    assert snapshot.underlying_id == "BTC-USD"
    assert snapshot.implied_futures_price == "95050"
    assert snapshot.actual_futures_price == "95100"
    assert snapshot.basis == "50"
    assert snapshot.net_profit is None
    assert snapshot.total_slippage is None
    assert snapshot.annualized_net_return == "0.22"
    assert snapshot.risk_tags == ["funding_credit_assumed"]
    assert snapshot.legs == [{"instrument_key": "okx:option:BTC-C", "side": "buy", "price": "5000", "size": "1", "role": "call"}]


def test_records_alert_history_for_opportunity(tmp_path):
    store = OpportunityHistoryStore(tmp_path / "history.sqlite3")
    event = store.record_observations([opportunity()], observed_at_ms=1810880000000)[0]

    store.record_alert(
        event.opportunity_id,
        channel="telegram",
        sent_at_ms=1810880010000,
        status="sent",
        message="Net profit 120 above threshold",
    )

    alerts = store.alerts(event.opportunity_id)
    assert len(alerts) == 1
    assert alerts[0].channel == "telegram"
    assert alerts[0].sent_at_ms == 1810880010000
    assert alerts[0].status == "sent"
    assert alerts[0].message == "Net profit 120 above threshold"
