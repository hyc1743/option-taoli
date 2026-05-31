# Bybit 官方 API 调研

调研日期：2026-05-31

## 结论

Bybit V5 API 可以覆盖第一版监控所需的期权、现货、永续、交割合约、盘口深度、指数价格、标记价格、永续资金费率、限频和合约元数据。V5 通过统一的 `category=spot|linear|inverse|option` 区分市场类型，REST 适合启动快照、元数据同步、断线恢复和低频补全；实时行情应以各市场独立 WebSocket public endpoint 为主。

本调研未发现阻塞 Bybit adapter 开发的问题。需要注意：账户实际费率接口 `GET /v5/account/fee-rate` 需要鉴权；无 API key 的监控模式应使用静态费率配置，配置 API key 后再读取账户实际 maker/taker 费率。

## 官方入口

- REST base endpoint：`https://api.bybit.com`
- REST path prefix：`/v5`
- Public WebSocket Spot：`wss://stream.bybit.com/v5/public/spot`
- Public WebSocket Linear：`wss://stream.bybit.com/v5/public/linear`
- Public WebSocket Inverse：`wss://stream.bybit.com/v5/public/inverse`
- Public WebSocket Option：`wss://stream.bybit.com/v5/public/option`
- 公共市场数据：无需鉴权
- 账户费率接口：`GET /v5/account/fee-rate`，需要 API key 鉴权

官方文档依据：

- https://bybit-exchange.github.io/docs/v5/intro
- `GET /v5/market/instruments-info`
- `GET /v5/market/tickers`
- `GET /v5/market/orderbook`
- `GET /v5/market/funding/history`
- WebSocket public `tickers.{symbol}`
- WebSocket public `orderbook.{depth}.{symbol}`
- WebSocket connect endpoints
- Rate Limit Rules
- Account `GET /v5/account/fee-rate`

## 市场与接口覆盖

| 数据需求 | 官方接口/订阅 | 关键参数 | 关键字段 | 用途 |
| --- | --- | --- | --- | --- |
| 合约/品种元数据 | `GET /v5/market/instruments-info` | `category`, `symbol`, `baseCoin`, `status`, `limit`, `cursor` | `category`, `symbol`, `status`, `baseCoin`, `quoteCoin`, `settleCoin`, `contractType`, `optionsType`, `launchTime`, `deliveryTime`, `deliveryFeeRate`, `priceFilter`, `lotSizeFilter`, `leverageFilter`, `upperFundingRate`, `lowerFundingRate` | 构建 SPOT/linear perpetual/linear futures/inverse/OPTION universe、期权链、交易规则 |
| REST ticker | `GET /v5/market/tickers` | `category`, `symbol`, `baseCoin`, `expDate` | spot: `bid1Price`, `ask1Price`, `lastPrice`, `volume24h`；linear/inverse: `lastPrice`, `indexPrice`, `markPrice`, `fundingRate`, `nextFundingTime`, `bid1Price`, `ask1Price`, `fundingIntervalHour`；option: `bid1Price`, `ask1Price`, `markPrice`, `indexPrice`, `underlyingPrice`, `markIv`, Greeks | 快照行情、最优 bid/ask、标记价、指数价、资金费率 |
| REST 盘口 | `GET /v5/market/orderbook` | `category`, `symbol`, `limit` | `s`, `a`, `b`, `ts`, `u`, `seq`, `cts` | 启动快照、断线恢复、深度与滑点估算 |
| WS ticker | public `tickers.{symbol}` | 按 Spot/Linear/Inverse/Option endpoint 连接后订阅 topic | 与 REST ticker 主要字段对齐，包含 `ts`、`cs` 等序列字段 | 实时最优价、最新价、标记价、指数价、资金费率 |
| WS 盘口 | public `orderbook.{depth}.{symbol}` | `depth`, `symbol` | `topic`, `type`, `ts`, `data.s`, `data.b`, `data.a`, `data.u`, `data.seq`, `cts` | 实时 order book 维护 |
| 永续资金费率 | `GET /v5/market/tickers` | `category=linear|inverse`, `symbol` | `fundingRate`, `nextFundingTime`, `fundingIntervalHour`, `fundingCap` | 当前/预测资金费率与下次结算时间 |
| 资金费率历史 | `GET /v5/market/funding/history` | `category=linear|inverse`, `symbol`, `startTime`, `endTime`, `limit` | `symbol`, `fundingRate`, `fundingRateTimestamp` | 资金费率回看和报警解释 |
| 账户实际费率 | `GET /v5/account/fee-rate` | `category`, `symbol`, `baseCoin` | `symbol`, `baseCoin`, `takerFeeRate`, `makerFeeRate` | 精确手续费后净收益，需要鉴权 |

## 合约类型确认

V5 使用 `category` 统一区分产品线：

- `spot`：现货
- `linear`：USDT/USDC 永续与 USDT futures
- `inverse`：inverse perpetual 与 inverse futures
- `option`：USDT/USDC options

期权元数据包含 `optionsType=Call|Put`、`baseCoin`、`quoteCoin`、`settleCoin`、`deliveryTime`，行权价需要从官方 `symbol` 或 `displayName` 的命名结构解析。Bybit 期权样本包含 `BTC-26MAR27-78000-P-USDT` 这类 symbol；adapter 必须用 fixture 锁定解析规则，避免只按单一历史格式处理。

## 字段映射草案

| 内部字段 | Bybit 字段 | 说明 |
| --- | --- | --- |
| `exchange` | 常量 `bybit` | adapter 注入 |
| `marketType` | `category` + `contractType` | `spot` -> `spot`；`linear/inverse` 结合 `deliveryTime`、`contractType` 区分永续/交割；`option` -> `option` |
| `instrumentId` | `symbol` | 主键使用官方 symbol |
| `baseAsset` | `baseCoin` | 现货、期权、衍生品元数据 |
| `quoteAsset` | `quoteCoin` | 现货、期权、衍生品元数据 |
| `settlementAsset` | `settleCoin` | 期权和合约 |
| `expiry` | `deliveryTime` | 期权/交割合约到期或交割时间，毫秒时间戳 |
| `strike` | 从 `symbol` 解析 | 期权行权价；需要 adapter fixture 覆盖 |
| `optionType` | `optionsType` 或 `symbol` 后缀 | `Call`/`C` -> call，`Put`/`P` -> put |
| `contractType` | `contractType` | linear/inverse 合约类型 |
| `tickSize` | `priceFilter.tickSize` | 最小价格变动 |
| `minOrderQty` | `lotSizeFilter.minOrderQty` | 最小下单数量 |
| `qtyStep` | `lotSizeFilter.qtyStep` 或 spot `basePrecision` | 数量步长 |
| `bidPrice` | ticker `bid1Price` 或盘口第一档 | 字符串 decimal |
| `askPrice` | ticker `ask1Price` 或盘口第一档 | 字符串 decimal |
| `bidSize` | ticker `bid1Size` 或盘口第一档 | 数量单位按市场类型解释 |
| `askSize` | ticker `ask1Size` 或盘口第一档 | 数量单位按市场类型解释 |
| `bookBids` | orderbook `b` | 单档形状 `[price, size]` |
| `bookAsks` | orderbook `a` | 单档形状 `[price, size]` |
| `markPrice` | ticker `markPrice` | linear/inverse/option |
| `indexPrice` | ticker `indexPrice` | linear/inverse/option |
| `underlyingPrice` | option ticker `underlyingPrice` | 期权底层参考价 |
| `fundingRateCurrent` | ticker `fundingRate` | 永续当前/预测资金费率 |
| `nextFundingTime` | ticker `nextFundingTime` | 下一资金费率时间 |
| `fundingIntervalHour` | ticker `fundingIntervalHour` | 资金费率间隔小时数 |
| `fundingRateHistory` | funding history `fundingRate` | 历史资金费率 |
| `fundingRateTimestamp` | funding history `fundingRateTimestamp` | 历史资金费率时间 |
| `makerFeeRate` | `account/fee-rate.makerFeeRate` | 需要鉴权；未配置时使用静态配置 |
| `takerFeeRate` | `account/fee-rate.takerFeeRate` | 需要鉴权；未配置时使用静态配置 |
| `updatedAt` | ticker/orderbook `ts` | 毫秒时间戳 |

## 限频与订阅约束

- HTTP IP 默认限制为 600 requests / 5 seconds / IP；超过后可能返回 403，需要停止请求并等待封禁自动解除。
- API endpoint rate limit 以 rolling one-second window per UID 计算；响应头包含 `X-Bapi-Limit`、`X-Bapi-Limit-Status`、`X-Bapi-Limit-Reset-Timestamp`。
- WebSocket 不应在 5 分钟内建立超过 500 个连接；market data 每 IP 不超过 1000 个连接，并按 Spot、Linear、Inverse、Options 分开计数。
- Public WebSocket endpoint 按市场类型拆分，订阅时不能把 spot、linear、inverse、option 混在同一个连接上。
- REST orderbook：contract 和 spot 支持 1000 档，option 支持 25 档；RPI 订单不包含在 API 盘口中。
- WS orderbook：linear/inverse/spot 支持 1/50/200/1000 档，option 支持 25/100 档；收到 `snapshot` 要重置本地 order book，`delta` 中 size 为 `0` 表示删除价位。
- linear/inverse/spot level 1 orderbook 只有 snapshot；若 3 秒无变化会重推 snapshot 且 `u` 可能相同。

## 对套利计算的影响

- Put-Call Parity：期权同到期同行权价由 `baseCoin`、`deliveryTime`、解析出的 `strike`、`optionsType` 分组；期权 ticker 同时给出 bid/ask、mark/index/underlying price，可用于偏差展示和风控解释。
- Box Spread：同一 `baseCoin` 和 `deliveryTime` 下枚举两档 strike 的 call/put 组合；执行性必须使用 orderbook 或 WS orderbook 深度计算，不应只用 ticker 最优价。
- 隐含期货基差：期权平价反推隐含期货价后，与 `linear` 或 `inverse` 的 ticker `markPrice`、`indexPrice`、`fundingRate`、`nextFundingTime`、`fundingIntervalHour` 对比。
- 净收益：账户实际费率需要鉴权；系统必须支持静态 maker/taker 费率，并在 API key 可用时用 `GET /v5/account/fee-rate` 覆盖。

## 实测样本

2026-05-31 对生产公共 API 做了只读抽样：

- `GET https://api.bybit.com/v5/market/instruments-info?category=option&baseCoin=BTC&limit=2` 返回 BTC 期权，样本字段包含 `symbol`, `baseCoin`, `quoteCoin`, `settleCoin`, `optionsType`, `deliveryTime`, `deliveryFeeRate`, `priceFilter`, `lotSizeFilter`, `displayName`。
- `GET https://api.bybit.com/v5/market/instruments-info?category=spot&symbol=BTCUSDT` 返回现货，样本字段包含 `symbol`, `baseCoin`, `quoteCoin`, `status`, `lotSizeFilter`, `priceFilter`, `riskParameters`。
- `GET https://api.bybit.com/v5/market/tickers?category=option&baseCoin=BTC` 返回期权 ticker，样本字段包含 `bid1Price`, `ask1Price`, `bid1Iv`, `ask1Iv`, `markPrice`, `indexPrice`, `underlyingPrice`, `markIv`, `delta`, `gamma`, `vega`, `theta`。
- `GET https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT` 返回永续 ticker，样本字段包含 `lastPrice`, `indexPrice`, `markPrice`, `openInterest`, `fundingRate`, `nextFundingTime`, `fundingIntervalHour`, `fundingCap`, `bid1Price`, `ask1Price`。
- `GET https://api.bybit.com/v5/market/orderbook?category=spot&symbol=BTCUSDT&limit=5` 返回 `s`, `a`, `b`, `ts`, `u`, `seq`, `cts`。
- `GET https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&limit=2` 返回 `symbol`, `fundingRate`, `fundingRateTimestamp`。

## 待后续 adapter 测试锁定的问题

这些不是当前阻塞项，但实现时必须用 fixture 覆盖：

- Bybit 期权 symbol 已出现 `BTC-26MAR27-78000-P-USDT` 这种带结算币后缀格式；解析 expiry、strike、call/put 时必须覆盖当前真实格式。
- `linear` 同时包含 USDT/USDC perpetual 和 futures，adapter 需要结合 `contractType`、`deliveryTime` 和 symbol 规则区分永续与交割。
- 期权和合约的数量单位、现货数量单位不同；滑点、资金占用和收益计算必须按市场类型分开处理。
- 账户实际费率需要鉴权，系统应支持静态费率配置作为无 API key 的监控模式，并在配置了 API key 时使用 `account/fee-rate`。
