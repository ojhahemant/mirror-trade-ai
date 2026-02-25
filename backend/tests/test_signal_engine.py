"""
Unit tests for signal generation and lifecycle management.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from decimal import Decimal
import pytz

IST = pytz.timezone("Asia/Kolkata")


def make_df(n: int = 500):
    np.random.seed(99)
    t = datetime(2024, 6, 3, 9, 15, tzinfo=IST)
    from datetime import timedelta
    rows = []
    price = 48000.0
    for i in range(n):
        open_ = price
        close = price + np.random.randn() * 80
        high = max(open_, close) + abs(np.random.randn()) * 30
        low = min(open_, close) - abs(np.random.randn()) * 30
        rows.append({
            "time": t,
            "open": open_, "high": high, "low": low, "close": close,
            "volume": int(abs(np.random.randn()) * 100000 + 80000),
            "oi": 0,
        })
        price = close
        t += timedelta(minutes=15)
    return pd.DataFrame(rows)


class TestSignalLevels:
    """Test stop/target calculation logic."""

    def test_buy_signal_levels(self):
        from ml.model_engine import ATR_SL_MULTIPLIER, ATR_T1_MULTIPLIER, ATR_T2_MULTIPLIER

        entry = Decimal("48000")
        atr = Decimal("150")

        sl = entry - atr * ATR_SL_MULTIPLIER
        t1 = entry + atr * ATR_T1_MULTIPLIER
        t2 = entry + atr * ATR_T2_MULTIPLIER

        assert sl < entry < t1 < t2
        rr = (t1 - entry) / (entry - sl)
        assert rr >= Decimal("1.5")

    def test_sell_signal_levels(self):
        from ml.model_engine import ATR_SL_MULTIPLIER, ATR_T1_MULTIPLIER, ATR_T2_MULTIPLIER

        entry = Decimal("48000")
        atr = Decimal("150")

        sl = entry + atr * ATR_SL_MULTIPLIER
        t1 = entry - atr * ATR_T1_MULTIPLIER
        t2 = entry - atr * ATR_T2_MULTIPLIER

        assert t2 < t1 < entry < sl
        rr = (entry - t1) / (sl - entry)
        assert rr >= Decimal("1.5")

    def test_risk_reward_minimum(self):
        from ml.model_engine import ATR_SL_MULTIPLIER, ATR_T1_MULTIPLIER, MIN_RISK_REWARD

        atr = Decimal("200")
        rr = ATR_T1_MULTIPLIER / ATR_SL_MULTIPLIER
        assert rr >= MIN_RISK_REWARD


class TestOptionsProcessor:
    """Test options chain calculations."""

    def test_pcr_calculation(self):
        from data.options_fetcher import OptionsProcessor

        chain = [
            {"option_type": "CE", "oi": 100000},
            {"option_type": "CE", "oi": 50000},
            {"option_type": "PE", "oi": 150000},
            {"option_type": "PE", "oi": 50000},
        ]
        proc = OptionsProcessor()
        pcr = proc.compute_pcr(chain)
        # PE OI = 200000, CE OI = 150000
        expected = Decimal("200000") / Decimal("150000")
        assert abs(pcr - expected) < Decimal("0.001")

    def test_max_pain_calculation(self):
        from data.options_fetcher import OptionsProcessor

        chain = [
            {"option_type": "CE", "oi": 50000, "strike": 47800},
            {"option_type": "PE", "oi": 80000, "strike": 47800},
            {"option_type": "CE", "oi": 200000, "strike": 48000},
            {"option_type": "PE", "oi": 200000, "strike": 48000},
            {"option_type": "CE", "oi": 80000, "strike": 48200},
            {"option_type": "PE", "oi": 50000, "strike": 48200},
        ]
        proc = OptionsProcessor()
        max_pain = proc.compute_max_pain(chain, Decimal("48000"))
        assert max_pain in [Decimal("47800"), Decimal("48000"), Decimal("48200")]

    def test_iv_rank_bounds(self):
        from data.options_fetcher import OptionsProcessor

        proc = OptionsProcessor()
        iv_history = [Decimal(str(i)) for i in range(10, 40)]

        # Current IV at min
        rank = proc.compute_iv_rank(Decimal("10"), iv_history)
        assert rank == Decimal("0")

        # Current IV at max
        rank = proc.compute_iv_rank(Decimal("39"), iv_history)
        assert rank == Decimal("100")

        # Current IV in middle
        rank = proc.compute_iv_rank(Decimal("25"), iv_history)
        assert Decimal("0") < rank < Decimal("100")


class TestBacktester:
    """Test backtest engine metrics."""

    def test_empty_trades_returns_zero_metrics(self):
        from ml.backtester import BacktestEngine

        engine = BacktestEngine()
        metrics = engine._empty_metrics(None, None)
        assert metrics["total_signals"] == 0
        assert metrics["win_rate"] == 0

    def test_monthly_breakdown_structure(self):
        from ml.backtester import BacktestEngine

        engine = BacktestEngine()
        trades = [
            {"entry_time": "2024-01-10 09:15", "pnl_points": 200, "is_win": True},
            {"entry_time": "2024-01-15 10:30", "pnl_points": -150, "is_win": False},
            {"entry_time": "2024-02-05 11:00", "pnl_points": 300, "is_win": True},
        ]
        monthly = engine._monthly_breakdown(trades)
        assert len(monthly) == 2  # Jan and Feb
        assert monthly[0]["month"] == "2024-01"
        assert monthly[0]["pnl"] == 50  # 200 - 150

    def test_streak_calculation(self):
        from ml.backtester import BacktestEngine

        engine = BacktestEngine()
        outcomes = [True, True, True, False, True, False, False, True]
        streaks = engine._compute_streaks(outcomes)
        assert streaks["max_win"] == 3
        assert streaks["max_loss"] == 2
