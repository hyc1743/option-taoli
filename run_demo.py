"""最小 smoke run：生成一张静态看板 HTML 并启动本地文件服务。"""
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from option_taoli.adapters.deribit import DeribitAdapter
from option_taoli.monitor import ArbitrageMonitor, MarketDataBatch, MonitorConfig, MonitoredOpportunity
from option_taoli.market_depth import standardize_quote
from option_taoli.option_chain import build_option_chain
from option_taoli.put_call_parity import calculate_put_call_parity
from option_taoli.opportunity_adjustments import apply_opportunity_adjustments
from option_taoli.opportunity_history import OpportunityHistoryStore

HOST = "0.0.0.0"
PORT = 8080
OUT_DIR = Path("public")
OUT_DIR.mkdir(exist_ok=True)

# --- 1. 构建少量仿真数据（Deribit BTC 期权），跑一遍完整流程 ---
adapter = DeribitAdapter(normalized_at_ms=1810880000000, received_at_ms=1810880000123)

call_inst = adapter.normalize_instrument({
    "instrument_name": "BTC-27MAY27-100000-C", "kind": "option",
    "base_currency": "BTC", "quote_currency": "USD", "settlement_currency": "BTC",
    "expiration_timestamp": 1811744000000, "strike": "100000", "option_type": "call",
    "instrument_type": "reversed", "settlement_period": "month", "contract_size": "1",
    "tick_size": "0.5", "price_index": "btc_usd", "state": "open",
})
put_inst = adapter.normalize_instrument({
    "instrument_name": "BTC-27MAY27-100000-P", "kind": "option",
    "base_currency": "BTC", "quote_currency": "USD", "settlement_currency": "BTC",
    "expiration_timestamp": 1811744000000, "strike": "100000", "option_type": "put",
    "instrument_type": "reversed", "settlement_period": "month", "contract_size": "1",
    "tick_size": "0.5", "price_index": "btc_usd", "state": "open",
})

chain = build_option_chain([call_inst, put_inst])
pair = chain.complete_pairs()[0]

call_q = standardize_quote(adapter.normalize_quote(
    {"instrument_name": "BTC-27MAY27-100000-C", "best_bid_price": "5990", "best_ask_price": "6000",
     "best_bid_amount": "3", "best_ask_amount": "3", "timestamp": 1810880000000}, market_type="option"))
put_q = standardize_quote(adapter.normalize_quote(
    {"instrument_name": "BTC-27MAY27-100000-P", "best_bid_price": "5000", "best_ask_price": "5010",
     "best_bid_amount": "3", "best_ask_amount": "3", "timestamp": 1810880000000}, market_type="option"))
hedge_q = standardize_quote(adapter.normalize_quote(
    {"instrument_name": "BTC-PERPETUAL", "best_bid_price": "100900", "best_ask_price": "100910",
     "best_bid_amount": "2", "best_ask_amount": "2", "timestamp": 1810880000000}, market_type="perpetual"))

opp = calculate_put_call_parity(pair, call_q, put_q, hedge_q)
assert opp is not None
adj = apply_opportunity_adjustments(opp, fee_rate="0.0001", capital_requirement_rate="0.1", now_ms=1810880000000)

batch = MarketDataBatch(
    instruments=[call_inst, put_inst],
    quotes_by_instrument_key={call_q.instrument_key: call_q, put_q.instrument_key: put_q},
    hedge_quotes_by_underlying={("deribit", "btc_usd"): hedge_q},
)

# --- 2. 用 ArbitrageMonitor 完整跑一遍 ---
store = OpportunityHistoryStore(str(OUT_DIR / "opportunities.sqlite3"))
monitor = ArbitrageMonitor(
    MonitorConfig(fee_rate="0.0001", capital_requirement_rate="0.1"),
    history_store=store,
)
result = monitor.scan_once(batch, observed_at_ms=1810880000000)

# --- 3. 写出看板 HTML ---
(OUT_DIR / "index.html").write_text(result.dashboard_html, encoding="utf-8")
print(f"看板已生成：{OUT_DIR.resolve()}/index.html")

# --- 4. 启动本地文件服务 ---
print(f"启动本地 HTTP 服务 → http://localhost:{PORT}")
HTTPServer((HOST, PORT), SimpleHTTPRequestHandler).serve_forever()
