"""V1.1 relative-strength calculations; no network calls."""
from __future__ import annotations

from typing import Iterable, Optional
import math


def _clean(candles: Iterable[dict]) -> dict[int, float]:
    result = {}
    for row in candles or []:
        try:
            ts = int(row["timestamp"])
            close = float(row["close"])
            if ts > 0 and math.isfinite(close) and close > 0:
                result[ts] = close
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    return result


def relative_strength(asset_candles, btc_candles, lookback: int) -> Optional[dict]:
    """Excess return (asset return minus BTC return) on aligned closed bars.

    lookback is a number of bars, not days. Callers must supply confirmed bars
    from the same timeframe and exclude the still-forming candle.
    """
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 1:
        raise ValueError("lookback must be a positive integer")
    a, b = _clean(asset_candles), _clean(btc_candles)
    common = sorted(set(a) & set(b))
    if len(common) <= lookback:
        return None
    start, end = common[-lookback - 1], common[-1]
    ar = (a[end] / a[start] - 1.0) * 100
    br = (b[end] / b[start] - 1.0) * 100
    ratio_start, ratio_end = a[start] / b[start], a[end] / b[end]
    return {
        "asset_return_pct": ar,
        "btc_return_pct": br,
        "relative_strength_pct": ar - br,
        "ratio_change_pct": (ratio_end / ratio_start - 1.0) * 100,
        "bars": len(common),
        "lookback_bars": lookback,
        "start_timestamp": start,
        "end_timestamp": end,
    }


def calculate_rs_windows(asset_candles, btc_candles, windows=None) -> dict:
    """Compute caller-defined bar windows; defaults are 1d/3d/7d for 1H bars."""
    windows = windows or {"1d": 24, "3d": 72, "7d": 168}
    return {name: relative_strength(asset_candles, btc_candles, bars)
            for name, bars in windows.items()}
