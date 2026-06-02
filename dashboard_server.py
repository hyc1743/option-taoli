#!/usr/bin/env python3
"""Arbitrage Dashboard Web Server — 无外部依赖。

用法:
    python3 dashboard_server.py [--port 8080]

访问 http://localhost:8080 查看看板。
页面加载时立即展示（内置示例数据），点击"实盘扫描"拉取多交易所实时数据。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent / "src"))

from option_taoli.monitor import ArbitrageMonitor, MarketDataBatch, MonitorConfig
from option_taoli.opportunity_history import OpportunityHistoryStore

# Import multi-exchange fetchers from scan_multi
from scan_multi import FETCHERS, ExchangeSnapshot

# ─── Config ─────────────────────────────────────────────────

CURRENCY = "BTC"
FEE_RATE = "0.0005"
CAPITAL_RATE = "0.1"
SCAN_EXCHANGES = list(FETCHERS.keys())  # all: deribit, binance, okx, bybit, gate
DEFAULT_SCAN_EXCHANGES = list(SCAN_EXCHANGES)
ROOT_DIR = Path(__file__).parent
CLIENT_ENTRY = ROOT_DIR / "src" / "dashboard_client.js"
CLIENT_BUNDLE = ROOT_DIR / "public" / "dashboard.bundle.js"
CLIENT_BUILD_INPUTS = [
    CLIENT_ENTRY,
    ROOT_DIR / "webpack.config.js",
    ROOT_DIR / "package.json",
    ROOT_DIR / "package-lock.json",
]

# ─── Global state ───────────────────────────────────────────

_scan_lock = threading.Lock()
_scan_result: dict[str, Any] | None = None
_scanning = False
_scan_error: str | None = None
_scan_time: str = "—"
_scan_progress: list[str] = []


def _empty_or_cached() -> dict:
    if _scan_result is not None:
        result = dict(_scan_result)
        result["scanning"] = _scanning
        result["progress"] = list(_scan_progress)
        if _scanning:
            result["status"] = "scanning"
        return result
    return {"opportunities": [], "total": 0, "atm_price": "—",
            "scanned_at": "—", "stats": {}, "error": None, "scanning": _scanning,
            "status": "scanning" if _scanning else "idle", "progress": list(_scan_progress)}


def _log(message: str) -> None:
    print(f"[dashboard] {time.strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)


def _progress(message: str) -> None:
    with _scan_lock:
        _scan_progress.append(f"{time.strftime('%H:%M:%S')} {message}")
        del _scan_progress[:-80]
    _log(message)


def _result_from_snapshots(
    snapshots: dict[str, ExchangeSnapshot],
    *,
    now_ms: int,
    partial: bool,
) -> dict[str, Any]:
    all_instruments = []
    all_quotes: dict[str, Any] = {}
    all_hedges: dict[tuple[str, str], Any] = {}
    atm_prices: dict[str, str] = {}

    for name, snap in snapshots.items():
        all_instruments.extend(snap.instruments)
        all_quotes.update(snap.quotes_by_key)
        if snap.hedge_quote and snap.hedge_key:
            all_hedges[snap.hedge_key] = snap.hedge_quote
        for hedge_key, hedge_quote in snap.extra_hedges:
            all_hedges[hedge_key] = hedge_quote
        if snap.atm_price > 0:
            atm_prices[name] = f"${snap.atm_price:,.0f}"

    atm_display = " | ".join(f"{k}:{v}" for k, v in atm_prices.items()) if atm_prices else "—"
    exch_info = {
        n: {"instruments": len(s.instruments), "errors": len(s.errors), "has_hedge": s.hedge_quote is not None}
        for n, s in snapshots.items()
    }

    if not all_instruments:
        return {
            "opportunities": [], "total": 0, "atm_price": atm_display,
            "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "scanned_at_ms": now_ms, "stats": {}, "error": None,
            "scanning": partial, "partial": partial, "exchanges": exch_info,
        }

    batch = MarketDataBatch(
        instruments=all_instruments,
        quotes_by_instrument_key=all_quotes,
        hedge_quotes_by_underlying=all_hedges,
    )

    store = None if partial else OpportunityHistoryStore("data/opportunities.sqlite3")
    monitor = ArbitrageMonitor(
        MonitorConfig(fee_rate=FEE_RATE, capital_requirement_rate=CAPITAL_RATE),
        history_store=store,
    )
    result = monitor.scan_once(batch, observed_at_ms=now_ms)

    opps = []
    for o in result.displayed_opportunities:
        d = {
            "id": o.opportunity_id,
            "type": o.opportunity_type,
            "exchange": o.exchange,
            "underlying": o.underlying_id,
            "expiry_ms": o.expiry_time_ms,
            "strike": o.strike,
            "lower_strike": o.lower_strike,
            "upper_strike": o.upper_strike,
            "direction": o.direction,
            "gross_profit": o.gross_profit,
            "annualized_return": o.annualized_net_return,
            "capital": o.capital_required,
            "executable": o.is_executable,
            "pcp_execution_mode": o.pcp_execution_mode,
            "risk_tags": o.risk_tags or [],
        }
        try:
            legs = getattr(o, "legs", [])
            if legs and not isinstance(legs, str):
                d["legs"] = [{"instrument_key": getattr(l, "instrument_key", ""),
                               "side": getattr(l, "side", ""),
                               "price": getattr(l, "price", ""),
                               "size": getattr(l, "size", ""),
                               "role": getattr(l, "role", "")} for l in legs]
        except Exception:
            pass
        opps.append(d)

    by_type: dict[str, int] = {}
    by_exchange: dict[str, int] = {}
    exec_count = 0
    for o in opps:
        by_type[o["type"]] = by_type.get(o["type"], 0) + 1
        by_exchange[o["exchange"]] = by_exchange.get(o["exchange"], 0) + 1
        if o["executable"]:
            exec_count += 1

    return {
        "opportunities": opps, "total": len(opps),
        "atm_price": atm_display,
        "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "scanned_at_ms": now_ms,
        "stats": {"by_type": by_type, "by_exchange": by_exchange, "executable": exec_count},
        "exchanges": exch_info,
        "error": None, "scanning": partial, "partial": partial,
    }


def _refresh_scan_result_from_snapshots(snapshots: dict[str, ExchangeSnapshot], *, now_ms: int, partial: bool) -> None:
    global _scan_result
    with _scan_lock:
        snapshot_copy = dict(snapshots)
    if not snapshot_copy:
        return
    try:
        result = _result_from_snapshots(snapshot_copy, now_ms=now_ms, partial=partial)
    except Exception as exc:
        _progress(f"partial result failed: {exc}")
        return
    _scan_result = result
    label = "partial result" if partial else "final result"
    _progress(f"{label}: opportunities={result.get('total', 0)} exchanges={len(snapshot_copy)}")


def _parse_scan_exchanges(value: str | None) -> list[str]:
    if not value:
        return list(DEFAULT_SCAN_EXCHANGES)
    requested = [part.strip().lower() for part in value.split(",") if part.strip()]
    selected = [exchange for exchange in requested if exchange in FETCHERS]
    if selected == ["deribit"]:
        return list(DEFAULT_SCAN_EXCHANGES)
    return selected or list(DEFAULT_SCAN_EXCHANGES)


def _do_scan(exchanges: list[str] | None = None):
    global _scan_result, _scanning, _scan_error, _scan_time, _scan_progress
    if _scanning:
        _progress("scan ignored: already running")
        return
    selected_exchanges = list(exchanges or DEFAULT_SCAN_EXCHANGES)
    with _scan_lock:
        _scan_progress = []
    _scanning = True
    try:
        now_ms = int(time.time() * 1000)
        _progress(f"scan started: exchanges={','.join(selected_exchanges)} currency={CURRENCY}")

        # Phase 1: parallel fetch all exchanges
        snapshots: dict[str, ExchangeSnapshot] = {}
        threads: list[threading.Thread] = []

        def _worker(exch: str):
            try:
                _progress(f"fetch {exch}: start")
                snap = FETCHERS[exch](now_ms)
                with _scan_lock:
                    snapshots[exch] = snap
                _progress(f"fetch {exch}: ok options={len(snap.instruments)} errors={len(snap.errors)}")
                _refresh_scan_result_from_snapshots(snapshots, now_ms=now_ms, partial=True)
            except Exception as exc:
                _progress(f"fetch {exch}: error {exc}")
                with _scan_lock:
                    snapshots[exch] = ExchangeSnapshot(exch, [], {}, None, None, 0, [str(exc)])
                _refresh_scan_result_from_snapshots(snapshots, now_ms=now_ms, partial=True)

        for ex in selected_exchanges:
            t = threading.Thread(target=_worker, args=(ex,), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join(timeout=120)

        _refresh_scan_result_from_snapshots(snapshots, now_ms=now_ms, partial=False)
        _scan_error = None
        final_total = _scan_result.get("total", 0) if _scan_result else 0
        final_exec = (_scan_result.get("stats", {}) or {}).get("executable", 0) if _scan_result else 0
        _progress(f"scan finished: opportunities={final_total} executable={final_exec}")
    except Exception as exc:
        _scan_error = str(exc)
        _progress(f"scan failed: {exc}")
        _scan_result = {"opportunities": [], "total": 0, "atm_price": "—",
                         "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                         "scanned_at_ms": 0, "stats": {}, "error": str(exc), "scanning": False,
                         "exchanges": {}}
    finally:
        _scan_time = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        _scanning = False


# ─── HTML Template ──────────────────────────────────────────

STYLE = """\
:root {
    color-scheme: light;
    --bg: #ffffff;
    --text: #000000;
    --muted: #6b7280;
    --faint: #9ca3af;
    --line: #111827;
    --soft-line: #d1d5db;
    --accent: #2563eb;
    --good: #047857;
    --bad: #dc2626;
    --warn: #b45309;
    --mono: "Fira Code VF", "Noto Sans Mono CJK SC", "Noto Sans Mono CJK TC", "Noto Sans", "Cascadia Code PL", "Lucida Console", Consolas, system-ui, monospace;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{background:var(--bg);color:var(--text);font-family:var(--mono);font-size:12px;line-height:1.35;-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
body{min-height:100vh;display:flex;flex-direction:column}
button,input,a{font:inherit}
button{border-radius:0}
a{color:var(--text);text-decoration:none}
a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* Header */
.shell{width:min(1016px,100%);margin:0 auto;min-height:100vh;display:flex;flex-direction:column;padding:0 16px}
.header{padding:12px 0 8px;display:flex;align-items:flex-start;justify-content:space-between;gap:24px}
.header-left{display:flex;align-items:baseline;gap:10px;min-width:0}
.header-logo{font-size:12px;font-weight:700;color:var(--text);white-space:nowrap}
.header-sub{font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.header-right{display:flex;gap:18px;align-items:center;justify-content:flex-end;flex-wrap:wrap}
.header-stat{font-size:12px;color:var(--text);white-space:nowrap}
.header-stat strong{font-weight:600}
.badge{display:inline-block;padding:0 4px;font-size:12px;font-weight:400;text-transform:none;border:1px solid var(--soft-line);background:var(--bg);color:var(--muted)}
.badge-live{color:var(--good);border-color:var(--good)}
.badge-err{color:var(--bad);border-color:var(--bad)}
.badge-idle{color:var(--muted);border-color:var(--soft-line)}
.rule{border:0;border-top:1px dashed var(--line);width:100%;height:0}

/* Stats bar */
.stats{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;padding:12px 0}
.stat{min-width:0}
.stat-label{font-size:12px;font-weight:400;color:var(--muted);margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.stat-value{font-size:12px;font-weight:700;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.stat-value.up{color:var(--warn)}
.stat-value.gr{color:var(--good)}

/* Controls */
.controls{display:flex;gap:10px 14px;padding:12px 0;align-items:center;flex-wrap:wrap}
.controls-spacer{flex:1}
.btn{min-height:28px;padding:2px 8px;font-size:12px;font-weight:600;cursor:pointer;border:1px solid var(--line);background:var(--bg);color:var(--text);user-select:none}
.btn:hover{background:#f3f4f6}
.btn:disabled{cursor:not-allowed;color:var(--faint);border-color:var(--soft-line)}
.btn-primary{color:var(--accent);border-color:var(--accent)}
.btn-sm{padding:2px 6px}
.pill{min-height:24px;padding:2px 8px;font-size:12px;font-weight:400;border:1px solid var(--soft-line);background:var(--bg);color:var(--muted);cursor:pointer;user-select:none}
.pill:hover{border-color:var(--line);color:var(--text)}
.pill.on,.pill[aria-pressed="true"]{border-color:var(--line);color:var(--text);background:#f9fafb}
.pill .count{font-size:12px;margin-left:3px;color:var(--muted)}
.pcp-filter{display:inline-flex;align-items:center;gap:4px;position:relative;flex-wrap:wrap}
.pcp-subfilter{display:inline-flex;align-items:center;gap:4px;padding-left:4px;border-left:1px solid var(--soft-line)}
.pcp-filter.pcp-off .pcp-subfilter{opacity:.55}
.exchange-filter{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.exchange-filter label{display:inline-flex;gap:3px;align-items:center;font-size:12px;color:var(--muted);cursor:pointer;user-select:none}
.exchange-filter label:has(input:checked){color:var(--text)}
.exchange-filter input{width:13px;height:13px;accent-color:var(--accent)}
.refresh-timer{font-size:12px;color:var(--muted);margin-left:2px}

/* Content */
.content{flex:1;padding:12px 0 56px;overflow-x:auto}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;min-width:920px}
thead th{position:sticky;top:0;background:var(--bg);border-bottom:1px dashed var(--line);padding:4px 6px;text-align:left;font-size:12px;font-weight:400;color:var(--muted);white-space:nowrap}
.sort-btn{border:0;background:transparent;color:inherit;padding:0;cursor:pointer;text-align:left}
.sort-btn:hover{text-decoration:underline;color:var(--text)}
thead th.sorted{color:var(--text)}
thead th .ar{font-size:12px;margin-left:2px;color:var(--muted)}
tbody td{padding:4px 6px;border-bottom:1px solid #eeeeee;font-size:12px;white-space:nowrap;vertical-align:middle}
tbody tr:hover{background:#f9fafb}
tbody tr.exec td:first-child{color:var(--good)}
tbody tr.noexec td:first-child{color:var(--muted)}
td.ty{font-weight:600;font-size:12px;cursor:pointer}
td.ty.pcp{color:var(--accent)}
td.ty.box{color:var(--warn)}
td.ty.ifb{color:var(--good)}
td.n{font-variant-numeric:tabular-nums}
td.n.up{color:var(--warn);font-weight:600}
td.n.rt{color:var(--warn)}
td.n.ca{color:var(--muted)}
.dir{display:inline-block;padding:1px 4px;font-size:12px;border:1px solid var(--soft-line);color:var(--muted)}
.rt{display:inline-flex;flex-wrap:wrap;gap:2px}
.rt span{display:inline-block;padding:1px 4px;font-size:12px;border:1px solid var(--soft-line);color:var(--muted)}
.rt span.inv{border-color:var(--warn);color:var(--warn)}
.rt span.warn{border-color:var(--bad);color:var(--bad)}

/* Detail */
.detail{display:none}
.detail.open{display:table-row}
.detail td{padding:10px 6px;background:#fafafa;border-bottom:1px dashed var(--line);white-space:normal}
.dg{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:6px 12px;margin-bottom:10px}
.dg dt{font-size:12px;font-weight:400;color:var(--muted)}
.dg dd{font-size:12px;font-weight:600;margin-top:1px;overflow-wrap:anywhere}
.dleg{margin-top:12px;font-size:12px;color:var(--muted);overflow-x:auto}
.dleg-title{font-size:12px;font-weight:700;color:var(--text);margin-bottom:6px}
.dleg table{min-width:860px;border-collapse:collapse}
.dleg th{padding:4px 6px;border-bottom:1px dashed var(--line);color:var(--muted);text-align:left;font-size:12px;font-weight:400}
.dleg td{padding:4px 6px;border-bottom:1px solid #eeeeee;background:transparent;white-space:normal}
.leg-action{font-weight:700;text-transform:uppercase}
.side-buy{color:var(--good)}
.side-sell{color:var(--bad)}
.sim-head{display:flex;align-items:center;gap:10px;margin-top:12px;margin-bottom:6px}
.sim-btn{border:1px solid var(--line);background:var(--bg);color:var(--text);font-size:12px;font-weight:600;padding:3px 8px;cursor:pointer}
.sim-btn:hover{text-decoration:underline}
.payoff-chart{display:none;border:1px dashed var(--line);padding:10px;margin:8px 0 12px;background:var(--bg)}
.payoff-chart.show{display:block}
.payoff-chart svg{width:100%;max-width:760px;height:auto;display:block}
.payoff-note{font-size:12px;color:var(--muted);margin-top:6px}

/* Status bar */
.status-bar{position:fixed;bottom:0;left:0;right:0;background:var(--bg);z-index:10}
.status-inner{width:min(1016px,100%);margin:0 auto;padding:8px 16px;border-top:1px dashed var(--line);font-size:12px;color:var(--text);display:flex;justify-content:space-between;align-items:center;gap:12px}
.status-actions{display:flex;align-items:center;gap:14px}
.link-button{border:0;background:transparent;color:var(--text);cursor:pointer;padding:0}
.link-button:hover{text-decoration:underline}

/* Empty */
.empty{padding:56px 0;text-align:center;color:var(--muted)}
.empty h2{font-size:12px;font-weight:700;color:var(--text);margin-bottom:8px}
.empty p{font-size:12px;max-width:520px;margin:0 auto 16px;line-height:1.6}
.empty .btn{display:inline-block}

/* Scanning indicator */
.scanning-bar{display:none;padding:8px 0;color:var(--warn);font-size:12px}
.scanning-bar.show{display:block}
.scanning-dots::after{content:'';animation:dots 1.5s steps(4,end) infinite}
@keyframes dots{0%{content:''}25%{content:'.'}50%{content:'..'}75%{content:'...'}}
.progress-panel{display:none;padding:8px 0;border-top:1px dashed var(--line);border-bottom:1px dashed var(--line);font-size:12px;color:var(--muted);max-height:170px;overflow:auto;white-space:pre-wrap}
.progress-panel.show{display:block}
.err-bar{display:none;padding:8px 0;color:var(--bad);font-size:12px}
.err-bar.show{display:block}

@media(max-width:700px){
    .shell{padding:0 16px}
    .header{display:block}
    .header-left{margin-bottom:8px}
    .header-right{justify-content:flex-start;gap:10px 16px}
    .stats{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 16px}
    .controls{gap:8px}
    .controls-spacer{display:none}
    .btn,.pill,.exchange-filter label,.link-button,a{min-height:44px;display:inline-flex;align-items:center}
    .btn,.pill{padding:0 10px}
    .exchange-filter input{width:16px;height:16px}
    table{min-width:760px}
    .status-inner{align-items:flex-start;flex-direction:column;padding:8px 16px}
    .content{padding-bottom:92px}
}
@media(prefers-reduced-motion:reduce){
    *,*::before,*::after{animation-duration:.001ms!important;animation-iteration-count:1!important;scroll-behavior:auto!important}
}
"""

HTML = """\
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>套利监控 · Arbitrage Monitor</title>
<style>{style}</style>
</head>
<body>

<div class="shell">
<header class="header">
  <div class="header-left">
    <span class="header-logo">Taoli Monitor</span>
    <span class="header-sub">Option Arbitrage Monitor</span>
  </div>
  <div class="header-right">
    <span class="header-stat">BTC <strong>{atm_price}</strong></span>
    <span class="header-stat">更新 <strong id="scan-time">{scanned_at}</strong></span>
    <span class="badge {status_class}" id="status-badge">{status_text}</span>
  </div>
</header>
<hr class="rule">

<div class="scanning-bar" id="scanning-bar">scan: <span id="scan-stage">等待后端扫描</span><span class="scanning-dots"></span></div>
<pre class="progress-panel" id="progress-log"></pre>
<div class="err-bar" id="err-bar">error: <span id="err-text"></span></div>

<div class="stats">
  <div class="stat"><div class="stat-label">套利机会</div><div class="stat-value" id="stat-total">{total}</div></div>
  <div class="stat"><div class="stat-label">可执行</div><div class="stat-value gr" id="stat-exec">{executable}</div></div>
  {exch_stats_html}
  {type_stats}
</div>
<hr class="rule">

<div class="controls">
  <button class="btn btn-primary" data-scan-button="1" id="btn-scan">Scan live</button>
  <span class="controls-spacer"></span>
  <span class="pcp-filter">
    <button type="button" class="pill on" data-type="put_call_parity" aria-pressed="true">PCP<span class="count"></span></button>
    <span class="pcp-subfilter">
      <button type="button" class="pill on" data-pcp-mode="same_exchange" aria-pressed="true">同所PCP<span class="count"></span></button>
      <button type="button" class="pill on" data-pcp-mode="cross_exchange" aria-pressed="true">跨所PCP<span class="count"></span></button>
    </span>
  </span>
  <button type="button" class="pill on" data-type="box_spread" aria-pressed="true">Box<span class="count"></span></button>
  <button type="button" class="pill on" data-type="implied_futures_basis" aria-pressed="true">IFB<span class="count"></span></button>
  <div class="exchange-filter" id="exchange-filter">
    <label><input type="checkbox" data-exchange="binance" checked>Binance</label>
    <label><input type="checkbox" data-exchange="okx" checked>OKX</label>
    <label><input type="checkbox" data-exchange="bybit" checked>Bybit</label>
    <label><input type="checkbox" data-exchange="gate" checked>Gate</label>
    <label><input type="checkbox" data-exchange="deribit" checked>Deribit</label>
  </div>
  <button type="button" class="btn btn-sm" id="refresh-toggle" aria-pressed="false">暂停刷新</button>
  <span id="refresh-timer" class="refresh-timer">--s</span>
</div>
<hr class="rule">

<div class="content">
  <div class="table-wrap">
    {table_html}
  </div>
</div>
</div>

<div class="status-bar">
  <div class="status-inner">
    <span>Multi-exchange BTC Options v2.0</span>
    <span class="status-actions"><button type="button" class="link-button" id="manual-scan">手动扫描</button><a href="/api/scan?cache=1">JSON API</a></span>
  </div>
</div>

<script>
window.__TAOLI_DATA__ = {opps_json};
window.__TAOLI_SCAN_STATE__ = {scan_json};
</script>
<script>{client_bundle}</script>
</body>
</html>"""


def _render(data: dict) -> str:
    stats = data.get("stats", {})
    by_type = stats.get("by_type", {})

    type_stats = ""
    for t, label in [("put_call_parity", "PCP"), ("box_spread", "Box"), ("implied_futures_basis", "IFB")]:
        cnt = by_type.get(t, 0)
        type_stats += f'<div class="stat"><div class="stat-label">{label}</div><div class="stat-value" data-stat-type="{t}">{cnt}</div></div>'

    exch_stats_html = ""
    exch_info = data.get("exchanges", {})
    if exch_info:
        exch_stats_html = '<div class="stat"><div class="stat-label">交易所</div><div class="stat-value" style="font-size:12px">' + \
            " ".join(f'{n}:{d.get("instruments",0)}' for n, d in sorted(exch_info.items())) + \
            '</div></div>'

    error = data.get("error")
    status_class = "badge-err" if error else ("badge-idle" if data.get("total", 0) == 0 else "badge-live")
    status_text = "ERROR" if error else ("IDLE" if data.get("total", 0) == 0 else "LIVE")

    table_html = _table(data.get("opportunities", []))

    template = HTML.replace("{{", "{").replace("}}", "}")
    return (template
            .replace("{style}", STYLE)
            .replace("{atm_price}", _esc(str(data.get("atm_price", "—"))))
            .replace("{scanned_at}", _esc(str(data.get("scanned_at", "—"))))
            .replace("{status_class}", status_class)
            .replace("{status_text}", status_text)
            .replace("{total}", str(data.get("total", 0)))
            .replace("{executable}", str(stats.get("executable", 0)))
            .replace("{type_stats}", type_stats)
            .replace("{exch_stats_html}", exch_stats_html)
            .replace("{table_html}", table_html)
            .replace("{opps_json}", json.dumps(data.get("opportunities", []), ensure_ascii=False))
            .replace("{scan_json}", json.dumps({
                "scanning": bool(data.get("scanning")),
                "progress": data.get("progress", []),
            }, ensure_ascii=False))
            .replace("{client_bundle}", _client_bundle())
            .replace("{currency}", CURRENCY))


def _table(opps: list[dict]) -> str:
    if not opps:
        return f"""<div class="empty">
<h2>等待数据</h2>
<p>尚未拉取多交易所实时数据。支持 Deribit / Binance / OKX / Bybit。扫描需要约 15-30 秒。</p>
<button class="btn btn-primary" data-scan-button="1">开始扫描</button>
</div>"""

    # Pass data to JS, render client-side
    return f"""<table>
<thead><tr>
    <th data-col="exchange" style="width:60px"><button type="button" class="sort-btn">交易所<span class="ar"></span></button></th>
    <th data-col="type" style="width:48px"><button type="button" class="sort-btn">类型<span class="ar"></span></button></th>
    <th data-col="expiry_ms" style="width:90px"><button type="button" class="sort-btn">行权日<span class="ar"></span></button></th>
    <th data-col="strike_display" style="width:90px"><button type="button" class="sort-btn">行权价<span class="ar"></span></button></th>
    <th data-col="gross_profit" style="width:90px"><button type="button" class="sort-btn">收益<span class="ar"></span></button></th>
    <th data-col="annualized_return" class="sorted" aria-sort="descending" style="width:80px"><button type="button" class="sort-btn">年化<span class="ar">desc</span></button></th>
    <th data-col="capital" style="width:80px"><button type="button" class="sort-btn">占用<span class="ar"></span></button></th>
    <th style="width:auto">风险<span class="ar"></span></th>
</tr></thead>
<tbody id="opp-tbody"></tbody></table>"""


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _client_bundle() -> str:
    return CLIENT_BUNDLE.read_text(encoding="utf-8")


def _dashboard_bundle_stale() -> bool:
    if not CLIENT_BUNDLE.exists():
        return True
    bundle_mtime = CLIENT_BUNDLE.stat().st_mtime
    return any(path.exists() and path.stat().st_mtime > bundle_mtime for path in CLIENT_BUILD_INPUTS)


def _ensure_dashboard_bundle(runner=subprocess.run) -> None:
    if not _dashboard_bundle_stale():
        return
    npm_cmd = _npm_command()
    if npm_cmd is None:
        if CLIENT_BUNDLE.exists():
            print("  → npm not found in PATH; using existing dashboard frontend bundle")
            return
        raise RuntimeError("npm is required to build the dashboard frontend bundle")
    if not (ROOT_DIR / "node_modules").exists():
        print("  → installing dashboard frontend dependencies")
        runner([*npm_cmd, "install"], cwd=ROOT_DIR, check=True)
    print("  → building obfuscated dashboard frontend")
    runner([*npm_cmd, "run", "build:dashboard"], cwd=ROOT_DIR, check=True)


def _npm_command() -> list[str] | None:
    npm_bin = os.environ.get("NPM_BIN")
    if npm_bin:
        return [npm_bin]
    if shutil.which("npm") is None:
        return None
    return ["npm"]



# ─── HTTP Handler ───────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        params = dict(__import__('urllib').parse.parse_qsl(self.path.split("?")[1] if "?" in self.path else ""))

        if path == "/" or path == "/index.html":
            result = _empty_or_cached()
            html = _render(result)
            self._respond(200, "text/html; charset=utf-8", html.encode("utf-8"))

        elif path == "/api/scan":
            live = params.get("live") == "1"
            cache = params.get("cache") == "1"

            if live:
                if _scanning:
                    self._respond(200, "application/json", json.dumps({"status": "scanning", "scanning": True}).encode())
                else:
                    selected_exchanges = _parse_scan_exchanges(params.get("exchanges"))
                    # return immediately, scan in background
                    _log(f"api scan requested: exchanges={','.join(selected_exchanges)}")
                    self._respond(200, "application/json", json.dumps({"status": "scanning", "scanning": True}).encode())
                    t = threading.Thread(target=_do_scan, args=(selected_exchanges,), daemon=True)
                    t.start()
            elif cache:
                result = _empty_or_cached()
                self._respond(200, "application/json", json.dumps(result, ensure_ascii=False).encode())
            else:
                self._respond(200, "application/json", json.dumps({"status": "use live=1 or cache=1"}).encode())

        elif path == "/api/health":
            self._respond(200, "application/json", b'{"ok":true}')

        else:
            self._respond(404, "text/plain", b"404")

    def _respond(self, status, ct, body):
        self.send_response(status)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        sys.stderr.write(
            "%s - - [%s] %s\n"
            % (self.address_string(), self.log_date_time_string(), format % args)
        )
        sys.stderr.flush()


def run_server(argv: list[str] | None = None, server_factory=HTTPServer, build_runner=subprocess.run):
    if argv is None:
        argv = sys.argv[1:]
    host = "0.0.0.0"
    port = 8080
    for a in argv:
        if a.startswith("--host="):
            host = a.split("=", 1)[1]
        if a.startswith("--port="):
            port = int(a.split("=", 1)[1])

    Path("data").mkdir(exist_ok=True)
    _ensure_dashboard_bundle(runner=build_runner)

    print(f"  套利监控看板")
    print(f"  → http://{host}:{port}")
    print(f"  → 首次加载立即展示，点击'实盘扫描'拉取 Deribit 数据")
    print()

    server = server_factory((host, port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  关闭")
        server.shutdown()


def main():
    run_server()


if __name__ == "__main__":
    main()
