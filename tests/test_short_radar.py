import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "strong_radar", Path(__file__).parents[1] / "strong_radar.py"
)
radar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(radar)


def short_a_features():
    return {
        "rs_3d_negative": True, "rs_7d_negative": True, "ratio_trend_down": True,
        "ema20_below_or_near_ema50_4h": True, "ema20_slope_down_4h": True,
        "ema5_crossed_below_ema10_1h": True, "ema10_weakening_ema20_1h": True,
        "rally_volume_decreasing": True, "range_contracting": True,
        "mtf_not_severely_conflicted": True, "rsi_30_to_50": True,
        "macd_hist_deteriorating": True, "obv_falling": True,
        "liquidity_passed": True, "within_1_5_atr_ema20": True,
        "risk_reward_passed": True, "data_fresh": True,
    }


def short_b_features():
    return {
        "rs_3d_negative": True, "ratio_trend_down": True,
        "ema20_below_ema50_4h": True, "ema50_below_or_weakening_ema100_4h": True,
        "ema5_below_ema10_below_ema20_1h": True,
        "closed_4h_close_below_previous_20_low_with_buffer": True,
        "same_elapsed_time_volume_ratio": 1.7, "mtf_not_severely_conflicted": True,
        "rsi_below_45": True, "macd_bearish": True, "obv_falling": True,
        "adx_above_20_rising": True, "liquidity_passed": True,
        "within_2_atr_ema20": True, "risk_reward_passed": True,
        "data_fresh": True, "four_hour_candle_closed": True,
    }


def test_short_a_scores_and_alerts():
    result = radar.evaluate_early_distribution(short_a_features())
    assert result["strategy"] == "RADAR-SHORT-A"
    assert result["score"] == 100
    assert result["state"] == "EARLY_ALERT"


def test_short_a_missing_core_gate_blocks():
    features = short_a_features()
    features["rs_7d_negative"] = False
    result = radar.evaluate_early_distribution(features)
    assert not result["eligible"]
    assert result["state"] == "WATCH"


def test_short_b_closed_candle_confirms():
    result = radar.evaluate_breakdown_momentum(short_b_features())
    assert result["strategy"] == "RADAR-SHORT-B"
    assert result["score"] == 100
    assert result["state"] == "CONFIRMED"


def test_short_b_intrabar_is_not_confirmed():
    features = short_b_features()
    features["four_hour_candle_closed"] = False
    result = radar.evaluate_breakdown_momentum(features)
    assert result["eligible"]
    assert result["state"] == "EARLY_ALERT"


def test_short_b_requires_same_elapsed_time_volume():
    features = short_b_features()
    features["same_elapsed_time_volume_ratio"] = 1.2
    result = radar.evaluate_breakdown_momentum(features)
    assert not result["eligible"]
    assert result["state"] == "WATCH"


def test_short_scores_are_independent_from_long():
    assert radar.WEIGHTS_SHORT_A is not radar.WEIGHTS_A
    assert radar.WEIGHTS_SHORT_B is not radar.WEIGHTS_B
