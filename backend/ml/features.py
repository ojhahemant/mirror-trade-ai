"""
Feature engineering for Bank Nifty ML model.
Computes all technical indicators, pattern signals, and derived features.
Uses pandas-ta (TA-Lib fallback) for indicator computation.
All price calculations use exact arithmetic via Decimal where possible.
"""
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple
import numpy as np
import pandas as pd
from loguru import logger

try:
    import pandas_ta as ta
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False
    logger.warning("pandas-ta not available — using manual indicator calculations")


# ── Constants ─────────────────────────────────────────────────────────────────
EMA_SHORT = 9
EMA_MID = 21
EMA_LONG = 50
EMA_TREND = 200
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2
ATR_PERIOD = 14
STOCH_K = 14
STOCH_D = 3
ROC_PERIOD = 10
VOL_AVG_PERIOD = 20
HV_PERIOD = 20
SUPPORT_RESISTANCE_THRESHOLD = 0.003  # 0.3%


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Compute Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def compute_rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """Compute RSI using Wilder's smoothing."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_macd(
    series: pd.Series,
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal: int = MACD_SIGNAL,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (macd_line, signal_line, histogram)."""
    ema_fast = compute_ema(series, fast)
    ema_slow = compute_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_bollinger(
    series: pd.Series,
    period: int = BB_PERIOD,
    std_dev: float = BB_STD,
) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Returns (upper, lower, pct_b, bandwidth)."""
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    pct_b = (series - lower) / (upper - lower + 1e-10)
    bandwidth = (upper - lower) / sma.replace(0, np.nan)
    return upper, lower, pct_b, bandwidth


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = ATR_PERIOD) -> pd.Series:
    """Compute Average True Range."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.ewm(alpha=1/period, min_periods=period, adjust=False).mean()


def compute_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = STOCH_K,
    d_period: int = STOCH_D,
) -> Tuple[pd.Series, pd.Series]:
    """Returns (stoch_k, stoch_d)."""
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    stoch_k = 100 * (close - lowest_low) / (highest_high - lowest_low + 1e-10)
    stoch_d = stoch_k.rolling(window=d_period).mean()
    return stoch_k, stoch_d


def compute_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume."""
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def encode_time_cyclical(values: pd.Series, max_val: float) -> Tuple[pd.Series, pd.Series]:
    """Encode time as sine/cosine for cyclical representation."""
    angle = 2 * np.pi * values / max_val
    return np.sin(angle), np.cos(angle)


def detect_key_levels(close: pd.Series, lookback: int = 50) -> pd.Series:
    """
    Detect support/resistance proximity.
    Returns fraction distance from nearest key level.
    """
    key_levels = []
    for i in range(lookback, len(close)):
        window = close.iloc[i-lookback:i]
        local_max = window.max()
        local_min = window.min()
        key_levels.append((local_max, local_min))

    proximity = pd.Series(index=close.index, dtype=float)
    for i in range(lookback, len(close)):
        levels = key_levels[i - lookback]
        price = close.iloc[i]
        min_dist = min(abs(price - lv) / price for lv in levels)
        proximity.iloc[i] = min_dist

    return proximity.fillna(1.0)


def compute_higher_highs_lower_lows(high: pd.Series, low: pd.Series, lookback: int = 5) -> Tuple[pd.Series, pd.Series]:
    """
    Detect higher highs (bullish) and lower lows (bearish) sequences.
    Returns (hh_flag, ll_flag) where 1 = pattern detected.
    """
    hh = pd.Series(0, index=high.index)
    ll = pd.Series(0, index=low.index)

    for i in range(lookback, len(high)):
        window_high = high.iloc[i-lookback:i+1].values
        window_low = low.iloc[i-lookback:i+1].values

        # Higher highs: each high > previous high
        hh_seq = all(window_high[j] > window_high[j-1] for j in range(1, len(window_high)))
        hh.iloc[i] = 1 if hh_seq else 0

        # Lower lows: each low < previous low
        ll_seq = all(window_low[j] < window_low[j-1] for j in range(1, len(window_low)))
        ll.iloc[i] = 1 if ll_seq else 0

    return hh, ll


def detect_ema_crossover(ema_short: pd.Series, ema_long: pd.Series) -> pd.Series:
    """
    Detect EMA crossovers.
    Returns: 1 = golden cross, -1 = death cross, 0 = no cross.
    """
    cross = pd.Series(0, index=ema_short.index)
    prev_short = ema_short.shift(1)
    prev_long = ema_long.shift(1)

    # Golden cross: short crosses above long
    golden = (prev_short <= prev_long) & (ema_short > ema_long)
    # Death cross: short crosses below long
    death = (prev_short >= prev_long) & (ema_short < ema_long)

    cross[golden] = 1
    cross[death] = -1
    return cross


def detect_ema_retest(
    close: pd.Series,
    ema: pd.Series,
    cross_signal: pd.Series,
    lookback: int = 5,
) -> pd.Series:
    """
    Detect price retest of EMA after a crossover (bounce flag).
    Returns 1 when price touches EMA after a recent cross.
    """
    retest = pd.Series(0, index=close.index)
    threshold = 0.002  # 0.2% distance = "touching" EMA

    for i in range(lookback, len(close)):
        # Check if there was a crossover in recent lookback
        recent_cross = cross_signal.iloc[i-lookback:i].abs().sum() > 0
        if not recent_cross:
            continue

        price = close.iloc[i]
        ema_val = ema.iloc[i]
        if ema_val == 0:
            continue

        dist = abs(price - ema_val) / ema_val
        if dist <= threshold:
            retest.iloc[i] = 1

    return retest


def detect_three_candle_momentum(close: pd.Series, direction: int = 1) -> pd.Series:
    """
    Detect 3-candle momentum confirmation.
    direction=1 for bullish (3 consecutive closes up), -1 for bearish.
    """
    flag = pd.Series(0, index=close.index)
    for i in range(3, len(close)):
        c = close.iloc[i-3:i+1].values
        if direction == 1:
            if c[1] > c[0] and c[2] > c[1] and c[3] > c[2]:
                flag.iloc[i] = 1
        else:
            if c[1] < c[0] and c[2] < c[1] and c[3] < c[2]:
                flag.iloc[i] = 1
    return flag


def engineer_features(
    df: pd.DataFrame,
    pcr: float = 1.0,
    max_pain: float = 0.0,
    iv_rank: float = 50.0,
) -> pd.DataFrame:
    """
    Main feature engineering pipeline.

    Args:
        df: OHLCV DataFrame with columns [time, open, high, low, close, volume]
        pcr: Put-Call Ratio from options chain
        max_pain: Max Pain strike price
        iv_rank: IV Rank (0-100)

    Returns:
        DataFrame with all features. NaN rows from indicator warmup are dropped.
    """
    if df.empty or len(df) < EMA_TREND + 10:
        logger.warning(f"Insufficient data for features: {len(df)} rows, need {EMA_TREND + 10}")
        return pd.DataFrame()

    df = df.copy()
    df = df.sort_values("time").reset_index(drop=True)

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    open_ = df["open"].astype(float)
    volume = df["volume"].astype(float)

    # ── EMA Features ──────────────────────────────────────────────────────────
    df["ema_9"] = compute_ema(close, EMA_SHORT)
    df["ema_21"] = compute_ema(close, EMA_MID)
    df["ema_50"] = compute_ema(close, EMA_LONG)
    df["ema_200"] = compute_ema(close, EMA_TREND)

    # EMA ratios (price / EMA)
    df["price_vs_ema200"] = np.where(close > df["ema_200"], 1, -1)
    df["price_vs_ema21"] = (close - df["ema_21"]) / df["ema_21"]
    df["ema9_vs_ema21"] = (df["ema_9"] - df["ema_21"]) / df["ema_21"]
    df["ema21_vs_ema50"] = (df["ema_21"] - df["ema_50"]) / df["ema_50"]

    # ── EMA Crossover Signals ─────────────────────────────────────────────────
    df["ema_cross_9_21"] = detect_ema_crossover(df["ema_9"], df["ema_21"])
    df["ema_cross_21_50"] = detect_ema_crossover(df["ema_21"], df["ema_50"])

    # ── Candle Structure ──────────────────────────────────────────────────────
    candle_range = high - low
    body = (close - open_).abs()
    df["candle_body_ratio"] = body / candle_range.replace(0, np.nan)
    df["upper_wick"] = (high - pd.concat([close, open_], axis=1).max(axis=1)) / candle_range.replace(0, np.nan)
    df["lower_wick"] = (pd.concat([close, open_], axis=1).min(axis=1) - low) / candle_range.replace(0, np.nan)
    df["candle_direction"] = np.sign(close - open_)

    # Gap (from previous close to current open)
    prev_close = close.shift(1)
    df["gap_pct"] = (open_ - prev_close) / prev_close.replace(0, np.nan)
    df["gap_up"] = (df["gap_pct"] > 0.002).astype(int)
    df["gap_down"] = (df["gap_pct"] < -0.002).astype(int)

    # ── Momentum Indicators ───────────────────────────────────────────────────
    df["rsi_14"] = compute_rsi(close, RSI_PERIOD)
    df["rsi_overbought"] = (df["rsi_14"] > 70).astype(int)
    df["rsi_oversold"] = (df["rsi_14"] < 30).astype(int)

    macd_line, signal_line, histogram = compute_macd(close)
    df["macd_line"] = macd_line
    df["macd_signal"] = signal_line
    df["macd_hist"] = histogram
    df["macd_bullish"] = np.where(histogram > 0, 1, -1)
    df["macd_cross"] = detect_ema_crossover(macd_line, signal_line)

    stoch_k, stoch_d = compute_stochastic(high, low, close)
    df["stoch_k"] = stoch_k
    df["stoch_d"] = stoch_d
    df["stoch_cross"] = detect_ema_crossover(stoch_k, stoch_d)

    df["roc_10"] = close.pct_change(ROC_PERIOD) * 100

    # ── Volatility Indicators ─────────────────────────────────────────────────
    df["atr_14"] = compute_atr(high, low, close, ATR_PERIOD)
    df["atr_pct"] = df["atr_14"] / close  # ATR as % of price

    bb_upper, bb_lower, bb_pct_b, bb_bw = compute_bollinger(close)
    df["bb_upper"] = bb_upper
    df["bb_lower"] = bb_lower
    df["bb_pct_b"] = bb_pct_b
    df["bb_bandwidth"] = bb_bw

    # Historical Volatility (20-period)
    log_returns = np.log(close / close.shift(1))
    df["hist_vol"] = log_returns.rolling(HV_PERIOD).std() * np.sqrt(252 * 26) * 100  # Annualized %

    # ── Volume Features ───────────────────────────────────────────────────────
    vol_avg = volume.rolling(VOL_AVG_PERIOD).mean()
    df["vol_ratio"] = volume / vol_avg.replace(0, np.nan)
    df["vol_spike"] = (df["vol_ratio"] > 2.0).astype(int)
    df["obv"] = compute_obv(close, volume)
    df["obv_ema"] = compute_ema(df["obv"], 21)
    df["obv_trend"] = np.sign(df["obv"] - df["obv_ema"])

    # ── Options-Derived Features ──────────────────────────────────────────────
    df["pcr"] = pcr
    df["pcr_bullish"] = (pcr < 0.8).astype(int)
    df["pcr_bearish"] = (pcr > 1.2).astype(int)

    if max_pain > 0:
        df["above_max_pain"] = (close > max_pain).astype(int)
        df["max_pain_dist_pct"] = (close - max_pain) / max_pain
    else:
        df["above_max_pain"] = 0
        df["max_pain_dist_pct"] = 0

    df["iv_rank"] = iv_rank
    df["high_iv_rank"] = (iv_rank > 70).astype(int)
    df["low_iv_rank"] = (iv_rank < 30).astype(int)

    # ── Time Features ─────────────────────────────────────────────────────────
    if df["time"].dt.tz is not None:
        local_time = df["time"].dt.tz_convert("Asia/Kolkata")
    else:
        local_time = df["time"]

    hour = local_time.dt.hour + local_time.dt.minute / 60
    hour_sin, hour_cos = encode_time_cyclical(hour, 24)
    df["hour_sin"] = hour_sin
    df["hour_cos"] = hour_cos
    df["day_of_week"] = local_time.dt.dayofweek

    # Session flags
    session_start_mins = 9 * 60 + 15  # 9:15 AM
    session_end_mins = 15 * 60 + 30   # 3:30 PM
    mins_from_midnight = local_time.dt.hour * 60 + local_time.dt.minute

    df["first_30min"] = ((mins_from_midnight >= session_start_mins) &
                         (mins_from_midnight < session_start_mins + 30)).astype(int)
    df["last_30min"] = ((mins_from_midnight >= session_end_mins - 30) &
                        (mins_from_midnight <= session_end_mins)).astype(int)

    # Minutes to weekly expiry (Thursday 3:30 PM)
    days_to_thursday = (3 - local_time.dt.dayofweek) % 7  # 3 = Thursday
    mins_to_expiry = days_to_thursday * 375 + (session_end_mins - mins_from_midnight)
    df["mins_to_expiry"] = mins_to_expiry.clip(lower=0)

    # ── Mirror Trade Pattern Features ─────────────────────────────────────────
    # EMA 9/21 golden/death cross
    df["ema_golden_cross"] = (df["ema_cross_9_21"] == 1).astype(int)
    df["ema_death_cross"] = (df["ema_cross_9_21"] == -1).astype(int)

    # Price retest of EMA 21 after cross
    df["ema21_retest_bull"] = detect_ema_retest(close, df["ema_21"], df["ema_cross_9_21"])
    df["ema21_retest_bear"] = detect_ema_retest(close, df["ema_21"], df["ema_cross_9_21"])

    # 3-candle momentum confirmation
    df["momentum_bull_3c"] = detect_three_candle_momentum(close, direction=1)
    df["momentum_bear_3c"] = detect_three_candle_momentum(close, direction=-1)

    # Higher Highs / Lower Lows (last 5 candles)
    df["higher_highs"], df["lower_lows"] = compute_higher_highs_lower_lows(high, low, lookback=5)

    # Support/Resistance proximity
    df["sr_proximity"] = detect_key_levels(close, lookback=50)
    df["near_sr"] = (df["sr_proximity"] <= SUPPORT_RESISTANCE_THRESHOLD).astype(int)

    # ── Composite Pattern Score ───────────────────────────────────────────────
    # Bullish confluence: EMA cross up + RSI not overbought + volume spike + momentum
    df["bull_score"] = (
        (df["ema9_vs_ema21"] > 0).astype(int) +
        df["ema_golden_cross"] +
        df["ema21_retest_bull"] +
        df["momentum_bull_3c"] +
        df["higher_highs"] +
        df["obv_trend"].clip(lower=0) +
        df["pcr_bullish"] +
        (df["rsi_14"].between(40, 65)).astype(int)
    )

    df["bear_score"] = (
        (df["ema9_vs_ema21"] < 0).astype(int) +
        df["ema_death_cross"] +
        df["ema21_retest_bear"] +
        df["momentum_bear_3c"] +
        df["lower_lows"] +
        (-df["obv_trend"]).clip(lower=0) +
        df["pcr_bearish"] +
        (df["rsi_14"].between(35, 60)).astype(int)
    )

    # ── Fill and Clean ────────────────────────────────────────────────────────
    feature_cols = [c for c in df.columns if c not in ["time", "open", "high", "low", "close", "volume", "oi",
                                                         "ema_9", "ema_21", "ema_50", "ema_200",
                                                         "bb_upper", "bb_lower", "obv", "obv_ema"]]
    df[feature_cols] = df[feature_cols].ffill().fillna(0)

    # Drop warmup rows (EMA 200 needs 200+ candles)
    df = df.dropna(subset=["ema_200"]).reset_index(drop=True)

    return df


def get_feature_columns() -> list:
    """Return list of feature column names used for ML training."""
    return [
        # EMA-based
        "price_vs_ema200", "price_vs_ema21", "ema9_vs_ema21", "ema21_vs_ema50",
        "ema_cross_9_21", "ema_cross_21_50",
        # Candle structure
        "candle_body_ratio", "upper_wick", "lower_wick", "candle_direction",
        "gap_pct", "gap_up", "gap_down",
        # Momentum
        "rsi_14", "rsi_overbought", "rsi_oversold",
        "macd_line", "macd_signal", "macd_hist", "macd_bullish", "macd_cross",
        "stoch_k", "stoch_d", "stoch_cross", "roc_10",
        # Volatility
        "atr_pct", "bb_pct_b", "bb_bandwidth", "hist_vol",
        # Volume
        "vol_ratio", "vol_spike", "obv_trend",
        # Options
        "pcr", "pcr_bullish", "pcr_bearish",
        "above_max_pain", "max_pain_dist_pct",
        "iv_rank", "high_iv_rank", "low_iv_rank",
        # Time
        "hour_sin", "hour_cos", "day_of_week",
        "first_30min", "last_30min", "mins_to_expiry",
        # Mirror Trade Patterns
        "ema_golden_cross", "ema_death_cross",
        "ema21_retest_bull", "ema21_retest_bear",
        "momentum_bull_3c", "momentum_bear_3c",
        "higher_highs", "lower_lows",
        "near_sr",
        # Composite
        "bull_score", "bear_score",
    ]


def get_latest_features(df: pd.DataFrame, pcr: float = 1.0, max_pain: float = 0.0, iv_rank: float = 50.0) -> Optional[Dict[str, Any]]:
    """
    Get feature dict for the most recent complete candle.
    Used for real-time inference.
    """
    features_df = engineer_features(df, pcr=pcr, max_pain=max_pain, iv_rank=iv_rank)
    if features_df.empty:
        return None

    feature_cols = get_feature_columns()
    last_row = features_df.iloc[-1]
    return {col: float(last_row[col]) for col in feature_cols if col in last_row.index}
