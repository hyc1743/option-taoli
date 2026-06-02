#!/usr/bin/env python3
"""实盘扫描脚本：对接 Deribit 真实 API，扫描 USDC 结算 BTC 期权套利机会。

用法：
    python3 scan_real.py

输出：终端打印扫描摘要，并生成 public/index.html 看板文件。
"""

from __future__ import annotations

import json
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib import parse, request

from option_taoli.adapters.deribit import DeribitAdapter
from option_taoli.market_depth import ExecutableQuote, standardize_quote
from option_taoli.monitor import ArbitrageMonitor, MarketDataBatch, MonitorConfig
from option_taoli.opportunity_history import OpportunityHistoryStore
from option_taoli.public_clients import _url

# ---- 配置 ----
DERIBIT_OPTION_CURRENCY = "USDC"
DERIBIT_USDC_UNDERLYING = "btc_usdc"
DERIBIT_SPOT_INSTRUMENT = "BTC_USDC"
DERIBIT_BASE = "https://www.deribit.com/api/v2"
MAX_EXPIRIES = 5          # 只取最近 N 个到期日
STRIKE_RANGE_PCT = 15     # 行权价在现价 ± N% 范围内
FEE_RATE = "0.0001"       # 0.01% 手续费
CAPITAL_RATE = "0.1"      # 10% 资金占用率

OUT_DIR = Path("public")
OUT_DIR.mkdir(exist_ok=True)


def http_get_json(url: str, timeout_seconds: int = 15) -> dict[str, Any]:
    with request.urlopen(url, timeout=timeout_seconds) as resp:
        return json.loads(resp.read().decode("utf-8"))


def print_step(msg: str) -> None:
    print(f"  {msg}")


def main() -> None:
    now_ms = int(time.time() * 1000)
    adapter = DeribitAdapter(normalized_at_ms=now_ms, received_at_ms=now_ms)

    # ---- Step 1: 获取 USDC 结算 BTC 期权合约列表 ----
    print("=" * 64)
    print("实盘套利扫描 — Deribit BTC_USDC 期权")
    print("=" * 64)
    print_step("获取 USDC 结算 BTC 期权合约列表...")
    instruments_raw = http_get_json(
        _url(
            DERIBIT_BASE,
            "public/get_instruments",
            {"currency": DERIBIT_OPTION_CURRENCY, "kind": "option", "expired": "false"},
        )
    )
    all_instruments = [raw for raw in instruments_raw["result"] if _is_deribit_btc_usdc_option(raw)]
    print(f"    → {len(all_instruments)} 个活跃期权合约")

    # ---- Step 2: 获取现货报价（用于确定 ATM 和买入现货对冲）----
    print_step("获取 BTC_USDC 现货报价...")
    spot_ticker = http_get_json(
        _url(DERIBIT_BASE, "public/ticker", {"instrument_name": DERIBIT_SPOT_INSTRUMENT})
    )["result"]
    spot_quote = standardize_quote(adapter.normalize_quote(spot_ticker, market_type="spot"))
    atm_price = float(spot_quote.mid_price)
    print(f"    → BTC_USDC 现货中间价: ${atm_price:,.2f}")

    # ---- Step 3: 筛选范围 ----
    strike_min = atm_price * (1 - STRIKE_RANGE_PCT / 100)
    strike_max = atm_price * (1 + STRIKE_RANGE_PCT / 100)

    print_step(f"筛选行权价范围: ${strike_min:,.0f} ~ ${strike_max:,.0f}, 最近 {MAX_EXPIRIES} 个到期日")

    # 先找出前 N 个未过期的到期日
    all_expiries = sorted(
        {inst["expiration_timestamp"] for inst in all_instruments if inst.get("expiration_timestamp")},
    )
    target_expiries = set(all_expiries[:MAX_EXPIRIES])

    # 筛选范围内的期权
    selected_raw = []
    skipped = 0
    for inst in all_instruments:
        strike = inst.get("strike")
        expiry = inst.get("expiration_timestamp")
        if strike is None or expiry is None:
            skipped += 1
            continue
        try:
            strike_val = float(strike)
        except (ValueError, TypeError):
            skipped += 1
            continue
        if strike_min <= strike_val <= strike_max and expiry in target_expiries:
            selected_raw.append(inst)

    print(f"    → {len(selected_raw)} 个期权在筛选范围内")

    if not selected_raw:
        print("错误：没有筛选到任何期权，扩大 STRIKE_RANGE_PCT 或 MAX_EXPIRIES 再试。")
        sys.exit(1)

    # ---- Step 4: 获取 ticker 快照（逐个请求，加延迟以防限频）----
    print_step(f"获取 {len(selected_raw)} 个期权的 ticker 报价...")
    instruments = []
    quotes_by_key: dict[str, ExecutableQuote] = {}
    errors = 0

    for i, raw_inst in enumerate(selected_raw):
        instrument_name = raw_inst["instrument_name"]
        try:
            ticker_raw = http_get_json(
                _url(DERIBIT_BASE, "public/ticker", {"instrument_name": instrument_name})
            )["result"]
            inst = adapter.normalize_instrument(raw_inst)
            q = standardize_quote(adapter.normalize_quote(ticker_raw, market_type="option"))
            instruments.append(inst)
            quotes_by_key[q.instrument_key] = q
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"    ⚠ {instrument_name}: {e}")

        # 进度条 + 限频延迟
        if (i + 1) % 50 == 0:
            progress = (i + 1) / len(selected_raw) * 100
            print(f"    ... {i+1}/{len(selected_raw)} ({progress:.0f}%)")
        time.sleep(0.15)  # ~7 req/s, 远低于 Deribit 100/s 公共限频

    print(f"    → 获取完成: {len(instruments)} 个可用期权, {errors} 个失败")

    # ---- Step 5: 构建 MarketDataBatch 并扫描 ----
    hedge_quotes_by_underlying: dict[tuple[str, str], ExecutableQuote] = {
        ("deribit", DERIBIT_USDC_UNDERLYING): spot_quote,
    }

    batch = MarketDataBatch(
        instruments=instruments,
        quotes_by_instrument_key=quotes_by_key,
        hedge_quotes_by_underlying=hedge_quotes_by_underlying,
    )

    print_step("运行套利扫描...")
    store = OpportunityHistoryStore(str(OUT_DIR / "opportunities.sqlite3"))
    monitor = ArbitrageMonitor(
        MonitorConfig(
            fee_rate=FEE_RATE,
            capital_requirement_rate=CAPITAL_RATE,
        ),
        history_store=store,
    )
    result = monitor.scan_once(batch, observed_at_ms=now_ms)

    # ---- Step 6: 输出结果 ----
    print()
    print("=" * 64)
    print("扫描结果")
    print("=" * 64)
    print(f"  总机会数:     {len(result.opportunities)}")
    print(f"  展示机会数:   {len(result.displayed_opportunities)}")
    print(f"  报警候选:     {len(result.alert_candidates)}")
    print(f"  历史事件:     {len(result.history_events)}")
    print()

    # 按类型统计
    type_counts: dict[str, int] = {}
    for opp in result.displayed_opportunities:
        t = opp.opportunity_type
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"  类型分布: {type_counts}")

    # 可执行性
    executable = [o for o in result.displayed_opportunities if o.is_executable]
    print(f"  可执行:       {len(executable)}")

    # 展示前 10 条最佳机会
    print()
    if result.displayed_opportunities:
        print("─" * 64)
        print("前 10 条最佳机会（按净收益排序）:")
        print("─" * 64)
        for i, opp in enumerate(result.displayed_opportunities[:10]):
            print(f"\n  [{i+1}] {opp.opportunity_type}")
            print(f"      交易所: {opp.exchange}  标的: {opp.underlying_id}")
            if opp.strike:
                print(f"      行权价: {opp.strike}")
            elif opp.lower_strike and opp.upper_strike:
                print(f"      行权价区间: {opp.lower_strike} ~ {opp.upper_strike}")
            print(f"      方向: {opp.direction}")
            print(f"      毛收益: {opp.gross_profit}")
            print(f"      净收益: {opp.net_profit}")
            print(f"      年化收益率: {opp.annualized_net_return or 'N/A'}")
            print(f"      滑点: {opp.total_slippage}")
            print(f"      资金占用: {opp.capital_required}")
            print(f"      可执行: {opp.is_executable}")
            if opp.risk_tags:
                print(f"      风险标签: {', '.join(opp.risk_tags)}")
            # 打印腿信息
            try:
                legs = opp.legs
                if hasattr(opp.legs, '__iter__') if not isinstance(opp.legs, str) else False:
                    pass
            except Exception:
                pass
    else:
        print("  未发现套利机会。")
        print("  （这是正常的——实盘市场效率高，套利空间通常转瞬即逝）")

    # ---- Step 7: 生成看板 ----
    html_path = OUT_DIR / "index.html"
    html_path.write_text(result.dashboard_html, encoding="utf-8")
    print(f"\n看板已生成: file://{html_path.resolve()}")

    # 简单统计看板大小
    print(f"看板大小: {len(result.dashboard_html):,} bytes")

    # 清理
    if hasattr(store, 'close'):
        store.close()
    elif hasattr(store, '_conn'):
        store._conn.close()
    print("\n扫描完成。")


def _is_deribit_btc_usdc_option(raw: dict[str, Any]) -> bool:
    return (
        str(raw.get("price_index", "")).lower() == DERIBIT_USDC_UNDERLYING
        or str(raw.get("instrument_name", "")).startswith(f"{DERIBIT_SPOT_INSTRUMENT}-")
    )


if __name__ == "__main__":
    main()
