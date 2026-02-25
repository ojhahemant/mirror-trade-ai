"""
Signal Engine: generates, manages, and tracks trading signals lifecycle.
Handles WebSocket broadcasting, Telegram/Email alerts, and P&L tracking.
"""
import asyncio
import json
import uuid
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Set
import pytz
import redis
from loguru import logger
from sqlalchemy import text

from api.config import settings
from api.models.database import AsyncSessionLocal
from data.data_pipeline import get_latest_candles, get_live_price
from data.options_fetcher import options_processor
from ml.model_engine import model_inference

IST = pytz.timezone(settings.ist_timezone)
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

REDIS_ACTIVE_SIGNAL_KEY = "signal:active"
REDIS_SIGNAL_CHANNEL = "channel:signals"
REDIS_LATEST_SIGNALS_KEY = "signals:latest"
REDIS_TTL = 3600 * 4  # 4 hours


class SignalEngine:
    """
    Core signal lifecycle manager.
    - Generates signals from ML model
    - Persists to database
    - Tracks P&L updates in real-time
    - Broadcasts via Redis pub/sub
    """

    def __init__(self):
        self._ws_connections: Set = set()

    async def generate_signal(self) -> Optional[Dict[str, Any]]:
        """
        Run full signal generation pipeline:
        1. Fetch latest candles
        2. Get options metrics
        3. Run ML inference
        4. Validate signal (R:R, confidence)
        5. Persist and broadcast
        """
        try:
            # Check if market is open
            now = datetime.now(IST)
            market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
            market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

            if not (market_open <= now <= market_close):
                logger.debug("Market is closed — skipping signal generation")
                return None

            # Check if there's already an active signal
            active_raw = redis_client.get(REDIS_ACTIVE_SIGNAL_KEY)
            if active_raw:
                active = json.loads(active_raw)
                # Update active signal P&L
                await self._update_active_signal_pnl(active)
                return None

            # Fetch candles and options data
            df = await get_latest_candles("15min", limit=500)
            if df.empty or len(df) < 250:
                logger.warning("Insufficient candle data for signal generation")
                return None

            # Get options metrics (cached)
            live_price_data = get_live_price()
            ltp = Decimal(str(live_price_data["ltp"])) if live_price_data else None

            pcr = float(options_processor.get_cached_pcr())
            max_pain = float(options_processor.get_cached_max_pain())
            iv_rank = float(options_processor.get_cached_iv_rank())

            # ML inference
            risk_conf_map = {
                "conservative": 75.0,
                "balanced": 65.0,
                "aggressive": 55.0,
            }
            min_conf = risk_conf_map.get("balanced", 65.0)

            signal_data = model_inference.predict(
                df,
                pcr=pcr,
                max_pain=max_pain,
                iv_rank=iv_rank,
                min_confidence=min_conf,
            )

            if signal_data is None:
                return None

            # Build signal object
            signal_id = str(uuid.uuid4())
            signal = {
                "id": signal_id,
                "timestamp": now.isoformat(),
                "direction": signal_data["direction"],
                "confidence": signal_data["confidence"],
                "entry_price": float(signal_data["entry_price"]),
                "entry_low": float(signal_data["entry_low"]),
                "entry_high": float(signal_data["entry_high"]),
                "stop_loss": float(signal_data["stop_loss"]),
                "target_1": float(signal_data["target_1"]),
                "target_2": float(signal_data["target_2"]),
                "risk_reward": signal_data["risk_reward"],
                "pattern_detected": signal_data.get("pattern_detected", ""),
                "timeframe": "15min",
                "atr_value": float(signal_data.get("atr_value", 0)),
                "status": "ACTIVE",
                "pnl_points": 0.0,
                "model_version": signal_data.get("model_version", ""),
            }

            # Persist to database
            await self._save_signal(signal)

            # Cache active signal
            redis_client.setex(REDIS_ACTIVE_SIGNAL_KEY, REDIS_TTL, json.dumps(signal))

            # Update latest signals cache
            await self._update_latest_signals_cache(signal)

            # Broadcast to WebSocket clients
            await self._broadcast_signal(signal)

            # Send alerts
            await self._send_alerts(signal)

            logger.info(
                f"Signal generated: {signal['direction']} @ {signal['entry_price']:.0f} "
                f"(conf={signal['confidence']:.1f}% rr={signal['risk_reward']:.2f})"
            )
            return signal

        except Exception as e:
            logger.error(f"Signal generation failed: {e}", exc_info=True)
            return None

    async def _save_signal(self, signal: Dict):
        """Persist signal to PostgreSQL."""
        async with AsyncSessionLocal() as session:
            try:
                await session.execute(text("""
                    INSERT INTO signals (
                        id, timestamp, direction, confidence,
                        entry_price, entry_low, entry_high,
                        stop_loss, target_1, target_2,
                        risk_reward, pattern_detected, timeframe,
                        atr_value, status, pnl_points, model_version
                    ) VALUES (
                        :id, :timestamp, :direction, :confidence,
                        :entry_price, :entry_low, :entry_high,
                        :stop_loss, :target_1, :target_2,
                        :risk_reward, :pattern_detected, :timeframe,
                        :atr_value, :status, :pnl_points, :model_version
                    )
                """), {
                    **signal,
                    "id": uuid.UUID(signal["id"]),
                })
                await session.commit()
            except Exception as e:
                logger.error(f"Signal save failed: {e}")
                await session.rollback()

    async def update_signal_status(self, signal_id: str, status: str, close_price: float, pnl: float):
        """Update signal outcome in DB and Redis."""
        now = datetime.now(IST)
        async with AsyncSessionLocal() as session:
            try:
                await session.execute(text("""
                    UPDATE signals
                    SET status = :status, closed_at = :closed_at,
                        close_price = :close_price, pnl_points = :pnl,
                        updated_at = :now
                    WHERE id = :signal_id
                """), {
                    "status": status,
                    "closed_at": now,
                    "close_price": close_price,
                    "pnl": pnl,
                    "now": now,
                    "signal_id": uuid.UUID(signal_id),
                })

                # Log event
                await session.execute(text("""
                    INSERT INTO signal_events (signal_id, event_type, price, timestamp)
                    VALUES (:signal_id, :event_type, :price, :timestamp)
                """), {
                    "signal_id": uuid.UUID(signal_id),
                    "event_type": status,
                    "price": close_price,
                    "timestamp": now,
                })

                await session.commit()
            except Exception as e:
                logger.error(f"Signal status update failed: {e}")
                await session.rollback()

        # Remove from active cache
        redis_client.delete(REDIS_ACTIVE_SIGNAL_KEY)

        # Broadcast update
        update_msg = {
            "type": "signal_update",
            "data": {
                "id": signal_id,
                "status": status,
                "close_price": close_price,
                "pnl_points": pnl,
            },
            "timestamp": now.isoformat(),
        }
        redis_client.publish(REDIS_SIGNAL_CHANNEL, json.dumps(update_msg))

    async def _update_active_signal_pnl(self, active: Dict):
        """Check and update active signal against current price."""
        live = get_live_price()
        if not live:
            return

        current_price = float(live["ltp"])
        direction = active["direction"]
        entry = float(active["entry_price"])
        sl = float(active["stop_loss"])
        t1 = float(active["target_1"])
        t2 = float(active["target_2"])
        signal_id = active["id"]

        # Compute unrealized P&L
        if direction == "BUY":
            pnl = current_price - entry
        else:
            pnl = entry - current_price

        # Check for exit conditions
        new_status = None
        if direction == "BUY":
            if current_price <= sl:
                new_status = "SL_HIT"
                close_price = sl
            elif current_price >= t2:
                new_status = "TARGET_2_HIT"
                close_price = t2
            elif current_price >= t1:
                new_status = "TARGET_1_HIT"
                close_price = t1
        else:
            if current_price >= sl:
                new_status = "SL_HIT"
                close_price = sl
            elif current_price <= t2:
                new_status = "TARGET_2_HIT"
                close_price = t2
            elif current_price <= t1:
                new_status = "TARGET_1_HIT"
                close_price = t1

        if new_status:
            final_pnl = close_price - entry if direction == "BUY" else entry - close_price
            await self.update_signal_status(signal_id, new_status, close_price, final_pnl)
            logger.info(f"Signal {signal_id} closed: {new_status} PnL={final_pnl:.0f} pts")
            return

        # Check expiry (4 candles = 60 min)
        signal_time = datetime.fromisoformat(active["timestamp"])
        if signal_time.tzinfo is None:
            signal_time = IST.localize(signal_time)

        elapsed_mins = (datetime.now(IST) - signal_time).total_seconds() / 60
        if elapsed_mins >= 60:  # 4 × 15min candles
            await self.update_signal_status(signal_id, "EXPIRED", current_price, pnl)
            return

        # Update unrealized P&L in Redis
        active["pnl_points"] = round(pnl, 2)
        redis_client.setex(REDIS_ACTIVE_SIGNAL_KEY, REDIS_TTL, json.dumps(active))

        # Broadcast P&L update
        update_msg = {
            "type": "signal_pnl_update",
            "data": {"id": signal_id, "pnl_points": round(pnl, 2), "current_price": current_price},
            "timestamp": datetime.now(IST).isoformat(),
        }
        redis_client.publish(REDIS_SIGNAL_CHANNEL, json.dumps(update_msg))

    async def _update_latest_signals_cache(self, new_signal: Dict):
        """Maintain a list of latest 10 signals in Redis."""
        cached = redis_client.get(REDIS_LATEST_SIGNALS_KEY)
        signals = json.loads(cached) if cached else []
        signals.insert(0, new_signal)
        signals = signals[:10]  # Keep last 10
        redis_client.setex(REDIS_LATEST_SIGNALS_KEY, REDIS_TTL * 2, json.dumps(signals))

    async def _broadcast_signal(self, signal: Dict):
        """Publish new signal to Redis pub/sub."""
        message = {
            "type": "new_signal",
            "data": signal,
            "timestamp": datetime.now(IST).isoformat(),
        }
        redis_client.publish(REDIS_SIGNAL_CHANNEL, json.dumps(message))

    async def _send_alerts(self, signal: Dict):
        """Send signal alerts via Telegram and/or email."""
        direction_emoji = "🟢" if signal["direction"] == "BUY" else "🔴"
        message = (
            f"{direction_emoji} *MIRROR TRADE AI — Bank Nifty Signal*\n\n"
            f"Direction: *{signal['direction']}*\n"
            f"Confidence: *{signal['confidence']:.1f}%*\n"
            f"Entry Zone: {signal['entry_low']:.0f} – {signal['entry_high']:.0f}\n"
            f"Stop Loss: {signal['stop_loss']:.0f}\n"
            f"Target 1: {signal['target_1']:.0f}\n"
            f"Target 2: {signal['target_2']:.0f}\n"
            f"Risk:Reward: 1:{signal['risk_reward']:.1f}\n"
            f"Pattern: {signal['pattern_detected']}\n"
            f"⏰ {signal['timestamp'][:19]}"
        )

        if settings.telegram_bot_token and settings.telegram_chat_id:
            await self._send_telegram(message)

    async def _send_telegram(self, text_msg: str):
        """Send Telegram message."""
        try:
            import aiohttp
            url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
            async with aiohttp.ClientSession() as session:
                await session.post(url, json={
                    "chat_id": settings.telegram_chat_id,
                    "text": text_msg,
                    "parse_mode": "Markdown",
                })
        except Exception as e:
            logger.warning(f"Telegram alert failed: {e}")

    async def get_active_signal(self) -> Optional[Dict]:
        """Get currently active signal."""
        cached = redis_client.get(REDIS_ACTIVE_SIGNAL_KEY)
        if cached:
            return json.loads(cached)

        # Fallback: query DB
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT id, timestamp, direction, confidence,
                       entry_price, entry_low, entry_high,
                       stop_loss, target_1, target_2, risk_reward,
                       pattern_detected, timeframe, atr_value,
                       status, pnl_points, model_version
                FROM signals
                WHERE status = 'ACTIVE'
                ORDER BY timestamp DESC
                LIMIT 1
            """))
            row = result.fetchone()

        if row:
            return dict(zip(result.keys(), row))
        return None

    async def get_signals_history(self, days: int = 30, limit: int = 50) -> List[Dict]:
        """Fetch historical signals from DB."""
        since = datetime.now(IST) - timedelta(days=days)
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT id, timestamp, direction, confidence,
                       entry_price, stop_loss, target_1, target_2,
                       risk_reward, pattern_detected, status, pnl_points, closed_at
                FROM signals
                WHERE timestamp >= :since
                ORDER BY timestamp DESC
                LIMIT :limit
            """), {"since": since, "limit": limit})
            rows = result.fetchall()
            cols = result.keys()

        return [dict(zip(cols, row)) for row in rows]

    async def get_win_rate_stats(self, days: int = 30) -> Dict:
        """Compute win rate and performance stats."""
        signals = await self.get_signals_history(days=days, limit=1000)
        if not signals:
            return {"total": 0, "win_rate": 0, "avg_rr": 0}

        closed = [s for s in signals if s["status"] not in ("ACTIVE", "CANCELLED")]
        wins = [s for s in closed if s.get("pnl_points", 0) > 0]
        losses = [s for s in closed if s.get("pnl_points", 0) <= 0]
        pnls = [float(s.get("pnl_points", 0)) for s in closed]

        win_pnls = [float(s["pnl_points"]) for s in wins]
        loss_pnls = [abs(float(s["pnl_points"])) for s in losses]
        avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0
        avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0
        avg_rr = avg_win / avg_loss if avg_loss > 0 else 0

        # Streak computation
        outcomes = [s.get("pnl_points", 0) > 0 for s in closed]
        cur_streak = 0
        if outcomes:
            last = outcomes[-1]
            for o in reversed(outcomes):
                if o == last:
                    cur_streak += 1 if last else -1
                else:
                    break

        return {
            "period_days": days,
            "total_signals": len(signals),
            "winning": len(wins),
            "losing": len(losses),
            "neutral": len(signals) - len(closed),
            "win_rate": round(len(wins) / len(closed) * 100, 2) if closed else 0,
            "avg_rr": round(avg_rr, 2),
            "total_pnl_points": round(sum(pnls), 2),
            "best_trade": round(max(pnls) if pnls else 0, 2),
            "worst_trade": round(min(pnls) if pnls else 0, 2),
            "current_streak": cur_streak,
            "max_win_streak": 0,  # Full computation in backtester
            "max_lose_streak": 0,
        }


# Singleton
signal_engine = SignalEngine()
