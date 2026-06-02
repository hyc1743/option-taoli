# 交易所接口字段映射表

整理日期：2026-05-31

## 结论

Deribit、Binance、OKX、Bybit 都能映射到统一行情模型所需的核心字段：交易所、市场类型、合约 ID、标的资产、报价资产、结算资产、到期日、行权价、期权方向、bid/ask、盘口深度、指数价、标记价、永续资金费率、手续费率和更新时间。

Gate 期权接入字段见 `docs/exchange-research/gate.md`。当前宽表仍保留前四个交易所，避免把每个 Gate 字段塞进已成型的对比表。

后续统一行情数据模型应拆成四类结构，而不是把所有字段塞进一个大对象：

- `Instrument`：合约/交易对元数据，低频同步。
- `Quote`：最优 bid/ask、最新价、标记价、指数价，实时更新。
- `OrderBook`：盘口快照与增量维护结果。
- `FundingRate`：永续资金费率当前值、下次结算时间和历史记录。

所有价格、数量、费率和乘数应按 decimal 字符串进入 adapter 边界，在计算层再转为高精度 decimal，避免浮点误差影响套利收益。

## 市场类型映射

| 内部 `marketType` | Deribit | Binance | OKX | Bybit |
| --- | --- | --- | --- | --- |
| `spot` | `kind=spot` | Spot API `symbol` | `instType=SPOT` | `category=spot` |
| `option` | `kind=option` | Options API `optionSymbols` | `instType=OPTION` | `category=option` |
| `perpetual` | `kind=future` + `settlement_period=perpetual` | USDⓈ-M `contractType=PERPETUAL` | `instType=SWAP` | `category=linear|inverse` + perpetual contract metadata |
| `future` | `kind=future` + non-perpetual `settlement_period` | USDⓈ-M non-`PERPETUAL` contract | `instType=FUTURES` | `category=linear|inverse` + dated futures metadata |

## Instrument 字段映射

| 内部字段 | Deribit | Binance | OKX | Bybit | 备注 |
| --- | --- | --- | --- | --- | --- |
| `exchange` | 常量 `deribit` | 常量 `binance` | 常量 `okx` | 常量 `bybit` | adapter 注入 |
| `instrumentId` | `instrument_name` | Options `optionSymbols[].symbol`；Spot/Futures `symbols[].symbol` | `instId` | `symbol` | 主键使用官方 ID |
| `marketType` | `kind` + `settlement_period` | API domain + `contractType` | `instType` | `category` + 合约元数据 | 转为 `spot|option|perpetual|future` |
| `baseAsset` | `base_currency` | Options `optionContracts[].baseAsset`；Spot/Futures `baseAsset` | `baseCcy` 或 `uly` 前段 | `baseCoin` | 衍生品缺字段时从官方 underlying/family 辅助 |
| `quoteAsset` | `quote_currency` | `quoteAsset` | `quoteCcy` 或 `uly` 后段 | `quoteCoin` | 价格报价币 |
| `settlementAsset` | `settlement_currency` | Options `settleAsset`；Futures `marginAsset` | `settleCcy` | `settleCoin` | spot 可为空 |
| `underlyingId` | `price_index` 或 instrument family 规则 | Options `underlying`；Futures `pair` | `uly` | `baseCoin` 或 symbol family | Put-Call 和隐含期货分组字段 |
| `instrumentFamily` | currency + expiry grouping | Options `underlying` | `instFamily` | `baseCoin` + `deliveryTime` | 主要用于期权链分组 |
| `expiry` | `expiration_timestamp` | Options `expiryDate`；Futures `deliveryDate` | `expTime` | `deliveryTime` | 毫秒时间戳；spot/永续可为空或按交易所语义处理 |
| `strike` | `strike` | `strikePrice` | `stk` | 从 `symbol` 或 `displayName` 解析 | 仅期权 |
| `optionType` | `option_type` | `side` | `optType` | `optionsType` 或 symbol 后缀 | 统一为 `call|put` |
| `contractSize` | `contract_size` | Options `unit`；Spot `1`；Futures 按合约规则 | `ctVal` + `ctMult` | 由合约规则和数量单位确定 | 收益、资金占用和滑点必须使用 |
| `contractValueCurrency` | `quote_currency`/`settlement_currency` | `quoteAsset`/`marginAsset` | `ctValCcy` | `quoteCoin`/`settleCoin` | 合约价值币种 |
| `contractType` | `instrument_type` 或 settlement 规则 | `contractType` | `ctType` | `contractType` | linear/inverse/future/perpetual 辅助字段 |
| `tickSize` | `tick_size` | filter `PRICE_FILTER.tickSize` | `tickSz` | `priceFilter.tickSize` | 下单校验与价格归一 |
| `minOrderSize` | instrument amount limits | filter `LOT_SIZE.minQty` 或 Options filters | `minSz` | `lotSizeFilter.minOrderQty` 或 `minOrderAmt` | 监控第一版用于执行性提示 |
| `qtyStep` | instrument amount step | filter `LOT_SIZE.stepSize` | `lotSz` | `lotSizeFilter.qtyStep` 或 spot `basePrecision` | 数量归一 |
| `makerFeeRate` | `maker_commission` | 静态配置或账户/费率接口补充 | `account/trade-fee.maker*` | `account/fee-rate.makerFeeRate` | OKX/Bybit 需要鉴权 |
| `takerFeeRate` | `taker_commission` | 静态配置或账户/费率接口补充 | `account/trade-fee.taker*` | `account/fee-rate.takerFeeRate` | OKX/Bybit 需要鉴权 |
| `status` | `state` | `status` | `state` | `status` | 只接入可交易状态，保留异常状态供告警 |

## Quote 字段映射

| 内部字段 | Deribit | Binance | OKX | Bybit | 备注 |
| --- | --- | --- | --- | --- | --- |
| `bidPrice` | `best_bid_price` 或盘口第一档 | Options WS `bo`/盘口第一档；Spot `bidPrice`；Futures WS `b` | `bidPx` 或盘口第一档 | `bid1Price` 或盘口第一档 | 无买盘时允许为空 |
| `askPrice` | `best_ask_price` 或盘口第一档 | Options WS `ao`/盘口第一档；Spot `askPrice`；Futures WS `a` | `askPx` 或盘口第一档 | `ask1Price` 或盘口第一档 | 无卖盘时允许为空 |
| `bidSize` | `best_bid_amount` 或盘口第一档 | Options WS `bq`；Spot `bidQty`；Futures WS `B` | `bidSz` 或盘口第一档 | `bid1Size` 或盘口第一档 | 数量单位按市场类型解释 |
| `askSize` | `best_ask_amount` 或盘口第一档 | Options WS `aq`；Spot `askQty`；Futures WS `A` | `askSz` 或盘口第一档 | `ask1Size` 或盘口第一档 | 数量单位按市场类型解释 |
| `lastPrice` | `last_price` | Options ticker/mark；Spot ticker；Futures ticker | `last` | `lastPrice` | 非核心计算字段，但用于展示 |
| `midPrice` | adapter 计算 | adapter 计算 | adapter 计算 | adapter 计算 | `(bid+ask)/2`，bid/ask 缺失时为空 |
| `markPrice` | `mark_price` | Options `markPrice`/WS `mp`；Futures `markPrice`/WS `p` | `markPx` | `markPrice` | 现货一般为空 |
| `indexPrice` | `index_price` 或 `get_index_price.result.index_price` | Options `indexPrice`/WS `i`；Futures `indexPrice`/WS `i` | `idxPx` | `indexPrice` | 现货可用自身盘口/最新价作为对冲参考，不强行填指数 |
| `underlyingPrice` | `underlying_price` | Options mark/index 来源 | 可由 index ticker 或 `uly` 对应指数补充 | `underlyingPrice` | 期权 Greeks/IV 展示 |
| `markIv` | `mark_iv` | Options `markIV`/WS mark field | 可后续接 Greeks/mark IV 来源 | `markIv` | 可选展示字段 |
| `bidIv` | `bid_iv` | Options `bidIV` | 可选 | `bid1Iv` | 可选展示字段 |
| `askIv` | `ask_iv` | Options `askIV` | 可选 | `ask1Iv` | 可选展示字段 |
| `delta` | ticker Greeks | Options mark `delta` | 可选 | `delta` | 可选风控解释字段 |
| `gamma` | ticker Greeks | Options mark `gamma` | 可选 | `gamma` | 可选风控解释字段 |
| `vega` | ticker Greeks | Options mark `vega` | 可选 | `vega` | 可选风控解释字段 |
| `theta` | ticker Greeks | Options mark `theta` | 可选 | `theta` | 可选风控解释字段 |
| `updatedAt` | `timestamp` | `T`、`E`、`time` | `ts` | `ts` | 毫秒时间戳 |

## OrderBook 字段映射

| 内部字段 | Deribit | Binance | OKX | Bybit | 备注 |
| --- | --- | --- | --- | --- | --- |
| `bookBids` | REST `bids`；WS `bids` 或增量 `[action, price, amount]` | REST `bids`；WS `b` | `bids` | `b` | 统一为 `[price, size]` 列表 |
| `bookAsks` | REST `asks`；WS `asks` 或增量 `[action, price, amount]` | REST `asks`；WS `a` | `asks` | `a` | 统一为 `[price, size]` 列表 |
| `sequence` | `change_id` | `lastUpdateId` 或 `u` | `seqId` | `u` 或 `seq` | 用于乱序/缺口检测 |
| `previousSequence` | `prev_change_id` | `pu` | `prevSeqId` | 无直接统一字段 | 缺失时用 snapshot 重建策略 |
| `eventTime` | `timestamp` | `E` | `ts` | `ts` | 事件时间 |
| `transactionTime` | 可为空 | `T` | 可为空 | `cts` | 撮合/交易时间，存在时优先用于延迟观察 |
| `checksum` | 可为空 | 可为空 | `checksum` | 可为空 | OKX order book 校验 |
| `isSnapshot` | 首条 snapshot 或 REST | REST snapshot；WS 流程判断 | `action=snapshot` 或 REST | `type=snapshot` 或 REST | adapter 输出统一布尔值 |

## FundingRate 字段映射

| 内部字段 | Deribit | Binance | OKX | Bybit | 备注 |
| --- | --- | --- | --- | --- | --- |
| `fundingRateCurrent` | `current_funding` | `lastFundingRate` 或 WS `r` | `fundingRate` | `fundingRate` | 永续当前/预测资金费率 |
| `fundingRate8h` | `funding_8h` | 按资金间隔换算或为空 | 按 `fundingTime`/`nextFundingTime` 推导 | 按 `fundingIntervalHour` 推导 | 统一展示可选字段 |
| `fundingTime` | ticker `timestamp` 或 perpetual stream 时间 | history `fundingTime` | `fundingTime` | history `fundingRateTimestamp` | 历史或当前结算时间 |
| `nextFundingTime` | 可从 ticker/perpetual stream 补充 | `nextFundingTime` 或 WS `T` | `nextFundingTime` | `nextFundingTime` | 持仓成本估算关键字段 |
| `fundingIntervalHour` | 默认按 Deribit 永续规则/官方字段补充 | 常见 8h，需按实际接口/配置 | 用 `fundingTime` 与 `nextFundingTime` 差值判断 | `fundingIntervalHour` | 不硬编码为 8 小时 |
| `interestRate` | `interest_rate` 或 `interest` | `interestRate` | `interestRate` | 可为空 | 解释资金费率来源 |
| `premium` | 可为空 | 可为空 | `premium` | 可为空 | 可选解释字段 |
| `updatedAt` | `timestamp` | `time`、`E` | `ts` | `ts` | 毫秒时间戳 |

## 接口来源映射

| 数据类别 | Deribit | Binance | OKX | Bybit |
| --- | --- | --- | --- | --- |
| 元数据 | `public/get_instruments`, `public/get_instrument` | Options `/eapi/v1/exchangeInfo`；Spot `/api/v3/exchangeInfo`；Futures `/fapi/v1/exchangeInfo` | `/api/v5/public/instruments` | `/v5/market/instruments-info` |
| ticker/quote | `public/ticker`, `ticker.{instrument_name}.{interval}` | Options mark/ticker streams；Spot `bookTicker`；Futures `bookTicker`, `premiumIndex` | `/api/v5/market/tickers`, WS `tickers` | `/v5/market/tickers`, WS `tickers.{symbol}` |
| 盘口 | `public/get_order_book`, WS `book.*` | Options/Spot/Futures depth REST 与 depth WS | `/api/v5/market/books`, WS `books/books5/bbo-tbt` | `/v5/market/orderbook`, WS `orderbook.{depth}.{symbol}` |
| 指数价 | `public/get_index_price`, ticker `index_price` | Options `/eapi/v1/index`；Futures `/fapi/v1/premiumIndex` | `/api/v5/market/index-tickers` | ticker `indexPrice` |
| 标记价 | ticker `mark_price` | Options `/eapi/v1/mark`；Futures `/fapi/v1/premiumIndex` | `/api/v5/public/mark-price` | ticker `markPrice` |
| 资金费率 | ticker/perpetual stream `current_funding`, `funding_8h` | `/fapi/v1/fundingRate`, `/fapi/v1/premiumIndex`, WS mark price | `/api/v5/public/funding-rate`, `/api/v5/public/funding-rate-history` | `/v5/market/tickers`, `/v5/market/funding/history` |
| 账户费率 | public instrument commission fields | 静态配置或账户/费率接口补充 | `/api/v5/account/trade-fee` | `/v5/account/fee-rate` |

## Adapter 实现约束

- 期权分组必须优先使用官方元数据字段；只有 Bybit 当前调研需要从 `symbol` 或 `displayName` 补充解析 strike。
- 盘口增量必须按交易所序列字段校验：Deribit `change_id/prev_change_id`，Binance `U/u/pu`，OKX `prevSeqId/seqId`，Bybit `u/seq`。
- 数量单位不能跨市场复用：现货通常是 base asset 数量，OKX 衍生品为合约张数，Deribit 期权和反向合约也有不同 amount 语义。
- 手续费后净收益计算必须支持两种模式：无 API key 时使用静态配置；有 API key 时优先读取账户实际费率。
- 资金费率间隔不能硬编码为 8 小时；Bybit 提供 `fundingIntervalHour`，OKX 需用 `fundingTime` 与 `nextFundingTime` 判断，其他交易所也应保留配置覆盖能力。
- `midPrice`、滑点、可成交数量和资金占用不是交易所原始字段，应由标准化后的 quote/order book 和 instrument 规则计算得到。

## 下一步对统一数据模型的要求

下一项 `定义系统内部统一行情数据模型` 应基于本表至少定义：

- instrument identity：`exchange`, `instrumentId`, `marketType`, `baseAsset`, `quoteAsset`, `settlementAsset`
- option identity：`underlyingId`, `instrumentFamily`, `expiry`, `strike`, `optionType`
- contract rules：`contractSize`, `contractValueCurrency`, `contractType`, `tickSize`, `minOrderSize`, `qtyStep`
- quote：`bidPrice`, `askPrice`, `bidSize`, `askSize`, `midPrice`, `markPrice`, `indexPrice`, `underlyingPrice`, `updatedAt`
- order book：`bookBids`, `bookAsks`, `sequence`, `previousSequence`, `eventTime`, `transactionTime`, `checksum`
- funding：`fundingRateCurrent`, `fundingRate8h`, `fundingTime`, `nextFundingTime`, `fundingIntervalHour`, `interestRate`, `premium`
- fees：`makerFeeRate`, `takerFeeRate`, `feeSource`
