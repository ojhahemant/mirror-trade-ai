"""
Data pipeline: historical backfill, live ingestion, TimescaleDB storage.
"""
import asyncio
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
import pytz
import pandas as pd
import redis
import json
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.models.database import AsyncSessionLocal
from data.kite_client import kite_client, TokenExpiredError

IST = pytz.timezone(settings.ist_timezone)
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

REDIS_LIVE_KEY = "banknifty_live"
REDIS_PRICE_KEY = "banknifty:price"
REDIS_CANDLES_KEY_PREFIX = "banknifty:candles:"

TIMEFRAMES = ["1min", "5min", "15min", "1hr", "1day"]
BACKFILL_YEARS = 3


async def store_candles(df: pd.DataFrame, timeframe: str, session: AsyncSession) -> int:
    """
    Insert OHLCV candles into TimescaleDB with deduplication.
    Returns number of rows inserted.
    """
    if df.empty:
        return 0

    rows_inserted = 0
    upsert_sql = text("""
        INSERT INTO candles (time, symbol, timeframe, open, high, low, close, volume, oi)
        VALUES (:time, :symbol, :timeframe, :open, :high, :low, :close, :volume, :oi)
        ON CONFLICT (time, symbol, timeframe) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            oi = EXCLUDED.oi
    """)

    for _, row in df.iterrows():
        try:
            await session.execute(upsert_sql, {
                "time": row["time"],
                "symbol": "BANKNIFTY",
                "timeframe": timeframe,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row.get("volume", 0)),
                "oi": int(row.get("oi", 0)) if pd.notna(row.get("oi", 0)) else 0,
            })
            rows_inserted += 1
        except Exception as e:
            logger.warning(f"Row insert failed: {e}")

    return rows_inserted


async def backfill_historical(timeframe: str = "15min", years: int = BACKFILL_YEARS):
    """
    Backfill historical data in chunks to avoid API limits.
    Kite allows max 60 days per request for 15min data.
    """
    logger.info(f"Starting backfill: {timeframe} × {years} years")

    end_date = datetime.now(IST).date()
    start_date = end_date - timedelta(days=365 * years)

    # Kite API limits: max days per request by timeframe
    chunk_days = {
        "1min": 30,
        "5min": 100,
        "15min": 100,
        "1hr": 400,
        "1day": 2000,
    }
    chunk = chunk_days.get(timeframe, 100)

    total_inserted = 0
    current = start_date

    async with AsyncSessionLocal() as session:
        while current < end_date:
            chunk_end = min(current + timedelta(days=chunk), end_date)
            try:
                df = kite_client.get_historical_data(current, chunk_end, timeframe)
                if not df.empty:
                    inserted = await store_candles(df, timeframe, session)
                    total_inserted += inserted
                    logger.debug(f"Stored {inserted} candles: {current} → {chunk_end}")
                await session.commit()
            except TokenExpiredError:
                logger.error("Kite token expired during backfill — stopping")
                raise
            except Exception as e:
                logger.warning(f"Chunk {current}→{chunk_end} failed: {e}")
                await session.rollback()

            current = chunk_end + timedelta(days=1)
            await asyncio.sleep(0.3)  # Rate limit respect

    logger.info(f"Backfill complete: {total_inserted} candles ({timeframe})")
    return total_inserted


async def get_latest_candles(timeframe: str = "15min", limit: int = 100) -> pd.DataFrame:
    """
    Fetch latest N candles from DB, with Redis cache.
    """
    cache_key = f"{REDIS_CANDLES_KEY_PREFIX}{timeframe}"
    cached = redis_client.get(cache_key)
    if cached:
        data = json.loads(cached)
        df = pd.DataFrame(data)
        if not df.empty:
            df["time"] = pd.to_datetime(df["time"])
            return df.tail(limit)

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT time, open, high, low, close, volume, oi
            FROM candles
            WHERE symbol = 'BANKNIFTY' AND timeframe = :tf
            ORDER BY time DESC
            LIMIT :lim
        """), {"tf": timeframe, "lim": limit})
        rows = result.fetchall()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume", "oi"])
    df = df.sort_values("time").reset_index(drop=True)

    # Cache for 60 seconds
    redis_client.setex(cache_key, 60, df.to_json(orient="records", date_format="iso"))
    return df


def update_live_price(tick: Dict):
    """
    Handle tick from Kite Ticker.
    Publishes to Redis pub/sub channel.
    """
    try:
        ltp = tick.get("last_price", 0)
        prev_close = tick.get("ohlc", {}).get("close", ltp)
        change = ltp - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0

        price_data = {
            "symbol": "BANKNIFTY",
            "ltp": float(ltp),
            "change": float(change),
            "change_pct": float(change_pct),
            "high": float(tick.get("ohlc", {}).get("high", 0)),
            "low": float(tick.get("ohlc", {}).get("low", 0)),
            "open": float(tick.get("ohlc", {}).get("open", 0)),
            "prev_close": float(prev_close),
            "volume": int(tick.get("volume", 0)),
            "timestamp": datetime.now(IST).isoformat(),
        }

        # Store in Redis
        redis_client.setex(REDIS_PRICE_KEY, 30, json.dumps(price_data))
        # Publish to subscribers (WebSocket broadcaster)
        redis_client.publish(REDIS_LIVE_KEY, json.dumps(price_data))
    except Exception as e:
        logger.error(f"Live price update failed: {e}")


def get_live_price() -> Optional[Dict]:
    """Get latest cached live price."""
    cached = redis_client.get(REDIS_PRICE_KEY)
    if cached:
        return json.loads(cached)

    # Fallback: direct API call
    quote = kite_client.get_live_quote()
    if quote:
        data = {k: float(v) if isinstance(v, Decimal) else v for k, v in quote.items()}
        if isinstance(data.get("timestamp"), datetime):
            data["timestamp"] = data["timestamp"].isoformat()
        redis_client.setex(REDIS_PRICE_KEY, 30, json.dumps(data))
        return data
    return None


async def fetch_and_refresh_candles(timeframe: str = "15min"):
    """
    Fetch last few candles from Kite and store.
    Called every 15 minutes by Celery.
    """
    end = datetime.now(IST).date()
    start = end - timedelta(days=2)  # Buffer for gaps

    try:
        df = kite_client.get_historical_data(start, end, timeframe)
        if df.empty:
            logger.warning("No candles returned from data source")
            return 0

        async with AsyncSessionLocal() as session:
            inserted = await store_candles(df, timeframe, session)
            await session.commit()

        # Invalidate cache
        redis_client.delete(f"{REDIS_CANDLES_KEY_PREFIX}{timeframe}")
        logger.info(f"Refreshed {inserted} candles ({timeframe})")
        return inserted
    except Exception as e:
        logger.error(f"Candle refresh failed: {e}")
        return 0


# CLI entry point
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=["backfill", "refresh"], default="backfill")
    parser.add_argument("--timeframe", default="15min")
    args = parser.parse_args()

    if args.action == "backfill":
        for tf in TIMEFRAMES:
            asyncio.run(backfill_historical(tf))
    elif args.action == "refresh":
        asyncio.run(fetch_and_refresh_candles(args.timeframe))
