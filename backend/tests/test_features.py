"""
Unit tests for feature engineering module.
"""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import pytz

from ml.features import (
    compute_ema, compute_rsi, compute_macd, compute_bollinger, compute_atr,
    compute_stochastic, compute_obv, detect_ema_crossover, detect_three_candle_momentum,
    engineer_features, get_feature_columns,
)

IST = pytz.timezone("Asia/Kolkata")


def make_sample_df(n: int = 500) -> pd.DataFrame:
    """Create synthetic OHLCV data for testing."""
    np.random.seed(42)
    base = 48000.0
    closes = [base + np.random.randn() * 100 for _ in range(n)]

    rows = []
    t = datetime(2024, 1, 2, 9, 15, tzinfo=IST)
    for i, c in enumerate(closes):
        o = c * (1 + np.random.randn() * 0.001)
        h = max(o, c) * (1 + abs(np.random.randn()) * 0.001)
        l = min(o, c) * (1 - abs(np.random.randn()) * 0.001)
        rows.append({
            "time": t,
            "open": o, "high": h, "low": l, "close": c,
            "volume": int(abs(np.random.randn()) * 100000 + 50000),
            "oi": 0,
        })
        t += timedelta(minutes=15)
    return pd.DataFrame(rows)


class TestIndicators:
    def test_ema_length(self):
        df = make_sample_df(100)
        ema = compute_ema(df["close"], 9)
        assert len(ema) == 100
        assert not ema.isna().all()

    def test_rsi_range(self):
        df = make_sample_df(200)
        rsi = compute_rsi(df["close"])
        valid = rsi.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_macd_returns_three_series(self):
        df = make_sample_df(100)
        macd, signal, hist = compute_macd(df["close"])
        assert len(macd) == len(df)
        assert len(signal) == len(df)
        assert len(hist) == len(df)

    def test_bollinger_upper_gt_lower(self):
        df = make_sample_df(100)
        upper, lower, pct_b, bw = compute_bollinger(df["close"])
        valid_mask = upper.notna() & lower.notna()
        assert (upper[valid_mask] >= lower[valid_mask]).all()

    def test_atr_positive(self):
        df = make_sample_df(100)
        atr = compute_atr(df["high"], df["low"], df["close"])
        valid = atr.dropna()
        assert (valid > 0).all()

    def test_stochastic_range(self):
        df = make_sample_df(100)
        k, d = compute_stochastic(df["high"], df["low"], df["close"])
        valid_k = k.dropna()
        assert (valid_k >= 0).all() and (valid_k <= 100).all()

    def test_obv_changes_with_volume(self):
        df = make_sample_df(50)
        obv = compute_obv(df["close"], df["volume"])
        assert len(obv) == 50

    def test_ema_crossover_values(self):
        df = make_sample_df(300)
        ema9 = compute_ema(df["close"], 9)
        ema21 = compute_ema(df["close"], 21)
        cross = detect_ema_crossover(ema9, ema21)
        assert set(cross.unique()).issubset({-1, 0, 1})

    def test_three_candle_momentum(self):
        df = make_sample_df(50)
        flag = detect_three_candle_momentum(df["close"], direction=1)
        assert len(flag) == 50
        assert flag.max() <= 1 and flag.min() >= 0


class TestFeatureEngineering:
    def test_engineer_features_output(self):
        df = make_sample_df(500)
        features = engineer_features(df, pcr=0.9, max_pain=48000, iv_rank=35.0)
        assert not features.empty
        assert len(features) > 100  # After warmup period

    def test_feature_columns_present(self):
        df = make_sample_df(500)
        features = engineer_features(df)
        expected_cols = get_feature_columns()
        for col in expected_cols:
            assert col in features.columns, f"Missing column: {col}"

    def test_no_inf_values(self):
        df = make_sample_df(500)
        features = engineer_features(df)
        feat_cols = get_feature_columns()
        feat_cols = [c for c in feat_cols if c in features.columns]
        assert not features[feat_cols].isin([float("inf"), float("-inf")]).any().any()

    def test_insufficient_data(self):
        df = make_sample_df(50)  # Too few for EMA 200
        features = engineer_features(df)
        assert features.empty

    def test_pcr_feature(self):
        df = make_sample_df(500)
        features = engineer_features(df, pcr=1.5)
        assert (features["pcr"] == 1.5).all()
        assert (features["pcr_bearish"] == 1).all()

    def test_bull_score_nonnegative(self):
        df = make_sample_df(500)
        features = engineer_features(df)
        assert (features["bull_score"] >= 0).all()
