"""
Pydantic schemas for request/response validation.
"""
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from enum import Enum
import uuid


# ── Enums ─────────────────────────────────────────────────────────────────────
class SignalDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


class SignalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    TARGET_1_HIT = "TARGET_1_HIT"
    TARGET_2_HIT = "TARGET_2_HIT"
    SL_HIT = "SL_HIT"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class RiskMode(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


# ── Auth Schemas ──────────────────────────────────────────────────────────────
class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    is_active: bool
    risk_mode: RiskMode
    alert_telegram: bool
    alert_email: bool
    alert_inapp: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── Market Data Schemas ───────────────────────────────────────────────────────
class CandleData(BaseModel):
    time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    oi: Optional[int] = None


class LivePriceResponse(BaseModel):
    symbol: str
    ltp: Decimal
    change: Decimal
    change_pct: Decimal
    high: Decimal
    low: Decimal
    open: Decimal
    prev_close: Decimal
    timestamp: datetime
    is_market_open: bool


class OptionsChainItem(BaseModel):
    strike: Decimal
    ce_ltp: Optional[Decimal]
    ce_oi: Optional[int]
    ce_change_oi: Optional[int]
    ce_iv: Optional[Decimal]
    pe_ltp: Optional[Decimal]
    pe_oi: Optional[int]
    pe_change_oi: Optional[int]
    pe_iv: Optional[Decimal]


class OptionsChainResponse(BaseModel):
    symbol: str
    expiry: str
    pcr: Decimal
    max_pain: Decimal
    iv_rank: Decimal
    underlying_price: Decimal
    timestamp: datetime
    chain: List[OptionsChainItem]


# ── Signal Schemas ────────────────────────────────────────────────────────────
class SignalResponse(BaseModel):
    id: uuid.UUID
    timestamp: datetime
    direction: SignalDirection
    confidence: float
    entry_price: Decimal
    entry_low: Optional[Decimal]
    entry_high: Optional[Decimal]
    stop_loss: Decimal
    target_1: Decimal
    target_2: Decimal
    risk_reward: float
    pattern_detected: Optional[str]
    timeframe: str
    atr_value: Optional[Decimal]
    status: SignalStatus
    closed_at: Optional[datetime]
    close_price: Optional[Decimal]
    pnl_points: Decimal
    model_version: Optional[str]

    class Config:
        from_attributes = True


class SignalListResponse(BaseModel):
    signals: List[SignalResponse]
    total: int


# ── Analytics Schemas ─────────────────────────────────────────────────────────
class WinRateResponse(BaseModel):
    period_days: int
    total_signals: int
    winning: int
    losing: int
    neutral: int
    win_rate: float
    avg_rr: float
    total_pnl_points: Decimal
    best_trade: Decimal
    worst_trade: Decimal
    current_streak: int
    max_win_streak: int
    max_lose_streak: int


class PerformanceChartPoint(BaseModel):
    date: str
    cumulative_pnl: Decimal
    daily_pnl: Decimal
    signals_count: int


class MonthlyPnL(BaseModel):
    month: str
    pnl: Decimal
    wins: int
    losses: int
    win_rate: float


class PerformanceResponse(BaseModel):
    equity_curve: List[PerformanceChartPoint]
    monthly_pnl: List[MonthlyPnL]
    total_pnl: Decimal
    sharpe_ratio: float
    max_drawdown: Decimal
    win_rate: float
    best_streak: int
    worst_streak: int


# ── Backtest Schemas ──────────────────────────────────────────────────────────
class BacktestRequest(BaseModel):
    from_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    to_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    min_confidence: Optional[float] = 65.0
    risk_mode: Optional[RiskMode] = RiskMode.BALANCED


class BacktestResult(BaseModel):
    from_date: str
    to_date: str
    total_signals: int
    winning_signals: int
    losing_signals: int
    win_rate: float
    avg_rr: float
    max_drawdown: Decimal
    sharpe_ratio: float
    total_pnl_points: Decimal
    best_trade: Decimal
    worst_trade: Decimal
    monthly_pnl: List[MonthlyPnL]
    equity_curve: List[Dict[str, Any]]


# ── User Settings Schemas ─────────────────────────────────────────────────────
class UserSettingsUpdate(BaseModel):
    risk_mode: Optional[RiskMode] = None
    alert_telegram: Optional[bool] = None
    alert_email: Optional[bool] = None
    alert_inapp: Optional[bool] = None
    telegram_chat_id: Optional[str] = None
    email_address: Optional[str] = None


# ── WebSocket Message Schemas ─────────────────────────────────────────────────
class WSMessage(BaseModel):
    type: str  # "signal", "price", "signal_update", "heartbeat"
    data: Dict[str, Any]
    timestamp: datetime


class PriceUpdate(BaseModel):
    symbol: str
    ltp: float
    change: float
    change_pct: float
    timestamp: str
