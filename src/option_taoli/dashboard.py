from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from html import escape
import re
from typing import Iterable

from option_taoli.opportunity_filters import OpportunityFilter, filter_opportunities
from option_taoli.opportunity_sorting import OpportunitySort, sort_opportunities


def render_opportunity_list_html(
    opportunities: Iterable[object],
    *,
    filters: OpportunityFilter | None = None,
    sort: OpportunitySort | None = None,
    generated_at_ms: int | None = None,
) -> str:
    candidates = list(opportunities)
    if filters is not None:
        candidates = filter_opportunities(candidates, filters)
    candidates = sort_opportunities(candidates, sort)

    generated_at = "unknown" if generated_at_ms is None else _datetime_label(generated_at_ms)
    rows = "\n".join(_render_row(candidate) for candidate in candidates)
    if not rows:
        rows = """
          <tr>
            <td colspan="19" class="empty">No opportunities match the current filters.</td>
          </tr>"""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Option Arbitrage Monitor</title>
  <style>
    {_base_css()}
    .filters {{
      display: grid;
      grid-template-columns: repeat(8, minmax(120px, 1fr));
      gap: 0;
      border-bottom: 1px solid var(--line);
      border-top: 1px solid var(--line);
    }}
    label {{
      display: grid;
      gap: 6px;
      padding: 10px;
      border-right: 1px solid var(--line);
      color: var(--muted);
      font-size: 11px;
    }}
    select, input {{
      width: 100%;
      background: #0B0C0A;
      color: var(--text);
      border: 1px solid var(--line);
      padding: 7px 8px;
      font: inherit;
    }}
    .table-wrap {{ overflow-x: auto; }}
    table {{
      width: 100%;
      min-width: 1280px;
      border-collapse: collapse;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      border-right: 1px solid var(--line);
      padding: 10px;
      text-align: left;
      vertical-align: middle;
      white-space: nowrap;
    }}
    th {{
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      background: #000000;
      position: sticky;
      top: 0;
    }}
    td {{ font-size: 12px; }}
    .num {{ text-align: right; }}
    .ok {{ color: var(--signal); }}
    .blocked {{ color: var(--danger); }}
    .tag {{
      display: inline-block;
      border: 1px solid var(--line);
      padding: 2px 5px;
      margin: 0 4px 4px 0;
      color: var(--amber);
    }}
    .empty {{
      color: var(--muted);
      text-align: center;
      padding: 28px;
    }}
    @media (max-width: 900px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .rail {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      header {{ display: block; }}
      .filters {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <aside class="rail">
      <strong>{len(candidates)}</strong>
      <span>Displayed opportunities</span>
      <span>Generated {escape(generated_at)}</span>
    </aside>
    <main>
      <header>
        <h1>Option Arbitrage Monitor</h1>
        <span class="meta">Put-Call Parity, Box Spread, Implied Futures Basis</span>
      </header>
      {_render_filters()}
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Arbitrage type</th>
              <th>Exchange</th>
              <th>Underlying</th>
              <th>Expiry</th>
              <th>Strike</th>
              <th class="num">Profit</th>
              <th>Exec</th>
              <th>Anchor</th>
              <th class="num">Maker Net</th>
              <th class="num">Taker Net</th>
              <th class="num">DTE</th>
              <th class="num">Funding</th>
              <th>Reason</th>
              <th class="num">Annualized</th>
              <th class="num">Depth</th>
              <th class="num">Capital</th>
              <th>Status</th>
              <th>Risk tags</th>
            </tr>
          </thead>
          <tbody>
{rows}
          </tbody>
        </table>
      </div>
    </main>
  </div>
</body>
</html>
"""


def render_opportunity_detail_html(
    candidate: object,
    *,
    generated_at_ms: int | None = None,
) -> str:
    generated_at = "unknown" if generated_at_ms is None else _datetime_label(generated_at_ms)
    title = _text(_value(candidate, "name"), fallback=_stable_name(candidate))
    status = "Executable" if _value(candidate, "is_executable") is not False else "Blocked"
    status_class = "ok" if status == "Executable" else "blocked"
    tags = _risk_tags(candidate)
    tag_html = " ".join(f'<span class="tag">{escape(tag)}</span>' for tag in tags)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Opportunity Detail</title>
  <style>
    {_base_css()}
    .detail {{
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(360px, 0.9fr);
      gap: 0;
      border-bottom: 1px solid var(--line);
    }}
    .section {{
      border-right: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      padding: 18px;
      min-width: 0;
    }}
    h2 {{
      margin: 0 0 14px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.2;
      text-transform: uppercase;
    }}
    .kv {{
      display: grid;
      grid-template-columns: minmax(170px, 0.45fr) minmax(0, 1fr);
      border-top: 1px solid var(--line);
    }}
    .kv div {{
      padding: 10px 0;
      border-bottom: 1px solid var(--line);
    }}
    .kv div:nth-child(odd) {{
      color: var(--muted);
      padding-right: 14px;
    }}
    .logic {{
      margin: 0;
      color: var(--text);
      line-height: 1.6;
      white-space: normal;
    }}
    .legs {{
      width: 100%;
      min-width: 760px;
      border-collapse: collapse;
    }}
    .legs th, .legs td {{
      white-space: normal;
    }}
    .leg-action {{
      font-weight: 700;
      text-transform: uppercase;
    }}
    .side-buy {{ color: var(--signal); }}
    .side-sell {{ color: var(--danger); }}
    .tags {{
      min-height: 30px;
    }}
    @media (max-width: 980px) {{
      .detail {{ grid-template-columns: 1fr; }}
      .section {{ border-right: 0; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <aside class="rail">
      <strong>{escape(status)}</strong>
      <span>Opportunity status</span>
      <span>Generated {escape(generated_at)}</span>
    </aside>
    <main>
      <header>
        <h1>Opportunity Detail</h1>
        <span class="meta">{title}</span>
      </header>
      <div class="detail">
        <section class="section">
          <h2>Identity</h2>
          {_render_key_values([
              ("Name", _value(candidate, "name") or _stable_name(candidate)),
              ("Arbitrage type", _opportunity_type(candidate)),
              ("Exchange", _value(candidate, "exchange")),
              ("Underlying", _value(candidate, "underlying_id")),
              ("Expiry", _date_label(_value(candidate, "expiry_time_ms"))),
              ("Strike", _format_strike(_value(candidate, "strike")) or _strike_range(candidate)),
              ("Direction", _value(candidate, "direction")),
              ("Status", status),
          ])}
        </section>
        <section class="section">
          <h2>Economics</h2>
          {_render_key_values([
              ("Gross profit", _value(candidate, "gross_profit")),
              ("Annualized return", _percent(_metric(candidate, "annualized_net_return", fallback_field="annualized_return"))),
              ("Total fees", _value(candidate, "total_fees")),
              ("Funding impact", _value(candidate, "funding_impact")),
              ("Capital required", _value(candidate, "capital_required")),
          ])}
        </section>
        <section class="section">
          <h2>Execution diagnostic</h2>
          {_render_key_values(_execution_rows(candidate))}
        </section>
        <section class="section">
          <h2>Price relationship</h2>
          {_render_key_values(_price_relationships(candidate))}
        </section>
        <section class="section">
          <h2>Risk tags</h2>
          <div class="tags">{tag_html}</div>
        </section>
        <section class="section">
          <h2>Trade logic</h2>
          <p class="logic">{_text(_value(candidate, "explanation"))}</p>
        </section>
        <section class="section">
          <h2>Execution legs</h2>
          {_render_legs(candidate)}
        </section>
      </div>
    </main>
  </div>
</body>
</html>
"""


def _base_css() -> str:
    return """:root {
      color-scheme: dark;
      --bg: #0B0C0A;
      --panel: #11130F;
      --line: #30342C;
      --text: #E5E7E0;
      --muted: #8B9284;
      --signal: #00E676;
      --danger: #FF3B30;
      --amber: #FFB800;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #0B0C0A;
      color: var(--text);
      font-family: "IBM Plex Mono", "JetBrains Mono", monospace;
      font-variant-numeric: tabular-nums;
    }
    .layout {
      display: grid;
      grid-template-columns: 176px minmax(0, 1fr);
      min-height: 100vh;
    }
    .rail {
      border-right: 1px solid var(--line);
      padding: 18px 14px;
      background: #000000;
    }
    .rail strong {
      display: block;
      color: var(--signal);
      font-size: 24px;
      line-height: 1;
      margin-bottom: 10px;
      overflow-wrap: anywhere;
    }
    .rail span, .meta {
      display: block;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }
    main { min-width: 0; }
    header {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 24px;
      padding: 20px 24px;
      border-bottom: 1px solid var(--line);
    }
    h1 {
      margin: 0;
      font-size: 24px;
      line-height: 1.1;
      font-weight: 700;
    }
    .ok { color: var(--signal); }
    .blocked { color: var(--danger); }
    .tag {
      display: inline-block;
      border: 1px solid var(--line);
      padding: 2px 5px;
      margin: 0 4px 4px 0;
      color: var(--amber);
    }
    @media (max-width: 900px) {
      .layout { grid-template-columns: 1fr; }
      .rail { border-right: 0; border-bottom: 1px solid var(--line); }
      header { display: block; }
    }"""


def _render_filters() -> str:
    return """<section class="filters" aria-label="Opportunity filters">
        <label>Arbitrage type<select name="opportunity_type"><option>All</option><option>put_call_parity</option><option>box_spread</option><option>implied_futures_basis</option></select></label>
        <label>PCP mode<select name="pcp_execution_mode"><option>All</option><option>same_exchange</option><option>cross_exchange</option></select></label>
        <label>Exchange<select name="exchange"><option>All</option><option>deribit</option><option>binance</option><option>okx</option><option>bybit</option></select></label>
        <label>Underlying<input name="underlying" type="text" placeholder="BTC"></label>
        <label>Expiry<input name="expiry" type="date"></label>
        <label>Min gross profit<input name="min_net_profit" type="number" step="0.01"></label>
        <label>Min annualized<input name="min_annualized" type="number" step="0.0001"></label>
        <label>Min depth<input name="min_depth" type="number" step="0.01"></label>
      </section>"""


def _render_key_values(rows: list[tuple[str, object | None]]) -> str:
    values = "\n".join(f"            <div>{escape(label)}</div><div>{_text(value)}</div>" for label, value in rows)
    return f"""<div class="kv">
{values}
          </div>"""


def _price_relationships(candidate: object) -> list[tuple[str, object | None]]:
    rows = [
        ("Synthetic forward price", _value(candidate, "synthetic_forward_price")),
        ("Hedge price", _value(candidate, "hedge_price")),
        ("Deviation", _value(candidate, "deviation")),
        ("Fixed cashflow", _value(candidate, "fixed_cashflow")),
        ("Entry value", _value(candidate, "entry_value")),
        ("Implied futures price", _value(candidate, "implied_futures_price")),
        ("Actual futures price", _value(candidate, "actual_futures_price")),
        ("Basis", _value(candidate, "basis")),
        ("Funding rate current", _value(candidate, "funding_rate_current")),
        ("Funding rate 8h", _value(candidate, "funding_rate_8h")),
        ("Funding rate annualized", _value(candidate, "funding_rate_annualized")),
    ]
    return [(label, value) for label, value in rows if value is not None]


def _render_legs(candidate: object) -> str:
    legs = _value(candidate, "legs") or []
    rows = "\n".join(
        _render_leg_row(candidate, leg, index)
        for index, leg in enumerate(legs, start=1)
    )
    if not rows:
        rows = """            <tr>
              <td colspan="10" class="empty">No execution legs available.</td>
            </tr>"""
    return f"""<table class="legs">
            <thead>
              <tr>
                <th>#</th>
                <th>Action</th>
                <th>Exchange</th>
                <th>Market</th>
                <th>Contract</th>
                <th>Expiry</th>
                <th>Strike</th>
                <th>Role</th>
                <th class="num">Price</th>
                <th class="num">Size</th>
              </tr>
            </thead>
            <tbody>
{rows}
            </tbody>
          </table>"""


def _render_leg_row(candidate: object, leg: object, index: int) -> str:
    instrument = _parse_instrument_key(getattr(leg, "instrument_key", None))
    side = str(getattr(leg, "side", "") or "")
    side_class = "side-buy" if side == "buy" else "side-sell" if side == "sell" else ""
    action = _action_label(side)
    strike = _leg_strike(candidate, leg, instrument)
    return (
        f"""            <tr>
              <td class="num">{index}</td>
              <td><span class="leg-action {side_class}">{_text(action)}</span></td>
              <td>{_text(instrument["exchange"])}</td>
              <td>{_text(instrument["market"])}</td>
              <td title="{_text(getattr(leg, "instrument_key", None))}">{_text(instrument["contract"])}</td>
              <td>{_text(_date_label(_value(candidate, "expiry_time_ms")))}</td>
              <td>{_text(_format_strike(strike))}</td>
              <td>{_text(getattr(leg, "role", None))}</td>
              <td class="num">{_text(getattr(leg, "price", None))}</td>
              <td class="num">{_text(getattr(leg, "size", None))}</td>
            </tr>"""
    )


def _parse_instrument_key(value: object | None) -> dict[str, str | None]:
    if value is None:
        return {"exchange": None, "market": None, "contract": None}
    parts = str(value).split(":", 2)
    return {
        "exchange": parts[0] if len(parts) > 0 else None,
        "market": parts[1] if len(parts) > 1 else None,
        "contract": parts[2] if len(parts) > 2 else str(value),
    }


def _action_label(side: str) -> str:
    if side == "buy":
        return "Buy"
    if side == "sell":
        return "Sell"
    return side


def _leg_strike(candidate: object, leg: object, instrument: dict[str, str | None]) -> str | None:
    role = str(getattr(leg, "role", "") or "")
    if role.startswith("lower_"):
        return _string_or_none(_value(candidate, "lower_strike"))
    if role.startswith("upper_"):
        return _string_or_none(_value(candidate, "upper_strike"))
    if role in {"call", "put"}:
        return _string_or_none(_value(candidate, "strike"))
    if instrument["market"] == "option":
        return _strike_from_contract(instrument["contract"])
    return None


def _strike_from_contract(contract: str | None) -> str | None:
    if not contract:
        return None
    for segment in contract.split("-"):
        if re.fullmatch(r"\d+(?:\.\d+)?", segment):
            return segment
    return None


def _string_or_none(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _render_row(candidate: object) -> str:
    status = "Executable" if _value(candidate, "is_executable") is not False else "Blocked"
    status_class = "ok" if status == "Executable" else "blocked"
    execution_status = _execution_status(candidate)
    execution_class = "ok" if execution_status == "Ready" else "blocked" if execution_status == "Blocked" else ""
    tags = _risk_tags(candidate)
    tag_html = " ".join(f'<span class="tag">{escape(tag)}</span>' for tag in tags) if tags else ""
    cells = [
        _text(_value(candidate, "name"), fallback=_stable_name(candidate)),
        _text(_opportunity_type(candidate)),
        _text(_value(candidate, "exchange")),
        _text(_value(candidate, "underlying_id")),
        _text(_date_label(_value(candidate, "expiry_time_ms"))),
        _text(_format_strike(_value(candidate, "strike")), fallback=_strike_range(candidate)),
        _text(_value(candidate, "gross_profit")),
        _text(_diagnostic_value(candidate, "anchor_leg")),
        _text(_diagnostic_value(candidate, "maker_anchor_net_profit")),
        _text(_diagnostic_value(candidate, "all_taker_net_profit")),
        _text(_diagnostic_value(candidate, "dte_hours")),
        _text(_diagnostic_value(candidate, "estimated_funding_impact")),
        _text(", ".join(_execution_reasons(candidate))),
        _text(_percent(_metric(candidate, "annualized_net_return", fallback_field="annualized_return"))),
        _text(_value(candidate, "min_depth")),
        _text(_value(candidate, "capital_required")),
    ]
    return f"""            <tr>
              <td>{cells[0]}</td>
              <td>{cells[1]}</td>
              <td>{cells[2]}</td>
              <td>{cells[3]}</td>
              <td>{cells[4]}</td>
              <td>{cells[5]}</td>
              <td class="num">{cells[6]}</td>
              <td class="{execution_class}">{escape(execution_status)}</td>
              <td>{cells[7]}</td>
              <td class="num">{cells[8]}</td>
              <td class="num">{cells[9]}</td>
              <td class="num">{cells[10]}</td>
              <td class="num">{cells[11]}</td>
              <td>{cells[12]}</td>
              <td class="num">{cells[13]}</td>
              <td class="num">{cells[14]}</td>
              <td class="num">{cells[15]}</td>
              <td class="{status_class}">{escape(status)}</td>
              <td>{tag_html}</td>
            </tr>"""


def _execution_rows(candidate: object) -> list[tuple[str, object | None]]:
    return [
        ("Status", _execution_status(candidate)),
        ("Strategy type", _diagnostic_value(candidate, "strategy_type")),
        ("Anchor leg", _diagnostic_value(candidate, "anchor_leg")),
        ("Maker anchor net profit", _diagnostic_value(candidate, "maker_anchor_net_profit")),
        ("All taker net profit", _diagnostic_value(candidate, "all_taker_net_profit")),
        ("Estimated open fees", _diagnostic_value(candidate, "estimated_open_fees")),
        ("Estimated settlement cost", _diagnostic_value(candidate, "estimated_settlement_cost")),
        ("Estimated funding impact", _diagnostic_value(candidate, "estimated_funding_impact")),
        ("DTE hours", _diagnostic_value(candidate, "dte_hours")),
        ("Moneyness", _diagnostic_value(candidate, "moneyness")),
        ("Depth OK", _diagnostic_value(candidate, "depth_ok")),
        ("Quote fresh", _diagnostic_value(candidate, "quote_fresh")),
        ("Reasons", ", ".join(_execution_reasons(candidate)) or None),
    ]


def _execution_status(candidate: object) -> str:
    value = _diagnostic_value(candidate, "status")
    if value is None:
        return ""
    return str(value).replace("_", " ").title()


def _execution_reasons(candidate: object) -> list[str]:
    diagnostic = _value(candidate, "execution_diagnostic")
    if diagnostic is None:
        return []
    value = getattr(diagnostic, "reject_reasons", None)
    if not value:
        return []
    return [str(reason) for reason in value]


def _diagnostic_value(candidate: object, field_name: str) -> object | None:
    diagnostic = _value(candidate, "execution_diagnostic")
    if diagnostic is None or not hasattr(diagnostic, field_name):
        return None
    return getattr(diagnostic, field_name)


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


def _metric(candidate: object, field_name: str, *, fallback_field: str | None = None) -> str | None:
    value = _value(candidate, field_name)
    if value is None and fallback_field is not None:
        value = _value(candidate, fallback_field)
    if value is None:
        return None
    return str(value)


def _opportunity_type(candidate: object) -> str | None:
    explicit = _value(candidate, "opportunity_type")
    if explicit is not None:
        return str(explicit)
    source = getattr(candidate, "opportunity", candidate)
    class_name = source.__class__.__name__
    if class_name == "PutCallParityOpportunity":
        return "put_call_parity"
    if class_name == "BoxSpreadOpportunity":
        return "box_spread"
    if class_name == "ImpliedFuturesBasisOpportunity":
        return "implied_futures_basis"
    return None


def _risk_tags(candidate: object) -> list[str]:
    value = _value(candidate, "risk_tags")
    if value is None:
        return []
    return [str(tag) for tag in value]


def _stable_name(candidate: object) -> str:
    parts = [
        _opportunity_type(candidate),
        _value(candidate, "exchange"),
        _value(candidate, "underlying_id"),
        _value(candidate, "expiry_time_ms"),
        _value(candidate, "strike") or _strike_range(candidate),
    ]
    return ":".join(str(part) for part in parts if part is not None)


def _strike_range(candidate: object) -> str | None:
    lower = _value(candidate, "lower_strike")
    upper = _value(candidate, "upper_strike")
    if lower is None or upper is None:
        return None
    return f"{_format_strike(lower)}-{_format_strike(upper)}"


def _format_strike(value: object | None) -> str | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except Exception:
        return str(value)
    if number == number.to_integral_value():
        return str(number.quantize(Decimal("1")))
    return format(number.normalize(), "f")


def _text(value: object | None, *, fallback: object | None = None) -> str:
    if value is None:
        value = fallback
    if value is None:
        return ""
    return escape(str(value))


def _percent(value: str | None) -> str | None:
    if value is None:
        return None
    return f"{Decimal(value) * Decimal('100'):.2f}%"


def _date_label(value: object | None) -> str | None:
    if value is None:
        return None
    return _datetime_label(int(value))[:10]


def _datetime_label(value_ms: int) -> str:
    return datetime.fromtimestamp(value_ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")
