# Binance 官方 API 调研

调研日期：2026-05-31

## 结论

Binance 需要同时接入三套官方 API：

- Options Trading：期权链、期权盘口、期权标记价、期权底层指数价。
- Spot Trading：现货盘口、最新价、最优 bid/ask。
- USDⓈ-M Futures：USDT/USDC 保证金永续与交割合约行情、盘口、标记价、指数价、资金费率。

这些公开市场数据接口可以覆盖第一版监控所需数据。实时行情应以 WebSocket 为主，REST 用于启动快照、元数据同步、断线恢复和低频补全。

本调研未发现阻塞 Binance adapter 开发的问题。后续实现需要特别注意 Options、Spot、Futures 的 base URL、WebSocket URL path 和字段缩写均不相同。

## 官方入口

### Options Trading

- REST base endpoint：`https://eapi.binance.com`
- REST path prefix：`/eapi/v1`
- Testnet REST：`https://testnet.binancefuture.com`
- Testnet WebSocket path：`wss://fstream.binancefuture.com/public/`、`/market/`、`/private/`

### Spot Trading

- REST base endpoints：`https://api.binance.com`，`https://api-gcp.binance.com`，`https://api1.binance.com` 到 `https://api4.binance.com`
- 市场数据专用 base endpoint：`https://data-api.binance.vision`

### USDⓈ-M Futures

- REST base endpoint：`https://fapi.binance.com`
- REST path prefix：`/fapi/v1`

官方文档依据：

- https://developers.binance.com/docs/derivatives/options-trading/general-info
- https://developers.binance.com/docs/derivatives/options-trading/market-data/Exchange-Information
- https://developers.binance.com/docs/derivatives/options-trading/market-data/Order-Book
- https://developers.binance.com/docs/derivatives/options-trading/market-data/Symbol-Price-Ticker
- https://developers.binance.com/docs/derivatives/options-trading/market-data/Option-Mark-Price
- https://developers.binance.com/docs/derivatives/options-trading/websocket-market-streams/Mark-Price
- https://developers.binance.com/docs/derivatives/options-trading/websocket-market-streams/Partial-Book-Depth-Streams
- https://developers.binance.com/docs/binance-spot-api-docs/rest-api/general-api-information
- https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints
- https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams
- https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info
- https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information
- https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book
- https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price
- https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History
- https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream
- https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Book-Ticker-Streams
- https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Partial-Book-Depth-Streams
- https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Diff-Book-Depth-Streams

## 市场与接口覆盖

| 数据需求 | 官方接口/订阅 | 关键参数 | 关键字段 | 用途 |
| --- | --- | --- | --- | --- |
| 期权链与元数据 | `GET /eapi/v1/exchangeInfo` | 无 | `optionContracts`, `optionSymbols`, `symbol`, `underlying`, `expiryDate`, `side`, `strikePrice`, `unit`, `quoteAsset`, `status`, `filters`, `rateLimits` | 构建期权链、合约乘数、最小交易量、限频 |
| 期权 REST 盘口 | `GET /eapi/v1/depth` | `symbol`, `limit` | `bids`, `asks`, `T`, `lastUpdateId` | 启动快照、断线恢复、深度与滑点估算 |
| 期权实时盘口 | `<symbol>@depth<level>@100ms` 或 `@500ms` | `symbol`, `level` | `e`, `E`, `T`, `s`, `U`, `u`, `pu`, `b`, `a` | 实时维护期权盘口 |
| 期权指数价 | `GET /eapi/v1/index` | `underlying` | `time`, `indexPrice` | Put-Call Parity 与隐含期货基差中的底层参考价 |
| 期权标记价/Greeks | `GET /eapi/v1/mark`；`<underlying>@optionMarkPrice` | REST 可选 `symbol`；WS 用 `underlying` | REST: `symbol`, `markPrice`, `bidIV`, `askIV`, `markIV`, `delta`, `theta`, `gamma`, `vega`, `riskFreeInterest`; WS: `s`, `mp`, `i`, `bo`, `ao`, `bq`, `aq`, `rf` | 标记价、IV、风险提示和 best quote 补充 |
| 现货 REST 深度 | `GET /api/v3/depth` | `symbol`, `limit` | `lastUpdateId`, `bids`, `asks` | 现货对冲腿盘口 |
| 现货 REST 最优价 | `GET /api/v3/ticker/bookTicker` | `symbol` 或 `symbols` | `symbol`, `bidPrice`, `bidQty`, `askPrice`, `askQty` | 快速获取现货 bid/ask |
| 现货 WS 深度 | `<symbol>@depth` 或 `<symbol>@depth@100ms` | `symbol` | `U`, `u`, `b`, `a` | 实时现货盘口维护 |
| U本位合约元数据 | `GET /fapi/v1/exchangeInfo` | 无 | `symbols`, `symbol`, `pair`, `contractType`, `deliveryDate`, `status`, `baseAsset`, `quoteAsset`, `marginAsset`, `filters`, `marketTakeBound`, `rateLimits` | 永续/交割合约 universe、交易规则、限频 |
| U本位 REST 深度 | `GET /fapi/v1/depth` | `symbol`, `limit` | `lastUpdateId`, `E`, `T`, `bids`, `asks` | 永续/交割合约盘口快照 |
| U本位 WS 最优价 | `<symbol>@bookTicker` | `symbol` | `u`, `E`, `T`, `s`, `b`, `B`, `a`, `A` | 实时最优 bid/ask |
| U本位 WS 深度 | `<symbol>@depth` 或 `@100ms` | `symbol` | `U`, `u`, `pu`, `b`, `a` | 实时深度维护 |
| U本位标记价/指数价/资金费率 | `GET /fapi/v1/premiumIndex`；`<symbol>@markPrice` 或 `@1s` | `symbol` 可选 | REST: `markPrice`, `indexPrice`, `estimatedSettlePrice`, `lastFundingRate`, `interestRate`, `nextFundingTime`, `time`; WS: `p`, `i`, `P`, `r`, `T` | 隐含期货基差套利对比端、资金费率影响 |
| U本位资金费率历史 | `GET /fapi/v1/fundingRate` | `symbol`, `startTime`, `endTime`, `limit` | `fundingRate`, `fundingTime`, `markPrice` | 资金费率回看和报警解释 |

## 字段映射草案

| 内部字段 | Binance Options | Binance Spot | Binance USDⓈ-M Futures | 说明 |
| --- | --- | --- | --- | --- |
| `exchange` | 常量 `binance` | 常量 `binance` | 常量 `binance` | adapter 注入 |
| `marketType` | `option` | `spot` | `contractType=PERPETUAL` -> `perpetual`，其他 -> `future` | 期权、现货、永续/交割分开标准化 |
| `instrumentId` | `optionSymbols[].symbol` | spot `symbol` | `symbols[].symbol` | 主键使用官方 symbol |
| `baseAsset` | `optionContracts[].baseAsset` | exchangeInfo `baseAsset` | `symbols[].baseAsset` | Spot exchangeInfo 后续字段映射表中补全 |
| `quoteAsset` | `quoteAsset` | exchangeInfo `quoteAsset` | `quoteAsset` |  |
| `settlementAsset` | `settleAsset` | 无 | `marginAsset` | Options 为 USDT 结算 |
| `underlyingId` | `underlying` | 无 | `pair` | 期权底层如 `BTCUSDT` |
| `expiry` | `expiryDate` | 无 | `deliveryDate` | 永续 `deliveryDate` 是远未来时间 |
| `strike` | `strikePrice` | 无 | 无 | 字符串转 decimal |
| `optionType` | `side` | 无 | 无 | `CALL`/`PUT` |
| `contractSize` | `unit` | `1` | `1` 或按合约规则补充 | 期权明确提供 `unit` |
| `bidPrice` | WS mark `bo` 或盘口第一档 | `bidPrice` / 第一档 | WS `b` / 第一档 | 字符串 decimal |
| `askPrice` | WS mark `ao` 或盘口第一档 | `askPrice` / 第一档 | WS `a` / 第一档 | 字符串 decimal |
| `bidSize` | WS mark `bq` 或盘口第一档 | `bidQty` / 第一档 | WS `B` / 第一档 | 字符串 decimal |
| `askSize` | WS mark `aq` 或盘口第一档 | `askQty` / 第一档 | WS `A` / 第一档 | 字符串 decimal |
| `bookBids` | `bids` 或 WS `b` | `bids` 或 WS `b` | `bids` 或 WS `b` | REST 为二维数组，WS 为更新数组 |
| `bookAsks` | `asks` 或 WS `a` | `asks` 或 WS `a` | `asks` 或 WS `a` |  |
| `markPrice` | REST `markPrice` / WS `mp` | 无 | REST `markPrice` / WS `p` |  |
| `indexPrice` | REST `indexPrice` / WS `i` | spot 最新/盘口 mid | REST `indexPrice` / WS `i` | 期权指数接口按 underlying 查询 |
| `fundingRateCurrent` | 无 | 无 | REST `lastFundingRate` / WS `r` | 永续专用 |
| `fundingNextTime` | 无 | 无 | `nextFundingTime` / WS `T` | 永续专用 |
| `updatedAt` | `T` 或 `E` | stream event time 或本地采集时间 | `time`, `E`, `T` | 优先交易时间，其次事件时间 |

## 限频与实现约束

- Options `/eapi/v1/exchangeInfo` 返回 `rateLimits`，官方说明 `/eapi/v1/exchangeInfo` 的 `rateLimits` 涵盖 `RAW_REQUEST`、`REQUEST_WEIGHT` 和 `ORDER`。
- Options 公共市场数据部分端点仍可能是 `MARKET_DATA` 安全类型；实现时必须按具体页面的 security type 处理，不能假设所有 `/eapi` 端点均无需 API key。
- Spot REST 深度权重随 `limit` 增加，`/api/v3/depth` 在 `limit=5000` 时权重为 250；不适合高频轮询。
- Futures `/fapi/v1/fundingRate` 与 `/fapi/v1/fundingInfo` 共享 500/5min/IP 限制。
- Futures 和 Options WebSocket 深度流都使用 `U`/`u`/`pu` 更新 ID；本地 order book 必须检测缺口并用 REST depth 重建。
- Binance Options WebSocket URL path 分 `/public` 与 `/market`，期权盘口在 `/public`，期权 mark price 在 `/market`；不能共用一个固定 path。

## 对套利计算的影响

- Put-Call Parity：Binance Options 的 `symbol` 格式如 `BTC-260626-140000-C`，但 adapter 不应只靠字符串解析；应以 `exchangeInfo.optionSymbols` 中的 `expiryDate`、`strikePrice`、`side`、`underlying` 为准。
- Box Spread：两档 strike 来自同一 `underlying`、同一 `expiryDate` 的 `CALL`/`PUT` 分组；盘口执行性来自 `depth` 或 WS depth。
- 隐含期货基差：期权隐含端使用 Options bid/ask 与 `indexPrice`/`unit`；实际期货端优先使用 USDⓈ-M `premiumIndex` 或 `markPrice` stream 的 `markPrice`、`indexPrice`、`lastFundingRate`。

## 实测样本

2026-05-31 对生产公共 API 做了只读抽样：

- `GET https://eapi.binance.com/eapi/v1/exchangeInfo` 返回 `optionContracts` 和 `optionSymbols`，样本字段包含 `symbol`, `side`, `strikePrice`, `expiryDate`, `underlying`, `unit`, `filters`。
- `GET https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT` 返回 `markPrice`, `indexPrice`, `lastFundingRate`, `interestRate`, `nextFundingTime`, `time`。
- `GET https://api.binance.com/api/v3/depth?symbol=BTCUSDT&limit=5` 返回 `lastUpdateId`, `bids`, `asks`。

## 待后续 adapter 测试锁定的问题

这些不是当前阻塞项，但实现时必须用 fixture 覆盖：

- Options 标记价流字段使用短字段名，REST 使用长字段名，转换函数必须分别测试。
- Options、Spot、Futures 的数量单位均以各自交易规则为准，滑点和资金占用计算不能混用。
- Spot symbol 元数据需要在统一字段映射阶段补充 `GET /api/v3/exchangeInfo` 的具体 filters 映射。
