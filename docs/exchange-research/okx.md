# OKX 官方 API 调研

调研日期：2026-05-31

## 结论

OKX V5 公共 API 可以覆盖第一版监控所需的期权、现货、永续、交割合约、盘口深度、指数价格、标记价格、永续资金费率、限频和合约元数据。实时行情应以 WebSocket public channel 为主，REST 用于启动快照、元数据同步、断线恢复和低频补全。

本调研未发现阻塞 OKX adapter 开发的问题。需要注意：OKX 的实际手续费率接口 `GET /api/v5/account/trade-fee` 需要 Read 权限和鉴权，公共 `GET /api/v5/public/instruments` 只提供 `groupId`，后续监控系统如要精确按账户费率计算净收益，应支持配置 API key 或静态费率。

## 官方入口

- REST base endpoint：`https://www.okx.com`
- Public REST path prefix：`/api/v5`
- Public WebSocket：`wss://ws.okx.com:8443/ws/v5/public`
- Business WebSocket：`wss://ws.okx.com:8443/ws/v5/business`
- Demo Public WebSocket：`wss://wspap.okx.com:8443/ws/v5/public`
- 公共市场数据：无需鉴权
- 账户费率接口：`GET /api/v5/account/trade-fee`，需要 `Read` 权限

官方文档依据：

- https://www.okx.com/docs-v5/en/
- `GET /api/v5/public/instruments`
- `GET /api/v5/market/tickers`
- `GET /api/v5/market/ticker`
- `GET /api/v5/market/books`
- `GET /api/v5/public/funding-rate`
- `GET /api/v5/public/funding-rate-history`
- `GET /api/v5/public/mark-price`
- `GET /api/v5/market/index-tickers`
- WebSocket public `tickers`
- WebSocket public `books`, `books5`, `bbo-tbt`, `books50-l2-tbt`, `books-l2-tbt`
- WebSocket public `funding-rate`
- WebSocket public `mark-price`
- WebSocket public `index-tickers`
- Account `GET /api/v5/account/trade-fee`

## 市场与接口覆盖

| 数据需求 | 官方接口/订阅 | 关键参数 | 关键字段 | 用途 |
| --- | --- | --- | --- | --- |
| 合约/品种元数据 | `GET /api/v5/public/instruments` | `instType`, `instFamily`, `instId` | `instType`, `instId`, `uly`, `instFamily`, `baseCcy`, `quoteCcy`, `settleCcy`, `ctVal`, `ctMult`, `ctValCcy`, `ctType`, `optType`, `stk`, `expTime`, `tickSz`, `lotSz`, `minSz`, `state`, `groupId` | 构建 SPOT/SWAP/FUTURES/OPTION universe、期权链、合约乘数、交易规则 |
| REST ticker | `GET /api/v5/market/tickers`；`GET /api/v5/market/ticker` | `instType`, `instFamily`, `instId` | `instType`, `instId`, `last`, `lastSz`, `askPx`, `askSz`, `bidPx`, `bidSz`, `volCcy24h`, `vol24h`, `ts` | 快照行情、最优 bid/ask |
| REST 盘口 | `GET /api/v5/market/books` | `instId`, `sz` | `asks`, `bids`, `ts`, `seqId` | 启动快照、断线恢复、深度与滑点估算 |
| WS ticker | public `tickers` | `channel=tickers`, `instId` | 与 REST ticker 对齐 | 实时最优价与最新价 |
| WS 盘口 | public `books`, `books5`, `bbo-tbt`, `books50-l2-tbt`, `books-l2-tbt` | `channel`, `instId` | `action`, `asks`, `bids`, `ts`, `checksum`, `prevSeqId`, `seqId` | 实时 order book 维护 |
| 标记价格 | `GET /api/v5/public/mark-price`；public `mark-price` | `instType`, `instFamily`, `instId` | `instType`, `instId`, `markPx`, `ts` | 永续、交割、期权标记价 |
| 指数价格 | `GET /api/v5/market/index-tickers`；public `index-tickers` | `instId` 或 `quoteCcy` | `instId`, `idxPx`, `high24h`, `low24h`, `open24h`, `ts` | 现货/底层指数参考价 |
| 永续资金费率 | `GET /api/v5/public/funding-rate`；public `funding-rate` | `instId`，可用 `ANY` 获取所有永续/X-Perps | `fundingRate`, `fundingTime`, `nextFundingTime`, `settFundingRate`, `settState`, `interestRate`, `premium`, `ts` | 隐含期货基差套利资金费率与持仓成本 |
| 资金费率历史 | `GET /api/v5/public/funding-rate-history` | `instId`, `after`, `before`, `limit` | `fundingRate`, `fundingTime`, `realizedRate`, `method` 等 | 资金费率回看和报警解释 |
| 账户实际费率 | `GET /api/v5/account/trade-fee` | `instType`, `instId`, `uly`, `instFamily` | `maker`, `taker`, `makerU`, `takerU`, `makerUSDC`, `takerUSDC` | 精确手续费后净收益，需要鉴权 |

## 合约类型确认

`GET /api/v5/public/instruments` 的 `instType` 支持：

- `SPOT`：现货
- `SWAP`：永续合约
- `FUTURES`：交割合约
- `OPTION`：期权

期权查询需要传 `instFamily`，例如 `BTC-USD`。期权字段以 `optType=C/P`、`stk`、`expTime` 描述看涨/看跌、行权价和到期时间。永续由 `instType=SWAP` 识别，交割合约由 `instType=FUTURES` 识别。

## 字段映射草案

| 内部字段 | OKX 字段 | 说明 |
| --- | --- | --- |
| `exchange` | 常量 `okx` | adapter 注入 |
| `marketType` | `instType` | `SPOT` -> `spot`，`SWAP` -> `perpetual`，`FUTURES` -> `future`，`OPTION` -> `option` |
| `instrumentId` | `instId` | 主键使用官方 instrument ID |
| `baseAsset` | `baseCcy` 或 `uly` 前段 | SPOT 有 `baseCcy`；衍生品以 `uly`/`instFamily` 辅助 |
| `quoteAsset` | `quoteCcy` 或 `uly` 后段 | SPOT 有 `quoteCcy`；衍生品以 `uly`/`instFamily` 辅助 |
| `settlementAsset` | `settleCcy` | OPTION/FUTURES/SWAP |
| `underlyingId` | `uly` | 如 `BTC-USD` |
| `instrumentFamily` | `instFamily` | OPTION/FUTURES/SWAP 分组 |
| `expiry` | `expTime` | 期权/交割合约自然交割或行权时间 |
| `strike` | `stk` | 仅期权 |
| `optionType` | `optType` | `C` -> call，`P` -> put |
| `contractSize` | `ctVal` + `ctMult` | 合约价值与乘数，资金占用和收益计算必须使用 |
| `contractValueCurrency` | `ctValCcy` | 合约价值币种 |
| `contractType` | `ctType` | `linear` / `inverse` |
| `bidPrice` | ticker `bidPx` 或盘口第一档 | 字符串 decimal |
| `askPrice` | ticker `askPx` 或盘口第一档 | 字符串 decimal |
| `bidSize` | ticker `bidSz` 或盘口第一档 | 衍生品为合约张数，现货为 base currency 数量 |
| `askSize` | ticker `askSz` 或盘口第一档 | 同上 |
| `bookBids` | `bids` | 单档形状 `[price, size, deprecated, orderCount]` |
| `bookAsks` | `asks` | 同上 |
| `markPrice` | `markPx` | `public/mark-price` 或 WS `mark-price` |
| `indexPrice` | `idxPx` | `market/index-tickers` 或 WS `index-tickers` |
| `fundingRateCurrent` | `fundingRate` | 预测下一结算周期资金费率 |
| `fundingRateSettled` | `settFundingRate` | 上一或当前结算使用的费率，取决于 `settState` |
| `fundingTime` | `fundingTime` | 下一资金费率结算时间 |
| `nextFundingTime` | `nextFundingTime` | 下一周期预测时间，用于判断实际资金费率间隔 |
| `makerFeeRate` | `account/trade-fee.maker*` | 需要鉴权；未配置时使用静态配置 |
| `takerFeeRate` | `account/trade-fee.taker*` | 需要鉴权；未配置时使用静态配置 |
| `updatedAt` | `ts` | 毫秒时间戳 |

## 限频与订阅约束

- `GET /api/v5/public/instruments`：20 requests / 2 seconds，规则为 IP + Instrument Type。
- `GET /api/v5/market/tickers` 和 `GET /api/v5/market/ticker`：20 requests / 2 seconds，规则为 IP。
- `GET /api/v5/market/books`：40 requests / 2 seconds，规则为 IP；服务端缓存更新后返回最新数据。
- `GET /api/v5/public/funding-rate`：10 requests / 2 seconds，规则为 IP + Instrument ID。
- `GET /api/v5/public/mark-price`：10 requests / 2 seconds，规则为 IP + Instrument ID。
- `GET /api/v5/market/index-tickers`：20 requests / 2 seconds，规则为 IP。
- `GET /api/v5/account/trade-fee`：5 requests / 2 seconds，规则为 User ID，权限为 Read。
- WebSocket `books-l2-tbt` 和 `books50-l2-tbt` 需要 VIP4 及以上费率等级；默认监控实现应使用 `books`、`books5` 或 `bbo-tbt`。
- WebSocket order book 要用 `prevSeqId`/`seqId` 维护顺序；发现缺口或序列重置时，应使用 REST `market/books` 重建。
- OKX 说明资金费率间隔可能从常见 8 小时调整为 6/4/2/1 小时；资金成本计算必须用 `fundingTime` 与 `nextFundingTime` 的差值判断实际间隔。

## 对套利计算的影响

- Put-Call Parity：期权同到期同行权价由 `instFamily`、`expTime`、`stk`、`optType` 分组；期权价格单位、合约价值和乘数必须结合 `ctVal`、`ctMult`、`ctValCcy` 处理。
- Box Spread：同一 `instFamily` 和 `expTime` 下枚举两档 `stk` 的 call/put 组合；执行性由 `market/books` 或 WS `books/books5` 提供。
- 隐含期货基差：期权平价反推隐含期货价；实际对比端使用 `SWAP` 或 `FUTURES` 的 ticker/mark-price/index-tickers/funding-rate。

## 实测样本

2026-05-31 对生产公共 API 做了只读抽样：

- `GET https://www.okx.com/api/v5/public/instruments?instType=OPTION&instFamily=BTC-USD` 返回 BTC 期权，样本字段包含 `instId`, `instType`, `instFamily`, `uly`, `expTime`, `optType`, `stk`, `ctVal`, `ctMult`, `ctValCcy`, `settleCcy`, `state`。
- `GET https://www.okx.com/api/v5/public/instruments?instType=SPOT&instId=BTC-USDT` 返回现货，样本字段包含 `baseCcy`, `quoteCcy`, `tickSz`, `lotSz`, `minSz`, `state`。
- `GET https://www.okx.com/api/v5/public/mark-price?instType=SWAP&instId=BTC-USDT-SWAP` 返回 `markPx`。
- `GET https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP` 返回 `fundingRate`, `fundingTime`, `nextFundingTime`, `settFundingRate`, `interestRate`, `premium`。
- `GET https://www.okx.com/api/v5/market/books?instId=BTC-USDT&sz=5` 返回 `asks`, `bids`, `ts`, `seqId`。
- `GET https://www.okx.com/api/v5/market/index-tickers?instId=BTC-USDT` 返回 `idxPx`。

## 待后续 adapter 测试锁定的问题

这些不是当前阻塞项，但实现时必须用 fixture 覆盖：

- 期权、永续、交割的数量单位为合约张数，现货为 base currency 数量；滑点与资金占用计算必须区别处理。
- 期权 `tickSz` 是 tick band 中最小值，精确下单 tick band 要用 OKX 的 instrument tick bands 接口；监控第一版可先用于价格展示和粗粒度校验。
- 账户实际费率需要鉴权，系统应支持静态费率配置作为无 API key 的监控模式，并在配置了 API key 时使用 `account/trade-fee`。
