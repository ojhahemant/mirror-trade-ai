"""
Backtesting engine: simulates strategy on historical data.
Produces comprehensive performance metrics and exportable reports.
"""
import json
import csv
import os
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
import pytz
from loguru import logger

from api.config import settings
from ml.features import engineer_features, get_feature_columns
from ml.model_engine import ModelInference, create_target, ATR_SL_MULTIPLIER, ATR_T1_MULTIPLIER, ATR_T2_MULTIPLIER

IST = pytz.timezone(settings.ist_timezone)
REPORTS_DIR = "/app/reports"
os.makedirs(REPORTS_DIR, exist_ok=True)


class BacktestEngine:
    """
    Event-driven backtester for Bank Nifty signals.
    Simulates signal generation and tracks outcomes candle-by-candle.
    """

    def __init__(self, min_confidence: float = 65.0):
        self.min_confidence = min_confidence
        self.model = ModelInference()

    def run(
        self,
        df: pd.DataFrame,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        pcr: float = 1.0,
        max_pain: float = 0.0,
        iv_rank: float = 50.0,
    ) -> Dict[str, Any]:
        """
        Run backtest on provided OHLCV DataFrame.

        Args:
            df: OHLCV DataFrame with 'time' column
            from_date / to_date: Date filters
            pcr, max_pain, iv_rank: Options-derived features (held constant for backtest)

        Returns:
            Dict with all performance metrics.
        """
        logger.info(f"Backtesting: {len(df)} candles, confidence≥{self.min_confidence}%")

        if df.empty or len(df) < 300:
            raise ValueError("Insufficient data for backtesting (need 300+ candles)")

        # Filter date range
        df = df.copy().sort_values("time").reset_index(drop=True)
        if from_date:
            df = df[pd.to_datetime(df["time"]).dt.date >= from_date]
        if to_date:
            df = df[pd.to_datetime(df["time"]).dt.date <= to_date]

        if df.empty:
            raise ValueError("No data in specified date range")

        # Feature engineering on full dataset
        features_df = engineer_features(df, pcr=pcr, max_pain=max_pain, iv_rank=iv_rank)
        if features_df.empty:
            raise ValueError("Feature engineering produced no results")

        feature_cols = get_feature_columns()
        feature_cols = [c for c in feature_cols if c in features_df.columns]

        trades = []
        active_signal = None
        lookback = 250  # Minimum rows for reliable features

        for i in range(lookback, len(features_df)):
            row = features_df.iloc[i]
            current_close = Decimal(str(row["close"]))
            current_time = row["time"]
            atr = Decimal(str(row.get("atr_14", float(current_close * Decimal("0.003")))))

            # ── Check active signal outcome ────────────────────────────────────
            if active_signal:
                direction = active_signal["direction"]
                sl = active_signal["stop_loss"]
                t1 = active_signal["target_1"]
                t2 = active_signal["target_2"]
                entry_time = active_signal["entry_time"]
                entry_price = active_signal["entry_price"]
                candles_open = i - active_signal["entry_idx"]
                high = Decimal(str(row["high"]))
                low = Decimal(str(row["low"]))

                outcome = None
                close_price = current_close

                if direction == "BUY":
                    if low <= sl:
                        outcome = "SL_HIT"
                        close_price = sl
                    elif high >= t2:
                        outcome = "TARGET_2_HIT"
                        close_price = t2
                    elif high >= t1:
                        outcome = "TARGET_1_HIT"
                        close_price = t1
                elif direction == "SELL":
                    if high >= sl:
                        outcome = "SL_HIT"
                        close_price = sl
                    elif low <= t2:
                        outcome = "TARGET_2_HIT"
                        close_price = t2
                    elif low <= t1:
                        outcome = "TARGET_1_HIT"
                        close_price = t1

                # Expire after 4 candles
                if outcome is None and candles_open >= 4:
                    outcome = "EXPIRED"

                if outcome:
                    if direction == "BUY":
                        pnl = close_price - entry_price
                    else:
                        pnl = entry_price - close_price

                    active_signal.update({
                        "outcome": outcome,
                        "close_price": float(close_price),
                        "close_time": str(current_time),
                        "pnl_points": float(pnl),
                        "is_win": pnl > 0,
                    })
                    trades.append(active_signal)
                    active_signal = None

            # ── Generate new signal (only if no active signal) ──────────────
            if active_signal is None:
                # Run model inference using a window of data
                window = features_df.iloc[max(0, i-lookback):i+1]
                X_row = np.array([[window.iloc[-1].get(col, 0) for col in feature_cols]], dtype=np.float32)

                if not self.model.is_ready:
                    # Fallback: rule-based signal for testing without model
                    signal = self._rule_based_signal(row, atr, feature_cols)
                else:
                    try:
                        from sklearn.preprocessing import StandardScaler
                        import joblib
                        from api.config import settings
                        scaler_path = os.path.join(settings.model_dir, "banknifty_scaler_latest.joblib")
                        if os.path.exists(scaler_path):
                            scaler = joblib.load(scaler_path)
                            X_scaled = scaler.transform(X_row)
                        else:
                            X_scaled = X_row

                        proba = self.model._model.predict_proba(X_scaled)[0]
                        pred = int(np.argmax(proba)) - 1
                        confidence = float(np.max(proba)) * 100

                        if confidence < self.min_confidence or pred == 0:
                            signal = None
                        else:
                            direction = "BUY" if pred == 1 else "SELL"
                            sl_d = atr * ATR_SL_MULTIPLIER
                            t1_d = atr * ATR_T1_MULTIPLIER
                            t2_d = atr * ATR_T2_MULTIPLIER

                            if direction == "BUY":
                                sl = current_close - sl_d
                                t1 = current_close + t1_d
                                t2 = current_close + t2_d
                            else:
                                sl = current_close + sl_d
                                t1 = current_close - t1_d
                                t2 = current_close - t2_d

                            rr = float(t1_d / sl_d) if sl_d > 0 else 0

                            signal = {
                                "direction": direction,
                                "confidence": round(confidence, 2),
                                "entry_price": float(current_close),
                                "stop_loss": float(sl),
                                "target_1": float(t1),
                                "target_2": float(t2),
                                "risk_reward": rr,
                                "atr": float(atr),
                            }
                    except Exception as e:
                        logger.warning(f"Inference failed at step {i}: {e}")
                        signal = None

                if signal and signal["risk_reward"] >= 1.5:
                    active_signal = {
                        **signal,
                        "entry_time": str(current_time),
                        "entry_idx": i,
                    }

        # Close any still-active signal at end of data
        if active_signal:
            last_close = Decimal(str(features_df.iloc[-1]["close"]))
            entry_price = Decimal(str(active_signal["entry_price"]))
            direction = active_signal["direction"]
            pnl = last_close - entry_price if direction == "BUY" else entry_price - last_close
            active_signal.update({
                "outcome": "EXPIRED",
                "close_price": float(last_close),
                "close_time": str(features_df.iloc[-1]["time"]),
                "pnl_points": float(pnl),
                "is_win": pnl > 0,
            })
            trades.append(active_signal)

        return self._compute_metrics(trades, from_date, to_date)

    def _rule_based_signal(self, row: pd.Series, atr: Decimal, feature_cols: list) -> Optional[Dict]:
        """Simple rule-based fallback when model isn't available."""
        ema9 = row.get("ema_9", 0)
        ema21 = row.get("ema_21", 0)
        rsi = row.get("rsi_14", 50)
        close = row.get("close", 0)

        if ema9 > ema21 and rsi > 45 and rsi < 70:
            direction = "BUY"
        elif ema9 < ema21 and rsi < 55 and rsi > 30:
            direction = "SELL"
        else:
            return None

        entry = Decimal(str(close))
        sl_d = atr * ATR_SL_MULTIPLIER
        t1_d = atr * ATR_T1_MULTIPLIER
        t2_d = atr * ATR_T2_MULTIPLIER

        if direction == "BUY":
            sl = entry - sl_d
            t1 = entry + t1_d
            t2 = entry + t2_d
        else:
            sl = entry + sl_d
            t1 = entry - t1_d
            t2 = entry - t2_d

        rr = float(t1_d / sl_d) if sl_d > 0 else 0
        return {
            "direction": direction,
            "confidence": 66.0,
            "entry_price": float(entry),
            "stop_loss": float(sl),
            "target_1": float(t1),
            "target_2": float(t2),
            "risk_reward": rr,
            "atr": float(atr),
        }

    def _compute_metrics(
        self,
        trades: List[Dict],
        from_date: Optional[date],
        to_date: Optional[date],
    ) -> Dict[str, Any]:
        """Compute comprehensive backtest metrics from trade list."""
        if not trades:
            return self._empty_metrics(from_date, to_date)

        total = len(trades)
        wins = [t for t in trades if t.get("is_win", False)]
        losses = [t for t in trades if not t.get("is_win", True)]
        pnls = [t.get("pnl_points", 0) for t in trades]

        win_rate = (len(wins) / total * 100) if total > 0 else 0
        total_pnl = sum(pnls)
        best_trade = max(pnls) if pnls else 0
        worst_trade = min(pnls) if pnls else 0

        # Average R:R on wins
        win_pnls = [t["pnl_points"] for t in wins]
        loss_pnls = [abs(t["pnl_points"]) for t in losses]
        avg_win = np.mean(win_pnls) if win_pnls else 0
        avg_loss = np.mean(loss_pnls) if loss_pnls else 0
        avg_rr = avg_win / avg_loss if avg_loss > 0 else 0

        # Equity curve and max drawdown
        cumulative = np.cumsum(pnls)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = running_max - cumulative
        max_drawdown = float(np.max(drawdown)) if len(drawdown) > 0 else 0

        # Sharpe Ratio (annualized, assumes 26 bars/day, 250 trading days)
        returns = np.array(pnls)
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(26 * 250))
        else:
            sharpe = 0.0

        # Monthly P&L breakdown
        monthly_pnl = self._monthly_breakdown(trades)

        # Equity curve (daily cumulative)
        equity_curve = self._equity_curve(trades)

        # Streaks
        streak_data = self._compute_streaks([t["is_win"] for t in trades])

        return {
            "from_date": str(from_date) if from_date else "N/A",
            "to_date": str(to_date) if to_date else "N/A",
            "total_signals": total,
            "winning_signals": len(wins),
            "losing_signals": len(losses),
            "neutral_signals": 0,
            "win_rate": round(win_rate, 2),
            "avg_rr": round(avg_rr, 2),
            "max_drawdown": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 3),
            "total_pnl_points": round(total_pnl, 2),
            "best_trade": round(best_trade, 2),
            "worst_trade": round(worst_trade, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "max_win_streak": streak_data["max_win"],
            "max_loss_streak": streak_data["max_loss"],
            "monthly_pnl": monthly_pnl,
            "equity_curve": equity_curve,
            "detailed_trades": trades[:200],  # Limit for response size
        }

    def _monthly_breakdown(self, trades: List[Dict]) -> List[Dict]:
        """Group trades by month and compute monthly P&L."""
        monthly: Dict[str, Dict] = {}
        for trade in trades:
            t = trade.get("entry_time", "")
            try:
                month = str(t)[:7]  # YYYY-MM
            except Exception:
                continue
            if month not in monthly:
                monthly[month] = {"pnl": 0, "wins": 0, "losses": 0}
            monthly[month]["pnl"] += trade.get("pnl_points", 0)
            if trade.get("is_win"):
                monthly[month]["wins"] += 1
            else:
                monthly[month]["losses"] += 1

        result = []
        for month in sorted(monthly.keys()):
            data = monthly[month]
            total = data["wins"] + data["losses"]
            result.append({
                "month": month,
                "pnl": round(data["pnl"], 2),
                "wins": data["wins"],
                "losses": data["losses"],
                "win_rate": round(data["wins"] / total * 100, 1) if total > 0 else 0,
            })
        return result

    def _equity_curve(self, trades: List[Dict]) -> List[Dict]:
        """Build daily equity curve."""
        curve = []
        cumulative = 0
        by_date: Dict[str, List] = {}
        for trade in trades:
            t = trade.get("entry_time", "")
            day = str(t)[:10]
            if day not in by_date:
                by_date[day] = []
            by_date[day].append(trade.get("pnl_points", 0))

        for day in sorted(by_date.keys()):
            daily = sum(by_date[day])
            cumulative += daily
            curve.append({
                "date": day,
                "daily_pnl": round(daily, 2),
                "cumulative_pnl": round(cumulative, 2),
                "signals_count": len(by_date[day]),
            })
        return curve

    def _compute_streaks(self, outcomes: List[bool]) -> Dict[str, int]:
        """Compute max win/loss streaks."""
        max_win = max_loss = cur_win = cur_loss = 0
        for outcome in outcomes:
            if outcome:
                cur_win += 1
                cur_loss = 0
                max_win = max(max_win, cur_win)
            else:
                cur_loss += 1
                cur_win = 0
                max_loss = max(max_loss, cur_loss)
        return {"max_win": max_win, "max_loss": max_loss}

    def _empty_metrics(self, from_date, to_date) -> Dict:
        return {
            "from_date": str(from_date), "to_date": str(to_date),
            "total_signals": 0, "winning_signals": 0, "losing_signals": 0,
            "win_rate": 0, "avg_rr": 0, "max_drawdown": 0,
            "sharpe_ratio": 0, "total_pnl_points": 0,
            "best_trade": 0, "worst_trade": 0,
            "monthly_pnl": [], "equity_curve": [], "detailed_trades": [],
        }

    def export_csv(self, results: Dict, filename: str = None) -> str:
        """Export detailed trades to CSV."""
        if filename is None:
            filename = f"backtest_{results['from_date']}_to_{results['to_date']}.csv"
        filepath = os.path.join(REPORTS_DIR, filename)

        trades = results.get("detailed_trades", [])
        if not trades:
            return filepath

        keys = ["direction", "confidence", "entry_price", "stop_loss",
                "target_1", "target_2", "risk_reward", "outcome",
                "close_price", "pnl_points", "entry_time", "close_time"]

        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(trades)

        logger.info(f"CSV exported: {filepath}")
        return filepath


# CLI entry point
if __name__ == "__main__":
    import argparse
    import asyncio
    from data.data_pipeline import get_latest_candles

    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_date", default="2022-01-01")
    parser.add_argument("--to", dest="to_date", default="2024-12-31")
    parser.add_argument("--confidence", type=float, default=65.0)
    args = parser.parse_args()

    from_d = date.fromisoformat(args.from_date)
    to_d = date.fromisoformat(args.to_date)

    df = asyncio.run(get_latest_candles("15min", limit=50000))
    engine = BacktestEngine(min_confidence=args.confidence)
    results = engine.run(df, from_date=from_d, to_date=to_d)
    csv_path = engine.export_csv(results)

    print(f"\n{'='*50}")
    print(f"BACKTEST RESULTS: {args.from_date} → {args.to_date}")
    print(f"{'='*50}")
    print(f"Total Signals:   {results['total_signals']}")
    print(f"Win Rate:        {results['win_rate']}%")
    print(f"Total P&L:       {results['total_pnl_points']} points")
    print(f"Max Drawdown:    {results['max_drawdown']} points")
    print(f"Sharpe Ratio:    {results['sharpe_ratio']}")
    print(f"CSV Report:      {csv_path}")
