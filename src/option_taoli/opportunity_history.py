from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class OpportunitySnapshot:
    opportunity_id: str
    opportunity_type: str | None
    exchange: str | None
    underlying_id: str | None
    expiry_time_ms: int | None
    strike: str | None
    direction: str | None
    gross_profit: str | None
    net_profit: str | None
    annualized_net_return: str | None
    total_slippage: str | None
    capital_required: str | None
    is_executable: bool | None
    risk_tags: list[str]
    legs: list[dict[str, str | None]]
    observed_at_ms: int
    is_active: bool
    synthetic_forward_price: str | None = None
    hedge_price: str | None = None
    deviation: str | None = None
    fixed_cashflow: str | None = None
    entry_value: str | None = None
    implied_futures_price: str | None = None
    actual_futures_price: str | None = None
    basis: str | None = None


@dataclass(frozen=True)
class OpportunityTimelineEvent:
    opportunity_id: str
    event_type: str
    event_at_ms: int
    snapshot: OpportunitySnapshot


@dataclass(frozen=True)
class AlertRecord:
    opportunity_id: str
    channel: str
    sent_at_ms: int
    status: str
    message: str


class OpportunityHistoryStore:
    def __init__(self, db_path: str | Path):
        self._connection = sqlite3.connect(str(db_path))
        self._connection.row_factory = sqlite3.Row
        self._create_schema()

    def record_observations(
        self,
        opportunities: Iterable[object],
        *,
        observed_at_ms: int,
    ) -> list[OpportunityTimelineEvent]:
        snapshots = [_snapshot_from_candidate(candidate, observed_at_ms=observed_at_ms) for candidate in opportunities]
        observed_ids = {snapshot.opportunity_id for snapshot in snapshots}
        events: list[OpportunityTimelineEvent] = []

        with self._connection:
            for snapshot in snapshots:
                previous = self.latest_snapshot(snapshot.opportunity_id)
                if previous is None or not previous.is_active:
                    events.append(self._insert_event(snapshot, "created", observed_at_ms))
                elif _snapshot_payload(previous) != _snapshot_payload(snapshot):
                    events.append(self._insert_event(snapshot, "updated", observed_at_ms))
                self._upsert_latest(snapshot)

            for active_snapshot in self.active_snapshots():
                if active_snapshot.opportunity_id in observed_ids:
                    continue
                disappeared = _replace_snapshot_state(active_snapshot, observed_at_ms=observed_at_ms, is_active=False)
                events.append(self._insert_event(disappeared, "disappeared", observed_at_ms))
                self._upsert_latest(disappeared)

        return events

    def latest_snapshot(self, opportunity_id: str) -> OpportunitySnapshot | None:
        row = self._connection.execute(
            "select snapshot_json from latest_opportunities where opportunity_id = ?",
            (opportunity_id,),
        ).fetchone()
        if row is None:
            return None
        return _snapshot_from_json(row["snapshot_json"])

    def active_snapshots(self) -> list[OpportunitySnapshot]:
        rows = self._connection.execute(
            "select snapshot_json from latest_opportunities where is_active = 1 order by observed_at_ms, opportunity_id"
        ).fetchall()
        return [_snapshot_from_json(row["snapshot_json"]) for row in rows]

    def timeline(self, opportunity_id: str) -> list[OpportunityTimelineEvent]:
        rows = self._connection.execute(
            """
            select opportunity_id, event_type, event_at_ms, snapshot_json
            from opportunity_events
            where opportunity_id = ?
            order by event_at_ms, id
            """,
            (opportunity_id,),
        ).fetchall()
        return [
            OpportunityTimelineEvent(
                opportunity_id=row["opportunity_id"],
                event_type=row["event_type"],
                event_at_ms=row["event_at_ms"],
                snapshot=_snapshot_from_json(row["snapshot_json"]),
            )
            for row in rows
        ]

    def record_alert(
        self,
        opportunity_id: str,
        *,
        channel: str,
        sent_at_ms: int,
        status: str,
        message: str,
    ) -> AlertRecord:
        record = AlertRecord(
            opportunity_id=opportunity_id,
            channel=channel,
            sent_at_ms=sent_at_ms,
            status=status,
            message=message,
        )
        with self._connection:
            self._connection.execute(
                """
                insert into alert_records (opportunity_id, channel, sent_at_ms, status, message)
                values (?, ?, ?, ?, ?)
                """,
                (record.opportunity_id, record.channel, record.sent_at_ms, record.status, record.message),
            )
        return record

    def alerts(self, opportunity_id: str) -> list[AlertRecord]:
        rows = self._connection.execute(
            """
            select opportunity_id, channel, sent_at_ms, status, message
            from alert_records
            where opportunity_id = ?
            order by sent_at_ms, id
            """,
            (opportunity_id,),
        ).fetchall()
        return [
            AlertRecord(
                opportunity_id=row["opportunity_id"],
                channel=row["channel"],
                sent_at_ms=row["sent_at_ms"],
                status=row["status"],
                message=row["message"],
            )
            for row in rows
        ]

    def _insert_event(
        self,
        snapshot: OpportunitySnapshot,
        event_type: str,
        event_at_ms: int,
    ) -> OpportunityTimelineEvent:
        self._connection.execute(
            """
            insert into opportunity_events (opportunity_id, event_type, event_at_ms, snapshot_json)
            values (?, ?, ?, ?)
            """,
            (snapshot.opportunity_id, event_type, event_at_ms, _snapshot_to_json(snapshot)),
        )
        return OpportunityTimelineEvent(
            opportunity_id=snapshot.opportunity_id,
            event_type=event_type,
            event_at_ms=event_at_ms,
            snapshot=snapshot,
        )

    def _upsert_latest(self, snapshot: OpportunitySnapshot) -> None:
        self._connection.execute(
            """
            insert into latest_opportunities (opportunity_id, observed_at_ms, is_active, snapshot_json)
            values (?, ?, ?, ?)
            on conflict(opportunity_id) do update set
                observed_at_ms = excluded.observed_at_ms,
                is_active = excluded.is_active,
                snapshot_json = excluded.snapshot_json
            """,
            (
                snapshot.opportunity_id,
                snapshot.observed_at_ms,
                1 if snapshot.is_active else 0,
                _snapshot_to_json(snapshot),
            ),
        )

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                create table if not exists latest_opportunities (
                    opportunity_id text primary key,
                    observed_at_ms integer not null,
                    is_active integer not null,
                    snapshot_json text not null
                )
                """
            )
            self._connection.execute(
                """
                create table if not exists opportunity_events (
                    id integer primary key autoincrement,
                    opportunity_id text not null,
                    event_type text not null,
                    event_at_ms integer not null,
                    snapshot_json text not null
                )
                """
            )
            self._connection.execute(
                """
                create table if not exists alert_records (
                    id integer primary key autoincrement,
                    opportunity_id text not null,
                    channel text not null,
                    sent_at_ms integer not null,
                    status text not null,
                    message text not null
                )
                """
            )


def _snapshot_from_candidate(candidate: object, *, observed_at_ms: int) -> OpportunitySnapshot:
    opportunity_id = _opportunity_id(candidate)
    return OpportunitySnapshot(
        opportunity_id=opportunity_id,
        opportunity_type=_string_value(candidate, "opportunity_type") or _opportunity_type(candidate),
        exchange=_string_value(candidate, "exchange"),
        underlying_id=_string_value(candidate, "underlying_id"),
        expiry_time_ms=_int_value(candidate, "expiry_time_ms"),
        strike=_string_value(candidate, "strike") or _strike_range(candidate),
        direction=_string_value(candidate, "direction"),
        gross_profit=_string_value(candidate, "gross_profit"),
        net_profit=_string_value(candidate, "net_profit") or _string_value(candidate, "gross_profit"),
        annualized_net_return=_string_value(candidate, "annualized_net_return")
        or _string_value(candidate, "annualized_return"),
        total_slippage=_string_value(candidate, "total_slippage"),
        capital_required=_string_value(candidate, "capital_required"),
        is_executable=_bool_value(candidate, "is_executable"),
        risk_tags=_risk_tags(candidate),
        legs=_legs(candidate),
        observed_at_ms=observed_at_ms,
        is_active=True,
        synthetic_forward_price=_string_value(candidate, "synthetic_forward_price"),
        hedge_price=_string_value(candidate, "hedge_price"),
        deviation=_string_value(candidate, "deviation"),
        fixed_cashflow=_string_value(candidate, "fixed_cashflow"),
        entry_value=_string_value(candidate, "entry_value"),
        implied_futures_price=_string_value(candidate, "implied_futures_price"),
        actual_futures_price=_string_value(candidate, "actual_futures_price"),
        basis=_string_value(candidate, "basis"),
    )


def _opportunity_id(candidate: object) -> str:
    key_parts = [
        _string_value(candidate, "opportunity_type") or _opportunity_type(candidate),
        _string_value(candidate, "exchange"),
        _string_value(candidate, "underlying_id"),
        str(_int_value(candidate, "expiry_time_ms")),
        _string_value(candidate, "strike") or _strike_range(candidate),
        _string_value(candidate, "direction"),
    ]
    raw_key = "|".join(part or "" for part in key_parts)
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]


def _snapshot_payload(snapshot: OpportunitySnapshot) -> dict[str, object | None]:
    payload = _snapshot_to_dict(snapshot)
    payload.pop("observed_at_ms")
    payload.pop("is_active")
    return payload


def _replace_snapshot_state(
    snapshot: OpportunitySnapshot,
    *,
    observed_at_ms: int,
    is_active: bool,
) -> OpportunitySnapshot:
    data = _snapshot_to_dict(snapshot)
    data["observed_at_ms"] = observed_at_ms
    data["is_active"] = is_active
    return OpportunitySnapshot(**data)


def _snapshot_to_json(snapshot: OpportunitySnapshot) -> str:
    return json.dumps(_snapshot_to_dict(snapshot), sort_keys=True, separators=(",", ":"))


def _snapshot_from_json(value: str) -> OpportunitySnapshot:
    return OpportunitySnapshot(**json.loads(value))


def _snapshot_to_dict(snapshot: OpportunitySnapshot) -> dict[str, object | None]:
    return {
        "opportunity_id": snapshot.opportunity_id,
        "opportunity_type": snapshot.opportunity_type,
        "exchange": snapshot.exchange,
        "underlying_id": snapshot.underlying_id,
        "expiry_time_ms": snapshot.expiry_time_ms,
        "strike": snapshot.strike,
        "direction": snapshot.direction,
        "gross_profit": snapshot.gross_profit,
        "net_profit": snapshot.net_profit,
        "annualized_net_return": snapshot.annualized_net_return,
        "total_slippage": snapshot.total_slippage,
        "capital_required": snapshot.capital_required,
        "is_executable": snapshot.is_executable,
        "risk_tags": snapshot.risk_tags,
        "legs": snapshot.legs,
        "observed_at_ms": snapshot.observed_at_ms,
        "is_active": snapshot.is_active,
        "synthetic_forward_price": snapshot.synthetic_forward_price,
        "hedge_price": snapshot.hedge_price,
        "deviation": snapshot.deviation,
        "fixed_cashflow": snapshot.fixed_cashflow,
        "entry_value": snapshot.entry_value,
        "implied_futures_price": snapshot.implied_futures_price,
        "actual_futures_price": snapshot.actual_futures_price,
        "basis": snapshot.basis,
    }


def _value(candidate: object, field_name: str) -> object | None:
    if hasattr(candidate, field_name):
        return getattr(candidate, field_name)

    adjustments = getattr(candidate, "adjustments", None)
    if adjustments is not None and hasattr(adjustments, field_name):
        return getattr(adjustments, field_name)

    opportunity = getattr(candidate, "opportunity", None)
    if opportunity is not None and hasattr(opportunity, field_name):
        return getattr(opportunity, field_name)

    return None


def _string_value(candidate: object, field_name: str) -> str | None:
    value = _value(candidate, field_name)
    if value is None:
        return None
    return str(value)


def _int_value(candidate: object, field_name: str) -> int | None:
    value = _value(candidate, field_name)
    if value is None:
        return None
    return int(value)


def _bool_value(candidate: object, field_name: str) -> bool | None:
    value = _value(candidate, field_name)
    if value is None:
        return None
    return bool(value)


def _opportunity_type(candidate: object) -> str | None:
    source = getattr(candidate, "opportunity", candidate)
    class_name = source.__class__.__name__
    if class_name == "PutCallParityOpportunity":
        return "put_call_parity"
    if class_name == "BoxSpreadOpportunity":
        return "box_spread"
    if class_name == "ImpliedFuturesBasisOpportunity":
        return "implied_futures_basis"
    return None


def _strike_range(candidate: object) -> str | None:
    lower = _string_value(candidate, "lower_strike")
    upper = _string_value(candidate, "upper_strike")
    if lower is None or upper is None:
        return None
    return f"{lower}-{upper}"


def _risk_tags(candidate: object) -> list[str]:
    value = _value(candidate, "risk_tags")
    if value is None:
        return []
    return [str(tag) for tag in value]


def _legs(candidate: object) -> list[dict[str, str | None]]:
    value = _value(candidate, "legs") or []
    return [
        {
            "instrument_key": _optional_string(getattr(leg, "instrument_key", None)),
            "side": _optional_string(getattr(leg, "side", None)),
            "price": _optional_string(getattr(leg, "price", None)),
            "size": _optional_string(getattr(leg, "size", None)),
            "role": _optional_string(getattr(leg, "role", None)),
        }
        for leg in value
    ]


def _optional_string(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)
