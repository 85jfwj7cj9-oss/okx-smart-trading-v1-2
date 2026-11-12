"""Pattern scanner over confirmed OHLCV candles; no order execution."""
from __future__ import annotations

from datetime import datetime, timezone
import math

from pattern_engine import (
    confirmed_fractal_pivots, classify_xabcd, predict_prz,
    detect_channel_breakout, detect_shark,
)
from pattern_extensions import (
    detect_double_top_bottom_state, detect_head_shoulders_state,
    detect_three_drives, detect_wedge_or_triangle, detect_flag,
    detect_breakout_retest_and_false_break,
)


def _atr(candles: list[dict], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        prev = float(candles[i-1]["close"])
        high, low = float(candles[i]["high"]), float(candles[i]["low"])
        trs.append(max(high-low, abs(high-prev), abs(low-prev)))
    tail = trs[-period:]
    return sum(tail)/len(tail) if tail else None


def is_xabcd_reversal_confirmed(candles: list[dict], d_index: int,
                               direction: str, completion_price: float) -> bool:
    """Confirm on the latest closed bar only, after the confirmed D pivot."""
    if not isinstance(candles, list) or len(candles) < 2:
        return False
    if not isinstance(d_index, int) or d_index < 0 or d_index >= len(candles) - 1:
        return False
    latest, previous = candles[-1], candles[-2]
    try:
        close = float(latest["close"])
        prev_high = float(previous["high"])
        prev_low = float(previous["low"])
        d_price = float(completion_price)
    except (KeyError, TypeError, ValueError):
        return False
    if direction == "LONG":
        return close > prev_high and close > d_price
    if direction == "SHORT":
        return close < prev_low and close < d_price
    return False


def _trade_plan(direction: str, entry: float, atr: float) -> dict:
    buffer = max(atr * 0.25, entry * 0.001)
    if direction == "LONG":
        stop = entry - atr - buffer
        risk = entry - stop
        targets = [entry + risk * r for r in (2, 3, 4)]
    else:
        stop = entry + atr + buffer
        risk = stop - entry
        targets = [entry - risk * r for r in (2, 3, 4)]
    return {
        "entry_price": round(entry, 10), "stop_loss": round(stop, 10),
        "tp1": round(targets[0], 10), "tp2": round(targets[1], 10),
        "tp3": round(targets[2], 10), "reward_risk_ratio": 2.0,
        "status": "simulation_only", "auto_trading": False,
        "sizing_required": True,
    }


class PatternScanner:
    """Scan confirmed 1D/4H/1H candle sets and return forming/confirmed patterns."""

    TIMEFRAMES = ("1W", "1D", "4H", "1H", "15M")

    def __init__(self, pivot_left: int = 3, pivot_right: int = 3,
                 prz_atr_distance: float = 0.5):
        self.pivot_left = pivot_left
        self.pivot_right = pivot_right
        self.prz_atr_distance = prz_atr_distance

    def scan_timeframe(self, symbol: str, timeframe: str,
                       candles: list[dict]) -> list[dict]:
        if timeframe not in self.TIMEFRAMES:
            raise ValueError(f"Unsupported pattern timeframe: {timeframe}")
        if not isinstance(candles, list) or len(candles) < 30:
            return []
        pivots = confirmed_fractal_pivots(
            candles, self.pivot_left, self.pivot_right
        )
        if len(pivots) < 3:
            return []
        last = candles[-1]
        price = float(last["close"])
        atr = _atr(candles)
        if atr is None or not math.isfinite(atr) or atr <= 0:
            return []
        results = []
        for item in classify_xabcd(pivots):
            item = dict(item)
            d_index = item["points"]["D"]["index"]
            # Latest closed candle must break its immediate predecessor after D.
            confirmed = is_xabcd_reversal_confirmed(
                candles, d_index, item["direction"], item["completion_price"]
            )
            ratios = item.get("ratios") or {}
            ratio_values = [float(v) for v in ratios.values()
                            if isinstance(v, (int, float)) and math.isfinite(float(v))]
            # Geometry-only score; not a win-probability estimate.
            ratio_quality = 1.0 / (1.0 + sum(abs(v) for v in ratio_values) / max(len(ratio_values), 1))
            pattern_score = min(95, max(60, round(65 + 35 * ratio_quality)))
            d_price = float(item.get("completion_price", price))
            item.update({"symbol": symbol, "timeframe": timeframe,
                         "strategy": f"PATTERN-{item['pattern']}",
                         "score": pattern_score, "price": price,
                         "invalidation_price": d_price,
                         "state": "CONFIRMED" if confirmed else "COMPLETED",
                         "trade_plan": (_trade_plan(item["direction"], price, atr)
                                        if confirmed else None),
                         "trading_mode": "simulation_only", "auto_trading": False})
            results.append(item)
        # Shark is an O-X-A-B-C structure, not an X-A-B-C-D pattern.
        for item in detect_shark(pivots):
            item = dict(item)
            c_index = item["points"]["C"]["index"]
            confirmed = is_xabcd_reversal_confirmed(
                candles, c_index, item["direction"], item["completion_price"]
            )
            item.update({"symbol": symbol, "timeframe": timeframe,
                         "strategy": "PATTERN-SHARK", "score": 75,
                         "price": price,
                         "invalidation_price": item["completion_price"],
                         "state": "CONFIRMED" if confirmed else "COMPLETED",
                         "trade_plan": (_trade_plan(item["direction"], price, atr)
                                        if confirmed else None),
                         "trading_mode": "simulation_only", "auto_trading": False})
            results.append(item)
        # Potential D zones are alerts only, never confirmed entries.
        for item in predict_prz(pivots):
            distance = abs(price - item["prz_mid"])
            distance_atr = distance / atr
            if distance_atr <= self.prz_atr_distance:
                item = dict(item)
                item.update({"symbol": symbol, "timeframe": timeframe,
                             "strategy": f"PATTERN-{item['pattern']}-PRZ",
                             "score": 70, "price": price,
                             "distance_atr": round(distance_atr, 4),
                             "state": "EARLY_ALERT",
                             "trade_plan": {"status": "simulation_only", "auto_trading": False},
                             "trading_mode": "simulation_only",
                             "auto_trading": False})
                results.append(item)
        structural = (
            detect_double_top_bottom_state(pivots, price)
            + detect_head_shoulders_state(pivots, price)
            + detect_three_drives(pivots, last_close=price)
            + detect_channel_breakout(pivots, price, current_index=len(candles)-1)
            + detect_wedge_or_triangle(pivots, last_close=price, current_index=len(candles)-1)
            + detect_flag(candles)
            + detect_breakout_retest_and_false_break(candles, atr=atr)
        )
        for item in structural:
            item = dict(item)
            item.update({"symbol": symbol, "timeframe": timeframe,
                         "strategy": f"PATTERN-{item['pattern']}",
                         "score": 72 if item.get("state") == "CONFIRMED" else 65,
                         "price": price,
                         "trade_plan": None,
                         "trading_mode": "simulation_only", "auto_trading": False})
            results.append(item)
        return results

    def scan_symbol(self, symbol: str, candles_by_timeframe: dict) -> dict:
        results = []
        for timeframe in self.TIMEFRAMES:
            candles = candles_by_timeframe.get(timeframe, [])
            results.extend(self.scan_timeframe(symbol, timeframe, candles))
        return {
            "symbol": symbol,
            "pattern_signals": results,
            "pattern_count": len(results),
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "trading_mode": "simulation_only",
            "auto_trading": False,
        }
