"""Tests for inverse (BTC-settled) option calculations."""

from decimal import Decimal

from option_taoli.adapters.deribit import DeribitAdapter
from option_taoli.box_spread import calculate_box_spreads
from option_taoli.implied_futures_basis import calculate_implied_futures_basis
from option_taoli.market_depth import standardize_quote
from option_taoli.option_chain import build_option_chain
from option_taoli.put_call_parity import calculate_put_call_parity


def test_inverse_put_call_parity_atm():
    """PCP with inverse options at ATM: implied forward should approximate spot."""
    adapter = DeribitAdapter(normalized_at_ms=1810880000000, received_at_ms=1810880000123)
    # Realistic inverse option prices: premiums in BTC per 1 BTC notional
    # ATM call ~0.025 BTC, ATM put ~0.025 BTC, spot ~74000, strike 74000
    call_inst = _make_option(adapter, "BTC-28JUN26-74000-C", 74000, "call")
    put_inst = _make_option(adapter, "BTC-28JUN26-74000-P", 74000, "put")
    chain = build_option_chain([call_inst, put_inst])
    pair = chain.complete_pairs()[0]

    call_q = _make_quote(adapter, "BTC-28JUN26-74000-C", "0.024", "0.026", "option")
    put_q = _make_quote(adapter, "BTC-28JUN26-74000-P", "0.023", "0.025", "option")
    hedge_q = _make_quote(adapter, "BTC-PERPETUAL", "73900", "74100", "perpetual")

    # Inverse: F = K / (1 - C + P)
    # Long synth: F = 74000 / (1 - 0.026 + 0.023) = 74000 / 0.997 = 74222.7
    # Profit = hedge_bid - F = 73900 - 74222.7 = -322.7 (no opportunity)
    # Short synth: F = 74000 / (1 - 0.024 + 0.025) = 74000 / 1.001 = 73926.1
    # Profit = F - hedge_ask = 73926.1 - 74100 = -173.9 (no opportunity)
    result = calculate_put_call_parity(
        pair, call_q, put_q, hedge_q, contract_type="inverse"
    )
    assert result is None  # ATM shouldn't have arbitrage


def test_inverse_put_call_parity_with_deviation():
    """PCP with inverse options where there is a deviation."""
    adapter = DeribitAdapter(normalized_at_ms=1810880000000, received_at_ms=1810880000123)
    call_inst = _make_option(adapter, "BTC-28JUN26-74000-C", 74000, "call")
    put_inst = _make_option(adapter, "BTC-28JUN26-74000-P", 74000, "put")
    chain = build_option_chain([call_inst, put_inst])
    pair = chain.complete_pairs()[0]

    # call expensive, put cheap → synthetic forward is high → sell synth, buy hedge
    call_q = _make_quote(adapter, "BTC-28JUN26-74000-C", "0.028", "0.030", "option")
    put_q = _make_quote(adapter, "BTC-28JUN26-74000-P", "0.018", "0.020", "option")
    hedge_q = _make_quote(adapter, "BTC-PERPETUAL", "73800", "73900", "perpetual")

    result = calculate_put_call_parity(
        pair, call_q, put_q, hedge_q, contract_type="inverse"
    )
    # Short synth: F = 74000 / (1 - 0.028 + 0.020) = 74000 / 0.992 = 74596.8
    # Profit = F - hedge_ask = 74596.8 - 73900 = 696.8
    assert result is not None
    assert result.direction == "short_synthetic_long_hedge"
    assert Decimal(result.gross_profit) > 0
    assert result.risk_tags == ["inverse_settlement"]


def test_inverse_implied_futures_basis():
    """Inverse IFB: implied futures deviate from actual."""
    adapter = DeribitAdapter(normalized_at_ms=1810880000000, received_at_ms=1810880000123)
    call_inst = _make_option(adapter, "BTC-28JUN26-74000-C", 74000, "call")
    put_inst = _make_option(adapter, "BTC-28JUN26-74000-P", 74000, "put")
    chain = build_option_chain([call_inst, put_inst])
    pair = chain.complete_pairs()[0]

    # call cheap, put expensive → implied forward low → buy implied, sell actual
    call_q = _make_quote(adapter, "BTC-28JUN26-74000-C", "0.020", "0.022", "option")
    put_q = _make_quote(adapter, "BTC-28JUN26-74000-P", "0.024", "0.026", "option")
    actual_q = _make_quote(adapter, "BTC-PERPETUAL", "74300", "74400", "perpetual")

    result = calculate_implied_futures_basis(
        pair, call_q, put_q, actual_q, contract_type="inverse"
    )
    # Implied ask: F = 74000 / (1 - 0.022 + 0.024) = 74000 / 1.002 = 73852.3
    # Profit = actual_bid - implied = 74300 - 73852.3 = 447.7
    assert result is not None
    assert result.direction == "buy_implied_sell_actual"
    assert Decimal(result.gross_profit) > 0
    assert "inverse_settlement" in result.risk_tags


def test_inverse_box_spread():
    """Inverse box spread: payoff in USD is K_u - K_l, entry cost in BTC * hedge_price."""
    adapter = DeribitAdapter(normalized_at_ms=1810880000000, received_at_ms=1810880000123)
    # Create instruments for two strikes: 72000 and 74000
    call_l = _make_option(adapter, "BTC-28JUN26-72000-C", 72000, "call")
    put_l = _make_option(adapter, "BTC-28JUN26-72000-P", 72000, "put")
    call_u = _make_option(adapter, "BTC-28JUN26-74000-C", 74000, "call")
    put_u = _make_option(adapter, "BTC-28JUN26-74000-P", 74000, "put")

    chain = build_option_chain([call_l, put_l, call_u, put_u])
    expiry = list(chain.expiries.values())[0]

    # Realistic BTC option premiums
    quotes = {
        call_l.instrument_key: _make_quote(adapter, "BTC-28JUN26-72000-C", "0.033", "0.035", "option"),
        put_l.instrument_key: _make_quote(adapter, "BTC-28JUN26-72000-P", "0.016", "0.018", "option"),
        call_u.instrument_key: _make_quote(adapter, "BTC-28JUN26-74000-C", "0.022", "0.024", "option"),
        put_u.instrument_key: _make_quote(adapter, "BTC-28JUN26-74000-P", "0.024", "0.026", "option"),
    }

    # hedge_price = 74000 (current BTC/USD)
    # Long box entry: buy C_l@0.035, sell C_u@0.022, buy P_u@0.026, sell P_l@0.016
    #   entry_btc = 0.035 - 0.022 + 0.026 - 0.016 = 0.023 BTC
    #   entry_usd = 0.023 * 74000 = 1702
    #   payoff = K_u - K_l = 74000 - 72000 = 2000 USD
    #   profit = 2000 - 1702 = 298
    results = calculate_box_spreads(
        expiry, quotes, now_ms=1810880000000, contract_type="inverse", hedge_price="74000"
    )

    long_boxes = [o for o in results if o.direction == "long_box"]
    assert len(long_boxes) == 1
    box = long_boxes[0]
    assert Decimal(box.fixed_cashflow) == Decimal("2000")
    assert Decimal(box.gross_profit) > 0
    assert Decimal(box.gross_profit) < Decimal("500")  # Should be ~298
    assert box.risk_tags == ["inverse_settlement"]


def _make_option(adapter: DeribitAdapter, name: str, strike: float, opt_type: str):
    return adapter.normalize_instrument({
        "instrument_name": name,
        "kind": "option",
        "base_currency": "BTC",
        "quote_currency": "USD",
        "settlement_currency": "BTC",
        "expiration_timestamp": 1811744000000,
        "strike": str(int(strike)),
        "option_type": opt_type,
        "instrument_type": "reversed",
        "settlement_period": "month",
        "contract_size": "1",
        "tick_size": "0.5",
        "price_index": "btc_usd",
        "state": "open",
    })


def _make_quote(adapter: DeribitAdapter, name: str, bid: str, ask: str, market_type: str):
    return standardize_quote(
        adapter.normalize_quote(
            {
                "instrument_name": name,
                "best_bid_price": bid,
                "best_ask_price": ask,
                "best_bid_amount": "50",
                "best_ask_amount": "50",
                "timestamp": 1810880000000,
            },
            market_type=market_type,
        )
    )
