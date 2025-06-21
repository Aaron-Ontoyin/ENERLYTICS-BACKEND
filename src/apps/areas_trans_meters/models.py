from typing import List, Optional, TYPE_CHECKING
from uuid import UUID as PyUUID

from sqlalchemy import String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from src.apps.data.models import Reading

from src.core.config import settings
from src.database import Base
from src.apps.areas_trans_meters.schemas import (
    CoverageAreaCreate,
    CoverageAreaUpdate,
    CoverageAreaType,
    TransformerCreate,
    TransformerUpdate,
    MeterCreate,
    MeterUpdate,
)


class Meter(Base[MeterCreate, MeterUpdate]):
    __tablename__ = f"{settings.API_NAME.lower()}__meters"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    transformer_id: Mapped[PyUUID] = mapped_column(
        ForeignKey(f"{settings.API_NAME.lower()}__transformers.id"), nullable=False
    )
    transformer: Mapped["Transformer"] = relationship(
        "Transformer", back_populates="meters", remote_side="Transformer.id"
    )

    readings: Mapped[List["Reading"]] = relationship(
        "Reading", back_populates="meter", cascade="all, delete-orphan"
    )


class Transformer(Base[TransformerCreate, TransformerUpdate]):
    __tablename__ = f"{settings.API_NAME.lower()}__transformers"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    coverage_area_id: Mapped[PyUUID] = mapped_column(
        ForeignKey(f"{settings.API_NAME.lower()}__coverage_areas.id"), nullable=False
    )

    coverage_area: Mapped["CoverageArea"] = relationship(
        "CoverageArea", back_populates="transformers", remote_side="CoverageArea.id"
    )

    meters: Mapped[List["Meter"]] = relationship(
        "Meter", back_populates="transformer", cascade="all, delete-orphan"
    )

    readings: Mapped[List["Reading"]] = relationship(
        "Reading", back_populates="transformer", cascade="all, delete-orphan"
    )

    @property
    def num_meters(self) -> int:
        return len(self.meters)


class CoverageArea(Base[CoverageAreaCreate, CoverageAreaUpdate]):
    __tablename__ = f"{settings.API_NAME.lower()}__coverage_areas"
    __table_args__ = (
        UniqueConstraint("type", "name", name="uq_coverage_area_type_name"),
    )

    type: Mapped[CoverageAreaType] = mapped_column(String(15), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    parent_id: Mapped[Optional[PyUUID]] = mapped_column(
        ForeignKey(f"{settings.API_NAME.lower()}__coverage_areas.id"), nullable=True
    )

    parent_area: Mapped[Optional["CoverageArea"]] = relationship(
        "CoverageArea", back_populates="sub_areas", remote_side="CoverageArea.id"
    )

    sub_areas: Mapped[List["CoverageArea"]] = relationship(
        "CoverageArea", back_populates="parent_area", cascade="all, delete-orphan"
    )

    transformers: Mapped[List["Transformer"]] = relationship(
        "Transformer", back_populates="coverage_area", cascade="all, delete-orphan"
    )

    @property
    def num_transformers(self) -> int:
        return len(self.transformers)

    @property
    def num_meters(self) -> int:
        return sum(len(transformer.meters) for transformer in self.transformers)
