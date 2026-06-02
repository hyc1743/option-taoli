# 系统内部统一行情数据模型

定义日期：2026-05-31

## 结论

系统内部行情模型分为低频元数据和高频行情数据两层：

- `Instrument`：交易所合约/交易对的稳定元数据，用于期权链、合约规则、手续费、数量单位和状态管理。
- `Quote`：单合约最优价、最新价、指数价、标记价和可选 Greeks，用于快速扫描和机会展示。
- `OrderBook`：标准化后的盘口快照，用于滑点、可成交数量和执行性判断。
- `FundingRate`：永续资金费率当前值、下次结算时间和历史费率，用于隐含期货基差套利持仓成本。
- `MarketSnapshot`：同一 `instrumentKey` 下的元数据、报价、盘口和资金费率组合视图，是套利计算层的直接输入。

模型边界原则：

- adapter 只负责把交易所官方字段转换为本模型，不在 adapter 内计算套利机会。
- 计算层只依赖本模型，不直接读取交易所原始字段。
- 价格、数量、费率、乘数、收益率全部使用 decimal string 表示，禁止在 adapter 边界使用 floating point。
- 时间统一为 Unix epoch milliseconds，字段名统一使用 `*TimeMs` 或 `updatedAtMs`。
- 任何来自交易所但模型未显式使用的字段放入 `raw`，但套利计算不得依赖 `raw`。

## 基础类型

```ts
type ExchangeId = "deribit" | "binance" | "okx" | "bybit" | "gate";

type MarketType = "spot" | "option" | "perpetual" | "future";

type OptionType = "call" | "put";

type ContractType = "linear" | "inverse" | "quanto" | "spot" | "unknown";

type InstrumentStatus =
  | "trading"
  | "pre_launch"
  | "delivering"
  | "expired"
  | "suspended"
  | "unknown";

type FeeSource = "public_metadata" | "authenticated_account" | "static_config";

type DecimalString = string;
type EpochMilliseconds = number;
```

## 标识规则

### `instrumentKey`

`instrumentKey` 是系统内部主键，格式：

```text
<exchange>:<marketType>:<instrumentId>
```

示例：

- `deribit:option:BTC-27JUN25-100000-C`
- `binance:perpetual:BTCUSDT`
- `okx:option:BTC-USD-250627-100000-C`
- `bybit:option:BTC-26MAR27-78000-P-USDT`
- `gate:option:BTC_USDT-20211130-65000-C`

### 分组键

期权套利需要稳定分组键：

```ts
interface OptionGroupKey {
  exchange: ExchangeId;
  underlyingId: string;
  expiryTimeMs: EpochMilliseconds;
  strike: DecimalString;
}
```

- Put-Call Parity 使用同一 `OptionGroupKey` 下的 call、put 与 spot/perpetual/future 对冲腿。
- Box Spread 使用同一 `exchange`、`underlyingId`、`expiryTimeMs` 下两档 `strike` 的 call/put。
- 隐含期货基差使用期权组反推隐含远期，再与同一 `underlyingId` 的 `perpetual` 或 `future` 对比。

## Instrument

`Instrument` 由元数据接口同步，更新频率低。所有参与套利计算的行情必须先有关联的 `Instrument`。

```ts
interface Instrument {
  instrumentKey: string;
  exchange: ExchangeId;
  marketType: MarketType;
  instrumentId: string;

  baseAsset: string;
  quoteAsset: string;
  settlementAsset?: string;
  underlyingId?: string;
  instrumentFamily?: string;

  expiryTimeMs?: EpochMilliseconds;
  strike?: DecimalString;
  optionType?: OptionType;

  contractType: ContractType;
  contractSize: DecimalString;
  contractValueCurrency?: string;

  tickSize?: DecimalString;
  minOrderSize?: DecimalString;
  qtyStep?: DecimalString;
  pricePrecision?: number;
  sizePrecision?: number;

  makerFeeRate?: DecimalString;
  takerFeeRate?: DecimalString;
  feeSource?: FeeSource;

  status: InstrumentStatus;
  rawSymbol?: string;
  sourceUpdatedAtMs?: EpochMilliseconds;
  normalizedAtMs: EpochMilliseconds;
  raw?: unknown;
}
```

必填约束：

- 所有市场必须有 `instrumentKey`, `exchange`, `marketType`, `instrumentId`, `baseAsset`, `quoteAsset`, `contractType`, `contractSize`, `status`, `normalizedAtMs`。
- `option` 必须有 `underlyingId`, `expiryTimeMs`, `strike`, `optionType`。
- `future` 必须有 `expiryTimeMs`。
- `perpetual` 必须不能依赖固定到期日；若交易所返回远未来 `deliveryDate`，只保留到 `raw` 或作为 `sourceUpdatedAtMs` 附属信息，不作为套利到期日。
- `makerFeeRate` 和 `takerFeeRate` 可为空，但计算净收益前必须由静态配置或账户费率补齐。

## Quote

`Quote` 是单合约行情的轻量实时视图。它可以来自 ticker、bookTicker、mark price stream 或 order book 第一档。

```ts
interface Quote {
  instrumentKey: string;
  exchange: ExchangeId;
  marketType: MarketType;
  instrumentId: string;

  bidPrice?: DecimalString;
  askPrice?: DecimalString;
  bidSize?: DecimalString;
  askSize?: DecimalString;
  midPrice?: DecimalString;
  lastPrice?: DecimalString;

  markPrice?: DecimalString;
  indexPrice?: DecimalString;
  underlyingPrice?: DecimalString;

  bidIv?: DecimalString;
  askIv?: DecimalString;
  markIv?: DecimalString;
  delta?: DecimalString;
  gamma?: DecimalString;
  vega?: DecimalString;
  theta?: DecimalString;

  sourceUpdatedAtMs?: EpochMilliseconds;
  receivedAtMs: EpochMilliseconds;
  normalizedAtMs: EpochMilliseconds;
  raw?: unknown;
}
```

计算约束：

- `midPrice` 由 adapter 在 `bidPrice` 和 `askPrice` 同时存在时计算，公式为 `(bid + ask) / 2`。
- `bidPrice > askPrice` 的 quote 必须标记为异常并拒绝进入套利计算。
- 期权套利执行价格必须使用可成交边：买入腿用 `askPrice`，卖出腿用 `bidPrice`。
- `markPrice`、`indexPrice` 只用于理论参考、展示和基差比较，不能替代真实可成交 bid/ask。

## OrderBook

`OrderBook` 是 adapter 维护后的标准化盘口快照。上游可以是 REST 快照，也可以是 WebSocket 增量合并结果。

```ts
interface OrderBookLevel {
  price: DecimalString;
  size: DecimalString;
}

interface OrderBook {
  instrumentKey: string;
  exchange: ExchangeId;
  marketType: MarketType;
  instrumentId: string;

  bids: OrderBookLevel[];
  asks: OrderBookLevel[];
  depth: number;

  sequence?: string;
  previousSequence?: string;
  checksum?: string;
  isSnapshot: boolean;

  eventTimeMs?: EpochMilliseconds;
  transactionTimeMs?: EpochMilliseconds;
  receivedAtMs: EpochMilliseconds;
  normalizedAtMs: EpochMilliseconds;
  raw?: unknown;
}
```

有效性约束：

- `bids` 必须按价格从高到低排序。
- `asks` 必须按价格从低到高排序。
- 任一档 `price <= 0` 或 `size < 0` 必须拒绝；增量里的删除语义应在 adapter 内处理，输出快照不得包含 `size=0` 档位。
- 如果 `bids[0].price > asks[0].price`，该盘口不得进入套利计算。
- adapter 必须负责交易所序列校验；发现缺口时用 REST 快照重建后再输出新的 `OrderBook`。

## FundingRate

`FundingRate` 只适用于 `perpetual`。交割合约、现货和期权没有资金费率。

```ts
interface FundingRate {
  instrumentKey: string;
  exchange: ExchangeId;
  instrumentId: string;

  fundingRateCurrent?: DecimalString;
  fundingRate8h?: DecimalString;
  fundingTimeMs?: EpochMilliseconds;
  nextFundingTimeMs?: EpochMilliseconds;
  fundingIntervalHours?: DecimalString;

  interestRate?: DecimalString;
  premium?: DecimalString;

  sourceUpdatedAtMs?: EpochMilliseconds;
  receivedAtMs: EpochMilliseconds;
  normalizedAtMs: EpochMilliseconds;
  raw?: unknown;
}
```

计算约束：

- 持仓成本不能硬编码为 8 小时；优先使用 `fundingIntervalHours`，其次使用 `fundingTimeMs` 与 `nextFundingTimeMs` 差值。
- 若交易所只给历史资金费率，当前周期估算必须标记数据来源，不得伪装为实时预测值。
- `fundingRate8h` 是标准化展示字段，不是所有交易所原始字段；缺失时由计算层按实际间隔换算。

## MarketSnapshot

`MarketSnapshot` 是套利计算层读取的组合结构。它允许 quote、order book、funding 在不同频率下更新，但必须引用同一个 `Instrument`。

```ts
interface MarketSnapshot {
  instrument: Instrument;
  quote?: Quote;
  orderBook?: OrderBook;
  fundingRate?: FundingRate;

  snapshotAtMs: EpochMilliseconds;
  dataQuality: DataQuality;
}

interface DataQuality {
  isTradable: boolean;
  hasExecutableQuote: boolean;
  hasDepth: boolean;
  hasFees: boolean;
  staleReasons: string[];
  warningTags: string[];
}
```

`DataQuality` 规则：

- `isTradable=true` 要求 `Instrument.status=trading`。
- `hasExecutableQuote=true` 要求存在合法 bid/ask，且 bid/ask 对应数量大于 0。
- `hasDepth=true` 要求 `OrderBook` 至少有一档合法 bid 和 ask。
- `hasFees=true` 要求 `makerFeeRate`、`takerFeeRate` 已由 public metadata、authenticated account 或 static config 补齐。
- 如果 `Quote`、`OrderBook` 或 `FundingRate` 超过配置的最大延迟，应在 `staleReasons` 中说明，并禁止进入机会排序的可执行结果。

## 数量单位与金额规则

统一模型不把所有 `size` 强行转换为同一种资产数量。adapter 输出原始市场语义下的标准化数量，并通过 `Instrument` 描述如何解释：

- spot：`size` 通常是 base asset 数量。
- option：`size` 依交易所规则，收益计算必须乘以 `contractSize`。
- linear perpetual/future：名义价值通常按 quote/settlement asset 计算。
- inverse perpetual/future：名义价值、保证金和 PnL 单位可能不同，必须结合 `contractType`, `contractSize`, `contractValueCurrency`, `settlementAsset` 处理。

后续计算层必须提供独立的数量换算函数，不允许在套利公式中直接假设 `size` 就是 BTC 或 USDT。

## 数据新鲜度配置

第一版默认数据新鲜度建议：

| 数据类型 | 默认最大延迟 | 超时影响 |
| --- | --- | --- |
| `Instrument` | 1 hour | 禁止新合约参与；已有合约保留但打 warning |
| `Quote` | 5 seconds | 禁止标记为可执行机会 |
| `OrderBook` | 5 seconds | 禁止使用深度和滑点过滤通过 |
| `FundingRate` | 5 minutes | 隐含期货基差机会打资金费率 stale 标签 |

这些值是系统默认配置，后续实现应允许按交易所和市场类型覆盖。

## 套利计算输入约束

### Put-Call Parity

必须输入：

- 同一 `exchange`, `underlyingId`, `expiryTimeMs`, `strike` 的 call `MarketSnapshot`
- 同一组的 put `MarketSnapshot`
- 一个 hedge snapshot：spot、perpetual 或 future
- call/put/hedge 的 executable quote 或 order book
- 三条腿的 maker/taker fee rate

输出机会前必须能说明买卖方向、理论关系、偏差、手续费、滑点和净收益。

### Box Spread

必须输入：

- 同一 `exchange`, `underlyingId`, `expiryTimeMs` 下两档 strike
- 每档 strike 的 call 和 put `MarketSnapshot`
- 四条期权腿的 executable quote 或 order book
- 四条腿手续费和最小可成交数量

输出机会前必须能说明盒式固定到期现金流、当前建仓成本、手续费后收益、年化收益率和最小可执行规模。

### 隐含期货基差

必须输入：

- 一组 call/put `MarketSnapshot`，用于反推隐含期货价格
- 一个实际 perpetual 或 future `MarketSnapshot`
- 实际合约的 `FundingRate`，如果是 perpetual
- 期权腿和期货/永续腿的 executable quote 或 order book

输出机会前必须能说明隐含期货价、实际合约价、基差、资金费率影响、持仓成本和风险标签。

## 标准化错误

adapter 遇到以下情况不得静默吞掉：

```ts
type NormalizationErrorCode =
  | "missing_required_field"
  | "invalid_decimal"
  | "invalid_timestamp"
  | "unknown_market_type"
  | "unknown_option_type"
  | "invalid_order_book"
  | "sequence_gap"
  | "unsupported_contract_shape"
  | "stale_data";

interface NormalizationError {
  exchange: ExchangeId;
  marketType?: MarketType;
  instrumentId?: string;
  code: NormalizationErrorCode;
  message: string;
  blockedLogic: Array<"put_call_parity" | "box_spread" | "implied_futures_basis">;
  raw?: unknown;
}
```

当错误会导致某类套利逻辑无法可靠计算时，必须填 `blockedLogic`，用于报警和开发排查。

## 后续实现边界

- adapter 输出本模型对象和 `NormalizationError`，不输出套利机会。
- 期权链标准化解析应围绕 `Instrument` 和 `OptionGroupKey` 实现。
- 盘口标准化应围绕 `OrderBook`、`Quote` 和数据新鲜度规则实现。
- 永续价格、指数价格、标记价格、资金费率标准化应围绕 `Quote` 与 `FundingRate` 实现。
- 计算层应只消费 `MarketSnapshot`，这样三类套利公式可以复用同一套数据质量和手续费检查。
