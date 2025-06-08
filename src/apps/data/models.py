from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, DateTime, Numeric, ForeignKey, Index, Enum as SQLEnum
from uuid import UUID as PyUUID

from src.core.config import settings
from src.database import Base
from src.apps.data.schemas import ReadingCreate, ReadingUpdate, ReadingType

if TYPE_CHECKING:
    from src.apps.areas_trans_meters.models import Meter, Transformer


class Reading(Base[ReadingCreate, ReadingUpdate]):
    """
    Unified readings table for all measurement types.
    Partitioned by timestamp for optimal time-series performance.
    """

    __tablename__ = f"{settings.API_NAME.lower()}__readings"

    meter_id: Mapped[Optional[PyUUID]] = mapped_column(
        ForeignKey(f"{settings.API_NAME.lower()}__meters.id"), nullable=True, index=True
    )
    transformer_id: Mapped[Optional[PyUUID]] = mapped_column(
        ForeignKey(f"{settings.API_NAME.lower()}__transformers.id"),
        nullable=True,
        index=True,
    )

    reading_type: Mapped[ReadingType] = mapped_column(
        SQLEnum(ReadingType), nullable=False, index=True
    )
    value: Mapped[float] = mapped_column(Numeric(precision=15, scale=6), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    is_estimated: Mapped[bool] = mapped_column(default=False)
    confidence_score: Mapped[Optional[float]] = mapped_column(
        Numeric(3, 2), nullable=True
    )

    source_info: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    meter: Mapped[Optional["Meter"]] = relationship(
        "Meter", back_populates="readings", foreign_keys=[meter_id]
    )
    transformer: Mapped[Optional["Transformer"]] = relationship(
        "Transformer", back_populates="readings", foreign_keys=[transformer_id]
    )

    __table_args__ = (
        Index("idx_readings_type_time", "reading_type", "timestamp"),
        Index("idx_readings_meter_type_time", "meter_id", "reading_type", "timestamp"),
        Index(
            "idx_readings_transformer_type_time",
            "transformer_id",
            "reading_type",
            "timestamp",
        ),
        Index("idx_readings_time_desc", "timestamp", postgresql_using="btree"),
        {"postgresql_partition_by": "RANGE (timestamp)"},
        {
            "postgresql_check": "((meter_id IS NOT NULL) AND (transformer_id IS NULL)) OR ((meter_id IS NULL) AND (transformer_id IS NOT NULL))"
        },
    )
