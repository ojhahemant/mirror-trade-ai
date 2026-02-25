"""
Auth routes: register, login, profile.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import uuid
import pytz
from loguru import logger

from api.models.database import get_db
from api.models.schemas import UserRegister, UserLogin, TokenResponse, UserResponse
from api.middleware.auth import hash_password, verify_password, create_access_token, get_current_user
from api.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])
IST = pytz.timezone(settings.ist_timezone)


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    # Check duplicate email/username
    existing = await db.execute(text(
        "SELECT id FROM users WHERE email=:email OR username=:username"
    ), {"email": body.email, "username": body.username})
    if existing.fetchone():
        raise HTTPException(status_code=400, detail="Email or username already taken")

    user_id = uuid.uuid4()
    hashed = hash_password(body.password)

    await db.execute(text("""
        INSERT INTO users (id, email, username, hashed_password)
        VALUES (:id, :email, :username, :hashed)
    """), {"id": user_id, "email": body.email, "username": body.username, "hashed": hashed})

    return UserResponse(
        id=user_id,
        email=body.email,
        username=body.username,
        is_active=True,
        risk_mode="balanced",
        alert_telegram=False,
        alert_email=False,
        alert_inapp=True,
        created_at=datetime.now(IST),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    """Login and get JWT token."""
    result = await db.execute(text(
        "SELECT id, hashed_password, is_active FROM users WHERE email=:email"
    ), {"email": body.email})
    row = result.fetchone()

    if not row or not verify_password(body.password, row[1]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not row[2]:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    token = create_access_token(str(row[0]), body.email)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expiry_hours * 3600,
    )


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user profile."""
    result = await db.execute(text(
        "SELECT id, email, username, is_active, risk_mode, "
        "alert_telegram, alert_email, alert_inapp, created_at "
        "FROM users WHERE id=:id"
    ), {"id": uuid.UUID(current_user["sub"])})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=row[0], email=row[1], username=row[2], is_active=row[3],
        risk_mode=row[4], alert_telegram=row[5], alert_email=row[6],
        alert_inapp=row[7], created_at=row[8],
    )
