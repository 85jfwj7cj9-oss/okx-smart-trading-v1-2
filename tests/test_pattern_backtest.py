import pytest
from pattern_backtest import run_pattern_backtest, chronological_split


def bars(rows):
    return [dict(open=o, high=h, low=l, close=c) for o,h,l,c in rows]


def test_signal_executes_next_bar_and_tp():
    data = bars([(100,101,99,100),(101,104,100,103),(103,108,102,107),(107,108,106,107)])
    result = run_pattern_backtest(data,[{"signal_index":0,"direction":"LONG","stop_loss":95,"take_profit":105}])
    trade = result["trades"][0]
    assert trade["entry_index"] == 1
    assert trade["exit_reason"] == "take_profit"
    assert trade["status"] == "simulation_only"
    assert result["auto_trading"] is False


def test_conservative_stop_first_when_both_touched():
    data = bars([(100,101,99,100),(100,106,94,100),(100,101,99,100)])
    result = run_pattern_backtest(data,[{"signal_index":0,"direction":"LONG","stop_loss":95,"take_profit":105}])
    assert result["trades"][0]["exit_reason"] == "stop_loss"


def test_short_direction_and_costs():
    data = bars([(100,101,99,100),(100,101,96,97),(97,98,94,95)])
    result = run_pattern_backtest(data,[{"signal_index":0,"direction":"SHORT","stop_loss":105,"take_profit":95}],fee_rate=.001,slippage_rate=.001)
    assert result["trades"][0]["net_pnl"] < result["trades"][0]["gross_pnl"]


def test_no_future_execution_on_last_signal_bar():
    data = bars([(100,101,99,100),(100,101,99,100)])
    result = run_pattern_backtest(data,[{"signal_index":1,"direction":"LONG","stop_loss":95,"take_profit":105}])
    assert result["trade_count"] == 0


def test_chronological_split_no_shuffle():
    data = list(range(100))
    parts = chronological_split(data)
    assert parts["train"][-1] < parts["validation"][0]
    assert parts["validation"][-1] < parts["out_of_sample"][0]


def test_rejects_bad_risk_fraction():
    with pytest.raises(ValueError):
        run_pattern_backtest(bars([(100,101,99,100)]*4),[],risk_fraction=.2)


def test_positive_funding_is_paid_by_long_and_received_by_short():
    data = bars([(100, 101, 99, 100), (100, 101, 99, 100),
                 (100, 101, 99, 100), (100, 101, 99, 100)])
    long_result = run_pattern_backtest(
        data, [{"signal_index": 0, "direction": "LONG", "stop_loss": 90, "take_profit": 120}],
        fee_rate=0, slippage_rate=0, funding_rate_per_8h=0.001, candle_hours=8,
    )
    short_result = run_pattern_backtest(
        data, [{"signal_index": 0, "direction": "SHORT", "stop_loss": 110, "take_profit": 80}],
        fee_rate=0, slippage_rate=0, funding_rate_per_8h=0.001, candle_hours=8,
    )
    assert long_result["trades"][0]["funding"] > 0
    assert short_result["trades"][0]["funding"] < 0


def test_build_backtest_signals_only_accepts_confirmed_and_scored():
    from pattern_backtest import build_backtest_signals
    rows = [
        {"state": "EARLY_ALERT", "score": 99, "direction": "LONG", "signal_index": 1,
         "trade_plan": {"stop_loss": 90, "tp1": 120}},
        {"state": "CONFIRMED", "score": 79, "direction": "LONG", "signal_index": 2,
         "trade_plan": {"stop_loss": 90, "tp1": 120}},
        {"state": "CONFIRMED", "score": 85, "direction": "SHORT", "signal_index": 3,
         "symbol": "BTC-USDT-SWAP", "pattern": "HEAD_AND_SHOULDERS",
         "trade_plan": {"stop_loss": 110, "tp1": 90}},
    ]
    events = build_backtest_signals(rows, minimum_score=80)
    assert len(events) == 1
    assert events[0]["direction"] == "SHORT"
    assert events[0]["signal_index"] == 3


def test_position_notional_is_capped_by_max_leverage():
    data = bars([(100, 101, 99, 100), (100, 101, 99, 100),
                 (100, 101, 99, 100), (100, 101, 99, 100)])
    result = run_pattern_backtest(
        data, [{"signal_index": 0, "direction": "LONG", "stop_loss": 99.99, "take_profit": 120}],
        fee_rate=0, slippage_rate=0, risk_fraction=.01, initial_equity=1000,
        max_leverage=5,
    )
    trade = result["trades"][0]
    assert trade["notional"] <= 5000 + 1e-9
    assert trade["effective_leverage"] <= 5 + 1e-9


def test_invalid_leverage_and_candle_hours_rejected():
    data = bars([(100, 101, 99, 100)] * 4)
    with pytest.raises(ValueError):
        run_pattern_backtest(data, [], max_leverage=0)
    with pytest.raises(ValueError):
        run_pattern_backtest(data, [], candle_hours=0)


def test_position_sizing_reserves_fees_and_slippage_within_risk_budget():
    data = bars([
        (100, 101, 99, 100),
        (100, 101, 94, 95),
        (95, 96, 94, 95),
    ])
    result = run_pattern_backtest(
        data,
        [{"signal_index": 0, "direction": "LONG", "stop_loss": 95, "take_profit": 120}],
        fee_rate=0.001,
        slippage_rate=0.001,
        risk_fraction=0.01,
        initial_equity=1000,
        max_leverage=5,
    )
    trade = result["trades"][0]
    # The size calculation includes the estimated round-trip costs, so
    # stop-out loss including fees/slippage should not exceed the 1% budget
    # (funding is zero in this test).
    assert abs(trade["net_pnl"]) <= 10.0 + 1e-8
    assert trade["estimated_cost_reserve_per_unit"] > 0
    assert trade["risk_budget_per_unit"] > trade["price_risk_per_unit"]


def test_invalid_stop_target_geometry_is_skipped_for_both_sides():
    data = bars([(100, 101, 99, 100)] * 4)
    long_bad = run_pattern_backtest(
        data, [{"signal_index": 0, "direction": "LONG", "stop_loss": 105, "take_profit": 110}]
    )
    short_bad = run_pattern_backtest(
        data, [{"signal_index": 0, "direction": "SHORT", "stop_loss": 90, "take_profit": 95}]
    )
    assert long_bad["trade_count"] == 0
    assert short_bad["trade_count"] == 0


def test_pattern_performance_is_split_by_pattern_direction_and_timeframe():
    from pattern_backtest import summarize_pattern_performance
    trades = [
        {"status": "simulation_only", "pattern": "CRAB", "direction": "LONG",
         "timeframe": "4H", "net_pnl": 10, "r_multiple": 2},
        {"status": "simulation_only", "pattern": "CRAB", "direction": "LONG",
         "timeframe": "4H", "net_pnl": -5, "r_multiple": -1},
        {"status": "simulation_only", "pattern": "CRAB", "direction": "SHORT",
         "timeframe": "4H", "net_pnl": 4, "r_multiple": 1},
        {"status": "early_alert", "pattern": "CRAB", "direction": "LONG",
         "timeframe": "4H", "net_pnl": 999, "r_multiple": 99},
    ]
    result = summarize_pattern_performance(trades)
    long_bucket = next(x for x in result if x["direction"] == "LONG")
    short_bucket = next(x for x in result if x["direction"] == "SHORT")
    assert long_bucket["trade_count"] == 2
    assert long_bucket["win_rate"] == 0.5
    assert long_bucket["net_pnl"] == 5
    assert short_bucket["trade_count"] == 1
    assert all(x["source"] == "completed_simulation_trades_only" for x in result)
