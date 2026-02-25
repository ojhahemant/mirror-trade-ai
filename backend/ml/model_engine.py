"""
ML Model Engine: XGBoost classifier for Bank Nifty signal generation.
- Walk-forward validation
- SMOTE class balancing
- Optuna hyperparameter tuning
- Champion/Challenger model management
"""
import os
import json
import asyncio
import uuid
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
import numpy as np
import pandas as pd
import joblib
import pytz
from loguru import logger

from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import classification_report, accuracy_score
from sklearn.preprocessing import StandardScaler
import xgboost as xgb

try:
    from imblearn.over_sampling import SMOTE
    SMOTE_AVAILABLE = True
except ImportError:
    SMOTE_AVAILABLE = False
    logger.warning("imbalanced-learn not available — skipping SMOTE")

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False
    logger.warning("optuna not available — using default hyperparameters")

from api.config import settings
from ml.features import engineer_features, get_feature_columns, get_latest_features

IST = pytz.timezone(settings.ist_timezone)

# ── Paths ─────────────────────────────────────────────────────────────────────
MODEL_DIR = settings.model_dir
os.makedirs(MODEL_DIR, exist_ok=True)
MODEL_PATH = os.path.join(MODEL_DIR, "banknifty_xgb_latest.joblib")
SCALER_PATH = os.path.join(MODEL_DIR, "banknifty_scaler_latest.joblib")
METADATA_PATH = os.path.join(MODEL_DIR, "model_metadata.json")

# ── Configuration ─────────────────────────────────────────────────────────────
PREDICTION_HORIZON = 2      # candles (30 min for 15min TF)
MIN_CONFIDENCE = settings.min_confidence
N_FOLDS = 12
OPTUNA_TRIALS = 50
MIN_ACCURACY_IMPROVEMENT = 0.02  # 2% improvement required for champion swap

ATR_SL_MULTIPLIER = Decimal("1.5")
ATR_T1_MULTIPLIER = Decimal("2.0")
ATR_T2_MULTIPLIER = Decimal("3.5")
MIN_RISK_REWARD = Decimal("1.5")


def create_target(df: pd.DataFrame, horizon: int = PREDICTION_HORIZON) -> pd.Series:
    """
    Create 3-class target: BUY(1), SELL(-1), NEUTRAL(0).
    Uses future return over `horizon` candles.
    Threshold: ATR-normalized return > 0.5 → signal, else neutral.
    """
    future_close = df["close"].shift(-horizon)
    current_close = df["close"]
    atr = df["atr_14"] if "atr_14" in df.columns else (df["high"] - df["low"])

    future_return = (future_close - current_close) / current_close
    atr_pct = atr / current_close

    # Use 0.5x ATR as threshold for significant move
    threshold = atr_pct * 0.5

    target = pd.Series(0, index=df.index)
    target[future_return > threshold] = 1   # BUY
    target[future_return < -threshold] = -1  # SELL

    return target


def get_default_params() -> Dict[str, Any]:
    """Default XGBoost hyperparameters."""
    return {
        "n_estimators": 300,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 5,
        "gamma": 0.1,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "use_label_encoder": False,
        "eval_metric": "mlogloss",
        "objective": "multi:softprob",
        "num_class": 3,
        "random_state": 42,
        "n_jobs": -1,
        "tree_method": "hist",
    }


def tune_hyperparams(X: np.ndarray, y: np.ndarray, n_trials: int = OPTUNA_TRIALS) -> Dict[str, Any]:
    """Optuna hyperparameter tuning with time-series CV."""
    if not OPTUNA_AVAILABLE:
        return get_default_params()

    def objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 100, 500),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            "gamma": trial.suggest_float("gamma", 0, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 0, 1.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.5, 5.0),
            "use_label_encoder": False,
            "eval_metric": "mlogloss",
            "objective": "multi:softprob",
            "num_class": 3,
            "random_state": 42,
            "n_jobs": -1,
            "tree_method": "hist",
        }

        tscv = TimeSeriesSplit(n_splits=5)
        scores = []
        for train_idx, val_idx in tscv.split(X):
            X_tr, X_val = X[train_idx], X[val_idx]
            y_tr, y_val = y[train_idx], y[val_idx]

            # Map labels for XGBoost: -1, 0, 1 → 0, 1, 2
            y_tr_xgb = y_tr + 1
            y_val_xgb = y_val + 1

            model = xgb.XGBClassifier(**params)
            model.fit(X_tr, y_tr_xgb, eval_set=[(X_val, y_val_xgb)], verbose=False)
            pred = model.predict(X_val) - 1
            scores.append(accuracy_score(y_val, pred))

        return np.mean(scores)

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    best = study.best_params
    best.update({
        "use_label_encoder": False,
        "eval_metric": "mlogloss",
        "objective": "multi:softprob",
        "num_class": 3,
        "random_state": 42,
        "n_jobs": -1,
        "tree_method": "hist",
    })
    logger.info(f"Optuna best params (val accuracy={study.best_value:.4f}): {best}")
    return best


def walk_forward_validate(
    X: np.ndarray,
    y: np.ndarray,
    params: Dict,
    n_splits: int = N_FOLDS,
) -> Tuple[float, float]:
    """
    Walk-forward validation with TimeSeriesSplit.
    Returns (train_accuracy, val_accuracy).
    """
    tscv = TimeSeriesSplit(n_splits=n_splits)
    train_scores = []
    val_scores = []

    for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
        X_tr, X_val = X[train_idx], X[val_idx]
        y_tr, y_val = y[train_idx], y[val_idx]

        # XGBoost labels must be 0-indexed
        y_tr_xgb = y_tr + 1
        y_val_xgb = y_val + 1

        model = xgb.XGBClassifier(**params)
        model.fit(X_tr, y_tr_xgb, verbose=False)

        train_pred = model.predict(X_tr) - 1
        val_pred = model.predict(X_val) - 1

        train_scores.append(accuracy_score(y_tr, train_pred))
        val_scores.append(accuracy_score(y_val, val_pred))
        logger.debug(f"Fold {fold+1}: train={train_scores[-1]:.4f} val={val_scores[-1]:.4f}")

    return float(np.mean(train_scores)), float(np.mean(val_scores))


def train_model(df: pd.DataFrame, pcr: float = 1.0, max_pain: float = 0.0, iv_rank: float = 50.0) -> Dict[str, Any]:
    """
    Full training pipeline:
    1. Feature engineering
    2. Target creation
    3. SMOTE balancing
    4. Optuna tuning
    5. Walk-forward validation
    6. Final model training
    7. Save model

    Returns training metrics dict.
    """
    logger.info(f"Starting model training on {len(df)} candles")

    # Feature engineering
    features_df = engineer_features(df, pcr=pcr, max_pain=max_pain, iv_rank=iv_rank)
    if features_df.empty or len(features_df) < 500:
        raise ValueError(f"Insufficient data for training: {len(features_df)} rows")

    feature_cols = get_feature_columns()
    feature_cols = [c for c in feature_cols if c in features_df.columns]

    # Create target (drop last `horizon` rows with no future data)
    features_df["target"] = create_target(features_df)
    features_df = features_df.dropna(subset=["target"]).iloc[:-PREDICTION_HORIZON]

    X = features_df[feature_cols].values.astype(np.float32)
    y = features_df["target"].values.astype(int)

    logger.info(f"Class distribution: BUY={np.sum(y==1)}, SELL={np.sum(y==-1)}, NEUTRAL={np.sum(y==0)}")

    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # SMOTE oversampling
    if SMOTE_AVAILABLE:
        try:
            y_smote = y + 1  # Map to 0,1,2
            smote = SMOTE(random_state=42, k_neighbors=5)
            X_balanced, y_balanced = smote.fit_resample(X_scaled, y_smote)
            y_balanced = y_balanced - 1  # Map back
            logger.info(f"SMOTE: {len(X)} → {len(X_balanced)} samples")
        except Exception as e:
            logger.warning(f"SMOTE failed ({e}), using original data")
            X_balanced, y_balanced = X_scaled, y
    else:
        X_balanced, y_balanced = X_scaled, y

    # Hyperparameter tuning
    logger.info("Running Optuna hyperparameter tuning...")
    params = tune_hyperparams(X_balanced, y_balanced, n_trials=OPTUNA_TRIALS)

    # Walk-forward validation
    logger.info("Running walk-forward validation...")
    train_acc, val_acc = walk_forward_validate(X_balanced, y_balanced, params, n_splits=N_FOLDS)
    logger.info(f"Walk-forward: train={train_acc:.4f} val={val_acc:.4f}")

    # Train final model on all data
    final_model = xgb.XGBClassifier(**params)
    final_model.fit(X_balanced, y_balanced + 1, verbose=False)

    # Feature importance
    importance = dict(zip(feature_cols, final_model.feature_importances_))
    top_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]
    logger.info(f"Top features: {top_features}")

    # Save model and scaler
    version = f"v{datetime.now(IST).strftime('%Y%m%d_%H%M%S')}"
    model_path = os.path.join(MODEL_DIR, f"banknifty_xgb_{version}.joblib")
    scaler_path = os.path.join(MODEL_DIR, f"banknifty_scaler_{version}.joblib")

    joblib.dump(final_model, model_path)
    joblib.dump(scaler, scaler_path)
    joblib.dump(final_model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)

    metrics = {
        "version": version,
        "filename": model_path,
        "train_accuracy": round(train_acc, 4),
        "val_accuracy": round(val_acc, 4),
        "feature_count": len(feature_cols),
        "training_samples": len(X_balanced),
        "class_distribution": {
            "buy": int(np.sum(y == 1)),
            "sell": int(np.sum(y == -1)),
            "neutral": int(np.sum(y == 0)),
        },
        "hyperparams": params,
        "top_features": [{"feature": f, "importance": float(i)} for f, i in top_features],
        "trained_at": datetime.now(IST).isoformat(),
    }

    # Save metadata
    with open(METADATA_PATH, "w") as f:
        json.dump(metrics, f, indent=2)

    logger.info(f"Model saved: {model_path} (val_accuracy={val_acc:.4f})")
    return metrics


class ModelInference:
    """Real-time inference engine with model loading and caching."""

    def __init__(self):
        self._model = None
        self._scaler = None
        self._metadata = {}
        self._load_model()

    def _load_model(self):
        """Load the latest model from disk."""
        if os.path.exists(MODEL_PATH) and os.path.exists(SCALER_PATH):
            try:
                self._model = joblib.load(MODEL_PATH)
                self._scaler = joblib.load(SCALER_PATH)
                if os.path.exists(METADATA_PATH):
                    with open(METADATA_PATH) as f:
                        self._metadata = json.load(f)
                logger.info(f"Model loaded: {self._metadata.get('version', 'unknown')}")
            except Exception as e:
                logger.error(f"Model load failed: {e}")
                self._model = None
        else:
            logger.warning("No trained model found — signals will be unavailable until training completes")

    def reload(self):
        """Reload model from disk (after retraining)."""
        self._load_model()

    @property
    def is_ready(self) -> bool:
        return self._model is not None and self._scaler is not None

    @property
    def version(self) -> str:
        return self._metadata.get("version", "unknown")

    def predict(
        self,
        df: pd.DataFrame,
        pcr: float = 1.0,
        max_pain: float = 0.0,
        iv_rank: float = 50.0,
        min_confidence: float = MIN_CONFIDENCE,
    ) -> Optional[Dict[str, Any]]:
        """
        Run inference on latest candle data.
        Returns signal dict or None if below confidence threshold.
        """
        if not self.is_ready:
            logger.warning("Model not ready for inference")
            return None

        features = get_latest_features(df, pcr=pcr, max_pain=max_pain, iv_rank=iv_rank)
        if features is None:
            return None

        feature_cols = get_feature_columns()
        X = np.array([[features.get(col, 0) for col in feature_cols]], dtype=np.float32)

        try:
            X_scaled = self._scaler.transform(X)
            # XGBoost returns probabilities for classes [0,1,2] mapped from [-1,0,1]
            proba = self._model.predict_proba(X_scaled)[0]
            # proba[0]=SELL(-1), proba[1]=NEUTRAL(0), proba[2]=BUY(1)
            pred_class = int(np.argmax(proba)) - 1  # Map back to -1,0,1

            confidence = float(np.max(proba)) * 100

            if confidence < min_confidence:
                logger.debug(f"Signal below threshold: {confidence:.1f}% < {min_confidence}%")
                return None

            direction_map = {1: "BUY", -1: "SELL", 0: "NEUTRAL"}
            direction = direction_map[pred_class]

            if direction == "NEUTRAL":
                return None

            # Get ATR for stop/target calculation
            features_df = engineer_features(df, pcr=pcr, max_pain=max_pain, iv_rank=iv_rank)
            if features_df.empty:
                return None

            last = features_df.iloc[-1]
            entry_price = Decimal(str(df["close"].iloc[-1]))
            atr = Decimal(str(last.get("atr_14", float(entry_price * Decimal("0.003")))))

            # Calculate levels
            sl_distance = atr * ATR_SL_MULTIPLIER
            t1_distance = atr * ATR_T1_MULTIPLIER
            t2_distance = atr * ATR_T2_MULTIPLIER

            if direction == "BUY":
                stop_loss = entry_price - sl_distance
                target_1 = entry_price + t1_distance
                target_2 = entry_price + t2_distance
            else:  # SELL
                stop_loss = entry_price + sl_distance
                target_1 = entry_price - t1_distance
                target_2 = entry_price - t2_distance

            risk_reward = t1_distance / sl_distance if sl_distance > 0 else Decimal("0")

            # Reject signals with poor R:R
            if risk_reward < MIN_RISK_REWARD:
                logger.debug(f"Signal rejected: R:R {risk_reward:.2f} < {MIN_RISK_REWARD}")
                return None

            # Pattern detection (from features)
            patterns = []
            if last.get("ema_golden_cross", 0) == 1:
                patterns.append("EMA Golden Cross")
            if last.get("ema_death_cross", 0) == 1:
                patterns.append("EMA Death Cross")
            if last.get("ema21_retest_bull", 0) == 1:
                patterns.append("EMA 21 Retest")
            if last.get("momentum_bull_3c", 0) == 1:
                patterns.append("3-Candle Bullish")
            if last.get("momentum_bear_3c", 0) == 1:
                patterns.append("3-Candle Bearish")
            if last.get("higher_highs", 0) == 1:
                patterns.append("Higher Highs")
            if last.get("lower_lows", 0) == 1:
                patterns.append("Lower Lows")
            if last.get("near_sr", 0) == 1:
                patterns.append("Near S/R Level")

            pattern_str = " + ".join(patterns) if patterns else "Momentum Signal"

            return {
                "direction": direction,
                "confidence": round(confidence, 2),
                "entry_price": entry_price,
                "entry_low": entry_price - (atr * Decimal("0.3")),
                "entry_high": entry_price + (atr * Decimal("0.3")),
                "stop_loss": stop_loss,
                "target_1": target_1,
                "target_2": target_2,
                "risk_reward": float(risk_reward),
                "atr_value": atr,
                "pattern_detected": pattern_str,
                "model_version": self.version,
                "features": features,
                "probabilities": {
                    "buy": float(proba[2]),
                    "neutral": float(proba[1]),
                    "sell": float(proba[0]),
                },
            }

        except Exception as e:
            logger.error(f"Inference error: {e}")
            return None


# Singletons
model_inference = ModelInference()


def champion_challenger_check(new_metrics: Dict, current_metrics: Dict) -> bool:
    """
    Returns True if new model should replace champion.
    Requires >2% improvement in val_accuracy.
    """
    new_acc = new_metrics.get("val_accuracy", 0)
    curr_acc = current_metrics.get("val_accuracy", 0)
    return new_acc > curr_acc + MIN_ACCURACY_IMPROVEMENT


# CLI entry point
if __name__ == "__main__":
    import argparse
    import asyncio
    from data.data_pipeline import get_latest_candles

    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=["train", "predict"], default="train")
    args = parser.parse_args()

    if args.action == "train":
        df = asyncio.run(get_latest_candles("15min", limit=10000))
        if df.empty:
            print("No data available. Run backfill first.")
        else:
            metrics = train_model(df)
            print(f"Training complete: {metrics}")
