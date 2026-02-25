"""
Market data routes: candles, live price, options chain, PCR.
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from loguru import logger
import pytz

from api.config import settings
from data.data_pipeline import get_latest_candles, get_live_price
from data.options_fetcher import options_processor
from data.kite_client import kite_client

router = APIRouter(prefix="/api/market", tags=["market"])
IST = pytz.timezone(settings.ist_timezone)


@router.get("/candles")
async def get_candles(
    timeframe: str = Query(default="15min", enum=["1min", "5min", "15min", "1hr", "1day"]),
    limit: int = Query(default=100, ge=10, le=1000),
):
    """Fetch OHLCV candles for charting."""
    df = await get_latest_candles(timeframe, limit=limit)
    if df.empty:
        return {"candles": [], "timeframe": timeframe, "count": 0}

    candles = []
    for _, row in df.iterrows():
        time_val = row["time"]
        if hasattr(time_val, "isoformat"):
            time_str = time_val.isoformat()
        else:
            time_str = str(time_val)

        candles.append({
            "time": time_str,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row.get("volume", 0)),
            "oi": int(row.get("oi", 0)) if row.get("oi") else 0,
        })

    return {
        "symbol": "BANKNIFTY",
        "timeframe": timeframe,
        "count": len(candles),
        "candles": candles,
    }


@router.get("/live-price")
async def get_live_price_endpoint():
    """Get current Bank Nifty live price."""
    now = datetime.now(IST)
    is_market_open = (
        now.weekday() < 5 and
        now.replace(hour=9, minute=15) <= now <= now.replace(hour=15, minute=30)
    )

    price_data = get_live_price()
    if price_data is None:
        # Return last known or mock
        return {
            "symbol": "BANKNIFTY",
            "ltp": 48000.0,
            "change": 0.0,
            "change_pct": 0.0,
            "high": 48200.0,
            "low": 47800.0,
            "open": 48000.0,
            "prev_close": 48000.0,
            "timestamp": now.isoformat(),
            "is_market_open": is_market_open,
            "data_source": "mock",
        }

    price_data["is_market_open"] = is_market_open
    price_data["data_source"] = "live"
    return price_data


@router.get("/options-chain")
async def get_options_chain():
    """Fetch current expiry options chain with PCR, Max Pain, IV Rank."""
    live = get_live_price()
    underlying = None
    if live:
        from decimal import Decimal
        underlying = Decimal(str(live.get("ltp", 48000)))

    result = options_processor.process_and_cache(underlying)
    if result is None:
        raise HTTPException(status_code=503, detail="Options chain unavailable")
    return result


@router.get("/pcr")
async def get_pcr():
    """Get current Put-Call Ratio and Max Pain."""
    pcr = float(options_processor.get_cached_pcr())
    max_pain = float(options_processor.get_cached_max_pain())
    iv_rank = float(options_processor.get_cached_iv_rank())

    interpretation = "Neutral"
    if pcr > 1.2:
        interpretation = "Bearish (High Put Writing)"
    elif pcr < 0.8:
        interpretation = "Bullish (High Call Writing)"

    return {
        "pcr": pcr,
        "max_pain": max_pain,
        "iv_rank": iv_rank,
        "interpretation": interpretation,
        "timestamp": datetime.now(IST).isoformat(),
    }


@router.get("/market-status")
async def get_market_status():
    """Check if market is currently open."""
    now = datetime.now(IST)
    is_weekday = now.weekday() < 5
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    is_open = is_weekday and market_open <= now <= market_close

    return {
        "is_open": is_open,
        "current_time_ist": now.isoformat(),
        "market_open": market_open.isoformat(),
        "market_close": market_close.isoformat(),
        "session": "Regular" if is_open else "Closed",
        "next_open": "9:15 AM IST" if not is_open else None,
    }
