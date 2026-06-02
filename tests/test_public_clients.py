from option_taoli.public_clients import (
    BinancePublicClient,
    BybitPublicClient,
    DeribitPublicClient,
    GatePublicClient,
    OkxPublicClient,
)


class FakeJSONGetter:
    def __init__(self):
        self.urls = []

    def __call__(self, url: str, timeout_seconds: int) -> dict:
        self.urls.append((url, timeout_seconds))
        return {"url": url}


def test_deribit_public_client_builds_official_market_data_urls():
    getter = FakeJSONGetter()
    client = DeribitPublicClient(get_json=getter, timeout_seconds=7)

    client.get_instruments(currency="BTC", kind="option", expired=False)
    client.ticker(instrument_name="BTC-PERPETUAL")
    client.get_order_book(instrument_name="BTC-PERPETUAL", depth=5)
    client.get_index_price(index_name="btc_usd")

    assert getter.urls == [
        (
            "https://www.deribit.com/api/v2/public/get_instruments?currency=BTC&kind=option&expired=false",
            7,
        ),
        ("https://www.deribit.com/api/v2/public/ticker?instrument_name=BTC-PERPETUAL", 7),
        ("https://www.deribit.com/api/v2/public/get_order_book?instrument_name=BTC-PERPETUAL&depth=5", 7),
        ("https://www.deribit.com/api/v2/public/get_index_price?index_name=btc_usd", 7),
    ]


def test_binance_public_client_builds_separate_options_spot_and_usdm_urls():
    getter = FakeJSONGetter()
    client = BinancePublicClient(get_json=getter, timeout_seconds=6)

    client.options_exchange_info()
    client.option_depth(symbol="BTC-260626-140000-C", limit=10)
    client.option_mark(symbol="BTC-260626-140000-C")
    client.spot_book_ticker(symbol="BTCUSDT")
    client.usdm_exchange_info()
    client.usdm_premium_index(symbol="BTCUSDT")
    client.usdm_funding_rate(symbol="BTCUSDT", limit=2)

    assert getter.urls == [
        ("https://eapi.binance.com/eapi/v1/exchangeInfo", 6),
        ("https://eapi.binance.com/eapi/v1/depth?symbol=BTC-260626-140000-C&limit=10", 6),
        ("https://eapi.binance.com/eapi/v1/mark?symbol=BTC-260626-140000-C", 6),
        ("https://api.binance.com/api/v3/ticker/bookTicker?symbol=BTCUSDT", 6),
        ("https://fapi.binance.com/fapi/v1/exchangeInfo", 6),
        ("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT", 6),
        ("https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=2", 6),
    ]


def test_okx_public_client_builds_v5_public_and_market_urls():
    getter = FakeJSONGetter()
    client = OkxPublicClient(get_json=getter, timeout_seconds=5)

    client.instruments(inst_type="OPTION", inst_family="BTC-USD")
    client.tickers(inst_type="SWAP", inst_family="BTC-USDT")
    client.books(inst_id="BTC-USDT-SWAP", size=5)
    client.mark_price(inst_type="SWAP", inst_id="BTC-USDT-SWAP")
    client.index_tickers(inst_id="BTC-USDT")
    client.funding_rate(inst_id="BTC-USDT-SWAP")

    assert getter.urls == [
        ("https://www.okx.com/api/v5/public/instruments?instType=OPTION&instFamily=BTC-USD", 5),
        ("https://www.okx.com/api/v5/market/tickers?instType=SWAP&instFamily=BTC-USDT", 5),
        ("https://www.okx.com/api/v5/market/books?instId=BTC-USDT-SWAP&sz=5", 5),
        ("https://www.okx.com/api/v5/public/mark-price?instType=SWAP&instId=BTC-USDT-SWAP", 5),
        ("https://www.okx.com/api/v5/market/index-tickers?instId=BTC-USDT", 5),
        ("https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP", 5),
    ]


def test_bybit_public_client_builds_v5_market_urls():
    getter = FakeJSONGetter()
    client = BybitPublicClient(get_json=getter, timeout_seconds=4)

    client.instruments_info(category="option", base_coin="BTC", limit=2)
    client.tickers(category="linear", symbol="BTCUSDT")
    client.orderbook(category="spot", symbol="BTCUSDT", limit=5)
    client.funding_history(category="linear", symbol="BTCUSDT", limit=2)

    assert getter.urls == [
        ("https://api.bybit.com/v5/market/instruments-info?category=option&baseCoin=BTC&limit=2", 4),
        ("https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT", 4),
        ("https://api.bybit.com/v5/market/orderbook?category=spot&symbol=BTCUSDT&limit=5", 4),
        ("https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&limit=2", 4),
    ]


def test_gate_public_client_builds_options_urls():
    getter = FakeJSONGetter()
    client = GatePublicClient(get_json=getter, timeout_seconds=3)

    client.options_underlyings()
    client.options_expirations(underlying="BTC_USDT")
    client.options_contracts(underlying="BTC_USDT", expiration=1811744000)
    client.options_tickers(underlying="BTC_USDT")
    client.options_order_book(contract="BTC_USDT-20211130-65000-C", limit=5, with_id=True)
    client.options_underlying_ticker(underlying="BTC_USDT")

    assert getter.urls == [
        ("https://api.gateio.ws/api/v4/options/underlyings", 3),
        ("https://api.gateio.ws/api/v4/options/expirations?underlying=BTC_USDT", 3),
        ("https://api.gateio.ws/api/v4/options/contracts?underlying=BTC_USDT&expiration=1811744000", 3),
        ("https://api.gateio.ws/api/v4/options/tickers?underlying=BTC_USDT", 3),
        (
            "https://api.gateio.ws/api/v4/options/order_book?contract=BTC_USDT-20211130-65000-C&limit=5&with_id=true",
            3,
        ),
        ("https://api.gateio.ws/api/v4/options/underlying/tickers/BTC_USDT", 3),
    ]
