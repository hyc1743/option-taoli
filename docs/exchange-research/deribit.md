# Deribit 官方 API 调研

调研日期：2026-05-31

## 结论

Deribit 的公开 API 可以覆盖第一版监控所需的期权、现货、永续/交割合约、盘口深度、指数价格、标记价格、永续资金费率和合约元数据。实时行情应以 WebSocket 订阅为主，REST 用于启动快照、元数据同步和异常恢复。

本调研未发现阻塞 Deribit adapter 开发的问题。后续实现仍需在 adapter 测试中用官方示例和实时样本锁定字段转换。

## 官方入口

- REST/JSON-RPC HTTP：`https://www.deribit.com/api/v2`
- WebSocket：`wss://www.deribit.com/ws/api/v2`
- 测试环境：将主机替换为 `test.deribit.com`
- 公共市场数据：无需鉴权
- 私有账户/交易接口：OAuth 2.0 风格鉴权。第一版默认不自动交易，市场监控路径不依赖私有权限。

官方文档依据：

- https://docs.deribit.com/articles/deribit-quickstart
- https://docs.deribit.com/api-reference/market-data/public-get_instruments
- https://docs.deribit.com/api-reference/market-data/public-get_instrument
- https://docs.deribit.com/api-reference/market-data/public-get_order_book
- https://docs.deribit.com/api-reference/market-data/public-ticker
- https://docs.deribit.com/api-reference/market-data/public-get_index_price
- https://docs.deribit.com/subscriptions/orderbook/bookinstrument_nameinterval
- https://docs.deribit.com/subscriptions/orderbook/bookinstrument_namegroupdepthinterval
- https://docs.deribit.com/subscriptions/market-data/tickerinstrument_nameinterval
- https://docs.deribit.com/subscriptions/market-data/perpetualinstrument_nameinterval
- https://support.deribit.com/hc/en-us/articles/25944617523357-Rate-Limits
- https://support.deribit.com/hc/en-us/articles/29592500256669-Market-Data-Collection-Best-Practices

## 市场与接口覆盖

| 数据需求 | 官方接口/订阅 | 关键参数 | 关键字段 | 用途 |
| --- | --- | --- | --- | --- |
| 合约列表与元数据 | `public/get_instruments` | `currency`, `kind`, `expired` | `instrument_name`, `kind`, `base_currency`, `quote_currency`, `counter_currency`, `settlement_currency`, `expiration_timestamp`, `strike`, `option_type`, `instrument_type`, `settlement_period`, `contract_size`, `tick_size`, `maker_commission`, `taker_commission`, `price_index`, `state` | 构建期权链、现货/期货/永续 universe、手续费和合约乘数 |
| 单合约元数据 | `public/get_instrument` | `instrument_name` | 同上，单合约详情 | adapter 单合约补全与异常核验 |
| REST 盘口快照 | `public/get_order_book` | `instrument_name`, `depth` | `bids`, `asks`, `best_bid_price`, `best_ask_price`, `best_bid_amount`, `best_ask_amount`, `mark_price`, `index_price`, `underlying_price`, `interest_rate`, `funding_8h`, `current_funding` | 启动快照、断线恢复、深度与滑点估算 |
| 实时全量/增量盘口 | `book.{instrument_name}.{interval}` | `instrument_name`, `interval` | 首条 `snapshot`，后续 `[action, price, amount]` 增量，`change_id`, `prev_change_id` | 高频 order book 维护 |
| 实时聚合盘口 | `book.{instrument_name}.{group}.{depth}.{interval}` | `group`, `depth`, `interval` | `bids`, `asks` 价格数量对 | 深度较低但实现简单的实时监控 |
| REST ticker | `public/ticker` | `instrument_name` | `best_bid_price`, `best_ask_price`, `mark_price`, `index_price`, `last_price`, `underlying_price`, `interest_rate`, `bid_iv`, `ask_iv`, `mark_iv`, `current_funding`, `funding_8h`, `timestamp` | 单合约轻量行情、标记价、资金费率 |
| 实时 ticker | `ticker.{instrument_name}.{interval}` | `instrument_name`, `interval` | 与 REST ticker 对齐，包含期权 IV/Greeks、永续 funding、期货 delivery 字段 | 主实时行情通道 |
| 指数价格 | `public/get_index_price`；`deribit_price_index.{index_name}` | `index_name` | `index_price` | 现货/指数参考价格 |
| 永续资金/利息 | `ticker.{instrument_name}.{interval}`；`perpetual.{instrument_name}.{interval}` | 永续 `instrument_name` | `current_funding`, `funding_8h`, `interest`, `index_price`, `timestamp` | 隐含期货基差套利的资金费率与持仓成本 |
| 合约生命周期 | `instrument.state.{kind}.{currency}` | `kind`, `currency` | instrument state event | 动态增删期权链与交割合约 |

## 合约类型确认

`public/get_instruments` 的 `kind` 支持 `future`, `option`, `spot`, `future_combo`, `option_combo`。系统第一版只需要独立腿监控，因此 Deribit adapter 应优先接入：

- 期权：`kind=option`
- 现货：`kind=spot`
- 永续与交割合约：`kind=future`，其中 `settlement_period=perpetual` 识别永续，其余到期合约按交割合约处理

## 字段映射草案

| 内部字段 | Deribit 字段 | 说明 |
| --- | --- | --- |
| `exchange` | 常量 `deribit` | adapter 注入 |
| `marketType` | `kind` + `settlement_period` | `option`, `spot`, `perpetual`, `future` |
| `instrumentId` | `instrument_name` | 主键使用官方合约名 |
| `baseAsset` | `base_currency` | BTC/ETH 等 |
| `quoteAsset` | `quote_currency` | USD/USDC/BTC 等 |
| `settlementAsset` | `settlement_currency` | 非 spot 字段 |
| `expiry` | `expiration_timestamp` | 毫秒 epoch |
| `strike` | `strike` | 仅期权 |
| `optionType` | `option_type` | `call`/`put` |
| `contractSize` | `contract_size` | 收益与资金占用计算必须使用 |
| `bidPrice` | `best_bid_price` 或盘口第一档 | 无买盘时可能为 `null` |
| `askPrice` | `best_ask_price` 或盘口第一档 | 无卖盘时可能为 `null` |
| `bidSize` | `best_bid_amount` 或盘口第一档 | 期权为标的币数量，反向期货/永续为 USD 单位 |
| `askSize` | `best_ask_amount` 或盘口第一档 | 同上 |
| `bookBids` | `bids` | REST 为 `[price, amount]`；增量 WS 为 `[action, price, amount]` |
| `bookAsks` | `asks` | 同上 |
| `markPrice` | `mark_price` | ticker/order book 均可取 |
| `indexPrice` | `index_price` 或 `public/get_index_price.result.index_price` | 指数参考价 |
| `underlyingPrice` | `underlying_price` | 期权 IV 计算底层价 |
| `fundingRateCurrent` | `current_funding` | 永续 ticker 字段 |
| `fundingRate8h` | `funding_8h` | 永续 ticker 字段 |
| `makerFeeRate` | `maker_commission` | 元数据字段 |
| `takerFeeRate` | `taker_commission` | 元数据字段 |
| `updatedAt` | `timestamp` | ticker/order book 毫秒时间戳 |

## 限频与订阅约束

- `public/get_instruments` 有独立限制：持续 1 request/second，burst 50；不能频繁轮询。
- `public/subscribe`/`private/subscribe` 有独立 credit 限制，官方建议批量订阅。
- 官方最佳实践建议实时数据使用 WebSocket，REST 保留给初始化、历史/快照和偶发状态同步。
- `book.*.raw` 和其他 raw 订阅只对授权用户可用；无鉴权监控应默认使用 `100ms` 或 `agg2`。
- 盘口增量流必须校验 `change_id`/`prev_change_id`，发现缺口后用 REST 快照重建。

## 对套利计算的影响

- Put-Call Parity：期权同到期同行权价由 `expiration_timestamp`、`strike`、`option_type` 分组；合成远期对比使用期权 bid/ask、`contract_size`、费用和 spot/future/index 价格。
- Box Spread：可由同到期日两档 `strike` 的 call/put 组合枚举；执行价差、深度和滑点来自 order book。
- 隐含期货基差：期权平价反推隐含期货价；实际对比端使用 `BTC-PERPETUAL` 等永续 ticker 的 `mark_price`/`index_price`/`funding_8h` 或交割合约 ticker。

## 实测样本

2026-05-31 对生产公共 API 做了只读抽样：

- `GET https://www.deribit.com/api/v2/public/get_instruments?currency=BTC&kind=option` 返回 BTC 期权，样本字段包含 `instrument_name`, `maker_commission`, `taker_commission`, `expiration_timestamp`, `strike`, `option_type`, `contract_size`, `settlement_period`, `state`。
- `GET https://www.deribit.com/api/v2/public/ticker?instrument_name=BTC-PERPETUAL` 返回永续 ticker，样本字段包含 `best_bid_price`, `best_ask_price`, `index_price`, `mark_price`, `current_funding`, `funding_8h`, `timestamp`。

## 待后续 adapter 测试锁定的问题

这些不是当前阻塞项，但实现时必须用 fixture 覆盖：

- 期权、spot、linear future、inverse future 的 `amount` 单位不同，资金占用和滑点计算不能共用一个单位假设。
- REST 盘口和 WebSocket 增量盘口的数据形状不同，必须分别标准化。
- `raw` 订阅需要授权，默认配置不能依赖 raw。
