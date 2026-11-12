from datetime import datetime, timedelta, timezone
import pytest
from relative_strength import relative_strength
from liquidity_filter import evaluate_liquidity
from signal_lifecycle import transition
from strong_radar import evaluate_early_accumulation, evaluate_breakout_momentum


def bars(closes):
    return [{"timestamp": i+1, "close": p} for i,p in enumerate(closes)]


def test_relative_strength_aligned_excess_return():
    r = relative_strength(bars([100,110,120]), bars([100,105,110]), 2)
    assert r["relative_strength_pct"] == pytest.approx(10.0)
    assert r["ratio_change_pct"] > 0


def test_relative_strength_requires_enough_aligned_bars():
    assert relative_strength(bars([100,110]), bars([100,105]), 2) is None


def test_relative_strength_rejects_invalid_window():
    with pytest.raises(ValueError): relative_strength([], [], 0)


def test_liquidity_passes_valid_ticker():
    t = {"last":"100", "bidPx":"99.95", "askPx":"100.05", "volCcyQuote24h":"6000000", "ts":"100000"}
    assert evaluate_liquidity(t, now_ms=110000)["passed"]


def test_liquidity_rejects_low_turnover_and_wide_spread():
    t = {"last":"100", "bidPx":"99", "askPx":"101", "volCcyQuote24h":"1000", "ts":"100000"}
    r = evaluate_liquidity(t, now_ms=101000)
    assert not r["passed"]
    assert "turnover_below_minimum" in r["reasons"]
    assert "spread_above_maximum" in r["reasons"]


def test_lifecycle_early_then_confirmed():
    now = datetime.now(timezone.utc)
    assert transition("WATCH", "intrabar_setup", now, now) == "EARLY_ALERT"
    assert transition("EARLY_ALERT", "closed_bar_confirmed", now, now) == "CONFIRMED"


def test_lifecycle_expires_and_terminal_stays_terminal():
    created = datetime.now(timezone.utc) - timedelta(hours=9)
    now = datetime.now(timezone.utc)
    assert transition("WATCH", "still_valid", created, now) == "EXPIRED"
    assert transition("EXPIRED", "closed_bar_confirmed", created, now) == "EXPIRED"


def test_early_radar_missing_data_does_not_score_full():
    r = evaluate_early_accumulation({"data_fresh": True})
    assert r["score"] == 0
    assert not r["eligible"]


def test_early_radar_requires_core_gates():
    f = {"rs_3d_positive":True,"rs_7d_positive":True,"ratio_trend_up":True,
         "ema20_above_or_near_ema50_4h":True,"ema20_slope_up_4h":True,
         "ema5_crossed_ema10_1h":True,"ema10_improving_ema20_1h":True,
         "liquidity_passed":True,"data_fresh":True,"minimum_score":80,
         "pullback_volume_decreasing":True,"range_contracting":True,
         "mtf_not_severely_conflicted":True,"rsi_50_to_70":True,
         "macd_hist_improving":True,"obv_rising":True,
         "within_1_5_atr_ema20":True,"risk_reward_passed":True}
    assert evaluate_early_accumulation(f)["eligible"]


def test_breakout_intrabar_is_not_confirmed():
    f = {"rs_3d_positive":True,"ratio_trend_up":True,"ema20_above_ema50_4h":True,
         "ema50_above_or_improving_ema100_4h":True,"ema5_above_ema10_above_ema20_1h":True,
         "closed_4h_close_above_previous_20_high_with_buffer":True,
         "same_elapsed_time_volume_ratio":1.8,"mtf_not_severely_conflicted":True,
         "rsi_55_to_80":True,"macd_bullish":True,"obv_rising":True,
         "adx_above_20_rising":True,"liquidity_passed":True,
         "within_2_atr_ema20":True,"risk_reward_passed":True,"data_fresh":True}
    assert evaluate_breakout_momentum(f)["state"] == "EARLY_ALERT"
    f["four_hour_candle_closed"] = True
    assert evaluate_breakout_momentum(f)["state"] == "CONFIRMED"
