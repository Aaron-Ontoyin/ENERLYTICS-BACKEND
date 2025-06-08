from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text

from src.database import Base
from src.core.config import settings
from .schemas import AlertCreate, AlertUpdate, AlertStatus


class Alert(Base[AlertCreate, AlertUpdate]):
    __tablename__ = f"{settings.API_NAME.lower()}__alerts"

    title: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AlertStatus] = mapped_column(String(10), nullable=False)
