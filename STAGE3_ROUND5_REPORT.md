# Stage 3 Round 5 Change Report

## Focus
Backtest risk sizing and leverage realism.

## Changes
- Added `max_leverage` (default 5x) to the pattern backtester.
- Position size remains risk-based but is capped by maximum notional exposure (`equity * max_leverage`).
- Rejects invalid leverage, candle duration, and non-finite funding inputs.
- Adds per-trade quantity, notional, and effective leverage fields.
- Adds aggregate total fees, total funding, and configured leverage to the backtest summary.
- Added regression tests for leverage cap and invalid risk parameters.
- Preserved simulation-only behavior; no order execution code added.

## Tests executed
- `python -m pytest -q tests/test_pattern_backtest.py`: 10 passed.
- `python -m pytest -q --ignore=tests/test_app.py`: 205 passed.
- `python -m compileall -q .`: passed.

## Not verified
- Flask route tests: Flask is not installed in this execution environment.
- Live OKX API connectivity and full-universe scan.
- Live LINE delivery.
- Render deployment.
- Profitability: no verified historical exchange dataset or out-of-sample results supplied.

## Important
The leverage cap is a notional cap, not a guarantee against liquidation. Actual exchange contract sizing, maintenance margin tiers, funding timestamps, tick/lot sizes, and liquidation mechanics still require exchange-specific simulation before any real trading use. System remains simulation-only.
