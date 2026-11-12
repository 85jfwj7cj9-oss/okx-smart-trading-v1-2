"""Causal price-pattern detection for OKX SMART TRADING.

Only confirmed OHLCV candles should be supplied. Fractal pivots are confirmed
only after `right` bars have elapsed; no future bars are used after that point.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any
import math


@dataclass(frozen=True)
class Pivot:
    index: int
    timestamp: int | float | None
    price: float
    kind: str  # HIGH or LOW


def _finite_positive(value: Any) -> bool:
    try:
        x = float(value)
        return math.isfinite(x) and x > 0
    except (TypeError, ValueError, OverflowError):
        return False


def confirmed_fractal_pivots(candles: list[dict], left: int = 3,
                             right: int = 3) -> list[Pivot]:
    """Return alternating, confirmed fractal pivots in chronological order."""
    if left < 1 or right < 1:
        raise ValueError("left and right must be >= 1")
    if len(candles or []) < left + right + 3:
        return []
    raw: list[Pivot] = []
    for i in range(left, len(candles) - right):
        window = candles[i-left:i+right+1]
        row = candles[i]
        try:
            high = float(row["high"])
            low = float(row["low"])
            highs = [float(x["high"]) for x in window]
            lows = [float(x["low"]) for x in window]
        except (KeyError, TypeError, ValueError):
            continue
        # Strict uniqueness avoids treating flat tops/bottoms as many pivots.
        if high == max(highs) and highs.count(high) == 1:
            raw.append(Pivot(i, row.get("timestamp"), high, "HIGH"))
        if low == min(lows) and lows.count(low) == 1:
            raw.append(Pivot(i, row.get("timestamp"), low, "LOW"))
    raw.sort(key=lambda p: (p.index, 0 if p.kind == "LOW" else 1))
    # A candle can qualify as both only on an extreme outside bar; retain the
    # larger normalized excursion as one pivot to preserve alternation.
    cleaned: list[Pivot] = []
    for p in raw:
        if cleaned and p.index == cleaned[-1].index:
            prev = cleaned[-1]
            if p.kind != prev.kind:
                candle = candles[p.index]
                span = max(float(candle["high"]) - float(candle["low"]), 1e-12)
                p_exc = (p.price - float(candle["low"])) / span if p.kind == "HIGH" else (float(candle["high"]) - p.price) / span
                prev_exc = (prev.price - float(candle["low"])) / span if prev.kind == "HIGH" else (float(candle["high"]) - prev.price) / span
                if p_exc > prev_exc:
                    cleaned[-1] = p
            continue
        if not cleaned:
            cleaned.append(p)
        elif p.kind == cleaned[-1].kind:
            # Keep the more extreme pivot of the same type.
            prev = cleaned[-1]
            more_extreme = p.price > prev.price if p.kind == "HIGH" else p.price < prev.price
            if more_extreme:
                cleaned[-1] = p
        else:
            cleaned.append(p)
    return cleaned


def _ratio(a: float, b: float) -> float | None:
    if not _finite_positive(abs(a)) or not _finite_positive(abs(b)):
        return None
    return abs(a) / abs(b)


def _near(value: float | None, target: float, tolerance: float) -> bool:
    return value is not None and abs(value - target) <= tolerance


def _between(value: float | None, low: float, high: float) -> bool:
    return value is not None and low <= value <= high


# Tolerances are configurable, intentionally explicit and backtestable.
HARMONIC_RULES = {
    "GARTLEY": {"ab_xa": (0.618, 0.035), "bc_ab": (0.382, 0.886),
                "cd_bc": (1.27, 1.618), "ad_xa": (0.786, 0.04)},
    "BAT": {"ab_xa": (0.45, 0.08), "bc_ab": (0.382, 0.886),
            "cd_bc": (1.618, 2.618), "ad_xa": (0.886, 0.04)},
    "BUTTERFLY": {"ab_xa": (0.786, 0.04), "bc_ab": (0.382, 0.886),
                  "cd_bc": (1.618, 2.618), "ad_xa": (1.27, 1.618)},
    "CRAB": {"ab_xa": (0.50, 0.12), "bc_ab": (0.382, 0.886),
             "cd_bc": (2.24, 3.618), "ad_xa": (1.618, 0.06)},
    "DEEP_CRAB": {"ab_xa": (0.886, 0.04), "bc_ab": (0.382, 0.886),
                  "cd_bc": (2.0, 3.618), "ad_xa": (1.618, 0.06)},
    "ALTERNATE_BAT": {"ab_xa": (0.382, 0.04), "bc_ab": (0.382, 0.886),
                      "cd_bc": (2.0, 3.618), "ad_xa": (1.13, 0.05)},
}


def classify_xabcd(points: list[Pivot], tolerance: float = 0.04) -> list[dict]:
    """Classify all recent five-pivot windows as harmonic candidates."""
    if len(points) < 5:
        return []
    out = []
    for offset in range(max(0, len(points)-20), len(points)-4):
        x, a, b, c, d = points[offset:offset+5]
        kinds = [x.kind, a.kind, b.kind, c.kind, d.kind]
        if kinds == ["LOW", "HIGH", "LOW", "HIGH", "LOW"]:
            direction = "LONG"
        elif kinds == ["HIGH", "LOW", "HIGH", "LOW", "HIGH"]:
            direction = "SHORT"
        else:
            continue
        xa = a.price - x.price
        ab = b.price - a.price
        bc = c.price - b.price
        cd = d.price - c.price
        ad = d.price - a.price
        r_ab_xa = _ratio(ab, xa)
        r_bc_ab = _ratio(bc, ab)
        r_cd_bc = _ratio(cd, bc)
        r_ad_xa = _ratio(ad, xa)
        # Cypher is based on AB/XA, BC/XA and CD/XC confluence.
        r_bc_xa = _ratio(bc, xa)
        r_cd_xc = _ratio(d.price-c.price, c.price-x.price)
        if (_between(r_ab_xa, 0.382, 0.618)
                and _between(r_bc_xa, 1.13, 1.414)
                and _near(r_cd_xc, 0.786, 0.05)):
            out.append({
                "pattern": "CYPHER", "direction": direction, "state": "COMPLETED",
                "points": {k: asdict(v) for k, v in zip("XABCD", (x,a,b,c,d))},
                "ratios": {"AB_XA": r_ab_xa, "BC_XA": r_bc_xa,
                           "CD_XC": r_cd_xc},
                "completion_price": d.price,
                "confirmed_pivot_timestamp": d.timestamp,
            })
        # 5-0 uses a distinct ratio family: AB extends XA, BC extends AB,
        # and CD retraces approximately 50% of BC. Do not force it through
        # the Gartley/Bat/Crab AD/XA rules.
        if (_between(r_ab_xa, 1.13, 1.618)
                and _between(r_bc_ab, 1.618, 2.24)
                and _near(r_cd_bc, 0.50, 0.08)):
            out.append({
                "pattern": "FIVE_ZERO", "direction": direction, "state": "COMPLETED",
                "points": {k: asdict(v) for k, v in zip("XABCD", (x,a,b,c,d))},
                "ratios": {"AB_XA": r_ab_xa, "BC_AB": r_bc_ab,
                           "CD_BC": r_cd_bc, "AD_XA": r_ad_xa},
                "completion_price": d.price,
                "confirmed_pivot_timestamp": d.timestamp,
            })
        for name, rule in HARMONIC_RULES.items():
            ab_target, ab_tol = rule["ab_xa"]
            ad_target, ad_tol = rule["ad_xa"]
            ab_ok = _near(r_ab_xa, ab_target, max(tolerance, ab_tol))
            if name == "BUTTERFLY":
                ad_ok = _between(r_ad_xa, *rule["ad_xa"])
            else:
                ad_ok = _near(r_ad_xa, ad_target, max(tolerance, ad_tol))
            bc_ok = _between(r_bc_ab, *rule["bc_ab"])
            cd_ok = _between(r_cd_bc, *rule["cd_bc"])
            if ab_ok and bc_ok and cd_ok and ad_ok:
                out.append({
                    "pattern": name, "direction": direction, "state": "COMPLETED",
                    "points": {k: asdict(v) for k, v in zip("XABCD", (x,a,b,c,d))},
                    "ratios": {"AB_XA": r_ab_xa, "BC_AB": r_bc_ab,
                               "CD_BC": r_cd_bc, "AD_XA": r_ad_xa},
                    "completion_price": d.price,
                    "confirmed_pivot_timestamp": d.timestamp,
                })
    return out


def detect_shark(points: list[Pivot], tolerance: float = 0.04) -> list[dict]:
    """Detect a provisional O-X-A-B-C Shark reversal using confirmed pivots.

    Ratio family is intentionally explicit/configurable: XA/OX 0.382-0.618,
    AB/XA 1.13-1.618, BC/OX 0.886-1.13. This is a pattern candidate, not
    an entry signal; confirmation must occur on a later closed candle.
    """
    if len(points) < 5:
        return []
    o, x, a, b, c = points[-5:]
    kinds = [p.kind for p in (o, x, a, b, c)]
    if kinds == ["LOW", "HIGH", "LOW", "HIGH", "LOW"]:
        direction = "LONG"
        ox = x.price - o.price
        xa = x.price - a.price
        ab = b.price - a.price
        bc = b.price - c.price
    elif kinds == ["HIGH", "LOW", "HIGH", "LOW", "HIGH"]:
        direction = "SHORT"
        ox = o.price - x.price
        xa = a.price - x.price
        ab = a.price - b.price
        bc = c.price - b.price
    else:
        return []
    if min(ox, xa, ab, bc) <= 0:
        return []
    xa_ox = xa / ox
    ab_xa = ab / xa
    bc_ox = bc / ox
    if not (0.382 - tolerance <= xa_ox <= 0.618 + tolerance
            and 1.13 - tolerance <= ab_xa <= 1.618 + tolerance
            and 0.886 - tolerance <= bc_ox <= 1.13 + tolerance):
        return []
    return [{
        "pattern": "SHARK", "direction": direction, "state": "COMPLETED",
        "points": {k: asdict(v) for k, v in zip("OXABC", (o, x, a, b, c))},
        "ratios": {"XA_OX": xa_ox, "AB_XA": ab_xa, "BC_OX": bc_ox},
        "completion_price": c.price,
        "confirmed_pivot_timestamp": c.timestamp,
        "confirmation_pivot_index": c.index,
    }]


def predict_prz(points: list[Pivot], patterns: list[str] | None = None) -> list[dict]:
    """Estimate D-zone from the last confirmed XABC; this is a forecast, not a signal."""
    if len(points) < 4:
        return []
    x, a, b, c = points[-4:]
    if [x.kind, a.kind, b.kind, c.kind] == ["LOW", "HIGH", "LOW", "HIGH"]:
        direction = "LONG"
    elif [x.kind, a.kind, b.kind, c.kind] == ["HIGH", "LOW", "HIGH", "LOW"]:
        direction = "SHORT"
    else:
        return []
    xa = a.price - x.price
    # D projections from XA retracement/extension levels.
    ratios = {
        "GARTLEY": (0.786, 0.786),
        "BAT": (0.886, 0.886),
        "BUTTERFLY": (1.27, 1.618),
        "CRAB": (1.618, 1.618),
        "DEEP_CRAB": (1.618, 1.618),
        "ALTERNATE_BAT": (1.13, 1.13),
    }
    wanted = set(patterns or (*ratios.keys(), "CYPHER", "FIVE_ZERO"))
    result = []
    for name, (lo, hi) in ratios.items():
        if name not in wanted:
            continue
        p1 = a.price - xa * lo
        p2 = a.price - xa * hi
        lower, upper = sorted((p1, p2))
        result.append({
            "pattern": name, "direction": direction, "state": "FORMING",
            "prz_low": lower, "prz_high": upper,
            "prz_mid": (lower + upper) / 2,
            "basis": "XA projection only; BC/CD confluence must be validated",
            "points": {k: asdict(v) for k, v in zip("XABC", (x,a,b,c))}
        })
    if "CYPHER" in wanted:
        d = c.price - (c.price - x.price) * 0.786
        result.append({"pattern":"CYPHER","direction":direction,"state":"FORMING",
                       "prz_low":d*0.995,"prz_high":d*1.005,"prz_mid":d,
                       "basis":"78.6% XC retracement; confluence required",
                       "points":{k:asdict(v) for k,v in zip("XABC",(x,a,b,c))}})
    if "FIVE_ZERO" in wanted:
        d = c.price - (c.price - b.price) * 0.50
        result.append({"pattern":"FIVE_ZERO","direction":direction,"state":"FORMING",
                       "prz_low":d*0.995,"prz_high":d*1.005,"prz_mid":d,
                       "basis":"50% BC retracement; ratio confluence required",
                       "points":{k:asdict(v) for k,v in zip("XABC",(x,a,b,c))}})
    return result


def detect_double_top_bottom(pivots: list[Pivot], tolerance_pct: float = 1.5) -> list[dict]:
    """Simple confirmed swing-based double top/bottom detector."""
    if len(pivots) < 3:
        return []
    a, b, c = pivots[-3:]
    if [a.kind, b.kind, c.kind] == ["HIGH", "LOW", "HIGH"]:
        avg = (a.price + c.price) / 2
        diff = abs(a.price - c.price) / avg * 100
        if diff <= tolerance_pct:
            return [{"pattern":"DOUBLE_TOP","direction":"SHORT","state":"FORMING",
                     "neckline":b.price,"swing_price":avg,"similarity_pct":diff}]
    if [a.kind, b.kind, c.kind] == ["LOW", "HIGH", "LOW"]:
        avg = (a.price + c.price) / 2
        diff = abs(a.price - c.price) / avg * 100
        if diff <= tolerance_pct:
            return [{"pattern":"DOUBLE_BOTTOM","direction":"LONG","state":"FORMING",
                     "neckline":b.price,"swing_price":avg,"similarity_pct":diff}]
    return []


def detect_head_shoulders(pivots: list[Pivot], tolerance_pct: float = 3.0) -> list[dict]:
    """Detect classic or inverse H&S from five alternating confirmed pivots."""
    if len(pivots) < 5:
        return []
    p = pivots[-5:]
    kinds = [x.kind for x in p]
    if kinds == ["HIGH","LOW","HIGH","LOW","HIGH"]:
        ls, n1, head, n2, rs = [x.price for x in p]
        shoulders = abs(ls-rs)/((ls+rs)/2)*100
        if head > max(ls,rs) and shoulders <= tolerance_pct:
            return [{"pattern":"HEAD_AND_SHOULDERS","direction":"SHORT","state":"FORMING",
                     "neckline":(n1+n2)/2,"head":head,"shoulder_similarity_pct":shoulders}]
    if kinds == ["LOW","HIGH","LOW","HIGH","LOW"]:
        ls, n1, head, n2, rs = [x.price for x in p]
        shoulders = abs(ls-rs)/((ls+rs)/2)*100
        if head < min(ls,rs) and shoulders <= tolerance_pct:
            return [{"pattern":"INVERSE_HEAD_AND_SHOULDERS","direction":"LONG","state":"FORMING",
                     "neckline":(n1+n2)/2,"head":head,"shoulder_similarity_pct":shoulders}]
    return []



def detect_channel_breakout(pivots: list[Pivot], last_close: float,
                            current_index: int | None = None,
                            tolerance_pct: float = 1.5) -> list[dict]:
    """Detect a parallel rising/falling channel and close outside its boundary."""
    if len(pivots) < 6 or not _finite_positive(last_close):
        return []
    recent = pivots[-6:]
    highs = [p for p in recent if p.kind == "HIGH"]
    lows = [p for p in recent if p.kind == "LOW"]
    if len(highs) < 2 or len(lows) < 2:
        return []
    def slope(items):
        first, last = items[0], items[-1]
        span = max(last.index-first.index, 1)
        return (last.price-first.price)/span
    sh, sl = slope(highs), slope(lows)
    scale = max(abs(sh), abs(sl), 1e-12)
    parallel = abs(sh-sl)/scale*100 <= tolerance_pct
    if not parallel:
        return []
    upper_slope = sh
    lower_slope = sl
    # Project the latest upper/lower swing boundaries to the latest candle index.
    end_index = current_index if current_index is not None else max(p.index for p in recent)
    upper = highs[-1].price + upper_slope * (end_index-highs[-1].index)
    lower = lows[-1].price + lower_slope * (end_index-lows[-1].index)
    width = max(upper-lower, 1e-12)
    if upper_slope > 0 and last_close < lower:
        return [{"pattern":"RISING_CHANNEL_BREAKDOWN","direction":"SHORT",
                 "state":"CONFIRMED","channel_upper":upper,"channel_lower":lower}]
    if lower_slope < 0 and last_close > upper:
        return [{"pattern":"FALLING_CHANNEL_BREAKOUT","direction":"LONG",
                 "state":"CONFIRMED","channel_upper":upper,"channel_lower":lower}]
    if lower <= last_close <= upper and width/last_close < 0.25:
        return [{"pattern":"PARALLEL_CHANNEL","direction":"NEUTRAL",
                 "state":"FORMING","channel_upper":upper,"channel_lower":lower}]
    return []

def detect_three_drives(pivots: list[Pivot], tolerance_pct: float = 25.0) -> list[dict]:
    """Detect three progressively extending highs or lows with similar legs."""
    if len(pivots) < 5:
        return []
    p = pivots[-5:]
    kinds = [x.kind for x in p]
    if kinds == ["LOW","HIGH","LOW","HIGH","LOW"]:
        legs = [p[1].price-p[0].price, p[3].price-p[2].price]
        if legs[0] > 0 and legs[1] > legs[0] and abs(legs[1]/legs[0]-1)*100 <= tolerance_pct:
            return [{"pattern":"THREE_DRIVES_BEARISH","direction":"SHORT","state":"FORMING"}]
    if kinds == ["HIGH","LOW","HIGH","LOW","HIGH"]:
        legs = [p[0].price-p[1].price, p[2].price-p[3].price]
        if legs[0] > 0 and legs[1] > legs[0] and abs(legs[1]/legs[0]-1)*100 <= tolerance_pct:
            return [{"pattern":"THREE_DRIVES_BULLISH","direction":"LONG","state":"FORMING"}]
    return []
