from pydantic import BaseModel
from enum import Enum
from datetime import datetime


class AlertStatus(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    EXPIRED = "expired"


class AlertBase(BaseModel):
    title: str
    message: str
    status: AlertStatus


class AlertCreate(AlertBase): ...


class AlertUpdate(BaseModel):
    title: str | None = None
    message: str | None = None
    status: AlertStatus | None = None


class Alert(AlertBase):
    id: str
    created_at: datetime
    updated_at: datetime
