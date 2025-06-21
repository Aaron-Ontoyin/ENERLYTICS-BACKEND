from typing import Optional
from enum import Enum
from datetime import datetime
from uuid import UUID as PyUUID

from pydantic import BaseModel, EmailStr, model_validator


class UserType(str, Enum):
    ADMIN = "admin"
    USER = "user"


class UserBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    other_names: Optional[str] = None
    phone: Optional[str] = None
    type: Optional[UserType] = UserType.USER


class UserCreate(UserBase):
    key: str
    key_confirm: str

    @model_validator(mode="after")
    def check_keys_match(self):
        if self.key != self.key_confirm:
            raise ValueError("Keys do not match")
        return self


class UserUpdate(BaseModel):
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    type: Optional[UserType] = None
    other_names: Optional[str] = None
    phone: Optional[str] = None


class User(UserBase):
    id: PyUUID
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    key: str


class AccessTokenRefreshRequest(BaseModel):
    refresh_token: str
