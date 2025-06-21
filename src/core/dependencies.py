from uuid import UUID as PyUUID
from typing import Any, Dict, Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict

from .auth import AuthService
from src.database import aget_db
from src.apps.users.models import User as UserDB
from src.database.pagination import PageParams
from src.core.config import settings


security = HTTPBearer(
    scheme_name="Bearer",
    description="JWT Authorization header using the Bearer scheme",
)


class CurrentUser(BaseModel):
    db_user: UserDB
    payload: Dict[str, Any]

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)


async def _get_current_user_any_token(
    token_type: Literal["access", "refresh"],
    credentials: HTTPAuthorizationCredentials,
    db: AsyncSession,
) -> CurrentUser:
    """
    Get the current user from the database.

    Args:
        token_type (Literal["access", "refresh"]): The type of token.
        credentials (HTTPAuthorizationCredentials): The HTTP Authorization credentials.
        db (AsyncSession): The database session.

    Returns:
        The current user.

    Raises:
        HTTPException: If the user is not found.
    """
    token = credentials.credentials
    if token_type == "access":
        payload = await AuthService.verify_access_token(token, db)
    else:
        payload = await AuthService.verify_refresh_token(token, db)

    db_user = await UserDB.get_by_id(db, PyUUID(payload["user_id"]))
    if db_user:
        return CurrentUser(db_user=db_user, payload=payload)
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(aget_db),
) -> CurrentUser:
    """
    Get the current user from the database using the access token.

    Args:
        credentials (HTTPAuthorizationCredentials): The HTTP Authorization credentials.
        db (AsyncSession): The database session.

    Returns:
        The current user.

    Raises:
        HTTPException: If the user is not found.
    """
    return await _get_current_user_any_token(
        token_type="access",
        credentials=credentials,
        db=db,
    )


async def get_current_user_refresh(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(aget_db),
) -> CurrentUser:
    """
    Get the current user from the database using the refresh token.

    Args:
        credentials (HTTPAuthorizationCredentials): The HTTP Authorization credentials.
        db (AsyncSession): The database session.

    Returns:
        The current user.

    Raises:
        HTTPException: If the page number is less than 1 or the page size is not between 1 and the maximum page size.
    """
    return await _get_current_user_any_token(
        token_type="refresh",
        credentials=credentials,
        db=db,
    )


def get_page_params(
    page: int = 1,
    size: int = 100,
    sort_by: Literal["created_at", "updated_at"] | str = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
) -> PageParams:
    """
    FastAPI dependency for pagination parameters.

    Args:
        page (int): The page number.
        size (int): The page size.
        sort_by (Literal["created_at", "updated_at"] | str): The field to sort by.
        sort_order (Literal["asc", "desc"]): The order to sort by.

    Returns:
        The page parameters.

    Raises:
        HTTPException: If the page number is less than 1 or the page size is not between 1 and the maximum page size.
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page number must be greater than 0",
        )
    if size < 1 or size > settings.MAX_PAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Page size must be between 1 and {settings.MAX_PAGE_SIZE} inclusive.",
        )

    return PageParams(page=page, size=size, sort_by=sort_by, sort_order=sort_order)


def get_readings_page_params(
    page: int = 1,
    size: int = 100,
    sort_by: Literal["created_at", "updated_at"] | str = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
) -> PageParams:
    """
    FastAPI dependency for pagination parameters.

    Args:
        page (int): The page number.
        size (int): The page size.
        sort_by (Literal["created_at", "updated_at"] | str): The field to sort by.
        sort_order (Literal["asc", "desc"]): The order to sort by.

    Returns:
        The page parameters.

    Raises:
        HTTPException: If the page number is less than 1 or the page size is not between 1 and the maximum page size.
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page number must be greater than 0",
        )
    if size < 1 or size > settings.READINGS_MAX_PAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Page size must be between 1 and {settings.READINGS_MAX_PAGE_SIZE} inclusive.",
        )

    return PageParams(page=page, size=size, sort_by=sort_by, sort_order=sort_order)
