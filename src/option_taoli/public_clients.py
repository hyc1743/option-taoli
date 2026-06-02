from __future__ import annotations

import json
from typing import Any, Callable
from urllib import parse, request


JSONGetter = Callable[[str, int], dict[str, Any]]


class DeribitPublicClient:
    def __init__(
        self,
        *,
        base_url: str = "https://www.deribit.com/api/v2",
        get_json: JSONGetter | None = None,
        timeout_seconds: int = 10,
    ):
        self._base_url = base_url.rstrip("/")
        self._get_json = get_json or _http_get_json
        self._timeout_seconds = timeout_seconds

    def get_instruments(self, *, currency: str, kind: str, expired: bool | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"currency": currency, "kind": kind}
        if expired is not None:
            params["expired"] = _bool_text(expired)
        return self._get("public/get_instruments", params)

    def ticker(self, *, instrument_name: str) -> dict[str, Any]:
        return self._get("public/ticker", {"instrument_name": instrument_name})

    def get_order_book(self, *, instrument_name: str, depth: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"instrument_name": instrument_name}
        if depth is not None:
            params["depth"] = depth
        return self._get("public/get_order_book", params)

    def get_index_price(self, *, index_name: str) -> dict[str, Any]:
        return self._get("public/get_index_price", {"index_name": index_name})

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._get_json(_url(self._base_url, path, params), self._timeout_seconds)


class BinancePublicClient:
    def __init__(
        self,
        *,
        options_base_url: str = "https://eapi.binance.com",
        spot_base_url: str = "https://api.binance.com",
        usdm_base_url: str = "https://fapi.binance.com",
        get_json: JSONGetter | None = None,
        timeout_seconds: int = 10,
    ):
        self._options_base_url = options_base_url.rstrip("/")
        self._spot_base_url = spot_base_url.rstrip("/")
        self._usdm_base_url = usdm_base_url.rstrip("/")
        self._get_json = get_json or _http_get_json
        self._timeout_seconds = timeout_seconds

    def options_exchange_info(self) -> dict[str, Any]:
        return self._get(self._options_base_url, "/eapi/v1/exchangeInfo")

    def option_depth(self, *, symbol: str, limit: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"symbol": symbol}
        if limit is not None:
            params["limit"] = limit
        return self._get(self._options_base_url, "/eapi/v1/depth", params)

    def option_mark(self, *, symbol: str | None = None) -> dict[str, Any]:
        params = None if symbol is None else {"symbol": symbol}
        return self._get(self._options_base_url, "/eapi/v1/mark", params)

    def spot_book_ticker(self, *, symbol: str | None = None) -> dict[str, Any]:
        params = None if symbol is None else {"symbol": symbol}
        return self._get(self._spot_base_url, "/api/v3/ticker/bookTicker", params)

    def spot_depth(self, *, symbol: str, limit: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"symbol": symbol}
        if limit is not None:
            params["limit"] = limit
        return self._get(self._spot_base_url, "/api/v3/depth", params)

    def usdm_exchange_info(self) -> dict[str, Any]:
        return self._get(self._usdm_base_url, "/fapi/v1/exchangeInfo")

    def usdm_depth(self, *, symbol: str, limit: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"symbol": symbol}
        if limit is not None:
            params["limit"] = limit
        return self._get(self._usdm_base_url, "/fapi/v1/depth", params)

    def usdm_premium_index(self, *, symbol: str | None = None) -> dict[str, Any]:
        params = None if symbol is None else {"symbol": symbol}
        return self._get(self._usdm_base_url, "/fapi/v1/premiumIndex", params)

    def usdm_funding_rate(
        self,
        *,
        symbol: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if symbol is not None:
            params["symbol"] = symbol
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        if limit is not None:
            params["limit"] = limit
        return self._get(self._usdm_base_url, "/fapi/v1/fundingRate", params or None)

    def _get(self, base_url: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._get_json(_url(base_url, path, params), self._timeout_seconds)


class OkxPublicClient:
    def __init__(
        self,
        *,
        base_url: str = "https://www.okx.com",
        get_json: JSONGetter | None = None,
        timeout_seconds: int = 10,
    ):
        self._base_url = base_url.rstrip("/")
        self._get_json = get_json or _http_get_json
        self._timeout_seconds = timeout_seconds

    def instruments(
        self,
        *,
        inst_type: str,
        inst_family: str | None = None,
        inst_id: str | None = None,
    ) -> dict[str, Any]:
        return self._get(
            "/api/v5/public/instruments",
            _without_none({"instType": inst_type, "instFamily": inst_family, "instId": inst_id}),
        )

    def tickers(
        self,
        *,
        inst_type: str,
        inst_family: str | None = None,
        inst_id: str | None = None,
    ) -> dict[str, Any]:
        return self._get(
            "/api/v5/market/tickers",
            _without_none({"instType": inst_type, "instFamily": inst_family, "instId": inst_id}),
        )

    def books(self, *, inst_id: str, size: int | None = None) -> dict[str, Any]:
        return self._get("/api/v5/market/books", _without_none({"instId": inst_id, "sz": size}))

    def mark_price(
        self,
        *,
        inst_type: str,
        inst_family: str | None = None,
        inst_id: str | None = None,
    ) -> dict[str, Any]:
        return self._get(
            "/api/v5/public/mark-price",
            _without_none({"instType": inst_type, "instFamily": inst_family, "instId": inst_id}),
        )

    def index_tickers(self, *, inst_id: str | None = None, quote_ccy: str | None = None) -> dict[str, Any]:
        return self._get(
            "/api/v5/market/index-tickers",
            _without_none({"instId": inst_id, "quoteCcy": quote_ccy}),
        )

    def funding_rate(self, *, inst_id: str) -> dict[str, Any]:
        return self._get("/api/v5/public/funding-rate", {"instId": inst_id})

    def funding_rate_history(
        self,
        *,
        inst_id: str,
        after: str | None = None,
        before: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return self._get(
            "/api/v5/public/funding-rate-history",
            _without_none({"instId": inst_id, "after": after, "before": before, "limit": limit}),
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._get_json(_url(self._base_url, path, params), self._timeout_seconds)


class BybitPublicClient:
    def __init__(
        self,
        *,
        base_url: str = "https://api.bybit.com",
        get_json: JSONGetter | None = None,
        timeout_seconds: int = 10,
    ):
        self._base_url = base_url.rstrip("/")
        self._get_json = get_json or _http_get_json
        self._timeout_seconds = timeout_seconds

    def instruments_info(
        self,
        *,
        category: str,
        symbol: str | None = None,
        base_coin: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return self._get(
            "/v5/market/instruments-info",
            _without_none(
                {
                    "category": category,
                    "symbol": symbol,
                    "baseCoin": base_coin,
                    "status": status,
                    "limit": limit,
                    "cursor": cursor,
                }
            ),
        )

    def tickers(
        self,
        *,
        category: str,
        symbol: str | None = None,
        base_coin: str | None = None,
        exp_date: str | None = None,
    ) -> dict[str, Any]:
        return self._get(
            "/v5/market/tickers",
            _without_none({"category": category, "symbol": symbol, "baseCoin": base_coin, "expDate": exp_date}),
        )

    def orderbook(self, *, category: str, symbol: str, limit: int | None = None) -> dict[str, Any]:
        return self._get(
            "/v5/market/orderbook",
            _without_none({"category": category, "symbol": symbol, "limit": limit}),
        )

    def funding_history(
        self,
        *,
        category: str,
        symbol: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return self._get(
            "/v5/market/funding/history",
            _without_none(
                {
                    "category": category,
                    "symbol": symbol,
                    "startTime": start_time,
                    "endTime": end_time,
                    "limit": limit,
                }
            ),
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._get_json(_url(self._base_url, path, params), self._timeout_seconds)


class GatePublicClient:
    def __init__(
        self,
        *,
        base_url: str = "https://api.gateio.ws/api/v4",
        get_json: JSONGetter | None = None,
        timeout_seconds: int = 10,
    ):
        self._base_url = base_url.rstrip("/")
        self._get_json = get_json or _http_get_json
        self._timeout_seconds = timeout_seconds

    def options_underlyings(self) -> dict[str, Any]:
        return self._get("/options/underlyings")

    def options_expirations(self, *, underlying: str) -> dict[str, Any]:
        return self._get("/options/expirations", {"underlying": underlying})

    def options_contracts(self, *, underlying: str, expiration: int | None = None) -> dict[str, Any]:
        return self._get("/options/contracts", _without_none({"underlying": underlying, "expiration": expiration}))

    def options_tickers(self, *, underlying: str) -> dict[str, Any]:
        return self._get("/options/tickers", {"underlying": underlying})

    def options_order_book(
        self,
        *,
        contract: str,
        interval: str | None = None,
        limit: int | None = None,
        with_id: bool | None = None,
    ) -> dict[str, Any]:
        return self._get(
            "/options/order_book",
            _without_none(
                {
                    "contract": contract,
                    "interval": interval,
                    "limit": limit,
                    "with_id": None if with_id is None else _bool_text(with_id),
                }
            ),
        )

    def options_underlying_ticker(self, *, underlying: str) -> dict[str, Any]:
        return self._get(f"/options/underlying/tickers/{underlying}")

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._get_json(_url(self._base_url, path, params), self._timeout_seconds)


def _http_get_json(url: str, timeout_seconds: int) -> dict[str, Any]:
    with request.urlopen(url, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _url(base_url: str, path: str, params: dict[str, Any] | None = None) -> str:
    base = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    if not params:
        return base
    return f"{base}?{parse.urlencode(params)}"


def _without_none(params: dict[str, Any | None]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}


def _bool_text(value: bool) -> str:
    return "true" if value else "false"
