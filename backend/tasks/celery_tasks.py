"""
Celery tasks: scheduled data refresh, signal generation, model retraining.
"""
import asyncio
from datetime import datetime
from celery import Celery
from celery.schedules import crontab
from loguru import logger
import pytz

from api.config import settings

IST = pytz.timezone(settings.ist_timezone)

# ── Celery App ─────────────────────────────────────────────────────────────────
celery_app = Celery(
    "mirrortrade",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=False,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "tasks.celery_tasks.fetch_live_data": {"queue": "data"},
        "tasks.celery_tasks.generate_signal": {"queue": "signals"},
        "tasks.celery_tasks.retrain_model": {"queue": "default"},
        "tasks.celery_tasks.refresh_options": {"queue": "data"},
    },
)

# ── Beat Schedule (Cron Jobs) ─────────────────────────────────────────────────
celery_app.conf.beat_schedule = {
    # Every minute during market hours: fetch live data
    "fetch-live-data-every-minute": {
        "task": "tasks.celery_tasks.fetch_live_data",
        "schedule": crontab(minute="*"),
    },
    # Every 15 minutes: generate signal on candle close
    "generate-signal-every-15min": {
        "task": "tasks.celery_tasks.generate_signal",
        "schedule": crontab(minute="0,15,30,45"),
    },
    # Every 5 minutes: refresh options chain
    "refresh-options-every-5min": {
        "task": "tasks.celery_tasks.refresh_options",
        "schedule": crontab(minute="*/5"),
    },
    # Every 15 minutes: refresh candle data
    "refresh-candles-every-15min": {
        "task": "tasks.celery_tasks.refresh_candles",
        "schedule": crontab(minute="2,17,32,47"),
    },
    # Weekly model retraining: Sunday at 6 AM IST
    "retrain-model-weekly": {
        "task": "tasks.celery_tasks.retrain_model",
        "schedule": crontab(hour=6, minute=0, day_of_week=0),  # Sunday 6 AM
    },
    # Daily: check and expire stale signals
    "expire-stale-signals": {
        "task": "tasks.celery_tasks.expire_stale_signals",
        "schedule": crontab(minute="*/15"),
    },
}


def run_async(coro):
    """Helper to run async functions from sync Celery tasks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Tasks ──────────────────────────────────────────────────────────────────────

@celery_app.task(name="tasks.celery_tasks.fetch_live_data", bind=True, max_retries=3)
def fetch_live_data(self):
    """Fetch live price and update Redis cache."""
    try:
        from data.data_pipeline import get_live_price
        from data.kite_client import kite_client
        quote = kite_client.get_live_quote()
        if quote:
            from data.data_pipeline import update_live_price
            # Construct a mock tick for the updater
            tick = {
                "last_price": float(quote["ltp"]),
                "ohlc": {
                    "open": float(quote["open"]),
                    "high": float(quote["high"]),
                    "low": float(quote["low"]),
                    "close": float(quote["prev_close"]),
                },
                "volume": 0,
            }
            update_live_price(tick)
        return {"status": "ok", "ltp": float(quote["ltp"]) if quote else None}
    except Exception as e:
        logger.error(f"fetch_live_data failed: {e}")
        raise self.retry(exc=e, countdown=10)


@celery_app.task(name="tasks.celery_tasks.generate_signal", bind=True, max_retries=2)
def generate_signal(self):
    """Run signal generation on 15-min candle close."""
    try:
        # Only run during market hours
        now = datetime.now(IST)
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

        if not (market_open <= now <= market_close) or now.weekday() >= 5:
            logger.debug("Market closed — skipping signal generation")
            return {"status": "skipped", "reason": "market_closed"}

        from signals.signal_engine import signal_engine
        signal = run_async(signal_engine.generate_signal())

        if signal:
            logger.info(f"Signal generated: {signal['direction']} {signal['confidence']:.1f}%")
            return {"status": "signal_generated", "direction": signal["direction"]}
        return {"status": "no_signal"}
    except Exception as e:
        logger.error(f"generate_signal failed: {e}")
        raise self.retry(exc=e, countdown=30)


@celery_app.task(name="tasks.celery_tasks.refresh_options", bind=True, max_retries=3)
def refresh_options(self):
    """Refresh options chain data and compute PCR/Max Pain."""
    try:
        from data.options_fetcher import options_processor
        from data.data_pipeline import get_live_price
        from decimal import Decimal

        live = get_live_price()
        underlying = Decimal(str(live["ltp"])) if live else None
        result = options_processor.process_and_cache(underlying)

        if result:
            logger.debug(f"Options refreshed: PCR={result.get('pcr', 'N/A'):.2f}")
            return {"status": "ok", "pcr": result.get("pcr")}
        return {"status": "no_data"}
    except Exception as e:
        logger.warning(f"refresh_options failed: {e}")
        raise self.retry(exc=e, countdown=30)


@celery_app.task(name="tasks.celery_tasks.refresh_candles", bind=True, max_retries=3)
def refresh_candles(self):
    """Fetch latest 15-min candles and store in DB."""
    try:
        from data.data_pipeline import fetch_and_refresh_candles
        inserted = run_async(fetch_and_refresh_candles("15min"))
        logger.debug(f"Candle refresh: {inserted} rows")
        return {"status": "ok", "inserted": inserted}
    except Exception as e:
        logger.error(f"refresh_candles failed: {e}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(name="tasks.celery_tasks.retrain_model", bind=True, max_retries=1)
def retrain_model(self):
    """
    Weekly model retraining with Champion/Challenger evaluation.
    Only promotes new model if it beats current by >2% val_accuracy.
    """
    logger.info("Starting weekly model retraining...")
    try:
        from data.data_pipeline import get_latest_candles
        from ml.model_engine import train_model, champion_challenger_check, model_inference
        import json, os
        from api.config import settings

        # Load current champion metrics
        metadata_path = os.path.join(settings.model_dir, "model_metadata.json")
        current_metrics = {}
        if os.path.exists(metadata_path):
            with open(metadata_path) as f:
                current_metrics = json.load(f)

        # Fetch training data
        df = run_async(get_latest_candles("15min", limit=50000))
        if df.empty:
            logger.warning("No data for retraining")
            return {"status": "skipped", "reason": "no_data"}

        # Train new model
        new_metrics = train_model(df)

        # Champion/Challenger check
        if champion_challenger_check(new_metrics, current_metrics):
            logger.info(
                f"New champion! {new_metrics['val_accuracy']:.4f} > "
                f"{current_metrics.get('val_accuracy', 0):.4f}"
            )
            model_inference.reload()

            # Save to DB
            run_async(_save_model_version(new_metrics, is_champion=True))
            return {"status": "champion_promoted", "metrics": new_metrics}
        else:
            logger.info(
                f"Challenger rejected: {new_metrics['val_accuracy']:.4f} <= "
                f"{current_metrics.get('val_accuracy', 0):.4f} + 2%"
            )
            run_async(_save_model_version(new_metrics, is_champion=False))
            return {"status": "challenger_rejected", "metrics": new_metrics}

    except Exception as e:
        logger.error(f"retrain_model failed: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=3600)


async def _save_model_version(metrics: dict, is_champion: bool):
    """Save model version metadata to DB."""
    from api.models.database import AsyncSessionLocal
    from sqlalchemy import text
    import uuid

    async with AsyncSessionLocal() as session:
        try:
            await session.execute(text("""
                INSERT INTO model_versions (
                    id, version, filename, is_champion,
                    train_accuracy, val_accuracy, trained_at,
                    feature_count, hyperparams, metrics
                ) VALUES (
                    :id, :version, :filename, :is_champion,
                    :train_acc, :val_acc, NOW(),
                    :features, :hyperparams, :metrics
                )
                ON CONFLICT (version) DO UPDATE SET
                    is_champion = EXCLUDED.is_champion
            """), {
                "id": uuid.uuid4(),
                "version": metrics.get("version", "unknown"),
                "filename": metrics.get("filename", ""),
                "is_champion": is_champion,
                "train_acc": metrics.get("train_accuracy", 0),
                "val_acc": metrics.get("val_accuracy", 0),
                "features": metrics.get("feature_count", 0),
                "hyperparams": json.dumps(metrics.get("hyperparams", {})),
                "metrics": json.dumps(metrics),
            })
            await session.commit()
        except Exception as e:
            logger.error(f"Model version save failed: {e}")


@celery_app.task(name="tasks.celery_tasks.expire_stale_signals")
def expire_stale_signals():
    """Auto-expire signals that have been open too long without hitting targets."""
    try:
        from data.data_pipeline import get_live_price
        from signals.signal_engine import signal_engine
        run_async(signal_engine._update_active_signal_pnl_check())
        return {"status": "ok"}
    except Exception as e:
        logger.warning(f"expire_stale_signals: {e}")
        return {"status": "error", "error": str(e)}


import json  # needed in retrain_model scope
