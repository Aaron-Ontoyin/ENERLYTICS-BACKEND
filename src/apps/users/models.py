from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.config import settings
from src.database.models import Base
from .schemas import UserCreate, UserUpdate, UserType


class User(Base[UserCreate, UserUpdate]):
    __tablename__ = f"{settings.API_NAME.lower()}__users"

    hashed_key: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    other_names: Mapped[str] = mapped_column(String, nullable=True)
    phone: Mapped[str] = mapped_column(String, nullable=True)
    type: Mapped[UserType] = mapped_column(String, nullable=True)
