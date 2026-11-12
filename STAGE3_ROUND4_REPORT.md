# Stage 3 Round 4 Change Report

## Changes
- Corrected simulated funding cash-flow direction: positive funding is paid by LONG and received by SHORT; negative funding reverses the cash flow.
- Added `build_backtest_signals()` to convert scanner output into backtest events only when state is `CONFIRMED`, score meets the configured floor, direction is valid, and stop/target values are finite and positive.
- Added regression tests for funding direction and confirmed-signal filtering.
- Preserved simulation-only behavior; no exchange order placement was added.

## Tests executed
- `python -m pytest -q tests/test_pattern_backtest.py`: 8 passed.
- `python -m pytest -q --ignore=tests/test_app.py`: 203 passed.
- Full suite collection: blocked because Flask is not installed in this execution environment (`ModuleNotFoundError: flask`). Attempted installation, but package index/network access was unavailable.

## Not verified
- Flask route/browser tests.
- Live OKX API connectivity and full-market scan.
- Render deployment.
- Live LINE delivery.
- Out-of-sample profitability; no live or historical exchange dataset was supplied for a verified performance claim.

## Important usage note
`build_backtest_signals()` requires `signal_index` to reference the exact candle array passed to `run_pattern_backtest()`. It intentionally excludes `EARLY_ALERT`, `FORMING`, and `COMPLETED` states.
