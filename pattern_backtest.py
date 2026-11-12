"""Causal OHLCV backtester for pattern signals (simulation only).

Signals become actionable only after their signal_index candle has closed;
execution is at the next candle open with adverse slippage. If SL and TP are
both touched in one candle, SL is assumed first (conservative OHLC assumption).
"""
from __future__ import annotations
import math
from statistics import mean


def _num(value, field):
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite")
    return value


def run_pattern_backtest(candles, signals, *, fee_rate=0.0005,
                         slippage_rate=0.0005, funding_rate_per_8h=0.0, candle_hours=1.0,
                         risk_fraction=0.005, initial_equity=10000.0,
                         max_leverage=5.0):
    """Run one-position-at-a-time backtest. Signal fields: signal_index,
    direction (LONG/SHORT), stop_loss, take_profit (or tp1), pattern, symbol.
    Entry is next bar open; no same-bar signal execution/lookahead allowed.
    """
    if not isinstance(candles, list) or len(candles) < 2:
        raise ValueError("at least two candles required")
    for key, value in (("fee_rate", fee_rate), ("slippage_rate", slippage_rate),
                       ("risk_fraction", risk_fraction), ("initial_equity", initial_equity),
                       ("max_leverage", max_leverage), ("funding_rate_per_8h", funding_rate_per_8h),
                       ("candle_hours", candle_hours)):
        if _num(value, key) < 0:
            raise ValueError(f"{key} cannot be negative")
    if risk_fraction <= 0 or risk_fraction > 0.05 or initial_equity <= 0 or max_leverage <= 0 or candle_hours <= 0:
        raise ValueError("risk_fraction must be in (0, 0.05], equity/leverage/candle_hours must be positive")
    equity = float(initial_equity)
    trades, used_signal_indices = [], set()
    ordered = sorted(signals, key=lambda x: int(x.get("signal_index", -1)))
    next_free = 0
    for sig in ordered:
        idx = int(sig.get("signal_index", -1))
        if idx < 0 or idx + 1 >= len(candles) or idx in used_signal_indices:
            continue
        direction = str(sig.get("direction", "")).upper()
        if direction not in ("LONG", "SHORT"):
            continue
        stop = _num(sig.get("stop_loss"), "stop_loss")
        target = _num(sig.get("take_profit", sig.get("tp1")), "take_profit")
        entry_bar = idx + 1
        if entry_bar < next_free:
            continue
        raw_entry = _num(candles[entry_bar].get("open"), "entry open")
        entry = raw_entry * (1 + slippage_rate if direction == "LONG" else 1 - slippage_rate)
        if (direction == "LONG" and not stop < entry < target) or (direction == "SHORT" and not target < entry < stop):
            continue
        risk_per_unit = abs(entry - stop)
        # Reserve the risk budget for adverse entry/exit execution costs as well
        # as the price move to the stop. This is still an estimate: actual fees
        # depend on the exchange account tier and funding is settled at discrete
        # exchange timestamps, so funding is reported separately below.
        estimated_cost_per_unit = (
            entry * fee_rate + stop * fee_rate
            + entry * slippage_rate + stop * slippage_rate
        )
        risk_budget_per_unit = risk_per_unit + estimated_cost_per_unit
        # Risk-based size is capped by configured notional leverage.
        risk_qty = equity * risk_fraction / risk_budget_per_unit
        leverage_qty = equity * max_leverage / entry
        qty = min(risk_qty, leverage_qty)
        if not math.isfinite(qty) or qty <= 0:
            continue
        entry_fee = entry * qty * fee_rate
        exit_price, exit_idx, reason = None, None, "end_of_data"
        for j in range(entry_bar, len(candles)):
            high, low = _num(candles[j].get("high"), "high"), _num(candles[j].get("low"), "low")
            if direction == "LONG":
                stop_hit, target_hit = low <= stop, high >= target
            else:
                stop_hit, target_hit = high >= stop, low <= target
            if stop_hit:
                exit_price, exit_idx, reason = stop, j, "stop_loss"
                break
            if target_hit:
                exit_price, exit_idx, reason = target, j, "take_profit"
                break
        if exit_price is None:
            exit_idx = len(candles) - 1
            exit_price = _num(candles[exit_idx].get("close"), "final close")
        exit_fill = exit_price * (1 - slippage_rate if direction == "LONG" else 1 + slippage_rate)
        gross = (exit_fill - entry) * qty * (1 if direction == "LONG" else -1)
        exit_fee = exit_fill * qty * fee_rate
        held_bars = max(1, exit_idx - entry_bar + 1)
        # Funding is prorated by the supplied candle duration.
        # Positive funding means longs pay shorts; negative funding means
        # shorts pay longs. Apply the correct cash-flow sign by direction.
        funding_notional = entry * qty * funding_rate_per_8h * (held_bars * candle_hours / 8)
        funding = funding_notional if direction == "LONG" else -funding_notional
        net = gross - entry_fee - exit_fee - funding
        equity += net
        trades.append({"symbol": sig.get("symbol"), "pattern": sig.get("pattern"),
                       "direction": direction, "signal_index": idx,
                       "entry_index": entry_bar, "exit_index": exit_idx,
                       "entry_price": entry, "exit_price": exit_fill,
                       "quantity": qty, "notional": entry * qty,
                       "effective_leverage": (entry * qty / max(equity - net, 1e-12)),
                       "stop_loss": stop, "take_profit": target,
                       "price_risk_per_unit": risk_per_unit,
                       "estimated_cost_reserve_per_unit": estimated_cost_per_unit,
                       "risk_budget_per_unit": risk_budget_per_unit,
                       "gross_pnl": gross, "fees": entry_fee + exit_fee,
                       "funding": funding, "net_pnl": net,
                       "r_multiple": net / (risk_budget_per_unit * qty),
                       "exit_reason": reason, "status": "simulation_only"})
        used_signal_indices.add(idx)
        next_free = exit_idx + 1
    wins = sum(t["net_pnl"] > 0 for t in trades)
    gross_profit = sum(t["net_pnl"] for t in trades if t["net_pnl"] > 0)
    gross_loss = -sum(t["net_pnl"] for t in trades if t["net_pnl"] < 0)
    peak, max_dd = initial_equity, 0.0
    curve = initial_equity
    for trade in trades:
        curve += trade["net_pnl"]
        peak = max(peak, curve)
        max_dd = max(max_dd, (peak - curve) / peak if peak else 0.0)
    return {"status": "simulation_only", "auto_trading": False,
            "initial_equity": initial_equity, "final_equity": equity,
            "net_pnl": equity - initial_equity, "trade_count": len(trades),
            "win_rate": wins / len(trades) if trades else 0.0,
            "profit_factor": gross_profit / gross_loss if gross_loss else (None if gross_profit else 0.0),
            "max_drawdown": max_dd,
            "max_leverage": max_leverage,
            "total_fees": sum(t["fees"] for t in trades),
            "total_funding": sum(t["funding"] for t in trades),
            "expectancy": mean(t["net_pnl"] for t in trades) if trades else 0.0,
            "trades": trades}


def build_backtest_signals(pattern_results, *, minimum_score=80):
    """Convert scanner output into causal backtest events.

    Only CONFIRMED signals with a complete, valid risk plan are eligible.
    EARLY_ALERT/FORMING/COMPLETED candidates are deliberately excluded.
    Scanner candle indices must refer to the same candle array passed to the
    backtester; this function does not infer indices from wall-clock time.
    """
    events = []
    for item in pattern_results or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("state", "")).upper() != "CONFIRMED":
            continue
        try:
            score = float(item.get("score", 0))
            signal_index = int(item["signal_index"])
            plan = item.get("trade_plan") or {}
            stop = float(plan.get("stop_loss", item.get("stop_loss")))
            target = float(plan.get("tp1", plan.get("take_profit", item.get("tp1"))))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        direction = str(item.get("direction", "")).upper()
        if score < minimum_score or direction not in ("LONG", "SHORT"):
            continue
        if not all(math.isfinite(x) and x > 0 for x in (stop, target)):
            continue
        events.append({
            "signal_index": signal_index,
            "direction": direction,
            "stop_loss": stop,
            "take_profit": target,
            "pattern": item.get("pattern"),
            "symbol": item.get("symbol"),
            "score": score,
        })
    return events


def chronological_split(candles, train=0.60, validation=0.20):
    """Chronological, non-shuffled split; remaining portion is out-of-sample."""
    if not 0 < train < 1 or not 0 < validation < 1 or train + validation >= 1:
        raise ValueError("train and validation must be positive and sum below 1")
    n = len(candles)
    a, b = int(n * train), int(n * (train + validation))
    if min(a, b-a, n-b) < 1:
        raise ValueError("not enough candles for three non-empty splits")
    return {"train": candles[:a], "validation": candles[a:b], "out_of_sample": candles[b:]}


def summarize_pattern_performance(trades):
    """Return auditable performance buckets by pattern, direction and timeframe.

    The function only summarizes completed simulation trade records; it does
    not infer missing results or mix early alerts with confirmed entries.
    """
    buckets = {}
    for trade in trades or []:
        if not isinstance(trade, dict) or trade.get("status") != "simulation_only":
            continue
        try:
            pnl = float(trade["net_pnl"])
            r_multiple = float(trade.get("r_multiple", 0.0))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(pnl) or not math.isfinite(r_multiple):
            continue
        pattern = str(trade.get("pattern") or "UNKNOWN").upper()
        direction = str(trade.get("direction") or "UNKNOWN").upper()
        timeframe = str(trade.get("timeframe") or "UNKNOWN").upper()
        key = (pattern, direction, timeframe)
        bucket = buckets.setdefault(key, {"trades": 0, "wins": 0, "net_pnl": 0.0,
                                           "gross_profit": 0.0, "gross_loss": 0.0,
                                           "r_sum": 0.0})
        bucket["trades"] += 1
        bucket["wins"] += int(pnl > 0)
        bucket["net_pnl"] += pnl
        bucket["gross_profit"] += max(0.0, pnl)
        bucket["gross_loss"] += max(0.0, -pnl)
        bucket["r_sum"] += r_multiple
    result = []
    for (pattern, direction, timeframe), item in sorted(buckets.items()):
        count = item["trades"]
        loss = item["gross_loss"]
        result.append({
            "pattern": pattern, "direction": direction, "timeframe": timeframe,
            "trade_count": count, "win_rate": item["wins"] / count,
            "net_pnl": item["net_pnl"],
            "profit_factor": item["gross_profit"] / loss if loss else (None if item["gross_profit"] else 0.0),
            "expectancy": item["net_pnl"] / count,
            "average_r": item["r_sum"] / count,
            "source": "completed_simulation_trades_only",
        })
    return result
