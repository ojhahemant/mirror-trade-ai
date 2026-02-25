"""
Mirror Trade AI — FastAPI Application Entry Point.
Includes REST API, WebSocket, and background initialization.
"""
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Set
import redis.asyncio as aioredis
import pytz
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from loguru import logger

from api.config import settings
from api.routes import auth, market, signals, analytics, user
from data.data_pipeline import get_live_price

IST = pytz.timezone(settings.ist_timezone)

# ── WebSocket Connection Manager ──────────────────────────────────────────────
class ConnectionManager:
    """Manages WebSocket connections and broadcasting."""

    def __init__(self):
        self._connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)
        logger.debug(f"WS client connected. Total: {len(self._connections)}")

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)
        logger.debug(f"WS client disconnected. Total: {len(self._connections)}")

    async def broadcast(self, message: dict):
        dead = set()
        for ws in self._connections.copy():
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections.discard(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


# ── Redis Pub/Sub Listener ────────────────────────────────────────────────────
async def redis_listener():
    """Listen to Redis pub/sub and forward to WebSocket clients."""
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe("channel:signals", "banknifty_live")

    logger.info("Redis listener started")
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            await manager.broadcast(data)
        except Exception as e:
            logger.warning(f"Redis message broadcast failed: {e}")


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """App startup and shutdown."""
    logger.info("Starting Mirror Trade AI API...")

    # Start Redis listener in background
    listener_task = asyncio.create_task(redis_listener())

    # Start Kite ticker if available
    from data.data_pipeline import update_live_price
    from data.kite_client import kite_client
    kite_client.start_ticker(update_live_price)

    logger.info(f"API ready on port {settings.app_port}")
    yield

    # Cleanup
    listener_task.cancel()
    kite_client.stop_ticker()
    logger.info("Mirror Trade AI API stopped")


# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Mirror Trade AI — Bank Nifty",
    description="AI-powered Bank Nifty trading signals API",
    version="1.0.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

# ── Middleware ─────────────────────────────────────────────────────────────────
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(market.router)
app.include_router(signals.router)
app.include_router(analytics.router)
app.include_router(user.router)


# ── Health ─────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "mirror-trade-ai",
        "timestamp": datetime.now(IST).isoformat(),
        "ws_connections": manager.connection_count,
    }


@app.get("/")
async def root():
    return {
        "service": "Mirror Trade AI — Bank Nifty Edition",
        "version": "1.0.0",
        "docs": "/docs",
    }


# ── WebSocket: Live Signals ────────────────────────────────────────────────────
@app.websocket("/ws/live-signals")
async def ws_live_signals(websocket: WebSocket):
    """
    WebSocket endpoint for live signals and price updates.
    Broadcasts:
    - new_signal: when a new trading signal is generated
    - signal_update: when signal status changes (T1/T2/SL hit)
    - signal_pnl_update: live P&L updates
    - heartbeat: every 30s
    """
    await manager.connect(websocket)
    try:
        # Send current state on connect
        from signals.signal_engine import signal_engine
        active = await signal_engine.get_active_signal()
        await websocket.send_json({
            "type": "connected",
            "data": {
                "active_signal": active,
                "ws_count": manager.connection_count,
            },
            "timestamp": datetime.now(IST).isoformat(),
        })

        # Keep connection alive, heartbeats
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                # Handle client messages (ping/pong)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({
                    "type": "heartbeat",
                    "data": {"timestamp": datetime.now(IST).isoformat()},
                    "timestamp": datetime.now(IST).isoformat(),
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# ── WebSocket: Price Feed ──────────────────────────────────────────────────────
@app.websocket("/ws/price-feed")
async def ws_price_feed(websocket: WebSocket):
    """
    WebSocket endpoint for tick-by-tick price stream.
    Sends price update every second.
    """
    await manager.connect(websocket)
    try:
        while True:
            price = get_live_price()
            if price:
                await websocket.send_json({
                    "type": "price",
                    "data": price,
                    "timestamp": datetime.now(IST).isoformat(),
                })
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"Price feed WS error: {e}")
        manager.disconnect(websocket)
