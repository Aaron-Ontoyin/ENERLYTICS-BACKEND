from datetime import datetime
from typing import TYPE_CHECKING, Optional, Self, Any, Dict
from collections.abc import Sequence
from uuid import UUID as PyUUID, uuid4

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, DateTime, Numeric, ForeignKey, text
from sqlalchemy import Index, Enum as SQLEnum, CheckConstraint, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.database import Base
from src.database.models import SelectInloadT
from src.apps.data.schemas import ReadingCreate, ReadingUpdate, ReadingType


if TYPE_CHECKING:
    from src.apps.areas_trans_meters.models import Meter, Transformer


async def ensure_partition_exists(session: AsyncSession, timestamp: datetime):
    """Ensure a partition exists for the given timestamp"""
    year = timestamp.year
    month = timestamp.month

    partition_name = f"{settings.API_NAME.lower()}__readings_{year}_{month:02d}"
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)

    result = await session.execute(
        text(
            """
        SELECT EXISTS (
            SELECT 1 FROM pg_class 
            WHERE relname = :partition_name
        )
    """
        ),
        {"partition_name": partition_name},
    )

    if not result.scalar():
        start_date_str = start_date.strftime("%Y-%m-%d %H:%M:%S")
        end_date_str = end_date.strftime("%Y-%m-%d %H:%M:%S")

        await session.execute(
            text(
                f"""
            CREATE TABLE {partition_name} PARTITION OF {settings.API_NAME.lower()}__readings
            FOR VALUES FROM ('{start_date_str}') TO ('{end_date_str}')
        """
            )
        )
        await session.commit()


class Reading(Base[ReadingCreate, ReadingUpdate]):
    """
    Unified readings table for all measurement types.
    Partitioned by timestamp for optimal time-series performance.
    """

    __tablename__ = f"{settings.API_NAME.lower()}__readings"

    id: Mapped[PyUUID] = mapped_column(PGUUID, default=uuid4)

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
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

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
        CheckConstraint(
            "((meter_id IS NOT NULL) AND (transformer_id IS NULL)) OR ((meter_id IS NULL) AND (transformer_id IS NOT NULL))",
            name="check_meter_or_transformer",
        ),
        PrimaryKeyConstraint("id", "timestamp", name="pk_readings_id_timestamp"),
        {"postgresql_partition_by": "RANGE (timestamp)"},
    )

    @classmethod
    async def create(
        cls,
        db: AsyncSession,
        obj_in: ReadingCreate | Dict[str, Any],
        selectinloads: Optional[Sequence[SelectInloadT]] = None,
    ) -> Self:
        timestamp = (
            obj_in.timestamp
            if isinstance(obj_in, ReadingCreate)
            else obj_in["timestamp"]
        )
        await ensure_partition_exists(db, timestamp)
        return await super().create(db, obj_in)

    @classmethod
    async def bulk_create(
        cls, db: AsyncSession, objs_in: Sequence[ReadingCreate | Dict[str, Any]]
    ) -> None:
        for obj_in in objs_in:
            timestamp = (
                obj_in.timestamp
                if isinstance(obj_in, ReadingCreate)
                else obj_in["timestamp"]
            )
            await ensure_partition_exists(db, timestamp)
        return await super().bulk_create(db, objs_in)

    @classmethod
    async def get_or_create(
        cls,
        db: AsyncSession,
        obj_in: ReadingCreate,
        identifier: str | None = None,
        selectinloads: Optional[Sequence[SelectInloadT]] = None,
    ) -> Self:
        await ensure_partition_exists(db, obj_in.timestamp)
        return await super().get_or_create(db, obj_in, identifier, selectinloads)

    @classmethod
    async def create_with_user(
        cls,
        db: AsyncSession,
        obj_in: ReadingCreate,
        user_id: str,
    ) -> Self:
        await ensure_partition_exists(db, obj_in.timestamp)
        return await super().create_with_user(db, obj_in, user_id)
