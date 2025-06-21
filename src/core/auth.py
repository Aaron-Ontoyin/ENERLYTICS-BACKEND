from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Literal
from enum import Enum

from pydantic import BaseModel, Field
from jose import JWTError, jwt
import bcrypt
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import secrets

from src.database import Filter
from src.database.models import TokenBlacklist
from src.core.config import settings


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    access_expires_in: int = Field(..., description="Access token expires in seconds")
    refresh_expires_in: int = Field(..., description="Refresh token expires in seconds")


class AccessToken(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(..., description="Access token expires in seconds")


class RefreshToken(BaseModel):
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(..., description="Refresh token expires in seconds")


class AuthService:
    """
    Authentication service.
    """

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password.

        Args:
            plain_password: The plain password.
            hashed_password: The hashed password.

        Returns:
            True if the password is correct, False otherwise.
        """
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )

    @staticmethod
    def get_password_hash(password: str) -> str:
        """
        Get the hash of a password.

        Args:
            password: The password to hash.

        Returns:
            The hash of the password.
        """
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def create_access_token(
        user_id: str, expires_delta: Optional[timedelta] = None
    ) -> AccessToken:
        """
        Create an access token.

        Args:
            user_id: The ID of the user.
            expires_delta: The expiration delta.

        Returns:
            An AccessToken object.
        """
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                hours=settings.ACCESS_TOKEN_EXPIRE_HOURS
            )

        payload = {
            "user_id": user_id,
            "exp": expire,
            "type": TokenType.ACCESS,
            "jti": secrets.token_urlsafe(32),
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        return AccessToken(
            access_token=token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_HOURS * 60,
        )

    @staticmethod
    def create_refresh_token(user_id: str) -> RefreshToken:
        """
        Create a refresh token.

        Args:
            user_id: The ID of the user.

        Returns:
            A RefreshToken object.
        """
        expire = datetime.now(timezone.utc) + timedelta(
            hours=settings.REFRESH_TOKEN_EXPIRE_HOURS
        )
        payload = {
            "user_id": user_id,
            "exp": expire,
            "type": TokenType.REFRESH,
            "jti": secrets.token_urlsafe(32),
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        return RefreshToken(
            refresh_token=token,
            expires_in=settings.REFRESH_TOKEN_EXPIRE_HOURS * 60,
        )

    @staticmethod
    def create_token_pair(user_id: str) -> TokenPair:
        """
        Create both access and refresh tokens.

        Args:
            user_id: The ID of the user.

        Returns:
            A TokenPair object containing both access and refresh tokens.
        """
        access_token = AuthService.create_access_token(user_id)
        refresh_token = AuthService.create_refresh_token(user_id)
        return TokenPair(
            access_token=access_token.access_token,
            refresh_token=refresh_token.refresh_token,
            access_expires_in=access_token.expires_in,
            refresh_expires_in=refresh_token.expires_in,
        )

    @staticmethod
    async def verify_access_token(token: str, db: AsyncSession) -> Dict[str, Any]:
        """
        Verify an access token.

        Args:
            token: The token to verify.
            db: The database session.

        Returns:
            The payload of the token.

        Raises:
            HTTPException: If the token is invalid or blacklisted.
        """
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            if payload.get("type") != TokenType.ACCESS:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type",
                )
            await AuthService.check_blacklist(payload["jti"], db)
            return payload
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate access token",
            )

    @staticmethod
    async def verify_refresh_token(token: str, db: AsyncSession) -> Dict[str, Any]:
        """
        Verify a refresh token.

        Args:
            token: The token to verify.
            db: The database session.

        Returns:
            The payload of the token.

        Raises:
            HTTPException: If the token is invalid or blacklisted.
        """
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            if payload.get("type") != TokenType.REFRESH:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type",
                )
            await AuthService.check_blacklist(payload["jti"], db)
            return payload
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate refresh token",
            )

    @staticmethod
    async def verify_token(token: str, db: AsyncSession) -> Dict[str, Any]:
        """
        Verify a token.

        Args:
            token: The token to verify.
            db: The database session.

        Returns:
            The payload of the token.

        Raises:
            HTTPException: If the token is invalid or blacklisted.
        """
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            await AuthService.check_blacklist(payload["jti"], db)
            return payload
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
            )

    @staticmethod
    async def check_blacklist(jti: str, db: AsyncSession) -> None:
        """
        Verify if a token is blacklisted.

        Args:
            jti: The JWT ID of the token.
            db: The database session.
        """
        blacklisted_token = await TokenBlacklist.get_one_or_none(
            db, Filter(field="jti", operator="==", value=jti)
        )
        if blacklisted_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
            )
