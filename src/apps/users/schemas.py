from typing import Optional
from enum import Enum
from datetime import datetime

from pydantic import BaseModel


class UserType(str, Enum):
    ADMIN = "admin"
    USER = "user"


class UserBase(BaseModel):
    email: str
    first_name: str
    last_name: str
    other_names: Optional[str] = None
    phone: Optional[str] = None
    type: Optional[UserType] = UserType.USER


class UserCreate(UserBase):
    key: str


class UserUpdate(BaseModel):
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    type: Optional[UserType] = None
    other_names: Optional[str] = None
    phone: Optional[str] = None


class User(UserBase):
    id: str
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    key: str


class AccessTokenRefreshRequest(BaseModel):
    refresh_token: str
