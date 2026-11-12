"""Deterministic V1.1 long-only radar scoring on already-computed snapshots.

This module does not fetch data, place orders, or claim that a signal is a fill.
The caller must pass confirmed-candle features and separately validated freshness.
"""
from __future__ import annotations

WEIGHTS_A = {"btc_rs":20, "trend_4h":20, "structure_1h":20,
             "volume_contraction":5, "mtf":10, "momentum":15,
             "liquidity":5, "risk_quality":5}
WEIGHTS_B = {"btc_rs":20, "trend_4h":20, "trend_1h":5,
             "breakout_volume":25, "mtf":10, "momentum":10,
             "liquidity":5, "risk_quality":5}


def _score(weights, checks):
    detail, total = {}, 0.0
    for key, weight in weights.items():
        value = checks.get(key)
        # Missing evidence earns zero, never implicit full credit.
        points = float(weight) if value is True else 0.0
        detail[key] = {"passed": value is True, "points": points, "maximum": weight}
        total += points
    return {"score": round(total, 2), "grade": (
        "S" if total >= 90 else "A" if total >= 80 else
        "B" if total >= 70 else "C" if total >= 60 else "EXCLUDE"),
        "breakdown": detail}


def evaluate_early_accumulation(features: dict) -> dict:
    """A-mode. Core gates are strict; supporting conditions contribute points."""
    f = features or {}
    checks = {
        "btc_rs": bool(f.get("rs_3d_positive") and f.get("rs_7d_positive") and f.get("ratio_trend_up")),
        "trend_4h": bool(f.get("ema20_above_or_near_ema50_4h") and f.get("ema20_slope_up_4h")),
        "structure_1h": bool(f.get("ema5_crossed_ema10_1h") and f.get("ema10_improving_ema20_1h")),
        "volume_contraction": bool(f.get("pullback_volume_decreasing") and f.get("range_contracting")),
        "mtf": bool(f.get("mtf_not_severely_conflicted")),
        "momentum": bool(f.get("rsi_50_to_70") and f.get("macd_hist_improving") and f.get("obv_rising")),
        "liquidity": bool(f.get("liquidity_passed")),
        "risk_quality": bool(f.get("within_1_5_atr_ema20") and f.get("risk_reward_passed")),
    }
    scored = _score(WEIGHTS_A, checks)
    core = checks["btc_rs"] and checks["trend_4h"] and checks["structure_1h"] and checks["liquidity"]
    eligible = core and scored["score"] >= int(f.get("minimum_score", 80)) and f.get("data_fresh") is True
    return {"strategy": "RADAR-LONG-A", **scored, "core_gates_passed": core,
            "eligible": eligible, "state": "EARLY_ALERT" if eligible else "WATCH",
            "reasons": [k for k,v in checks.items() if v]}


def evaluate_breakout_momentum(features: dict) -> dict:
    """B-mode. A formal confirmation requires a closed 4H breakout candle."""
    f = features or {}
    checks = {
        "btc_rs": bool(f.get("rs_3d_positive") and f.get("ratio_trend_up")),
        "trend_4h": bool(f.get("ema20_above_ema50_4h") and f.get("ema50_above_or_improving_ema100_4h")),
        "trend_1h": bool(f.get("ema5_above_ema10_above_ema20_1h")),
        "breakout_volume": bool(f.get("closed_4h_close_above_previous_20_high_with_buffer") and f.get("same_elapsed_time_volume_ratio", 0) >= 1.5),
        "mtf": bool(f.get("mtf_not_severely_conflicted")),
        "momentum": bool(f.get("rsi_55_to_80") and f.get("macd_bullish") and f.get("obv_rising") and f.get("adx_above_20_rising")),
        "liquidity": bool(f.get("liquidity_passed")),
        "risk_quality": bool(f.get("within_2_atr_ema20") and f.get("risk_reward_passed")),
    }
    scored = _score(WEIGHTS_B, checks)
    core = checks["btc_rs"] and checks["trend_4h"] and checks["breakout_volume"] and checks["liquidity"]
    eligible = core and scored["score"] >= int(f.get("minimum_score", 80)) and f.get("data_fresh") is True
    confirmed = eligible and f.get("four_hour_candle_closed") is True
    return {"strategy": "RADAR-LONG-B", **scored, "core_gates_passed": core,
            "eligible": eligible, "state": "CONFIRMED" if confirmed else "EARLY_ALERT" if eligible else "WATCH",
            "reasons": [k for k,v in checks.items() if v]}


WEIGHTS_SHORT_A = {"btc_rs":20, "trend_4h":20, "structure_1h":20,
                   "volume_contraction":5, "mtf":10, "momentum":15,
                   "liquidity":5, "risk_quality":5}
WEIGHTS_SHORT_B = {"btc_rs":20, "trend_4h":20, "trend_1h":5,
                   "breakdown_volume":25, "mtf":10, "momentum":10,
                   "liquidity":5, "risk_quality":5}


def evaluate_early_distribution(features: dict) -> dict:
    """SHORT-A: early bearish setup; requires weakness vs BTC and weakening structure."""
    f = features or {}
    checks = {
        "btc_rs": bool(f.get("rs_3d_negative") and f.get("rs_7d_negative") and f.get("ratio_trend_down")),
        "trend_4h": bool(f.get("ema20_below_or_near_ema50_4h") and f.get("ema20_slope_down_4h")),
        "structure_1h": bool(f.get("ema5_crossed_below_ema10_1h") and f.get("ema10_weakening_ema20_1h")),
        "volume_contraction": bool(f.get("rally_volume_decreasing") and f.get("range_contracting")),
        "mtf": bool(f.get("mtf_not_severely_conflicted")),
        "momentum": bool(f.get("rsi_30_to_50") and f.get("macd_hist_deteriorating") and f.get("obv_falling")),
        "liquidity": bool(f.get("liquidity_passed")),
        "risk_quality": bool(f.get("within_1_5_atr_ema20") and f.get("risk_reward_passed")),
    }
    scored = _score(WEIGHTS_SHORT_A, checks)
    core = checks["btc_rs"] and checks["trend_4h"] and checks["structure_1h"] and checks["liquidity"]
    eligible = core and scored["score"] >= int(f.get("minimum_score", 80)) and f.get("data_fresh") is True
    return {"strategy": "RADAR-SHORT-A", **scored, "core_gates_passed": core,
            "eligible": eligible, "state": "EARLY_ALERT" if eligible else "WATCH",
            "reasons": [k for k,v in checks.items() if v]}


def evaluate_breakdown_momentum(features: dict) -> dict:
    """SHORT-B: bearish breakdown; confirmation only after a closed 4H candle."""
    f = features or {}
    checks = {
        "btc_rs": bool(f.get("rs_3d_negative") and f.get("ratio_trend_down")),
        "trend_4h": bool(f.get("ema20_below_ema50_4h") and f.get("ema50_below_or_weakening_ema100_4h")),
        "trend_1h": bool(f.get("ema5_below_ema10_below_ema20_1h")),
        "breakdown_volume": bool(f.get("closed_4h_close_below_previous_20_low_with_buffer") and f.get("same_elapsed_time_volume_ratio", 0) >= 1.5),
        "mtf": bool(f.get("mtf_not_severely_conflicted")),
        "momentum": bool(f.get("rsi_below_45") and f.get("macd_bearish") and f.get("obv_falling") and f.get("adx_above_20_rising")),
        "liquidity": bool(f.get("liquidity_passed")),
        "risk_quality": bool(f.get("within_2_atr_ema20") and f.get("risk_reward_passed")),
    }
    scored = _score(WEIGHTS_SHORT_B, checks)
    core = checks["btc_rs"] and checks["trend_4h"] and checks["breakdown_volume"] and checks["liquidity"]
    eligible = core and scored["score"] >= int(f.get("minimum_score", 80)) and f.get("data_fresh") is True
    confirmed = eligible and f.get("four_hour_candle_closed") is True
    return {"strategy": "RADAR-SHORT-B", **scored, "core_gates_passed": core,
            "eligible": eligible, "state": "CONFIRMED" if confirmed else "EARLY_ALERT" if eligible else "WATCH",
            "reasons": [k for k,v in checks.items() if v]}
