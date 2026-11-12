# OKX SMART TRADING V1.1 — Stage 3 Round 6 Report

## Scope
Round 6 tightens simulation position sizing so the configured risk budget reserves for estimated round-trip trading fees and adverse entry/exit slippage, in addition to the price distance from entry to stop. The maximum notional leverage cap remains in force. No real order execution was added.

## Code changes
- Updated `pattern_backtest.py` position sizing to calculate `risk_budget_per_unit` as stop-distance risk plus estimated round-trip fees and slippage.
- Quantity is now the minimum of risk-budget sizing and maximum-leverage notional sizing.
- Trade records now expose price risk, estimated cost reserve, and total risk budget per unit.
- R-multiple denominator now uses the estimated risk budget including fees/slippage.
- Added regression coverage for cost-aware risk sizing and invalid LONG/SHORT stop/target geometry.

## Tests executed
- `python -m pytest -q --ignore=tests/test_app.py`: **207 passed**.
- `python -m compileall -q -x '__pycache__' .`: passed.
- Full `python -m pytest -q`: blocked during collection because Flask is not installed in this execution environment (`ModuleNotFoundError: No module named 'flask'`). An attempt to install dependencies failed because package-index DNS/network access is unavailable.

## Not verified
- Flask route/UI integration tests.
- PostgreSQL driver and live PostgreSQL integration.
- Live OKX API connectivity and full-universe scan.
- Live LINE delivery.
- Render deployment.
- Actual profitability or out-of-sample performance on verified exchange historical data.

## Risk-model limitations
- Fee/slippage reserve uses configured constant rates. Actual fees depend on account tier and execution type.
- Funding is still an estimated prorated cost in the existing backtester; exact funding requires historical settlement timestamps and rates. It is not included in the position-size reserve because the future holding period is unknown at entry.
- The 5x cap is a notional cap, not a liquidation/maintenance-margin model.
- System remains simulation-only; no real trading API/order code is enabled.
