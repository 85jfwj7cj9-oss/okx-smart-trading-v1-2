
import math
from datetime import datetime, timezone

import pandas as pd

from indicators import IndicatorEngine
from strategy import StrategyEngine
from risk_manager import RiskManager
from market_data import MarketData
from pattern_scanner import PatternScanner
from strong_radar import (evaluate_early_accumulation, evaluate_breakout_momentum,
                          evaluate_early_distribution, evaluate_breakdown_momentum)
from liquidity_filter import evaluate_liquidity
from config import Config


class SignalEngine:
    """OKX SMART TRADING V1.2.1 多週期模擬訊號分析引擎。"""

    TIMEFRAMES = ("1H", "4H")

    STRATEGY_NAMES = (
        "LONG-A",
        "LONG-B",
        "SHORT-A",
        "SHORT-B"
    )

    def __init__(
        self,
        market_data=None,
        indicator_engine=None,
        strategy_engine=None,
        risk_manager=None,
        pattern_scanner=None
    ):
        self.market_data = market_data or MarketData()
        self.indicator_engine = indicator_engine or IndicatorEngine()
        self.strategy_engine = strategy_engine or StrategyEngine()
        self.risk_manager = risk_manager or RiskManager()
        self.pattern_scanner = pattern_scanner or PatternScanner(
            pivot_left=Config.PATTERN_PIVOT_LEFT,
            pivot_right=Config.PATTERN_PIVOT_RIGHT,
            prz_atr_distance=Config.PATTERN_PRZ_ATR_DISTANCE,
        )

    @staticmethod
    def _safe_float(value):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None

        return number if math.isfinite(number) else None

    @staticmethod
    def _candles_to_dataframe(candles):
        if not isinstance(candles, list) or not candles:
            raise ValueError("Candle data is empty")

        df = pd.DataFrame(candles)

        required = [
            "timestamp", "open", "high",
            "low", "close", "volume"
        ]

        missing = [
            column for column in required
            if column not in df.columns
        ]

        if missing:
            raise ValueError(
                "Missing candle columns: " + ", ".join(missing)
            )

        for column in required:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

        df = df.dropna(subset=required)

        if df.empty:
            raise ValueError("Candle data has no valid rows")

        df = df.sort_values("timestamp")
        df = df.drop_duplicates(
            subset=["timestamp"],
            keep="last"
        )
        df = df.reset_index(drop=True)

        if len(df) < 30:
            raise ValueError(
                "Insufficient candle history; at least 30 rows required"
            )

        invalid = (
            (df["high"] < df["low"])
            | (df["high"] < df["open"])
            | (df["high"] < df["close"])
            | (df["low"] > df["open"])
            | (df["low"] > df["close"])
            | (df["volume"] < 0)
            | (df["open"] <= 0)
            | (df["high"] <= 0)
            | (df["low"] <= 0)
            | (df["close"] <= 0)
        )

        if invalid.any():
            raise ValueError("Invalid OHLCV candle data")

        return df

    def _get_confirmed_candles(self, inst_id, timeframe):
        candles = self.market_data.client.get_candles(
            inst_id,
            bar=timeframe,
            limit=100,
            confirmed_only=True
        )

        df = self._candles_to_dataframe(candles)
        if "market_ts_ms" in df.columns:
            market_ts = pd.to_numeric(df["market_ts_ms"], errors="coerce")
            source_ts = pd.to_numeric(df["timestamp"], errors="coerce")
            if market_ts.isna().any() or not market_ts.equals(source_ts):
                raise ValueError("Market timestamp validation failed")
            if (market_ts <= 0).any() or (market_ts > int(datetime.now(timezone.utc).timestamp()*1000) + 300000).any():
                raise ValueError("Market timestamp is invalid or in the future")
        if "fetched_at_utc" in df.columns:
            fetched = pd.to_datetime(df["fetched_at_utc"], utc=True, errors="coerce")
            if fetched.isna().any():
                raise ValueError("Fetched-at timestamp validation failed")
            age = (pd.Timestamp.now(tz="UTC") - fetched.max()).total_seconds()
            if age < -30 or age > 300:
                raise ValueError("Market data fetch is stale")
        return df

    def _prepare_features(self, df):
        result = self.indicator_engine.calculate_all(df.copy())

        if not isinstance(result, pd.DataFrame) or result.empty:
            raise ValueError(
                "Indicator engine returned invalid data"
            )

        return result

    @staticmethod
    def _extract_relative_strength(data):
        """
        擷取 1H／4H 相對 BTC 強弱。
        無效資料保留為 None，後續必須通過驗證。
        """
        values = {
            "1H": None,
            "4H": None
        }

        if not isinstance(data, dict):
            return values

        for timeframe in SignalEngine.TIMEFRAMES:
            item = data.get(timeframe)

            if isinstance(item, dict):
                raw_value = item.get("relative_strength_pct")
            else:
                raw_value = item

            values[timeframe] = SignalEngine._safe_float(
                raw_value
            )

        return values

    @staticmethod
    def _validate_relative_strength(relative_strength):
        """
        1H 和 4H 必須同時具備有效的相對 BTC 強弱數值。
        不允許 None、NaN、Infinity 或非數字。
        """
        if not isinstance(relative_strength, dict):
            raise ValueError(
                "Relative strength data is missing or invalid"
            )

        for timeframe in SignalEngine.TIMEFRAMES:
            value = SignalEngine._safe_float(
                relative_strength.get(timeframe)
            )

            if value is None:
                raise ValueError(
                    f"Missing or invalid BTC relative strength: {timeframe}"
                )

            relative_strength[timeframe] = value

        return relative_strength

    @staticmethod
    def _normalize_strategy_result(result):
        if not isinstance(result, dict):
            raise ValueError(
                "Strategy engine returned invalid result"
            )

        normalized = dict(result)
        raw_signals = result.get("signals", [])

        if not isinstance(raw_signals, list):
            raw_signals = []

        valid_signals = []

        for raw in raw_signals:
            if not isinstance(raw, dict):
                continue

            signal = dict(raw)

            name = str(
                signal.get("signal", "")
            ).upper()

            direction = str(
                signal.get("direction", "")
            ).upper()

            score = SignalEngine._safe_float(
                signal.get("score")
            )

            price = SignalEngine._safe_float(
                signal.get("price")
            )

            if name not in SignalEngine.STRATEGY_NAMES:
                continue

            expected = (
                "LONG" if name.startswith("LONG")
                else "SHORT"
            )

            if direction != expected:
                continue

            if score is None or not 0 <= score <= 100:
                continue

            if signal.get("price") is not None and (
                price is None or price <= 0
            ):
                continue

            signal["signal"] = name
            signal["direction"] = direction
            signal["score"] = score
            signal["price"] = price

            reasons = signal.get("reasons", [])

            signal["reasons"] = (
                reasons if isinstance(reasons, list)
                else []
            )

            signal["candidate"] = True
            signal["status"] = "simulation_only"

            valid_signals.append(signal)

        valid_signals.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        normalized["signals"] = valid_signals

        if valid_signals:
            best = valid_signals[0]

            normalized.update({
                "direction": best["direction"],
                "candidate": True,
                "signal": best["signal"],
                "score": best["score"],
                "price": best["price"],
                "reasons": best["reasons"]
            })
        else:
            normalized.update({
                "direction": "NEUTRAL",
                "candidate": False,
                "signal": None,
                "score": 0,
                "price": None,
                "reasons": []
            })

        normalized["status"] = "simulation_only"

        return normalized

    @staticmethod
    def _extract_latest_atr(features):
        if (
            not isinstance(features, pd.DataFrame)
            or features.empty
        ):
            return None

        for column in ("atr", "atr_14"):
            if column not in features.columns:
                continue

            value = SignalEngine._safe_float(
                features.iloc[-1][column]
            )

            if value is not None and value > 0:
                return value

        return None

    def _create_strategy_trade_plans(
        self,
        symbol,
        signals,
        atr,
        equity=None
    ):
        plans = {}

        for signal in signals:
            name = signal["signal"]
            direction = signal["direction"]
            entry_price = signal.get("price")

            if entry_price is None or entry_price <= 0:
                plan = {
                    "symbol": symbol,
                    "strategy": name,
                    "direction": direction,
                    "status": "error",
                    "reason": "Invalid or missing entry price",
                    "auto_trading": False
                }

                plans[name] = plan
                signal["trade_plan"] = plan
                continue

            try:
                plan = self.risk_manager.create_trade_plan(
                    symbol=symbol,
                    side=direction,
                    entry_price=entry_price,
                    atr=atr,
                    equity=equity
                )

                if not isinstance(plan, dict):
                    raise ValueError(
                        "Risk manager returned invalid trade plan"
                    )

                plan = dict(plan)

                plan.update({
                    "symbol": symbol,
                    "strategy": name,
                    "direction": direction,
                    "status": plan.get(
                        "status",
                        "simulation_only"
                    ),
                    "auto_trading": False
                })

                plans[name] = plan
                signal["trade_plan"] = plan

            except Exception as exc:
                plan = {
                    "symbol": symbol,
                    "strategy": name,
                    "direction": direction,
                    "status": "error",
                    "reason": str(exc),
                    "auto_trading": False
                }

                plans[name] = plan
                signal["trade_plan"] = plan

        return plans

    @staticmethod
    def _select_best_trade_plan(signals, trade_plans):
        for signal in signals:
            plan = trade_plans.get(
                signal.get("signal")
            )

            if not isinstance(plan, dict):
                continue

            if plan.get("status") == "error":
                continue

            return signal, plan

        return None, None

    @staticmethod
    def _latest(features, key, offset=0):
        try:
            value = float(features.iloc[-1-offset][key])
            return value if math.isfinite(value) else None
        except (KeyError, IndexError, TypeError, ValueError, OverflowError):
            return None

    def _evaluate_v11_radars(self, f1h, f4h, rs, daily_rs=None,
                             liquidity_passed=False, liquidity_detail=None):
        """Evaluate four independent V1.1 radars from closed-candle features."""
        e = self._latest
        rs1d = (daily_rs or {}).get("1D") or {}
        rs3d = (daily_rs or {}).get("3D") or {}
        rs7d = (daily_rs or {}).get("7D") or {}
        rs1 = rs1d.get("relative_strength_pct") if isinstance(rs1d, dict) else None
        rs3 = rs3d.get("relative_strength_pct") if isinstance(rs3d, dict) else None
        rs7 = rs7d.get("relative_strength_pct") if isinstance(rs7d, dict) else None
        rs4h = rs.get("4H")
        rs1h = rs.get("1H")
        ratio_up = (rs1h is not None and rs4h is not None and rs1h > 0 and rs4h > 0)
        ratio_down = (rs1h is not None and rs4h is not None and rs1h < 0 and rs4h < 0)

        ema20_4, ema50_4 = e(f4h, "ema_20"), e(f4h, "ema_50")
        ema100_4 = e(f4h, "ema_100")
        ema50_4_prev = e(f4h, "ema_50", 1)
        ema100_4_prev = e(f4h, "ema_100", 1)
        ema20_4_prev = e(f4h, "ema_20", 1)
        ema5_1, ema10_1, ema20_1 = e(f1h, "ema_5"), e(f1h, "ema_10"), e(f1h, "ema_20")
        ema5_1_prev, ema10_1_prev = e(f1h, "ema_5", 1), e(f1h, "ema_10", 1)
        ema10_1_prev2 = e(f1h, "ema_10", 2)
        ema20_4_slope = ema20_4 is not None and ema20_4_prev is not None and ema20_4 > ema20_4_prev
        ema20_4_slope_down = ema20_4 is not None and ema20_4_prev is not None and ema20_4 < ema20_4_prev
        close1, close4 = e(f1h, "close"), e(f4h, "close")
        atr1 = e(f1h, "atr_14") or e(f1h, "atr")
        rsi1, rsi4 = e(f1h, "rsi_14"), e(f4h, "rsi_14")
        macdh1, macdh1_prev = e(f1h, "macd_hist"), e(f1h, "macd_hist", 1)
        obv1, obv1_prev = e(f1h, "obv"), e(f1h, "obv", 1)
        adx4, adx4_prev = e(f4h, "adx"), e(f4h, "adx", 1)
        plus4, minus4 = e(f4h, "plus_di"), e(f4h, "minus_di")
        vol1, volma1 = e(f1h, "volume"), e(f1h, "volume_ma_20")
        recent_vol = f1h["volume"].tail(3).mean() if "volume" in f1h else None
        prior_vol = f1h["volume"].iloc[-6:-3].mean() if "volume" in f1h and len(f1h) >= 6 else None
        ranges = (f1h["high"] - f1h["low"]) if {"high","low"}.issubset(f1h.columns) else None
        range_contracting = bool(ranges is not None and len(ranges) >= 6 and ranges.tail(3).mean() < ranges.iloc[-6:-3].mean())
        vol_contracting = bool(recent_vol is not None and prior_vol is not None and recent_vol < prior_vol)
        previous_high20 = float(f4h["high"].iloc[-21:-1].max()) if len(f4h) >= 21 else None
        previous_low20 = float(f4h["low"].iloc[-21:-1].min()) if len(f4h) >= 21 else None
        four_hour_closed = True  # _get_confirmed_candles excludes forming bars.
        data_fresh = True  # MarketData validates source candle timestamps separately.
        liq = bool(liquidity_passed)
        within15 = bool(close1 and ema20_4 and atr1 and abs(close1-ema20_4) <= 1.5*atr1)
        within2 = bool(close1 and ema20_4 and atr1 and abs(close1-ema20_4) <= 2*atr1)
        risk_ok = bool(atr1 and close1 and atr1/close1 <= 0.08)

        bullish_mtf = bool(ema20_4 and ema50_4 and ema20_4 >= ema50_4*0.99
                           and (ema5_1 is None or ema20_1 is None or ema5_1 >= ema20_1*0.98))
        bearish_mtf = bool(ema20_4 and ema50_4 and ema20_4 <= ema50_4*1.01
                           and (ema5_1 is None or ema20_1 is None or ema5_1 <= ema20_1*1.02))
        features = {
            "rs_3d_positive": rs3 is not None and rs3 > 0,
            "rs_7d_positive": rs7 is not None and rs7 > 0,
            "rs_3d_negative": rs3 is not None and rs3 < 0,
            "rs_7d_negative": rs7 is not None and rs7 < 0,
            "ratio_trend_up": ratio_up,
            "ratio_trend_down": ratio_down,
            "ema20_above_or_near_ema50_4h": bool(ema20_4 and ema50_4 and ema20_4 >= ema50_4*0.99),
            "ema20_slope_up_4h": ema20_4_slope,
            "ema20_below_or_near_ema50_4h": bool(ema20_4 and ema50_4 and ema20_4 <= ema50_4*1.01),
            "ema20_slope_down_4h": ema20_4_slope_down,
            "ema5_crossed_ema10_1h": bool(ema5_1 and ema10_1 and ema5_1_prev and ema10_1_prev and ema5_1 > ema10_1 and ema5_1_prev <= ema10_1_prev),
            "ema10_improving_ema20_1h": bool(ema10_1 and ema20_1 and ema10_1 > ema20_1),
            "ema5_crossed_below_ema10_1h": bool(ema5_1 and ema10_1 and ema5_1_prev and ema10_1_prev and ema5_1 < ema10_1 and ema5_1_prev >= ema10_1_prev),
            "ema10_weakening_ema20_1h": bool(ema10_1 and ema20_1 and ema10_1 < ema20_1),
            "pullback_volume_decreasing": vol_contracting,
            "rally_volume_decreasing": vol_contracting,
            "range_contracting": range_contracting,
            "mtf_not_severely_conflicted": bool(ema20_4 and ema50_4 and ((ema20_4 >= ema50_4*0.99 and (ema20_1 is None or ema5_1 is None or ema5_1 >= ema20_1*0.98)) or (ema20_4 <= ema50_4*1.01 and (ema20_1 is None or ema5_1 is None or ema5_1 <= ema20_1*1.02)))),
            "rsi_50_to_70": rsi1 is not None and 50 <= rsi1 <= 70,
            "rsi_30_to_50": rsi1 is not None and 30 <= rsi1 <= 50,
            "rsi_55_to_80": rsi1 is not None and 55 <= rsi1 <= 80,
            "rsi_below_45": rsi1 is not None and rsi1 < 45,
            "macd_hist_improving": macdh1 is not None and macdh1_prev is not None and macdh1 > macdh1_prev,
            "macd_hist_deteriorating": macdh1 is not None and macdh1_prev is not None and macdh1 < macdh1_prev,
            "macd_bullish": macdh1 is not None and macdh1 > 0,
            "macd_bearish": macdh1 is not None and macdh1 < 0,
            "obv_rising": obv1 is not None and obv1_prev is not None and obv1 > obv1_prev,
            "obv_falling": obv1 is not None and obv1_prev is not None and obv1 < obv1_prev,
            "adx_above_20_rising": adx4 is not None and adx4_prev is not None and adx4 >= 20 and adx4 > adx4_prev,
            "liquidity_passed": liq,
            "within_1_5_atr_ema20": within15,
            "within_2_atr_ema20": within2,
            "risk_reward_passed": risk_ok,
            "closed_4h_close_above_previous_20_high_with_buffer": bool(close4 and previous_high20 and close4 > previous_high20 + 0.1*(e(f4h, "atr_14") or 0)),
            "closed_4h_close_below_previous_20_low_with_buffer": bool(close4 and previous_low20 and close4 < previous_low20 - 0.1*(e(f4h, "atr_14") or 0)),
            "same_elapsed_time_volume_ratio": (float(vol1/volma1) if vol1 is not None and volma1 else 0),
            "ema20_above_ema50_4h": bool(ema20_4 and ema50_4 and ema20_4 > ema50_4),
            "ema50_above_or_improving_ema100_4h": bool(ema50_4 and ema100_4 and (ema50_4 >= ema100_4 or (ema50_4_prev and ema50_4 > ema50_4_prev))),
            "ema20_below_ema50_4h": bool(ema20_4 and ema50_4 and ema20_4 < ema50_4),
            "ema50_below_or_weakening_ema100_4h": bool(ema50_4 and ema100_4 and (ema50_4 <= ema100_4 or (ema50_4_prev and ema50_4 < ema50_4_prev))),
            "ema5_above_ema10_above_ema20_1h": bool(ema5_1 and ema10_1 and ema20_1 and ema5_1 > ema10_1 > ema20_1),
            "ema5_below_ema10_below_ema20_1h": bool(ema5_1 and ema10_1 and ema20_1 and ema5_1 < ema10_1 < ema20_1),
            "four_hour_candle_closed": four_hour_closed,
            "data_fresh": data_fresh,
            "minimum_score": 70,
        }
        long_features = dict(features)
        short_features = dict(features)
        long_features["mtf_not_severely_conflicted"] = bullish_mtf
        short_features["mtf_not_severely_conflicted"] = bearish_mtf
        evaluated = {
            "RADAR-LONG-A": evaluate_early_accumulation(long_features),
            "RADAR-LONG-B": evaluate_breakout_momentum(long_features),
            "RADAR-SHORT-A": evaluate_early_distribution(short_features),
            "RADAR-SHORT-B": evaluate_breakdown_momentum(short_features),
        }
        for name, result in evaluated.items():
            if result.get("eligible") and close1 and atr1:
                direction = "LONG" if "LONG" in name else "SHORT"
                risk = atr1 * 1.5
                stop = close1 - risk if direction == "LONG" else close1 + risk
                tp1 = close1 + 2*risk if direction == "LONG" else close1 - 2*risk
                tp2 = close1 + 3*risk if direction == "LONG" else close1 - 3*risk
                result["trade_plan"] = {
                    "entry_price": round(close1, 10),
                    "stop_loss": round(stop, 10),
                    "tp1": round(tp1, 10), "tp2": round(tp2, 10),
                    "reward_risk_ratio": 2.0,
                    "status": "simulation_only", "auto_trading": False,
                    "sizing_required": True,
                }
            else:
                result["trade_plan"] = None
            result["liquidity_detail"] = liquidity_detail or {}
        return evaluated

    def analyze_symbol(self, inst_id, equity=None):
        symbol = inst_id

        try:
            if not isinstance(inst_id, str):
                raise ValueError("Invalid instrument ID")

            inst_id = inst_id.strip().upper()
            symbol = inst_id

            if not inst_id.endswith("-USDT-SWAP"):
                raise ValueError(
                    "Only USDT perpetual swaps are supported"
                )

            if inst_id == "BTC-USDT-SWAP":
                raise ValueError(
                    "BTC is the benchmark and cannot be analyzed against itself"
                )

            df_1h = self._get_confirmed_candles(
                inst_id,
                "1H"
            )

            df_4h = self._get_confirmed_candles(
                inst_id,
                "4H"
            )
            df_1d = self._get_confirmed_candles(inst_id, "1D")
            df_1w = self._get_confirmed_candles(inst_id, "1W")

            features_1h = self._prepare_features(df_1h)
            features_4h = self._prepare_features(df_4h)

            relative_data = (
                self.market_data.get_multi_timeframe_relative_strength(
                    inst_id,
                    timeframes=self.TIMEFRAMES,
                    limit=100
                )
            )

            relative_strength = self._extract_relative_strength(
                relative_data
            )

            # 關鍵修正：
            # 1H／4H 任何一個相對強弱資料無效，
            # 立即停止分析，不讓不完整資料進入策略引擎。
            relative_strength = (
                self._validate_relative_strength(
                    relative_strength
                )
            )

            daily_rs = {}
            daily_rs_method = getattr(self.market_data, "get_daily_relative_strength_profile", None)
            if callable(daily_rs_method):
                try:
                    daily_rs = daily_rs_method(inst_id, limit=30)
                except Exception:
                    daily_rs = {}
            liquidity_detail = {"passed": False, "reasons": ["ticker_unavailable"]}
            try:
                ticker = self.market_data.client.get_ticker(inst_id)
                liquidity_detail = evaluate_liquidity(
                    ticker,
                    min_turnover_usdt=Config.MIN_TURNOVER_USDT,
                    max_spread_pct=Config.MAX_SPREAD_PCT,
                    max_ticker_age_seconds=Config.MAX_TICKER_AGE_SECONDS,
                    now_ms=int(datetime.now(timezone.utc).timestamp()*1000),
                )
            except Exception:
                pass
            v11_radars = self._evaluate_v11_radars(
                features_1h, features_4h, relative_strength, daily_rs,
                liquidity_passed=liquidity_detail.get("passed") is True,
                liquidity_detail=liquidity_detail,
            )
            # 15M is an execution-timing aid only. Its failure must not
            # invalidate the independently confirmed 1H/4H/1D/1W analysis.
            df_15m = None
            try:
                df_15m = self._get_confirmed_candles(inst_id, "15M")
            except Exception:
                df_15m = None

            pattern_candles = {
                "1W": df_1w.to_dict("records"),
                "1D": df_1d.to_dict("records"),
                "4H": df_4h.to_dict("records"),
                "1H": df_1h.to_dict("records"),
            }
            if df_15m is not None:
                pattern_candles["15M"] = df_15m.to_dict("records")

            pattern_result = self.pattern_scanner.scan_symbol(
                inst_id, pattern_candles
            )

            strategy_result = self.strategy_engine.analyze(
                inst_id,
                features_1h,
                features_4h,
                relative_strength_1h=relative_strength["1H"],
                relative_strength_4h=relative_strength["4H"]
            )

            strategy = self._normalize_strategy_result(
                strategy_result
            )

            atr = self._extract_latest_atr(features_1h)
            current_price = self._safe_float(features_1h.iloc[-1]["close"])
            # Route every confirmed auxiliary setup through the existing risk manager.
            for radar_name, radar in v11_radars.items():
                if radar.get("eligible") and atr and current_price:
                    side = "LONG" if "LONG" in radar_name else "SHORT"
                    try:
                        radar["trade_plan"] = self.risk_manager.create_trade_plan(
                            symbol=inst_id, side=side, entry_price=current_price,
                            atr=atr, equity=equity
                        )
                        radar["trade_plan"]["status"] = "simulation_only"
                        radar["trade_plan"]["auto_trading"] = False
                    except Exception:
                        radar["eligible"] = False
                        radar["state"] = "WATCH"
                        radar["trade_plan"] = None
            for pattern in pattern_result.get("pattern_signals", []):
                if pattern.get("state") == "CONFIRMED" and atr and current_price:
                    try:
                        d_point = (pattern.get("points") or {}).get("D") or {}
                        d_price = self._safe_float(d_point.get("price"))
                        stop_override = None
                        if d_price is not None:
                            buffer = max(atr * 0.25, current_price * 0.001)
                            stop_override = (
                                d_price - buffer if pattern["direction"] == "LONG"
                                else d_price + buffer
                            )
                        plan = self.risk_manager.create_trade_plan(
                            symbol=inst_id, side=pattern["direction"],
                            entry_price=current_price, atr=atr, equity=equity,
                            stop_loss_override=stop_override
                        )
                        # Preserve three targets in the same simulation plan.
                        risk_distance = abs(current_price - plan["stop_loss"])
                        if pattern["direction"] == "LONG":
                            plan["tp3"] = round(current_price + risk_distance * 3.0, 8)
                        else:
                            plan["tp3"] = round(current_price - risk_distance * 3.0, 8)
                        plan["status"] = "simulation_only"
                        plan["auto_trading"] = False
                        pattern["trade_plan"] = plan
                    except Exception:
                        pattern["state"] = "COMPLETED"
                        pattern["trade_plan"] = None

            if not strategy["signals"]:
                return {
                    "symbol": inst_id,
                    "status": "analyzed",
                    "relative_strength": relative_strength,
                    "daily_relative_strength": daily_rs,
                    "v11_radars": v11_radars,
                    "pattern_signals": pattern_result.get("pattern_signals", []),
                    "direction": "NEUTRAL",
                    "candidate": False,
                    "strategy": strategy,
                    "strategy_trade_plans": {},
                    "trade_plan": None,
                    "selected_signal": None,
                    "trading_mode": "simulation_only",
                    "auto_trading": False
                }

            if atr is None:
                raise ValueError(
                    "ATR is missing or invalid; cannot create trade plan"
                )

            plans = self._create_strategy_trade_plans(
                symbol=inst_id,
                signals=strategy["signals"],
                atr=atr,
                equity=equity
            )

            selected_signal, trade_plan = (
                self._select_best_trade_plan(
                    strategy["signals"],
                    plans
                )
            )

            return {
                "symbol": inst_id,
                "status": "analyzed",
                "relative_strength": relative_strength,
                "daily_relative_strength": daily_rs,
                "v11_radars": v11_radars,
                "pattern_signals": pattern_result.get("pattern_signals", []),
                "direction": strategy["direction"],
                "candidate": strategy["candidate"],
                "strategy": strategy,
                "strategy_trade_plans": plans,
                "trade_plan": trade_plan,
                "selected_signal": (
                    selected_signal["signal"]
                    if selected_signal else None
                ),
                "atr": atr,
                "trading_mode": "simulation_only",
                "auto_trading": False
            }

        except Exception as exc:
            return {
                "symbol": symbol,
                "status": "error",
                "error": str(exc),
                "direction": "NEUTRAL",
                "candidate": False,
                "strategy": {
                    "signals": [],
                    "direction": "NEUTRAL",
                    "candidate": False,
                    "status": "error"
                },
                "strategy_trade_plans": {},
                "trade_plan": None,
                "selected_signal": None,
                "v11_radars": {},
                "pattern_signals": [],
                "trading_mode": "simulation_only",
                "auto_trading": False
            }

    def analyze_multiple(self, symbols, equity=None):
        return [
            self.analyze_symbol(
                symbol,
                equity=equity
            )
            for symbol in symbols
        ]
