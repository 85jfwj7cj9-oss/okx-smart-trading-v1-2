from pattern_scanner import PatternScanner


def test_pattern_scanner_returns_simulation_only_contract():
    candles = []
    # Deterministic oscillating series with valid OHLCV.
    for i in range(120):
        close = 100 + 8 * __import__("math").sin(i / 5) + i * 0.05
        candles.append({"timestamp": i, "open": close-0.2, "high": close+1,
                        "low": close-1, "close": close, "volume": 1000+i})
    scanner = PatternScanner()
    result = scanner.scan_symbol("ETH-USDT-SWAP", {
        "1D": candles, "4H": candles, "1H": candles
    })
    assert result["symbol"] == "ETH-USDT-SWAP"
    assert result["auto_trading"] is False
    assert result["trading_mode"] == "simulation_only"
    for item in result["pattern_signals"]:
        assert item["auto_trading"] is False
        assert item["trading_mode"] == "simulation_only"


def test_scanner_keeps_pattern_candidates_simulation_only_and_explicit_states():
    import math
    candles = []
    for i in range(160):
        close = 100 + 10 * math.sin(i / 4.5) + i * 0.03
        candles.append({"timestamp": i, "open": close-0.1,
                        "high": close+0.8, "low": close-0.8,
                        "close": close, "volume": 1000})
    result = PatternScanner().scan_timeframe("BTC-TEST", "4H", candles)
    assert all(x.get("auto_trading") is False for x in result)
    assert all(x.get("trading_mode") == "simulation_only" for x in result)
    assert all(x.get("state") in {"EARLY_ALERT", "COMPLETED", "CONFIRMED", "FORMING"}
               for x in result)


def test_xabcd_confirmation_uses_latest_bar_not_old_post_d_bar():
    from pattern_scanner import is_xabcd_reversal_confirmed
    candles = [
        {"high": 100, "low": 90, "close": 95},  # D
        {"high": 101, "low": 94, "close": 102},  # earlier break
        {"high": 104, "low": 98, "close": 100},  # latest did not break
    ]
    assert is_xabcd_reversal_confirmed(candles, 0, "LONG", 90) is False
    candles[-1] = {"high": 106, "low": 99, "close": 105}
    assert is_xabcd_reversal_confirmed(candles, 0, "LONG", 90) is True


def test_xabcd_confirmation_rejects_same_candle_as_d():
    from pattern_scanner import is_xabcd_reversal_confirmed
    candles = [{"high": 100, "low": 90, "close": 101}]
    assert is_xabcd_reversal_confirmed(candles, 0, "LONG", 90) is False


def test_shark_is_detected_as_oxabc_not_xabcd():
    from pattern_engine import Pivot, detect_shark
    pivots = [
        Pivot(10, 10, 100.0, "LOW"),
        Pivot(20, 20, 120.0, "HIGH"),
        Pivot(30, 30, 112.0, "LOW"),
        Pivot(40, 40, 125.0, "HIGH"),
        Pivot(50, 50, 102.0, "LOW"),
    ]
    found = detect_shark(pivots)
    assert len(found) == 1
    assert found[0]["pattern"] == "SHARK"
    assert found[0]["direction"] == "LONG"
    assert set(found[0]["points"]) == set("OXABC")


def test_shark_rejects_wrong_pivot_sequence():
    from pattern_engine import Pivot, detect_shark
    pivots = [
        Pivot(10, 10, 100.0, "LOW"),
        Pivot(20, 20, 120.0, "HIGH"),
        Pivot(30, 30, 112.0, "LOW"),
        Pivot(40, 40, 125.0, "HIGH"),
        Pivot(50, 50, 110.0, "HIGH"),
    ]
    assert detect_shark(pivots) == []


def test_pattern_scanner_accepts_15m_as_auxiliary_timeframe():
    from pattern_scanner import PatternScanner
    assert "15M" in PatternScanner.TIMEFRAMES
