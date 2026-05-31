# 部署说明和运行文档

整理日期：2026-05-31

## 当前交付形态

本仓库当前交付为 Python 包 `option_taoli`，提供以下能力：

- 四家交易所行情 adapter：Deribit、Binance、OKX、Bybit。
- 四家交易所公共 REST 客户端：Deribit、Binance、OKX、Bybit。
- 统一行情模型、期权链构建、盘口和永续市场标准化。
- Put-Call Parity、Box Spread、隐含期货基差三类套利计算。
- 手续费、滑点、资金费率、资金占用后处理。
- 机会过滤、排序、静态 HTML 看板列表和详情页渲染。
- SQLite 历史记录、Telegram 报警、Webhook 报警和报警阈值筛选。
- `ArbitrageMonitor` 扫描编排层，支持单轮扫描和持续轮询。

当前版本内置公共 REST 客户端和行情 adapter，但没有内置 WebSocket 维护器、Web 服务入口或自动交易入口。生产部署应将本包作为监控 worker 的核心库使用：可以直接使用 `DeribitPublicClient`、`BinancePublicClient`、`OkxPublicClient`、`BybitPublicClient` 拉取官方公共 REST 快照，也可以由外层 WebSocket 采集任务获取实时行情，再交给 adapter 和 `ArbitrageMonitor` 完成标准化后扫描、计算、看板渲染、历史记录和报警。

## 环境要求

- Python 3.12 或兼容版本。
- 运行时依赖仅使用 Python 标准库。
- 开发和验证需要安装 `pytest`。
- 建议使用独立虚拟环境运行，避免和系统 Python 包冲突。

## 本地安装与验证

在项目根目录执行：

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --upgrade pip pytest
python3 -m pytest -q
python3 -m compileall -q src tests
find . -type d -name __pycache__ -prune -exec rm -rf {} +
```

当前验证基线为：

- `python3 -m pytest -q`：全部测试通过。
- `python3 -m compileall -q src tests`：源码和测试可编译。

## 运行方式

第一版建议以 worker 方式运行。外层采集器每轮返回一个 `MarketDataBatch`，`ArbitrageMonitor` 负责将该批标准化行情转换为机会、记录历史、生成看板 HTML，并向配置的报警渠道发送通知。

1. 交易所采集层使用内置公共 REST client 或外层 WebSocket 从官方接口拉取原始行情。
2. 调用对应 adapter 将原始 payload 转为 `Instrument`、`Quote`、`OrderBook`、`FundingRate`。
3. 调用 `standardize_quote()`、`standardize_order_book()`、`standardize_perpetual_state()` 构建 `MarketDataBatch`。
4. 调用 `ArbitrageMonitor.scan_once()` 执行单轮扫描，或调用 `ArbitrageMonitor.run_polling()` 按固定间隔持续扫描。
5. 将 `MonitorScanResult.dashboard_html` 写入静态看板文件；需要详情页时再对具体机会调用 `render_opportunity_detail_html()`。

最小 smoke run 可参考 `tests/test_end_to_end_integration.py`。持续扫描编排可参考 `tests/test_monitor.py`，覆盖单轮扫描、历史记录、看板 HTML、Webhook 报警和两轮 polling。

示例：

```python
from pathlib import Path

from option_taoli.alert_rules import AlertRule
from option_taoli.adapters.deribit import DeribitAdapter
from option_taoli.monitor import ArbitrageMonitor, MarketDataBatch, MonitorConfig
from option_taoli.opportunity_history import OpportunityHistoryStore
from option_taoli.public_clients import DeribitPublicClient
from option_taoli.webhook_alerts import WebhookAlertConfig, WebhookAlerter

store = OpportunityHistoryStore("data/opportunities.sqlite3")
deribit_client = DeribitPublicClient()
deribit_adapter = DeribitAdapter()
monitor = ArbitrageMonitor(
    MonitorConfig(
        fee_rate="0.0001",
        capital_requirement_rate="0.1",
        alert_rule=AlertRule(min_net_profit="100", min_annualized_return="0.10"),
    ),
    history_store=store,
    alerters=[
        WebhookAlerter(
            WebhookAlertConfig(url="https://alerts.example.test/hook"),
            history_store=store,
        )
    ],
)

def fetch_batch() -> MarketDataBatch:
    # 示例仅展示采集入口；生产中应补齐期权链、对冲腿和盘口快照的批量采集。
    raw = deribit_client.ticker(instrument_name="BTC-PERPETUAL")
    quote = deribit_adapter.normalize_quote(raw["result"], market_type="perpetual")
    ...

for result in monitor.run_polling(fetch_batch, interval_seconds=5, max_cycles=1):
    Path("public/index.html").write_text(result.dashboard_html, encoding="utf-8")
```

## 公共 REST 客户端

公共 REST 客户端位于 `option_taoli.public_clients`，只封装官方公共 market data URL 和 JSON 获取，不做鉴权、不做限频调度、不做自动重试。生产中应在外层按交易所官方限频做节流和失败重试。

```python
from option_taoli.public_clients import BinancePublicClient, BybitPublicClient, DeribitPublicClient, OkxPublicClient

deribit = DeribitPublicClient()
binance = BinancePublicClient()
okx = OkxPublicClient()
bybit = BybitPublicClient()

deribit.get_instruments(currency="BTC", kind="option", expired=False)
binance.usdm_premium_index(symbol="BTCUSDT")
okx.funding_rate(inst_id="BTC-USDT-SWAP")
bybit.tickers(category="linear", symbol="BTCUSDT")
```

客户端支持注入 `get_json`，测试或生产代理层可替换底层 HTTP 获取逻辑：

```python
client = DeribitPublicClient(get_json=my_rate_limited_json_getter)
```

## 历史记录

历史记录使用 SQLite 标准库实现：

```python
from option_taoli.opportunity_history import OpportunityHistoryStore

store = OpportunityHistoryStore("data/opportunities.sqlite3")
events = store.record_observations(adjusted_candidates, observed_at_ms=1810880000000)
```

部署时建议：

- 将 SQLite 文件放在持久化目录，例如 `data/opportunities.sqlite3`。
- 对该目录做定期备份。
- 单 worker 写入最简单；多进程写入时需要由外层调度保证写入节奏，避免长事务。

## 报警配置

Telegram 报警需要 Bot Token 和 Chat ID：

```python
from option_taoli.telegram_alerts import TelegramAlertConfig, TelegramAlerter

alerter = TelegramAlerter(
    TelegramAlertConfig(bot_token="BOT_TOKEN", chat_id="CHAT_ID"),
    history_store=store,
)
```

Webhook 报警需要目标 URL，可选共享密钥：

```python
from option_taoli.webhook_alerts import WebhookAlertConfig, WebhookAlerter

alerter = WebhookAlerter(
    WebhookAlertConfig(url="https://alerts.example.test/hook", secret="shared-secret"),
    history_store=store,
)
```

报警阈值由 `AlertRule` 管理。直接使用报警筛选时可调用 `select_alert_candidates()`；通过 `ArbitrageMonitor` 运行时，在 `MonitorConfig.alert_rule` 中配置即可。

```python
from option_taoli.alert_rules import AlertRule, select_alert_candidates

rule = AlertRule(
    min_net_profit="100",
    min_annualized_return="0.10",
    max_slippage="5",
    min_depth="1",
    opportunity_types={"put_call_parity", "box_spread", "implied_futures_basis"},
)
candidates = select_alert_candidates(adjusted_candidates, rule, suppressed_opportunity_ids=already_alerted_ids)
```

## 看板发布

看板渲染函数输出静态 HTML 字符串。使用 `ArbitrageMonitor` 时，`MonitorScanResult.dashboard_html` 已包含列表看板；生产运行时可写入静态文件目录，由 Nginx、Caddy、对象存储或内部门户发布：

```python
from pathlib import Path
from option_taoli.dashboard import render_opportunity_list_html

html = render_opportunity_list_html(adjusted_candidates, generated_at_ms=1810880000000)
Path("public/index.html").write_text(html, encoding="utf-8")
```

当前实现不会启动 HTTP 服务；如果需要实时 Web 看板，应在外层增加 Web 服务或静态文件发布流程。

## 生产运行建议

- 交易所公共行情应优先使用 WebSocket，REST 用于启动快照、元数据同步和断线恢复。
- 资金费率、手续费率、合约乘数和数量单位必须按交易所与市场类型区分，不能跨市场复用。
- 未配置 API key 时，账户实际费率不可用，应使用静态费率配置并在风险标签或运行配置中标明。
- 报警去重应使用稳定 `opportunity_id`，避免同一机会在每轮扫描中重复发送。
- 每轮扫描应记录 `observed_at_ms`、`received_at_ms`、`normalized_at_ms`，便于定位行情延迟。
- 生产部署前需要按目标交易所限频设置采集频率，并为 WebSocket 断线、序列缺口和 REST 重建做外层处理。

## 故障排查

- adapter 抛出 `ValueError`：检查交易所原始 payload 是否缺少必填字段，或字段格式是否与已调研接口不一致。
- 机会为空：检查期权链是否有完整 call/put 配对，bid/ask 是否可执行，过滤阈值是否过高。
- 净收益为负：检查手续费、滑点、资金费率和资金占用参数。
- 报警未发送：检查 `AlertRule` 是否筛掉机会、`opportunity_id` 是否已被去重、Telegram/Webhook 配置是否有效。
- 看板为空：先用同一候选列表调用 `filter_opportunities()`，确认不是筛选条件导致。
