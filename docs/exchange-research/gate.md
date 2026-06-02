# Gate options research

- REST base endpoint: `https://api.gateio.ws/api/v4`
- Reference: https://www.gate.com/docs/developers/apiv4/zh_CN/options/

## Public endpoints

| Purpose | Endpoint | Notes |
| --- | --- | --- |
| Underlyings | `GET /options/underlyings` | Returns `name`, `index_price` |
| Expirations | `GET /options/expirations?underlying=BTC_USDT` | Unix seconds |
| Contracts | `GET /options/contracts?underlying=BTC_USDT` | Contract metadata |
| Tickers | `GET /options/tickers?underlying=BTC_USDT` | Top-of-book quote, IV, Greeks |
| Order book | `GET /options/order_book?contract=...` | Uses `p`/`s` level objects |
| Underlying ticker | `GET /options/underlying/tickers/BTC_USDT` | Index price for hedge grouping |

## Internal mapping

| Internal field | Gate field | Notes |
| --- | --- | --- |
| `exchange` | constant `gate` | Adapter injected |
| `instrument_id` | `name` | Example `BTC_USDT-20211130-65000-C` |
| `underlying_id` | `underlying` | Replaced with shared BTC hedge group in live scanner |
| `expiry_time_ms` | `expiration_time * 1000` | Gate returns seconds |
| `strike` | `strike_price` | Decimal string |
| `option_type` | `is_call` or symbol suffix | `true` = call |
| `contract_size` | `multiplier` | Gate contract face value in base asset |
| `tick_size` | `order_price_round` | Falls back to `mark_price_round` |
| `bid_price` / `ask_price` | `bid1_price` / `ask1_price` | Zero values are treated as missing |
| `bid_size` / `ask_size` | `bid1_size` / `ask1_size` | Zero values are treated as missing |
| `mark_iv`, Greeks | same names | `rho` is not represented in the current model |

The live scanner uses `BTC_USDT` options, filters contracts from `/options/contracts`, keeps ticker rows from `/options/tickers` for contract availability, and fetches `/options/order_book` for each selected contract so option executable quotes come from real depth. The Gate underlying index price is still used as a same-exchange spot-like hedge reference.
