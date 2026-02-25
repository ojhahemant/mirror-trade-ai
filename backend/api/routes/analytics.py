"""
Analytics routes: win rate, performance chart, backtest.
"""
from datetime import date
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, BackgroundTasks, Depends
from loguru import logger

from api.middleware.auth import get_optional_user
from signals.signal_engine import signal_engine

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/win-rate")
async def get_win_rate(
    days: int = Query(default=30, ge=1, le=365),
    _user=Depends(get_optional_user),
):
    """Get win rate and performance stats for the period."""
    stats = await signal_engine.get_win_rate_stats(days=days)
    return stats


@router.get("/performance-chart")
async def get_performance_chart(
    days: int = Query(default=30, ge=7, le=365),
    _user=Depends(get_optional_user),
):
    """Get equity curve and monthly P&L data."""
    signals = await signal_engine.get_signals_history(days=days, limit=1000)

    closed = [s for s in signals if s.get("status") not in ("ACTIVE", "CANCELLED")]

    # Build equity curve
    cumulative = 0.0
    equity_curve = []
    by_date: dict = {}

    for sig in sorted(closed, key=lambda x: str(x.get("timestamp", ""))):
        day = str(sig.get("timestamp", ""))[:10]
        pnl = float(sig.get("pnl_points", 0))
        if day not in by_date:
            by_date[day] = {"pnl": 0, "count": 0}
        by_date[day]["pnl"] += pnl
        by_date[day]["count"] += 1

    for day in sorted(by_date.keys()):
        cumulative += by_date[day]["pnl"]
        equity_curve.append({
            "date": day,
            "daily_pnl": round(by_date[day]["pnl"], 2),
            "cumulative_pnl": round(cumulative, 2),
            "signals_count": by_date[day]["count"],
        })

    # Monthly P&L
    monthly: dict = {}
    for sig in closed:
        month = str(sig.get("timestamp", ""))[:7]
        if month not in monthly:
            monthly[month] = {"pnl": 0, "wins": 0, "losses": 0}
        pnl = float(sig.get("pnl_points", 0))
        monthly[month]["pnl"] += pnl
        if pnl > 0:
            monthly[month]["wins"] += 1
        else:
            monthly[month]["losses"] += 1

    monthly_list = []
    for month in sorted(monthly.keys()):
        d = monthly[month]
        total = d["wins"] + d["losses"]
        monthly_list.append({
            "month": month,
            "pnl": round(d["pnl"], 2),
            "wins": d["wins"],
            "losses": d["losses"],
            "win_rate": round(d["wins"] / total * 100, 1) if total > 0 else 0,
        })

    # Key stats
    all_pnl = [float(s.get("pnl_points", 0)) for s in closed]
    wins = [p for p in all_pnl if p > 0]
    losses = [p for p in all_pnl if p <= 0]

    import numpy as np
    if len(all_pnl) > 1 and np.std(all_pnl) > 0:
        sharpe = float(np.mean(all_pnl) / np.std(all_pnl) * np.sqrt(26 * 250))
    else:
        sharpe = 0.0

    cumulative_arr = np.cumsum(all_pnl) if all_pnl else [0]
    running_max = np.maximum.accumulate(cumulative_arr)
    max_drawdown = float(np.max(running_max - cumulative_arr)) if len(cumulative_arr) > 0 else 0

    return {
        "equity_curve": equity_curve,
        "monthly_pnl": monthly_list,
        "total_pnl": round(sum(all_pnl), 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown": round(max_drawdown, 2),
        "win_rate": round(len(wins) / len(all_pnl) * 100, 2) if all_pnl else 0,
        "best_streak": 0,  # Computed in full backtest
        "worst_streak": 0,
    }


@router.get("/backtest")
async def run_backtest(
    from_date: str = Query(..., description="Start date YYYY-MM-DD"),
    to_date: str = Query(..., description="End date YYYY-MM-DD"),
    min_confidence: float = Query(default=65.0, ge=40.0, le=95.0),
    _user=Depends(get_optional_user),
):
    """
    Run backtest on historical data.
    Returns comprehensive performance metrics.
    """
    try:
        from_d = date.fromisoformat(from_date)
        to_d = date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if from_d >= to_d:
        raise HTTPException(status_code=400, detail="from_date must be before to_date")

    if (to_d - from_d).days > 1095:  # 3 years
        raise HTTPException(status_code=400, detail="Date range cannot exceed 3 years")

    try:
        from data.data_pipeline import get_latest_candles
        from ml.backtester import BacktestEngine

        df = await get_latest_candles("15min", limit=50000)
        if df.empty:
            raise HTTPException(status_code=503, detail="No historical data available")

        engine = BacktestEngine(min_confidence=min_confidence)
        results = engine.run(df, from_date=from_d, to_date=to_d)
        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")


@router.get("/backtest/download")
async def download_backtest_csv(
    from_date: str = Query(...),
    to_date: str = Query(...),
    _user=Depends(get_optional_user),
):
    """Download backtest results as CSV."""
    from fastapi.responses import FileResponse
    import os

    try:
        from_d = date.fromisoformat(from_date)
        to_d = date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    try:
        from data.data_pipeline import get_latest_candles
        from ml.backtester import BacktestEngine

        df = await get_latest_candles("15min", limit=50000)
        engine = BacktestEngine()
        results = engine.run(df, from_date=from_d, to_date=to_d)
        csv_path = engine.export_csv(results)

        if not os.path.exists(csv_path):
            raise HTTPException(status_code=404, detail="CSV file not generated")

        return FileResponse(
            csv_path,
            media_type="text/csv",
            filename=os.path.basename(csv_path),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
