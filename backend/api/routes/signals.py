"""
Signal routes: latest, active, history, detail.
"""
import uuid
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional
from loguru import logger

from api.middleware.auth import get_optional_user
from signals.signal_engine import signal_engine

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("/latest")
async def get_latest_signals(
    limit: int = Query(default=10, ge=1, le=50),
    _user=Depends(get_optional_user),
):
    """Get last N signals."""
    signals = await signal_engine.get_signals_history(days=90, limit=limit)
    return {
        "signals": signals,
        "total": len(signals),
    }


@router.get("/active")
async def get_active_signal(_user=Depends(get_optional_user)):
    """Get currently active (open) signal."""
    active = await signal_engine.get_active_signal()
    if active is None:
        return {"active_signal": None, "message": "No active signal at this time"}
    return {"active_signal": active}


@router.get("/history")
async def get_signal_history(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    direction: Optional[str] = Query(default=None, enum=["BUY", "SELL"]),
    _user=Depends(get_optional_user),
):
    """Get historical signals with optional filters."""
    signals = await signal_engine.get_signals_history(days=days, limit=limit)

    if direction:
        signals = [s for s in signals if s.get("direction") == direction]

    return {
        "signals": signals,
        "total": len(signals),
        "period_days": days,
    }


@router.get("/{signal_id}")
async def get_signal_detail(
    signal_id: str,
    _user=Depends(get_optional_user),
):
    """Get detailed info for a specific signal."""
    try:
        uid = uuid.UUID(signal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid signal ID format")

    from api.models.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT id, timestamp, direction, confidence,
                   entry_price, entry_low, entry_high,
                   stop_loss, target_1, target_2, risk_reward,
                   pattern_detected, timeframe, atr_value,
                   status, closed_at, close_price, pnl_points, model_version
            FROM signals WHERE id = :signal_id
        """), {"signal_id": uid})
        row = result.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Signal not found")

        cols = result.keys()
        signal = dict(zip(cols, row))

        # Get events
        events_result = await session.execute(text("""
            SELECT event_type, price, timestamp, notes
            FROM signal_events WHERE signal_id = :signal_id
            ORDER BY timestamp ASC
        """), {"signal_id": uid})
        events = [dict(zip(events_result.keys(), e)) for e in events_result.fetchall()]

    signal["events"] = events
    return signal
