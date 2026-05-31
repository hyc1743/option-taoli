from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from html import escape
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
            <td colspan="14" class="empty">No opportunities match the current filters.</td>
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
      vertical-align: top;
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
              <th>Direction</th>
              <th class="num">Gross profit</th>
              <th class="num">Net profit</th>
              <th class="num">Annualized</th>
              <th class="num">Slippage</th>
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
      min-width: 0;
      border-collapse: collapse;
    }}
    .legs th, .legs td {{
      white-space: normal;
    }}
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
              ("Strike", _value(candidate, "strike") or _strike_range(candidate)),
              ("Direction", _value(candidate, "direction")),
              ("Status", status),
          ])}
        </section>
        <section class="section">
          <h2>Economics</h2>
          {_render_key_values([
              ("Gross profit", _value(candidate, "gross_profit")),
              ("Net profit", _metric(candidate, "net_profit", fallback_field="gross_profit")),
              ("Annualized net return", _percent(_metric(candidate, "annualized_net_return", fallback_field="annualized_return"))),
              ("Total fees", _value(candidate, "total_fees")),
              ("Total slippage", _value(candidate, "total_slippage")),
              ("Funding impact", _value(candidate, "funding_impact")),
              ("Capital required", _value(candidate, "capital_required")),
          ])}
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
        <label>Exchange<select name="exchange"><option>All</option><option>deribit</option><option>binance</option><option>okx</option><option>bybit</option></select></label>
        <label>Underlying<input name="underlying" type="text" placeholder="BTC"></label>
        <label>Expiry<input name="expiry" type="date"></label>
        <label>Min net profit<input name="min_net_profit" type="number" step="0.01"></label>
        <label>Min annualized<input name="min_annualized" type="number" step="0.0001"></label>
        <label>Max slippage<input name="max_slippage" type="number" step="0.01"></label>
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
        f"""            <tr>
              <td>{_text(getattr(leg, "role", None))}</td>
              <td>{_text(getattr(leg, "side", None))}</td>
              <td>{_text(getattr(leg, "instrument_key", None))}</td>
              <td class="num">{_text(getattr(leg, "price", None))}</td>
              <td class="num">{_text(getattr(leg, "size", None))}</td>
            </tr>"""
        for leg in legs
    )
    if not rows:
        rows = """            <tr>
              <td colspan="5" class="empty">No execution legs available.</td>
            </tr>"""
    return f"""<table class="legs">
            <thead>
              <tr>
                <th>Role</th>
                <th>Side</th>
                <th>Instrument</th>
                <th class="num">Price</th>
                <th class="num">Size</th>
              </tr>
            </thead>
            <tbody>
{rows}
            </tbody>
          </table>"""


def _render_row(candidate: object) -> str:
    status = "Executable" if _value(candidate, "is_executable") is not False else "Blocked"
    status_class = "ok" if status == "Executable" else "blocked"
    tags = _risk_tags(candidate)
    tag_html = " ".join(f'<span class="tag">{escape(tag)}</span>' for tag in tags) if tags else ""
    cells = [
        _text(_value(candidate, "name"), fallback=_stable_name(candidate)),
        _text(_opportunity_type(candidate)),
        _text(_value(candidate, "exchange")),
        _text(_value(candidate, "underlying_id")),
        _text(_date_label(_value(candidate, "expiry_time_ms"))),
        _text(_value(candidate, "strike"), fallback=_strike_range(candidate)),
        _text(_value(candidate, "direction")),
        _text(_value(candidate, "gross_profit")),
        _text(_metric(candidate, "net_profit", fallback_field="gross_profit")),
        _text(_percent(_metric(candidate, "annualized_net_return", fallback_field="annualized_return"))),
        _text(_value(candidate, "total_slippage")),
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
              <td>{cells[6]}</td>
              <td class="num">{cells[7]}</td>
              <td class="num">{cells[8]}</td>
              <td class="num">{cells[9]}</td>
              <td class="num">{cells[10]}</td>
              <td class="num">{cells[11]}</td>
              <td class="num">{cells[12]}</td>
              <td class="{status_class}">{escape(status)}</td>
              <td>{tag_html}</td>
            </tr>"""


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
    return f"{lower}-{upper}"


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
    return datetime.fromtimestamp(value_ms / 1000, tz=UTC).isoformat(timespec="seconds")
