from pattern_engine import (
    Pivot, classify_xabcd, predict_prz, confirmed_fractal_pivots,
    detect_double_top_bottom, detect_head_shoulders,
)


def test_bullish_gartley_ratio_detection():
    pts = [
        Pivot(1, 1, 100.0, "LOW"),
        Pivot(5, 5, 200.0, "HIGH"),
        Pivot(9, 9, 138.2, "LOW"),
        Pivot(13, 13, 169.1, "HIGH"),
        Pivot(17, 17, 121.4, "LOW"),
    ]
    found = classify_xabcd(pts)
    assert any(x["pattern"] == "GARTLEY" and x["direction"] == "LONG" for x in found)


def test_prz_is_forecast_not_confirmation():
    pts = [
        Pivot(1, 1, 100.0, "LOW"),
        Pivot(5, 5, 200.0, "HIGH"),
        Pivot(9, 9, 138.2, "LOW"),
        Pivot(13, 13, 169.1, "HIGH"),
    ]
    zones = predict_prz(pts)
    assert zones
    assert all(x["state"] == "FORMING" for x in zones)
    assert all(x["prz_low"] <= x["prz_mid"] <= x["prz_high"] for x in zones)


def test_fractal_pivots_wait_for_right_bars():
    candles = []
    values = [10, 11, 12, 15, 12, 11, 10, 9, 11, 12, 10]
    for i, close in enumerate(values):
        candles.append({"timestamp": i, "open": close, "high": close+0.5,
                        "low": close-0.5, "close": close, "volume": 100})
    pivots = confirmed_fractal_pivots(candles, left=2, right=2)
    assert any(p.kind == "HIGH" and p.index == 3 for p in pivots)


def test_double_top_detection():
    pts = [Pivot(1,1,110,"HIGH"), Pivot(3,3,95,"LOW"), Pivot(5,5,110.5,"HIGH")]
    result = detect_double_top_bottom(pts)
    assert result and result[0]["pattern"] == "DOUBLE_TOP"


def test_head_shoulders_detection():
    pts = [
        Pivot(1,1,110,"HIGH"), Pivot(2,2,100,"LOW"),
        Pivot(3,3,125,"HIGH"), Pivot(4,4,99,"LOW"),
        Pivot(5,5,111,"HIGH"),
    ]
    result = detect_head_shoulders(pts)
    assert result and result[0]["direction"] == "SHORT"


def test_double_top_requires_neckline_close_for_confirmation():
    from pattern_extensions import detect_double_top_bottom_state
    pts = [Pivot(1, 1, 110, "HIGH"), Pivot(3, 3, 95, "LOW"), Pivot(5, 5, 110.5, "HIGH")]
    assert detect_double_top_bottom_state(pts, 100)[0]["state"] == "FORMING"
    assert detect_double_top_bottom_state(pts, 94)[0]["state"] == "CONFIRMED"


def test_head_shoulders_requires_neckline_close_for_confirmation():
    from pattern_extensions import detect_head_shoulders_state
    pts = [Pivot(1,1,110,"HIGH"), Pivot(2,2,100,"LOW"),
           Pivot(3,3,125,"HIGH"), Pivot(4,4,99,"LOW"),
           Pivot(5,5,111,"HIGH")]
    assert detect_head_shoulders_state(pts, 105)[0]["state"] == "FORMING"
    assert detect_head_shoulders_state(pts, 98)[0]["state"] == "CONFIRMED"


def test_three_drives_requires_three_complete_legs():
    from pattern_extensions import detect_three_drives
    pts = [Pivot(0,0,100,"LOW"), Pivot(1,1,110,"HIGH"),
           Pivot(2,2,101,"LOW"), Pivot(3,3,111.5,"HIGH"),
           Pivot(4,4,102,"LOW"), Pivot(5,5,115,"HIGH")]
    found = detect_three_drives(pts)
    assert found and found[0]["pattern"] == "THREE_DRIVES_BEARISH"


def test_breakout_retest_and_false_break_are_distinguished():
    from pattern_extensions import detect_breakout_retest_and_false_break
    base = [{"high": 10, "low": 8, "close": 9} for _ in range(23)]
    base[-2] = {"high": 12, "low": 9, "close": 11}
    base[-1] = {"high": 11.5, "low": 10, "close": 10.8}
    found = detect_breakout_retest_and_false_break(base, lookback=20, atr=1)
    assert any(x["pattern"] == "BULLISH_BREAKOUT_RETEST" for x in found)

    base[-1] = {"high": 11, "low": 9, "close": 9.5}
    found = detect_breakout_retest_and_false_break(base, lookback=20, atr=1)
    assert any(x["pattern"] == "BULLISH_FALSE_BREAKOUT" for x in found)
