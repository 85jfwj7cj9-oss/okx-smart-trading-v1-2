import pytest
from market_data import MarketData


def candles(n, start=100.0, step=1.0):
    return [{"timestamp": i, "close": start + i * step} for i in range(n)]


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_candles(self, inst_id, bar, limit, confirmed_only):
        self.calls.append((inst_id, bar, limit, confirmed_only))
        if inst_id == "BTC-USDT-SWAP":
            return candles(limit, 100.0, 0.5)
        return candles(limit, 100.0, 1.0)


def test_daily_profile_returns_one_three_seven_day_metrics():
    client = FakeClient()
    market = MarketData(client=client)
    result = market.get_daily_relative_strength_profile("ETH-USDT-SWAP", limit=30)

    assert set(result) == {"1D", "3D", "7D"}
    assert all(result[key] is not None for key in result)
    assert all(result[key]["lookback"] == int(key[:-1]) for key in result)
    assert len(client.calls) == 2
    assert all(call[1:] == ("1D", 30, True) for call in client.calls)


def test_daily_profile_rejects_insufficient_limit():
    market = MarketData(client=FakeClient())
    with pytest.raises(ValueError):
        market.get_daily_relative_strength_profile("ETH-USDT-SWAP", limit=7)


def test_btc_daily_profile_is_empty_without_api_calls():
    client = FakeClient()
    market = MarketData(client=client)
    assert market.get_daily_relative_strength_profile("BTC-USDT-SWAP") == {}
    assert client.calls == []
