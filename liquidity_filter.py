"""V1.1 conservative liquidity and quote-quality gates."""
from __future__ import annotations
import math


def _num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError, OverflowError):
        return None


def evaluate_liquidity(ticker: dict, min_turnover_usdt=5_000_000.0,
                       max_spread_pct=0.20, max_ticker_age_seconds=30.0,
                       now_ms=None) -> dict:
    """Evaluate ticker. OKX bid/ask and ts are expected in milliseconds."""
    reasons = []
    if not isinstance(ticker, dict):
        return {"passed": False, "reasons": ["ticker_missing"]}
    last = _num(ticker.get("last"))
    bid = _num(ticker.get("bidPx"))
    ask = _num(ticker.get("askPx"))
    turnover = _num(ticker.get("volCcyQuote24h"))
    ts = _num(ticker.get("ts"))
    if last is None or last <= 0: reasons.append("invalid_last")
    if turnover is None or turnover < min_turnover_usdt: reasons.append("turnover_below_minimum")
    spread = None
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        reasons.append("invalid_bid_ask")
    else:
        mid = (bid + ask) / 2
        spread = (ask - bid) / mid * 100 if mid else None
        if spread is None or spread > max_spread_pct: reasons.append("spread_above_maximum")
    age = None
    if ts is None or ts <= 0:
        reasons.append("missing_ticker_timestamp")
    elif now_ms is not None:
        age = (float(now_ms) - ts) / 1000
        if age < -5: reasons.append("future_ticker_timestamp")
        elif age > max_ticker_age_seconds: reasons.append("stale_ticker")
    return {"passed": not reasons, "reasons": reasons,
            "turnover_usdt_24h": turnover, "spread_pct": spread,
            "ticker_age_seconds": age}
