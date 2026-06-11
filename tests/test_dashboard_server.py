import dashboard_server
import re
import time
from pathlib import Path

from option_taoli.execution_diagnostics import ExecutionDiagnostic


CLIENT_SOURCE = Path("src/dashboard_client.js").read_text(encoding="utf-8")


class FakeServer:
    addresses = []

    def __init__(self, address, handler):
        self.address = address
        self.handler = handler
        self.shutdown_called = False
        FakeServer.addresses.append(address)

    def serve_forever(self):
        raise KeyboardInterrupt

    def shutdown(self):
        self.shutdown_called = True


def test_dashboard_server_defaults_to_all_interfaces(capsys):
    FakeServer.addresses.clear()

    dashboard_server.run_server(["--port=18080"], server_factory=FakeServer)

    out = capsys.readouterr().out
    assert FakeServer.addresses == [("0.0.0.0", 18080)]
    assert "http://0.0.0.0:18080" in out


def test_cache_response_reports_scan_in_progress():
    previous_result = dashboard_server._scan_result
    previous_scanning = dashboard_server._scanning
    previous_progress = list(dashboard_server._scan_progress)
    try:
        dashboard_server._scan_result = None
        dashboard_server._scanning = True
        dashboard_server._scan_progress = ["scan started", "fetch okx: start"]

        data = dashboard_server._empty_or_cached()

        assert data["scanning"] is True
        assert data["status"] == "scanning"
        assert data["progress"] == ["scan started", "fetch okx: start"]
    finally:
        dashboard_server._scan_result = previous_result
        dashboard_server._scanning = previous_scanning
        dashboard_server._scan_progress = previous_progress


def test_execution_diagnostic_serializes_for_scan_api():
    diagnostic = ExecutionDiagnostic(
        status="ready",
        strategy_type="sell_future_buy_synthetic",
        anchor_leg="call",
        all_taker_net_profit="95",
        maker_anchor_net_profit="120",
        estimated_open_fees="5",
        estimated_settlement_cost="1",
        estimated_funding_impact="-2",
        dte_hours="24",
        moneyness="0.01",
        depth_ok=True,
        quote_fresh=True,
        reject_reasons=[],
        risk_tags=["cross_exchange_execution"],
    )

    data = dashboard_server._execution_json(diagnostic)

    assert data["status"] == "ready"
    assert data["strategy_type"] == "sell_future_buy_synthetic"
    assert data["anchor_leg"] == "call"
    assert data["all_taker_net_profit"] == "95"
    assert data["maker_anchor_net_profit"] == "120"
    assert data["reject_reasons"] == []


def test_dashboard_bundle_stale_when_missing_or_source_is_newer(tmp_path, monkeypatch):
    bundle = tmp_path / "public" / "dashboard.bundle.js"
    source = tmp_path / "src" / "dashboard_client.js"
    bundle.parent.mkdir()
    source.parent.mkdir()
    source.write_text("source")
    monkeypatch.setattr(dashboard_server, "CLIENT_BUNDLE", bundle)
    monkeypatch.setattr(dashboard_server, "CLIENT_BUILD_INPUTS", [source])

    assert dashboard_server._dashboard_bundle_stale() is True

    bundle.write_text("bundle")
    old = time.time() - 20
    new = time.time()
    __import__("os").utime(bundle, (old, old))
    __import__("os").utime(source, (new, new))

    assert dashboard_server._dashboard_bundle_stale() is True


def test_dashboard_bundle_not_stale_when_bundle_is_newer(tmp_path, monkeypatch):
    bundle = tmp_path / "public" / "dashboard.bundle.js"
    source = tmp_path / "src" / "dashboard_client.js"
    bundle.parent.mkdir()
    source.parent.mkdir()
    bundle.write_text("bundle")
    source.write_text("source")
    old = time.time() - 20
    new = time.time()
    __import__("os").utime(source, (old, old))
    __import__("os").utime(bundle, (new, new))
    monkeypatch.setattr(dashboard_server, "CLIENT_BUNDLE", bundle)
    monkeypatch.setattr(dashboard_server, "CLIENT_BUILD_INPUTS", [source])

    assert dashboard_server._dashboard_bundle_stale() is False


def test_ensure_dashboard_bundle_installs_dependencies_before_build(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(dashboard_server, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(dashboard_server, "_dashboard_bundle_stale", lambda: True)
    monkeypatch.setattr(dashboard_server.shutil, "which", lambda name: "/usr/bin/npm")
    monkeypatch.delenv("NPM_BIN", raising=False)

    def fake_runner(cmd, cwd, check, env=None):
        calls.append((cmd, cwd, check))

    dashboard_server._ensure_dashboard_bundle(runner=fake_runner)

    assert calls == [
        (["npm", "install"], tmp_path, True),
        (["npm", "run", "build:dashboard"], tmp_path, True),
    ]


def test_ensure_dashboard_bundle_uses_npm_bin_env_when_npm_is_not_on_path(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(dashboard_server, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(dashboard_server, "_dashboard_bundle_stale", lambda: True)
    monkeypatch.setattr(dashboard_server.shutil, "which", lambda name: "/bin/bash" if name == "bash" else None)
    monkeypatch.setenv("NPM_BIN", "/opt/node/bin/npm")

    def fake_runner(cmd, cwd, check, env=None):
        calls.append((cmd, cwd, check))

    dashboard_server._ensure_dashboard_bundle(runner=fake_runner)

    assert calls == [
        (["/opt/node/bin/npm", "install"], tmp_path, True),
        (["/opt/node/bin/npm", "run", "build:dashboard"], tmp_path, True),
    ]


def test_ensure_dashboard_bundle_finds_npm_in_common_server_path(tmp_path, monkeypatch):
    npm = tmp_path / "nodejs" / "bin" / "npm"
    npm.parent.mkdir(parents=True)
    npm.write_text("#!/bin/sh\n")
    calls = []
    monkeypatch.setattr(dashboard_server, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(dashboard_server, "COMMON_NPM_PATHS", [npm])
    monkeypatch.setattr(dashboard_server, "_dashboard_bundle_stale", lambda: True)
    monkeypatch.setattr(dashboard_server.shutil, "which", lambda name: "/bin/bash" if name == "bash" else None)
    monkeypatch.delenv("NPM_BIN", raising=False)

    def fake_runner(cmd, cwd, check, env=None):
        calls.append((cmd, cwd, check))

    dashboard_server._ensure_dashboard_bundle(runner=fake_runner)

    assert calls == [
        ([str(npm), "install"], tmp_path, True),
        ([str(npm), "run", "build:dashboard"], tmp_path, True),
    ]


def test_ensure_dashboard_bundle_finds_npm_in_versioned_server_path(tmp_path, monkeypatch):
    npm = tmp_path / "server" / "nodejs" / "v22.16.0" / "bin" / "npm"
    npm.parent.mkdir(parents=True)
    npm.write_text("#!/bin/sh\n")
    calls = []
    monkeypatch.setattr(dashboard_server, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(dashboard_server, "COMMON_NPM_PATHS", [])
    monkeypatch.setattr(dashboard_server, "NPM_SEARCH_ROOTS", [tmp_path / "server" / "nodejs"])
    monkeypatch.setattr(dashboard_server, "_dashboard_bundle_stale", lambda: True)
    monkeypatch.setattr(dashboard_server.shutil, "which", lambda name: None)
    monkeypatch.delenv("NPM_BIN", raising=False)

    def fake_runner(cmd, cwd, check, env=None):
        calls.append((cmd, cwd, check))

    dashboard_server._ensure_dashboard_bundle(runner=fake_runner)

    assert calls == [
        ([str(npm), "install"], tmp_path, True),
        ([str(npm), "run", "build:dashboard"], tmp_path, True),
    ]


def test_ensure_dashboard_bundle_adds_npm_bin_dir_to_path(tmp_path, monkeypatch):
    npm = tmp_path / "nodejs" / "v22.20.0" / "bin" / "npm"
    npm.parent.mkdir(parents=True)
    npm.write_text("#!/bin/sh\n")
    calls = []
    monkeypatch.setattr(dashboard_server, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(dashboard_server, "COMMON_NPM_PATHS", [npm])
    monkeypatch.setattr(dashboard_server, "_dashboard_bundle_stale", lambda: True)
    monkeypatch.setattr(dashboard_server.shutil, "which", lambda name: None)
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.delenv("NPM_BIN", raising=False)

    def fake_runner(cmd, cwd, check, env=None):
        calls.append((cmd, cwd, check, env))

    dashboard_server._ensure_dashboard_bundle(runner=fake_runner)

    assert calls[0][3]["PATH"].startswith(f"{npm.parent}:/usr/bin")
    assert calls[1][3]["PATH"].startswith(f"{npm.parent}:/usr/bin")


def test_npm_command_finds_npm_from_login_shell(monkeypatch):
    class Result:
        stdout = "/root/.nvm/versions/node/v22.0.0/bin/npm\n"

    monkeypatch.setattr(dashboard_server.shutil, "which", lambda name: "/bin/bash" if name == "bash" else None)
    monkeypatch.setattr(dashboard_server, "COMMON_NPM_PATHS", [])
    monkeypatch.setattr(dashboard_server.subprocess, "run", lambda *args, **kwargs: Result())
    monkeypatch.delenv("NPM_BIN", raising=False)

    assert dashboard_server._npm_command() == ["/root/.nvm/versions/node/v22.0.0/bin/npm"]


def test_npm_command_uses_bin_bash_when_bash_is_not_on_path(monkeypatch):
    class Result:
        stdout = "/usr/local/node/bin/npm\n"

    monkeypatch.setattr(dashboard_server.Path, "exists", lambda self: str(self) == "/bin/bash")
    monkeypatch.setattr(dashboard_server.shutil, "which", lambda name: None)
    monkeypatch.setattr(dashboard_server, "COMMON_NPM_PATHS", [])
    monkeypatch.setattr(dashboard_server, "NPM_SEARCH_ROOTS", [])
    monkeypatch.setattr(dashboard_server.subprocess, "run", lambda *args, **kwargs: Result())
    monkeypatch.delenv("NPM_BIN", raising=False)

    assert dashboard_server._npm_command() == ["/usr/local/node/bin/npm"]


def test_ensure_dashboard_bundle_uses_existing_bundle_when_npm_is_missing(tmp_path, monkeypatch, capsys):
    bundle = tmp_path / "public" / "dashboard.bundle.js"
    bundle.parent.mkdir()
    bundle.write_text("bundle")
    monkeypatch.setattr(dashboard_server, "CLIENT_BUNDLE", bundle)
    monkeypatch.setattr(dashboard_server, "COMMON_NPM_PATHS", [])
    monkeypatch.setattr(dashboard_server, "NPM_SEARCH_ROOTS", [])
    monkeypatch.setattr(dashboard_server, "_dashboard_bundle_stale", lambda: True)
    monkeypatch.setattr(dashboard_server, "_npm_from_login_shell", lambda: None)
    monkeypatch.setattr(dashboard_server.shutil, "which", lambda name: None)
    monkeypatch.delenv("NPM_BIN", raising=False)

    calls = []
    dashboard_server._ensure_dashboard_bundle(runner=lambda *args, **kwargs: calls.append((args, kwargs)))

    assert calls == []
    assert "npm not found in PATH" in capsys.readouterr().out


def test_ensure_dashboard_bundle_skips_when_current(monkeypatch):
    calls = []
    monkeypatch.setattr(dashboard_server, "_dashboard_bundle_stale", lambda: False)

    dashboard_server._ensure_dashboard_bundle(runner=lambda *args, **kwargs: calls.append((args, kwargs)))

    assert calls == []


def test_render_outputs_valid_javascript_braces_and_progress_panel():
    previous_result = dashboard_server._scan_result
    previous_scanning = dashboard_server._scanning
    previous_progress = list(dashboard_server._scan_progress)
    try:
        dashboard_server._scan_result = None
        dashboard_server._scanning = True
        dashboard_server._scan_progress = ["07:40:00 fetch deribit: start"]

        html = dashboard_server._render(dashboard_server._empty_or_cached())
    finally:
        dashboard_server._scan_result = previous_result
        dashboard_server._scanning = previous_scanning
        dashboard_server._scan_progress = previous_progress

    assert "window.__TAOLI_DATA__ =" in html
    assert "window.__TAOLI_SCAN_STATE__ =" in html
    assert "function renderAll()" not in html
    assert "var oppData" not in html
    assert 'id="progress-log"' in html
    assert 'data-scan-button="1"' in html
    assert "resumeScanIfNeeded();" not in html
    assert "resumeScanIfNeeded();" in CLIENT_SOURCE
    assert "fetch deribit: start" in html
    assert "attempt > 180" in CLIENT_SOURCE
    assert "function applyScanData(d)" in CLIENT_SOURCE
    assert "function ensureTable()" in CLIENT_SOURCE
    assert "if (oppData.length) {" in CLIENT_SOURCE
    assert "rebuildTableRows();" in CLIENT_SOURCE
    assert "同所PCP" in html
    assert "跨所PCP" in html
    assert "data-pcp-mode" in html
    assert 'class="pcp-filter"' in html
    assert 'class="pcp-subfilter"' in html


def test_main_table_shows_expiry_hides_direction_and_refreshes_filter_counts():
    html = dashboard_server._render(
        {
            "opportunities": [
                {
                    "id": "pcp-1",
                    "type": "put_call_parity",
                    "exchange": "deribit",
                    "underlying": "btc_usd",
                    "expiry_ms": 1811744000000,
                    "strike": "100000",
                    "direction": "long_synthetic_short_hedge",
                    "gross_profit": "50",
                    "annualized_return": "0.2",
                    "capital": "10000",
                    "executable": True,
                    "pcp_execution_mode": "same_exchange",
                    "risk_tags": [],
                    "legs": [],
                }
            ],
            "total": 1,
            "atm_price": "$100,000",
            "scanned_at": "2027-05-21 00:00:00 UTC",
            "stats": {"executable": 1, "by_type": {"put_call_parity": 1}},
            "error": None,
            "scanning": False,
        }
    )

    assert "行权日" in html
    assert "方向" not in html
    assert "毛收益" not in html
    assert "收益" in html
    assert "'<td class=\"n\">'+tsToDate(o.expiry_ms)+'</td>'" in CLIENT_SOURCE
    assert "'<td><span class=\"dir\">'+o.direction+'</span></td>'" not in CLIENT_SOURCE
    assert 'data-col="annualized_return" class="sorted" aria-sort="descending"' in html
    assert "var sortCol = 'annualized_return', sortAsc = false;" in CLIENT_SOURCE
    assert "sortOppData(sortCol, sortAsc);" in CLIENT_SOURCE
    assert "vertical-align:middle" in html
    assert "function displayStrike(o)" in CLIENT_SOURCE
    assert "function fmtStrike(v)" in CLIENT_SOURCE
    assert "var s = displayStrike(o);" in CLIENT_SOURCE

    apply_scan_body = re.search(r"function applyScanData\(d\) \{(.*?)\n\}", CLIENT_SOURCE, re.S)
    assert apply_scan_body is not None
    assert "updateCounts();" in apply_scan_body.group(1)
    assert "sortOppData(sortCol, sortAsc);" in apply_scan_body.group(1)


def test_render_includes_execution_leg_table_columns():
    data = {
        "opportunities": [
            {
                "id": "deribit:pcp:btc_usd:1811744000000:100000:long",
                "type": "put_call_parity",
                "exchange": "deribit",
                "underlying": "btc_usd",
                "expiry_ms": 1811744000000,
                "strike": "100000",
                "lower_strike": None,
                "upper_strike": None,
                "direction": "long_synthetic_short_hedge",
                "gross_profit": "50",
                "annualized_return": "0.2",
                "capital": "10000",
                "executable": True,
                "pcp_execution_mode": "same_exchange",
                "risk_tags": [],
                "legs": [
                    {
                        "instrument_key": "deribit:option:BTC-27JUN25-100000-C",
                        "side": "buy",
                        "price": "5000",
                        "size": "1",
                        "role": "call",
                    }
                ],
            }
        ],
        "total": 1,
        "atm_price": "$100,000",
        "scanned_at": "2027-05-21 00:00:00 UTC",
        "stats": {"executable": 1, "by_type": {"put_call_parity": 1}},
        "error": None,
        "scanning": False,
    }

    html = dashboard_server._render(data)

    assert "执行腿" in CLIENT_SOURCE
    assert "动作" in CLIENT_SOURCE
    assert "交易所" in html
    assert "市场" in CLIENT_SOURCE
    assert "合约" in CLIENT_SOURCE
    assert "行权价" in html
    assert "价格" in CLIENT_SOURCE
    assert "数量" in CLIENT_SOURCE
    assert "legStrike(o, l)" in CLIENT_SOURCE
    assert "一键模拟" in CLIENT_SOURCE
    assert "function simulatePayoff" in CLIENT_SOURCE
    assert "function legPayoffAtExpiry" in CLIENT_SOURCE
    assert "payoff-chart-" in CLIENT_SOURCE
    assert "净收益" not in html
    assert "滑点" not in html


def test_detail_toggle_uses_consistent_dom_safe_ids():
    assert "function domId(value)" in CLIENT_SOURCE
    assert "var id = domId(o.id || '');" in CLIENT_SOURCE
    assert 'id="detail-\'+id+\'"' in CLIENT_SOURCE
    assert 'aria-controls="detail-\'+id+\'' in CLIENT_SOURCE
    assert 'onclick="toggleDetail(&quot;\'+id+\'&quot;, this)"' in CLIENT_SOURCE
    assert 'id="payoff-chart-\'+id+\'' in CLIENT_SOURCE
    assert 'id="detail-\'+o.id+\'' not in CLIENT_SOURCE
    assert "payoff-chart-'+esc(o.id)" not in CLIENT_SOURCE


def test_render_preserves_open_detail_rows_across_table_rebuilds():
    html = dashboard_server._render(
        {
            "opportunities": [],
            "total": 0,
            "atm_price": "—",
            "scanned_at": "2027-05-21 00:00:00 UTC",
            "stats": {"executable": 0, "by_type": {}},
            "error": None,
            "scanning": False,
        }
    )

    assert "var openDetailIds = new Set();" in CLIENT_SOURCE
    assert "openDetailIds.add(id);" in CLIENT_SOURCE
    assert "restoreOpenDetails();" in CLIENT_SOURCE
    assert "function refreshCachedData()" in CLIENT_SOURCE
    assert "var REFRESH_SECONDS = 6;" in CLIENT_SOURCE
    assert 'id="refresh-toggle" aria-pressed="false">暂停刷新</button>' in html
    assert "var refreshPaused = false;" in CLIENT_SOURCE
    assert "refreshPaused = !refreshPaused;" in CLIENT_SOURCE
    assert "refreshToggle.textContent = refreshPaused ? '继续刷新' : '暂停刷新';" in CLIENT_SOURCE
    assert "if (refreshPaused) return;" in CLIENT_SOURCE
    assert "selectedExchangeParam()" in CLIENT_SOURCE
    assert "function rowMatchesSelectedExchange(row, activeExchanges)" in CLIENT_SOURCE
    assert "function updateVisibleCounts(types, pcpModes, exec, total)" in CLIENT_SOURCE
    assert "window.toggleDetail = toggleDetail;" in CLIENT_SOURCE
    assert "window.simulatePayoff = simulatePayoff;" in CLIENT_SOURCE
    assert "input.addEventListener('change', updateTable);" in CLIENT_SOURCE
    assert "rowId.indexOf(exchange + ':') >= 0" in CLIENT_SOURCE
    assert 'data-exchange="\'+esc(o.exchange || \'\')+\'"' in CLIENT_SOURCE
    assert "data-exchange=\"deribit\"" in html
    assert "data-exchange=\"deribit\" checked" in html
    assert "selected = ['deribit', 'binance', 'okx', 'bybit', 'gate'];" in CLIENT_SOURCE
    assert "fetch('/api/scan?live=1&exchanges=' + encodeURIComponent(selectedExchangeParam()))" in CLIENT_SOURCE
    assert "_countdown = REFRESH_SECONDS;" in CLIENT_SOURCE
    assert "location.reload()" not in html
    assert "data-col=\"net_profit\"" not in html
    assert "data-col=\"slippage\"" not in html


def test_parse_scan_exchanges_defaults_to_all_exchanges():
    assert dashboard_server._parse_scan_exchanges(None) == ["deribit", "binance", "okx", "bybit", "gate"]
    assert dashboard_server._parse_scan_exchanges("") == ["deribit", "binance", "okx", "bybit", "gate"]


def test_parse_scan_exchanges_accepts_deribit_when_requested():
    assert dashboard_server._parse_scan_exchanges("deribit,okx,unknown") == ["deribit", "okx"]


def test_parse_scan_exchanges_adds_external_hedges_for_deribit_only():
    assert dashboard_server._parse_scan_exchanges("deribit") == ["deribit", "binance", "okx", "bybit", "gate"]


def test_http_log_message_is_visible(capsys):
    handler = dashboard_server.Handler.__new__(dashboard_server.Handler)
    handler.address_string = lambda: "127.0.0.1"
    handler.requestline = "GET /api/health HTTP/1.1"

    handler.log_request(200, 11)

    captured = capsys.readouterr()
    assert "GET /api/health HTTP/1.1" in captured.err
    assert "200" in captured.err
