from uuid import UUID as PyUUID
from typing import Any, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from .auth import AuthService
from src.database import aget_db
from src.apps.users.models import User as UserDB
from core.exceptions import NotFoundError


security = HTTPBearer()


class CurrentUser(BaseModel):
    db_user: UserDB
    payload: Dict[str, Any]


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(aget_db),
) -> CurrentUser:
    """
    Get the current user from the database.

    Args:
        credentials: The HTTP Authorization credentials.
        db: The database session.

    Returns:
        The current user.
    """
    token = credentials.credentials
    payload = await AuthService.verify_access_token(token, db)
    try:
        db_user = await UserDB.get_by_id(db, PyUUID(payload["user_id"]))
        return CurrentUser(db_user=db_user, payload=payload)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
