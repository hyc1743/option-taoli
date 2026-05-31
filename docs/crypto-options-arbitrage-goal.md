# 加密货币期权套利看板与监控报警系统 Goal 草案

## Goal

开发一个加密货币期权套利监控系统，接入 Deribit、Binance、OKX、Bybit 四个交易所的期权、现货和永续合约行情数据，用于实时发现、量化和跟踪期权定价偏差套利机会，并通过网页看板和报警提醒帮助用户快速判断是否存在可执行的低风险套利空间。

系统第一版必须同时实现以下三类套利监控，不分阶段延期：

- Put-Call Parity 套利
- Box Spread 套利
- 隐含期货基差套利

系统第一版定位为监控、分析和报警系统，不默认自动交易。

## 套利类型

### Put-Call Parity 套利

监控同一标的、同一到期日、同行权价的看涨期权、看跌期权与现货或期货价格之间的平价关系。

当价格关系出现偏离时，系统应自动计算理论价差、交易方向、对冲组合、预估收益、手续费影响和执行后的净套利空间。例如：买入看涨、卖出看跌合成多头，同时做空标的，以对冲方向风险并锁定价差。

### Box Spread 套利

监控由两组不同行权价构成的盒式价差组合，包括牛市看涨价差与熊市看跌价差。

系统应计算盒式头寸的固定到期现金流、理论贴现价值、当前建仓成本、手续费后收益、年化收益率和可执行性。系统需要枚举可用执行价组合，并结合盘口、深度和滑点过滤不可执行机会。

### 隐含期货基差套利

基于期权平价公式反推出市场隐含期货价格，并与实际永续合约或交割合约价格进行比较。

当隐含期货价格与实际期货或永续价格出现显著偏差时，系统应提示买入低估端、卖出高估端的对冲方向，并展示基差、资金费率影响、持仓成本、预估收敛收益和主要风险。

## 交易所接入范围

系统需要接入以下交易所：

- Deribit
- Binance
- OKX
- Bybit

每个交易所需要接入的数据范围包括：

- 期权行情
- 现货行情
- 永续合约行情
- 必要时接入交割合约行情
- 盘口 bid/ask 与深度数据
- 指数价格
- 标记价格
- 永续资金费率
- 费率、限频、合约命名和字段定义等元数据

## 官方接口接入原则

所有交易所接口必须以官方文档为准，包括但不限于：

- REST API 文档
- WebSocket API 文档
- 行情订阅格式
- 交易品种命名规则
- 期权合约字段定义
- 盘口深度接口
- 资金费率接口
- 永续合约标记价格接口
- 永续合约指数价格接口
- 请求频率限制
- 鉴权要求

开发过程中禁止基于经验臆测接口字段、URL、参数或返回结构。

如果开发中遇到以下情况，必须停止相关模块开发并反馈：

- 官方文档没有明确说明接口行为
- 不同文档之间存在冲突
- 返回字段含义不明确
- 合约命名规则无法可靠解析
- 某交易所不支持所需品类或数据粒度
- 资金费率、盘口、标记价格等关键数据无法确认来源
- API 权限、频率限制或历史数据能力不明确

反馈时需要明确说明：

- 哪个交易所
- 哪个市场类型
- 哪个接口
- 需要确认的问题
- 当前阻塞了哪个套利计算逻辑

## 开发思路

### 1. 官方接口调研层

逐一阅读 Deribit、Binance、OKX、Bybit 官方文档，确认每个交易所可用的期权、现货、永续接口，以及字段含义、订阅方式、限频规则和数据精度。

### 2. 交易所数据适配层

为每个交易所实现独立 adapter，将不同交易所的行情数据统一转换成系统内部标准结构。

内部标准结构包括：

- 标的资产
- 交易所
- 市场类型
- 合约 ID
- 到期日
- 行权价
- 看涨/看跌方向
- bid/ask
- mid price
- 盘口深度
- 指数价格
- 标记价格
- 永续资金费率
- 更新时间

### 3. 套利计算层

实现三类核心计算：

- Put-Call Parity 偏差计算
- Box Spread 组合枚举与收益计算
- 期权隐含期货价格反推与实际永续/期货价格比较

### 4. 机会过滤与排序层

根据用户配置过滤机会：

- 最小净收益
- 最小年化收益率
- 最大滑点
- 最小盘口深度
- 指定交易所
- 指定标的
- 指定到期日
- 指定套利类型

### 5. 看板展示层

提供网页看板，展示套利机会列表、详情页、历史记录和实时状态。

### 6. 报警系统

当机会满足阈值时，通过 Telegram、邮件或 Webhook 推送报警。

### 7. 历史记录与复盘

记录机会出现、更新、消失的时间线，保存关键价格、收益、风险标签和报警记录。

## 看板功能范围

网页看板需要统一展示所有套利机会，并支持按以下维度筛选：

- 套利类型
- 标的资产
- 交易所
- 到期日
- 收益率
- 风险等级
- 机会状态

每个套利机会至少需要展示：

- 标的资产，例如 BTC、ETH
- 交易所
- 套利类型
- 到期日
- 行权价
- 涉及的期权和对冲腿
- 每条腿的买卖方向
- 理论价格关系
- 当前市场偏差
- 手续费前收益
- 手续费后净收益
- 预估年化收益率
- 买卖价差和深度情况
- 预估滑点
- 保证金或资金占用
- 是否考虑滑点后仍然可执行
- 风险标签，例如流动性不足、资金费率波动、保证金占用高、腿数较多、成交不确定

## 报警功能范围

系统需要支持用户设置报警阈值，包括：

- 最小净收益
- 最小年化收益率
- 最大滑点
- 最小盘口深度
- 指定交易所
- 指定标的
- 指定到期日
- 指定套利类型

报警渠道包括：

- Telegram
- 邮件
- Webhook

当任一类型机会满足用户设定阈值时，系统应在看板中清晰展示，并及时发送报警。

## 成功标准

系统上线后，应能持续扫描 Deribit、Binance、OKX、Bybit 的期权、现货和永续合约市场，并同时发现 Put-Call Parity、Box Spread、隐含期货基差三类套利机会。

每条机会都必须能解释其套利逻辑、组合构成、预期收益和主要风险。系统需要保证计算逻辑准确、数据来源可追溯、机会展示清晰、报警可靠。

## To-do List

- [x] 阅读 Deribit 官方 API 文档，确认期权、现货/指数、永续、盘口、资金费率接口。
- [x] 阅读 Binance 官方 API 文档，确认期权、现货、永续、盘口、资金费率接口。
- [x] 阅读 OKX 官方 API 文档，确认期权、现货、永续、盘口、资金费率接口。
- [x] 阅读 Bybit 官方 API 文档，确认期权、现货、永续、盘口、资金费率接口。
- [x] 整理四个交易所的接口字段映射表。
- [x] 定义系统内部统一行情数据模型。
- [x] 实现 Deribit 数据 adapter。
- [x] 实现 Binance 数据 adapter。
- [x] 实现 OKX 数据 adapter。
- [x] 实现 Bybit 数据 adapter。
- [x] 实现期权链标准化解析。
- [x] 实现盘口 bid/ask 与深度标准化。
- [x] 实现永续价格、指数价格、标记价格、资金费率标准化。
- [x] 实现 Put-Call Parity 套利计算。
- [x] 实现 Box Spread 套利组合枚举与计算。
- [x] 实现隐含期货基差套利计算。
- [x] 实现手续费、滑点、资金费率和资金占用调整。
- [x] 实现机会过滤规则。
- [x] 实现机会排序规则。
- [x] 实现套利机会列表看板。
- [x] 实现套利机会详情页。
- [x] 实现历史机会记录。
- [x] 实现 Telegram 报警。
- [x] 实现邮件或 Webhook 报警。
- [x] 编写核心计算单元测试。
- [x] 编写交易所 adapter 测试。
- [x] 编写报警逻辑测试。
- [x] 完成端到端联调。
- [x] 完成部署说明和运行文档。

## 开发过程要求

开发时必须按 To-do list 推进。每完成一步，需要将对应项从 `[ ]` 标识为 `[x]`，并说明完成内容、涉及文件和验证方式。

## 完成记录

### 2026-05-31

- [x] 阅读 Deribit 官方 API 文档，确认期权、现货/指数、永续、盘口、资金费率接口。
  - 完成内容：确认 Deribit 公共 REST 与 WebSocket 可覆盖期权、现货、永续/交割合约、盘口深度、指数价、标记价、永续资金费率、费率与合约元数据；记录实时数据应优先使用 WebSocket，REST 用于启动快照、元数据同步和断线恢复。
  - 涉及文件：`docs/exchange-research/deribit.md`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：阅读 Deribit 官方文档与 Support 限频/市场数据最佳实践页面；对生产公共 API 执行只读抽样 `public/get_instruments?currency=BTC&kind=option` 与 `public/ticker?instrument_name=BTC-PERPETUAL`，确认关键字段存在。
- [x] 阅读 Binance 官方 API 文档，确认期权、现货、永续、盘口、资金费率接口。
  - 完成内容：确认 Binance 需要分别接入 Options Trading、Spot Trading、USDⓈ-M Futures 三套官方 API；记录期权链、期权/现货/永续盘口、期权指数价、期权标记价、U本位合约标记价、指数价和资金费率接口。
  - 涉及文件：`docs/exchange-research/binance.md`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：阅读 Binance 官方开发者文档；对生产公共 API 执行只读抽样 `/eapi/v1/exchangeInfo`、`/fapi/v1/premiumIndex?symbol=BTCUSDT`、`/api/v3/depth?symbol=BTCUSDT&limit=5`，确认关键字段存在。
- [x] 阅读 OKX 官方 API 文档，确认期权、现货、永续、盘口、资金费率接口。
  - 完成内容：确认 OKX V5 公共 REST 与 WebSocket 可覆盖期权、现货、永续、交割合约、盘口深度、指数价、标记价、永续资金费率和合约元数据；记录账户实际费率接口需要鉴权，未配置 API key 时应使用静态费率配置。
  - 涉及文件：`docs/exchange-research/okx.md`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：阅读 OKX 官方 V5 文档；对生产公共 API 执行只读抽样 `/api/v5/public/instruments?instType=OPTION&instFamily=BTC-USD`、`/api/v5/public/instruments?instType=SPOT&instId=BTC-USDT`、`/api/v5/public/mark-price?instType=SWAP&instId=BTC-USDT-SWAP`、`/api/v5/public/funding-rate?instId=BTC-USDT-SWAP`、`/api/v5/market/books?instId=BTC-USDT&sz=5`、`/api/v5/market/index-tickers?instId=BTC-USDT`，确认关键字段存在。
- [x] 阅读 Bybit 官方 API 文档，确认期权、现货、永续、盘口、资金费率接口。
  - 完成内容：确认 Bybit V5 公共 REST 与 WebSocket 可覆盖期权、现货、永续、交割合约、盘口深度、指数价、标记价、永续资金费率和合约元数据；记录 V5 通过 `category=spot|linear|inverse|option` 区分市场类型，账户实际费率接口需要鉴权，未配置 API key 时应使用静态费率配置。
  - 涉及文件：`docs/exchange-research/bybit.md`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：阅读 Bybit 官方 V5 文档；对生产公共 API 执行只读抽样 `/v5/market/instruments-info?category=option&baseCoin=BTC&limit=2`、`/v5/market/instruments-info?category=spot&symbol=BTCUSDT`、`/v5/market/tickers?category=option&baseCoin=BTC`、`/v5/market/tickers?category=linear&symbol=BTCUSDT`、`/v5/market/orderbook?category=spot&symbol=BTCUSDT&limit=5`、`/v5/market/funding/history?category=linear&symbol=BTCUSDT&limit=2`，确认关键字段存在。
- [x] 整理四个交易所的接口字段映射表。
  - 完成内容：基于 Deribit、Binance、OKX、Bybit 四份官方 API 调研文档，整理统一 `Instrument`、`Quote`、`OrderBook`、`FundingRate` 所需字段到四家交易所官方字段和接口来源的映射，并记录 adapter 实现约束。
  - 涉及文件：`docs/exchange-field-mapping.md`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：检查映射表覆盖四个交易所、四类市场类型、元数据、ticker/quote、盘口、指数价、标记价、资金费率、账户费率和下一步统一数据模型字段要求；用 `rg` 核对关键内部字段和交易所字段均已记录。
- [x] 定义系统内部统一行情数据模型。
  - 完成内容：定义内部统一行情模型 `Instrument`、`Quote`、`OrderBook`、`FundingRate`、`MarketSnapshot`、`DataQuality`、`NormalizationError`，明确 `instrumentKey`、期权分组键、decimal string、毫秒时间戳、数据新鲜度、手续费来源、数量单位和三类套利计算输入约束。
  - 涉及文件：`docs/internal-market-data-model.md`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：检查模型文档覆盖目标中列出的标的资产、交易所、市场类型、合约 ID、到期日、行权价、看涨/看跌方向、bid/ask、mid price、盘口深度、指数价格、标记价格、永续资金费率和更新时间；用 `rg` 核对三类套利、核心模型、错误模型和关键字段均已记录。
- [x] 实现 Deribit 数据 adapter。
  - 完成内容：创建 Python 包结构，定义内部行情 dataclass 模型，并实现 Deribit adapter 对 `public/get_instruments` 元数据、ticker quote、REST order book snapshot、永续 funding 字段的标准化转换；覆盖 option、perpetual、bid/ask、mid price、盘口排序、序列字段、标记价、指数价、手续费和 funding 字段。
  - 涉及文件：`src/option_taoli/models.py`，`src/option_taoli/adapters/deribit.py`，`tests/test_deribit_adapter.py`，`pyproject.toml`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `PYTHONPATH=src python3 -m pytest tests/test_deribit_adapter.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli'`；实现后运行 `python3 -m pytest -q`，确认 Deribit adapter 测试通过。
- [x] 实现 Binance 数据 adapter。
  - 完成内容：实现 Binance adapter 对 Options `exchangeInfo.optionSymbols`、Spot `bookTicker`、USDⓈ-M Futures `exchangeInfo`、`premiumIndex`、depth snapshot 和 funding 字段的标准化转换；覆盖 option、spot、perpetual、bid/ask、mid price、盘口排序、序列字段、标记价、指数价、资金费率、期权到期日/行权价/方向和交易规则 filters。
  - 涉及文件：`src/option_taoli/adapters/binance.py`，`tests/test_binance_adapter.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_binance_adapter.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.adapters.binance'`；实现后运行 `python3 -m pytest tests/test_binance_adapter.py -q` 和 `python3 -m pytest -q`，确认 Binance adapter 与现有 Deribit adapter 测试通过。
- [x] 实现 OKX 数据 adapter。
  - 完成内容：实现 OKX adapter 对 `public/instruments`、`market/tickers`、`market/books`、`public/mark-price`、`market/index-tickers`、`public/funding-rate` 字段的标准化转换；覆盖 option、spot、perpetual、bid/ask、mid price、盘口排序、序列字段、标记价、指数价、资金费率、期权到期日/行权价/方向、合约乘数和交易规则字段。
  - 涉及文件：`src/option_taoli/adapters/okx.py`，`tests/test_okx_adapter.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_okx_adapter.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.adapters.okx'`；实现后运行 `python3 -m pytest tests/test_okx_adapter.py -q` 和 `python3 -m pytest -q`，确认 OKX adapter 与现有 Deribit、Binance adapter 测试通过。
- [x] 实现 Bybit 数据 adapter。
  - 完成内容：实现 Bybit adapter 对 `market/instruments-info`、`market/tickers`、`market/orderbook`、ticker funding 字段和 `market/funding/history` 的标准化转换；覆盖 option、spot、linear perpetual、bid/ask、mid price、盘口排序、序列字段、标记价、指数价、underlying price、Greeks、资金费率、期权 symbol 行权价/方向解析和交易规则字段。
  - 涉及文件：`src/option_taoli/adapters/bybit.py`，`tests/test_bybit_adapter.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_bybit_adapter.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.adapters.bybit'`；实现后运行 `python3 -m pytest tests/test_bybit_adapter.py -q` 和 `python3 -m pytest -q`，确认 Bybit adapter 与现有 Deribit、Binance、OKX adapter 测试通过。
- [x] 实现期权链标准化解析。
  - 完成内容：实现 `build_option_chain()`，将四家交易所 adapter 标准化后的 `Instrument` 列表过滤为可交易且字段完整的期权链；按交易所、标的、到期日、行权价构建 call/put 配对，保持交易所隔离，提供 Put-Call Parity 所需完整配对列表，并按到期日输出 Box Spread 枚举所需的有序行权价和 strike 级 pair 索引。
  - 涉及文件：`src/option_taoli/option_chain.py`，`tests/test_option_chain.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_option_chain.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.option_chain'`；实现后运行 `python3 -m pytest tests/test_option_chain.py -q`，确认期权链标准化测试通过。
- [x] 实现盘口 bid/ask 与深度标准化。
  - 完成内容：实现交易所无关的 `standardize_quote()`、`standardize_order_book()` 和 `estimate_fill()`，将 adapter 输出的内部 `Quote`、`OrderBook` 转换为套利计算可直接使用的可执行 bid/ask、spread、mid price、有效深度和按目标数量吃单的成交估算；统一校验正价格、正数量、非交叉盘口，并对深度档位排序。
  - 涉及文件：`src/option_taoli/market_depth.py`，`tests/test_order_book_standardization.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_order_book_standardization.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.market_depth'`；实现后运行 `python3 -m pytest tests/test_order_book_standardization.py -q`，确认 quote bid/ask、order book 深度、吃单估算和异常盘口校验通过。
- [x] 实现永续价格、指数价格、标记价格、资金费率标准化。
  - 完成内容：实现 `standardize_perpetual_state()`，将 adapter 输出的内部 `Quote` 与 `FundingRate` 合并为统一永续市场状态，标准化永续市场价、标记价、指数价、标记价-指数价基差、基差率、当前/8h资金费率、资金费率结算时间、资金费率周期、利率、溢价和明确周期下的年化资金费率；统一校验永续市场类型、正价格、标记价/指数价必填和 funding 与 quote 合约一致性。
  - 涉及文件：`src/option_taoli/perpetual_market.py`，`tests/test_perpetual_market_standardization.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_perpetual_market_standardization.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.perpetual_market'`；实现后运行 `python3 -m pytest tests/test_perpetual_market_standardization.py -q`，确认永续价格、标记价、指数价、资金费率、基差和异常输入校验通过。
- [x] 实现 Put-Call Parity 套利计算。
  - 完成内容：实现 `calculate_put_call_parity()`，基于同交易所、同标的、同到期、同行权价的完整 call/put 配对与现货/永续/期货对冲腿可执行报价，计算两种可执行方向：买 call 卖 put 合成多头并卖出对冲腿，以及卖 call 买 put 合成空头并买入对冲腿；输出方向、三条腿买卖动作、执行价、合成远期价格、对冲价格、偏差、毛收益和解释文本。手续费、滑点和资金占用扣减保留给后续独立 To-do。
  - 涉及文件：`src/option_taoli/put_call_parity.py`，`tests/test_put_call_parity.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_put_call_parity.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.put_call_parity'`；实现后运行 `python3 -m pytest tests/test_put_call_parity.py -q`，确认正反两种 PCP 套利方向、无机会场景和输入匹配校验通过。
- [x] 实现 Box Spread 套利组合枚举与计算。
  - 完成内容：实现 `calculate_box_spreads()`，基于同交易所、同标的、同到期的标准化期权链枚举任意两档完整 strike 组合，分别计算 long box（买低 strike call、卖高 strike call、买高 strike put、卖低 strike put）和 short box（反向四腿）；输出方向、四条腿买卖动作、固定到期现金流、当前建仓成本/收入、毛收益、年化收益率和解释文本，并按毛收益降序返回机会。手续费、滑点和最小可执行规模扣减保留给后续独立 To-do。
  - 涉及文件：`src/option_taoli/box_spread.py`，`tests/test_box_spread.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_box_spread.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.box_spread'`；实现后运行 `python3 -m pytest tests/test_box_spread.py -q`，确认 long box、short box、缺失腿/缺失报价跳过和多组合收益排序通过。
- [x] 实现隐含期货基差套利计算。
  - 完成内容：实现 `calculate_implied_futures_basis()`，基于同一 call/put 配对可成交 bid/ask 反推出隐含期货买入价和卖出价，并与实际永续或交割合约可成交 bid/ask 比较；输出买入隐含期货并卖出实际期货、卖出隐含期货并买入实际期货两种方向，包含三条腿、隐含期货价、实际期货价、基差、毛收益、资金费率字段、风险标签和解释文本。手续费、滑点、资金费率影响金额和资金占用扣减保留给后续独立 To-do。
  - 涉及文件：`src/option_taoli/implied_futures_basis.py`，`tests/test_implied_futures_basis.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_implied_futures_basis.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.implied_futures_basis'`；实现后运行 `python3 -m pytest tests/test_implied_futures_basis.py -q`，确认两种隐含期货基差方向、无机会场景、资金费率风险标签和输入校验通过。
- [x] 实现手续费、滑点、资金费率和资金占用调整。
  - 完成内容：实现 `apply_opportunity_adjustments()`，对已有三类套利机会的统一 `legs` 和 `gross_profit` 进行后处理，按腿名义金额计算手续费，支持显式滑点成本和盘口深度成交结果推导滑点，支持永续资金费率按多空方向与持仓周期折算成本或收益，按保守资金占用率计算 `capital_required`、`net_profit`、`net_return`、`annualized_net_return`、可执行标记和风险标签。
  - 涉及文件：`src/option_taoli/opportunity_adjustments.py`，`tests/test_opportunity_adjustments.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_opportunity_adjustments.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.opportunity_adjustments'`；实现后运行 `python3 -m pytest tests/test_opportunity_adjustments.py -q` 和 `python3 -m pytest -q`，确认手续费、滑点、资金费率、资金占用、净收益、年化净收益和不可完全成交标记通过。
- [x] 实现机会过滤规则。
  - 完成内容：实现 `OpportunityFilter` 与 `filter_opportunities()`，支持按最小净收益、最小年化收益率、最大滑点、最小盘口深度、交易所、标的、到期日、套利类型和可执行状态过滤机会；过滤逻辑可直接处理原始机会对象，也可处理包含 `opportunity` 与 `adjustments` 的后处理候选对象，并在缺失可选指标时避免误杀机会。
  - 涉及文件：`src/option_taoli/opportunity_filters.py`，`tests/test_opportunity_filters.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_opportunity_filters.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.opportunity_filters'`；实现后运行 `python3 -m pytest tests/test_opportunity_filters.py -q` 和 `python3 -m pytest -q`，确认收益、年化、滑点、深度、交易所、标的、到期日、套利类型和可执行状态过滤通过。
- [x] 实现机会排序规则。
  - 完成内容：实现 `OpportunitySort` 与 `sort_opportunities()`，支持默认监控排序和用户指定字段排序；默认排序按可执行状态、净收益、年化收益率、滑点、盘口深度、到期时间综合排序，用户排序支持净收益、年化净收益、滑点、盘口深度、到期时间和资金占用，并保持相同排序键下的原始稳定顺序。
  - 涉及文件：`src/option_taoli/opportunity_sorting.py`，`tests/test_opportunity_sorting.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_opportunity_sorting.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.opportunity_sorting'`；实现后运行 `python3 -m pytest tests/test_opportunity_sorting.py -q` 和 `python3 -m pytest -q`，确认默认排序、自定义年化收益排序、最低滑点优先和稳定排序通过。
- [x] 实现套利机会列表看板。
  - 完成内容：实现 `render_opportunity_list_html()` 静态 HTML 看板渲染器，展示三类套利机会列表、筛选控件、交易所、标的、到期日、行权价/区间、方向、毛收益、净收益、年化收益率、滑点、盘口深度、资金占用、可执行状态和风险标签；渲染器复用机会过滤与排序规则，支持直接处理原始机会对象和包含 `opportunity`/`adjustments` 的候选对象，并对动态值进行 HTML 转义。
  - 涉及文件：`src/option_taoli/dashboard.py`，`tests/test_dashboard_list.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_dashboard_list.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.dashboard'`；实现后运行 `python3 -m pytest tests/test_dashboard_list.py -q` 和 `python3 -m pytest -q`，确认看板字段、筛选控件、过滤排序、风险标签、Industrial 视觉 token 和 HTML 转义通过。
- [x] 实现套利机会详情页。
  - 完成内容：实现 `render_opportunity_detail_html()` 静态 HTML 详情页渲染器，展示单条机会的身份信息、套利类型、交易所、标的、到期日、行权价/区间、方向、理论价格关系、毛收益、净收益、年化净收益、手续费、滑点、资金费率影响、资金占用、可执行状态、风险标签、套利解释和每条执行腿；详情页复用列表看板的 Industrial 视觉 token，并支持原始机会对象及 `opportunity`/`adjustments` 包装对象。
  - 涉及文件：`src/option_taoli/dashboard.py`，`tests/test_dashboard_detail.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_dashboard_detail.py -q` 观察到 `ImportError: cannot import name 'render_opportunity_detail_html'`；实现后运行 `python3 -m pytest tests/test_dashboard_detail.py -q`、`python3 -m pytest tests/test_dashboard_list.py tests/test_dashboard_detail.py -q` 和 `python3 -m pytest -q`，确认详情页逻辑、价格关系、执行腿、收益调整、风险标签、HTML 转义和列表页兼容性通过。
- [x] 实现历史机会记录。
  - 完成内容：实现 `OpportunityHistoryStore` SQLite 历史记录层，按稳定机会 ID 记录机会出现、更新、消失事件，保存最新快照、时间线快照、关键价格关系、毛收益、净收益、年化收益、滑点、资金占用、可执行状态、风险标签和执行腿；同时提供 `record_alert()` 与 `alerts()` 保存后续 Telegram/邮件/Webhook 报警记录。
  - 涉及文件：`src/option_taoli/opportunity_history.py`，`tests/test_opportunity_history.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_opportunity_history.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.opportunity_history'`；实现后运行 `python3 -m pytest tests/test_opportunity_history.py -q` 和 `python3 -m pytest -q`，确认创建/更新/消失时间线、SQLite 重开持久化快照、包装机会对象字段保存和报警记录读写通过。
- [x] 实现 Telegram 报警。
  - 完成内容：基于 Telegram Bot API `sendMessage` 接口形状实现 `TelegramAlerter`，构造 `https://api.telegram.org/bot<token>/sendMessage` 请求，发送 HTML 格式机会报警，包含套利类型、交易所、标的、到期日、方向、毛收益、净收益、年化净收益率、滑点、资金占用、可执行状态和风险标签；支持注入 HTTP sender 便于测试，发送成功或失败后写入 `OpportunityHistoryStore` 报警记录。
  - 涉及文件：`src/option_taoli/telegram_alerts.py`，`tests/test_telegram_alerts.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_telegram_alerts.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.telegram_alerts'`；实现后运行 `python3 -m pytest tests/test_telegram_alerts.py -q` 和 `python3 -m pytest -q`，确认 sendMessage URL/payload、HTML 消息内容、成功报警记录、失败报警记录和配置校验通过。
- [x] 实现邮件或 Webhook 报警。
  - 完成内容：实现 `WebhookAlerter` 与 `WebhookAlertConfig`，通过 HTTP POST JSON 发送结构化机会报警 payload，包含事件类型、发送时间、机会 ID、套利类型、交易所、标的、到期日、行权价、方向、毛收益、净收益、年化净收益率、滑点、资金占用、可执行状态和风险标签；支持可选共享密钥 header，2xx 响应记为成功，非 2xx 记为失败，并将结果写入 `OpportunityHistoryStore` 报警记录。
  - 涉及文件：`src/option_taoli/webhook_alerts.py`，`tests/test_webhook_alerts.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_webhook_alerts.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.webhook_alerts'`；实现后运行 `python3 -m pytest tests/test_webhook_alerts.py -q` 和 `python3 -m pytest -q`，确认 Webhook URL/payload/header、成功报警记录、失败报警记录和配置校验通过。
- [x] 编写核心计算单元测试。
  - 完成内容：补充核心计算测试覆盖，锁定 Put-Call Parity、Box Spread、隐含期货基差三类套利在 `discount_factor`、交易规模 `size`、固定现金流/建仓价值/毛收益缩放、隐含期货基差收益缩放，以及手续费/滑点调整后进入过滤排序的组合口径；结合既有测试覆盖三类套利正反方向、无机会场景、输入校验、资金费率风险标签、手续费、滑点、资金占用、过滤和排序。
  - 涉及文件：`tests/test_core_calculations.py`，`tests/test_put_call_parity.py`，`tests/test_box_spread.py`，`tests/test_implied_futures_basis.py`，`tests/test_opportunity_adjustments.py`，`tests/test_opportunity_filters.py`，`tests/test_opportunity_sorting.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：运行 `python3 -m pytest tests/test_core_calculations.py -q` 确认新增核心计算补充测试通过；运行 `python3 -m pytest -q` 确认全部 76 个测试通过。
- [x] 编写交易所 adapter 测试。
  - 完成内容：审查四家交易所 adapter 既有测试后，补充 Deribit WebSocket 盘口 `[action, price, amount]` 档位形状、Binance Options mark WebSocket 短字段、Binance USDⓈ-M mark price stream 短字段、OKX `FUTURES` 交割合约和 Bybit linear dated futures 的测试覆盖；修复 Binance adapter 对 `s/p/i/r/T/E` 等 WebSocket 短字段的标准化读取。
  - 涉及文件：`src/option_taoli/adapters/binance.py`，`tests/test_deribit_adapter.py`，`tests/test_binance_adapter.py`，`tests/test_okx_adapter.py`，`tests/test_bybit_adapter.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_binance_adapter.py -q` 观察到新增 Binance WebSocket 短字段测试失败；实现后运行 `python3 -m pytest tests/test_binance_adapter.py -q` 确认 7 个 Binance adapter 测试通过，运行 `python3 -m pytest tests/test_deribit_adapter.py tests/test_binance_adapter.py tests/test_okx_adapter.py tests/test_bybit_adapter.py -q` 确认 28 个 adapter 测试通过，运行 `python3 -m pytest -q` 确认全部 81 个测试通过。
- [x] 编写报警逻辑测试。
  - 完成内容：补充报警触发规则测试，覆盖最小净收益、最小年化收益、最大滑点、最小深度、交易所、标的、到期日、套利类型、可执行状态和已报警机会 ID 去重；新增 `AlertRule` 与 `select_alert_candidates()`，复用现有机会过滤口径，并与 Telegram、Webhook、历史记录报警测试一起覆盖从阈值筛选到发送结果落库的报警逻辑。
  - 涉及文件：`src/option_taoli/alert_rules.py`，`tests/test_alert_rules.py`，`tests/test_telegram_alerts.py`，`tests/test_webhook_alerts.py`，`tests/test_opportunity_history.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_alert_rules.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.alert_rules'`；实现后运行 `python3 -m pytest tests/test_alert_rules.py -q` 确认 3 个报警规则测试通过，运行 `python3 -m pytest tests/test_alert_rules.py tests/test_telegram_alerts.py tests/test_webhook_alerts.py tests/test_opportunity_history.py -q` 确认 14 个报警相关测试通过，运行 `python3 -m pytest -q` 确认全部 84 个测试通过。
- [x] 完成端到端联调。
  - 完成内容：新增端到端联调测试，使用 Deribit adapter fixture 标准化期权与永续报价，构建期权链并计算 Put-Call Parity 机会，再经过手续费/资金占用调整、报警阈值筛选、机会排序、看板列表渲染和 Webhook 报警发送，验证第一版核心链路可以从交易所原始样本一路流转到展示和报警 payload。
  - 涉及文件：`tests/test_end_to_end_integration.py`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：运行 `python3 -m pytest tests/test_end_to_end_integration.py -q` 确认端到端联调测试通过；运行 `python3 -m pytest -q` 确认全部 85 个测试通过。
- [x] 完成部署说明和运行文档。
  - 完成内容：新增部署与运行文档，说明当前 Python 包交付形态、环境要求、本地安装验证、worker 运行链路、SQLite 历史记录、Telegram/Webhook 报警配置、报警阈值、静态看板发布、生产运行建议和故障排查。
  - 涉及文件：`docs/deployment-and-runbook.md`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：运行 `rg -n "部署说明|运行方式|报警配置|看板发布|生产运行建议|test_end_to_end_integration" docs/deployment-and-runbook.md` 确认关键章节和 smoke test 引用已记录。
- [x] 补充持续扫描编排入口。
  - 完成内容：新增 `ArbitrageMonitor`、`MarketDataBatch`、`MonitorConfig` 和 `MonitorScanResult`，支持外层采集器注入标准化行情后执行单轮扫描和固定间隔 polling；单轮扫描会生成 Put-Call Parity、Box Spread、隐含期货基差机会，完成收益调整、过滤排序、历史记录、看板 HTML 生成、报警阈值筛选和多渠道报警发送，并对已报警机会 ID 做去重。
  - 涉及文件：`src/option_taoli/monitor.py`，`tests/test_monitor.py`，`docs/deployment-and-runbook.md`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_monitor.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.monitor'`；实现后运行 `python3 -m pytest tests/test_monitor.py -q` 确认 2 个监控编排测试通过，运行 `python3 -m pytest -q` 确认全部 87 个测试通过。
- [x] 补充四家交易所公共 REST 获取入口。
  - 完成内容：新增 `DeribitPublicClient`、`BinancePublicClient`、`OkxPublicClient`、`BybitPublicClient`，封装官方公共 market data REST URL，包括合约元数据、ticker/mark/index、盘口深度和资金费率相关端点；客户端使用标准库 HTTP JSON 获取，并支持注入 `get_json` 便于测试、限频、代理或重试封装。
  - 涉及文件：`src/option_taoli/public_clients.py`，`tests/test_public_clients.py`，`docs/deployment-and-runbook.md`，`docs/crypto-options-arbitrage-goal.md`。
  - 验证方式：按 TDD 先运行 `python3 -m pytest tests/test_public_clients.py -q` 观察到 `ModuleNotFoundError: No module named 'option_taoli.public_clients'`；实现后运行 `python3 -m pytest tests/test_public_clients.py -q` 确认 4 个公共 REST client URL 构造测试通过，运行 `python3 -m pytest -q` 确认全部 91 个测试通过。
