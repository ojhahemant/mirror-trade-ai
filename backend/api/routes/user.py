"""
User settings routes.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from api.middleware.auth import get_current_user
from api.models.database import get_db, AsyncSessionLocal
from api.models.schemas import UserSettingsUpdate, UserResponse

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("/settings")
async def get_settings(current_user: dict = Depends(get_current_user)):
    """Get current user settings."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT id, email, username, is_active, risk_mode,
                   alert_telegram, alert_email, alert_inapp,
                   telegram_chat_id, email_address, created_at
            FROM users WHERE id = :id
        """), {"id": uuid.UUID(current_user["sub"])})
        row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    cols = result.keys()
    return dict(zip(cols, row))


@router.put("/settings")
async def update_settings(
    body: UserSettingsUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update user settings."""
    updates = {}
    if body.risk_mode is not None:
        updates["risk_mode"] = body.risk_mode.value
    if body.alert_telegram is not None:
        updates["alert_telegram"] = body.alert_telegram
    if body.alert_email is not None:
        updates["alert_email"] = body.alert_email
    if body.alert_inapp is not None:
        updates["alert_inapp"] = body.alert_inapp
    if body.telegram_chat_id is not None:
        updates["telegram_chat_id"] = body.telegram_chat_id
    if body.email_address is not None:
        updates["email_address"] = body.email_address

    if not updates:
        return {"message": "No changes provided"}

    set_clause = ", ".join(f"{k}=:{k}" for k in updates)
    updates["id"] = uuid.UUID(current_user["sub"])

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(f"UPDATE users SET {set_clause} WHERE id=:id"),
            updates,
        )
        await session.commit()

    return {"message": "Settings updated successfully", "updated": list(updates.keys())}
