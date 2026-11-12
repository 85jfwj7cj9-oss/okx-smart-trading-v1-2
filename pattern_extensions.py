"""Additional conservative price-structure detectors.

All detectors operate on confirmed pivots/closed candles. Candidate structures
remain FORMING until a closed candle satisfies their explicit confirmation rule.
"""
from __future__ import annotations

from pattern_engine import Pivot, detect_double_top_bottom, detect_head_shoulders


def detect_double_top_bottom_state(pivots: list[Pivot], close: float) -> list[dict]:
    if len(pivots) < 3:
        return []
    a, b, c = pivots[-3:]
    if [a.kind, b.kind, c.kind] == ["HIGH", "LOW", "HIGH"]:
        avg = (a.price + c.price) / 2
        diff = abs(a.price - c.price) / avg * 100
        if diff <= 1.5:
            return [{"pattern": "DOUBLE_TOP", "direction": "SHORT",
                     "state": "CONFIRMED" if close < b.price else "FORMING",
                     "neckline": b.price, "swing_price": avg,
                     "similarity_pct": diff}]
    if [a.kind, b.kind, c.kind] == ["LOW", "HIGH", "LOW"]:
        avg = (a.price + c.price) / 2
        diff = abs(a.price - c.price) / avg * 100
        if diff <= 1.5:
            return [{"pattern": "DOUBLE_BOTTOM", "direction": "LONG",
                     "state": "CONFIRMED" if close > b.price else "FORMING",
                     "neckline": b.price, "swing_price": avg,
                     "similarity_pct": diff}]
    return []


def detect_head_shoulders_state(pivots: list[Pivot], close: float) -> list[dict]:
    if len(pivots) < 5:
        return []
    p = pivots[-5:]
    kinds = [x.kind for x in p]
    if kinds == ["HIGH", "LOW", "HIGH", "LOW", "HIGH"]:
        ls, n1, head, n2, rs = [x.price for x in p]
        similarity = abs(ls-rs) / max((ls+rs)/2, 1e-12) * 100
        neckline = (n1+n2)/2
        if head > max(ls, rs) and similarity <= 3:
            return [{"pattern":"HEAD_AND_SHOULDERS", "direction":"SHORT",
                     "state":"CONFIRMED" if close < neckline else "FORMING",
                     "neckline":neckline,"head":head,
                     "shoulder_similarity_pct":similarity}]
    if kinds == ["LOW", "HIGH", "LOW", "HIGH", "LOW"]:
        ls, n1, head, n2, rs = [x.price for x in p]
        similarity = abs(ls-rs) / max((ls+rs)/2, 1e-12) * 100
        neckline = (n1+n2)/2
        if head < min(ls, rs) and similarity <= 3:
            return [{"pattern":"INVERSE_HEAD_AND_SHOULDERS", "direction":"LONG",
                     "state":"CONFIRMED" if close > neckline else "FORMING",
                     "neckline":neckline,"head":head,
                     "shoulder_similarity_pct":similarity}]
    return []


def detect_three_drives(pivots: list[Pivot], tolerance_pct: float = 35.0,
                        last_close: float | None = None) -> list[dict]:
    """Detect three progressive drives using six alternating confirmed pivots."""
    if len(pivots) < 6:
        return []
    p = pivots[-6:]
    kinds = [x.kind for x in p]
    if kinds == ["LOW", "HIGH", "LOW", "HIGH", "LOW", "HIGH"]:
        legs = [p[1].price-p[0].price, p[3].price-p[2].price, p[5].price-p[4].price]
        progressive_structure = p[0].price < p[2].price < p[4].price and p[1].price < p[3].price < p[5].price
        if progressive_structure and all(x > 0 for x in legs) and legs[0] < legs[1] < legs[2] and max(legs)/min(legs) <= 1+tolerance_pct/100:
            confirmed = last_close is not None and last_close < p[4].price
            return [{"pattern":"THREE_DRIVES_BEARISH", "direction":"SHORT",
                     "state":"CONFIRMED" if confirmed else "FORMING",
                     "drive_lengths":legs, "confirmation_level":p[4].price}]
    if kinds == ["HIGH", "LOW", "HIGH", "LOW", "HIGH", "LOW"]:
        legs = [p[0].price-p[1].price, p[2].price-p[3].price, p[4].price-p[5].price]
        progressive_structure = p[0].price > p[2].price > p[4].price and p[1].price > p[3].price > p[5].price
        if progressive_structure and all(x > 0 for x in legs) and legs[0] < legs[1] < legs[2] and max(legs)/min(legs) <= 1+tolerance_pct/100:
            confirmed = last_close is not None and last_close > p[4].price
            return [{"pattern":"THREE_DRIVES_BULLISH", "direction":"LONG",
                     "state":"CONFIRMED" if confirmed else "FORMING",
                     "drive_lengths":legs, "confirmation_level":p[4].price}]
    return []


def _slope(points: list[Pivot]) -> float:
    if len(points) < 2:
        return 0.0
    return (points[-1].price - points[0].price) / max(points[-1].index - points[0].index, 1)


def detect_wedge_or_triangle(pivots: list[Pivot], last_close: float | None = None,
                             current_index: int | None = None) -> list[dict]:
    if len(pivots) < 6:
        return []
    recent = pivots[-8:]
    highs = [p for p in recent if p.kind == "HIGH"]
    lows = [p for p in recent if p.kind == "LOW"]
    if len(highs) < 3 or len(lows) < 3:
        return []
    sh, sl = _slope(highs), _slope(lows)
    scale = max(abs(sh), abs(sl), 1e-12)
    if abs(sh - sl) / scale < 0.08:
        return []
    end_index = current_index if current_index is not None else max(x.index for x in recent)
    upper = highs[-1].price + sh * (end_index - highs[-1].index)
    lower = lows[-1].price + sl * (end_index - lows[-1].index)
    if sh > 0 and sl > sh:
        name, direction = "RISING_WEDGE", "SHORT"
        confirmed = last_close is not None and last_close < lower
    elif sl < 0 and sh < sl:
        name, direction = "FALLING_WEDGE", "LONG"
        confirmed = last_close is not None and last_close > upper
    elif sh < 0 < sl:
        name, direction = "SYMMETRICAL_TRIANGLE", "NEUTRAL"
        confirmed = last_close is not None and (last_close > upper or last_close < lower)
        if confirmed:
            direction = "LONG" if last_close > upper else "SHORT"
    else:
        return []
    return [{"pattern": name, "direction": direction,
             "state": "CONFIRMED" if confirmed else "FORMING",
             "upper_boundary": upper, "lower_boundary": lower,
             "upper_slope": sh, "lower_slope": sl,
             "confirmation_rule": "closed_candle_break_of_boundary"}]


def detect_flag(candles: list[dict], lookback: int = 20, impulse_lookback: int = 10) -> list[dict]:
    """Detect a flag and distinguish consolidation from a closed-bar breakout."""
    if len(candles) < lookback + impulse_lookback + 2:
        return []
    impulse = candles[-(lookback + impulse_lookback):-lookback]
    consolidation = candles[-(lookback + 1):-1]
    latest = candles[-1]
    try:
        start, end = float(impulse[0]["close"]), float(impulse[-1]["close"])
        closes = [float(x["close"]) for x in consolidation]
        highs = [float(x["high"]) for x in consolidation]
        lows = [float(x["low"]) for x in consolidation]
        latest_close = float(latest["close"])
    except (KeyError, TypeError, ValueError):
        return []
    if start <= 0 or not closes:
        return []
    impulse_pct = (end / start - 1) * 100
    range_pct = (max(highs) - min(lows)) / max(abs(closes[-1]), 1e-12) * 100
    drift_pct = (closes[-1] / max(abs(closes[0]), 1e-12) - 1) * 100
    if impulse_pct >= 8 and range_pct <= abs(impulse_pct) * 0.65 and drift_pct <= 0:
        boundary = max(highs)
        return [{"pattern": "BULL_FLAG", "direction": "LONG",
                 "state": "CONFIRMED" if latest_close > boundary else "FORMING",
                 "impulse_pct": impulse_pct, "range_pct": range_pct,
                 "breakout_level": boundary}]
    if impulse_pct <= -8 and range_pct <= abs(impulse_pct) * 0.65 and drift_pct >= 0:
        boundary = min(lows)
        return [{"pattern": "BEAR_FLAG", "direction": "SHORT",
                 "state": "CONFIRMED" if latest_close < boundary else "FORMING",
                 "impulse_pct": impulse_pct, "range_pct": range_pct,
                 "breakout_level": boundary}]
    return []


def confirm_structural_candidates(candidates: list[dict], close: float,
                                  previous_close: float | None = None) -> list[dict]:
    """Promote only candidates whose explicit boundary was closed through."""
    out = []
    for original in candidates:
        item = dict(original)
        name = item.get("pattern")
        direction = item.get("direction")
        level = item.get("neckline", item.get("breakout_level"))
        confirmed = False
        if level is not None and direction == "LONG":
            confirmed = close > float(level)
        elif level is not None and direction == "SHORT":
            confirmed = close < float(level)
        elif name == "RISING_CHANNEL_BREAKDOWN":
            confirmed = True
        elif name == "FALLING_CHANNEL_BREAKOUT":
            confirmed = True
        if confirmed:
            item["state"] = "CONFIRMED"
        out.append(item)
    return out


def detect_breakout_retest_and_false_break(candles: list[dict], lookback: int = 20,
                                           atr: float | None = None) -> list[dict]:
    """Detect closed-candle range break, retest hold, and failed breakout.

    The reference range excludes the last two candles so a prior breakout can
    be distinguished from the current retest/failure candle.
    """
    if len(candles) < lookback + 3:
        return []
    reference = candles[-(lookback + 2):-2]
    previous, latest = candles[-2], candles[-1]
    try:
        resistance = max(float(x["high"]) for x in reference)
        support = min(float(x["low"]) for x in reference)
        prev_close = float(previous["close"])
        close = float(latest["close"])
        low = float(latest["low"])
        high = float(latest["high"])
    except (KeyError, TypeError, ValueError):
        return []
    tolerance = max((atr or 0.0) * 0.25, abs(close) * 0.002)
    out = []
    if prev_close > resistance and abs(low - resistance) <= tolerance and close > resistance:
        out.append({"pattern": "BULLISH_BREAKOUT_RETEST", "direction": "LONG",
                    "state": "CONFIRMED", "level": resistance,
                    "confirmation_rule": "retest_holds_above_resistance"})
    elif prev_close > resistance and close < resistance:
        out.append({"pattern": "BULLISH_FALSE_BREAKOUT", "direction": "SHORT",
                    "state": "CONFIRMED", "level": resistance,
                    "confirmation_rule": "close_back_below_resistance"})
    if prev_close < support and abs(high - support) <= tolerance and close < support:
        out.append({"pattern": "BEARISH_BREAKDOWN_RETEST", "direction": "SHORT",
                    "state": "CONFIRMED", "level": support,
                    "confirmation_rule": "retest_rejects_below_support"})
    elif prev_close < support and close > support:
        out.append({"pattern": "BEARISH_FALSE_BREAKDOWN", "direction": "LONG",
                    "state": "CONFIRMED", "level": support,
                    "confirmation_rule": "close_back_above_support"})
    # Fresh breakout is a separate state; it is not mislabeled as a retest.
    if close > resistance and prev_close <= resistance:
        out.append({"pattern": "RANGE_BREAKOUT", "direction": "LONG",
                    "state": "CONFIRMED", "level": resistance,
                    "confirmation_rule": "closed_candle_above_resistance"})
    elif close < support and prev_close >= support:
        out.append({"pattern": "RANGE_BREAKDOWN", "direction": "SHORT",
                    "state": "CONFIRMED", "level": support,
                    "confirmation_rule": "closed_candle_below_support"})
    return out
