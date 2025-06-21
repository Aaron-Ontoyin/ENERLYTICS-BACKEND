from enum import Enum
from typing import List, Optional
from uuid import UUID as PyUUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TransformerBase(BaseModel):
    name: str
    description: str


class TransformerCreate(TransformerBase):
    coverage_area_id: PyUUID


class TransformerUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    coverage_area_id: Optional[PyUUID] = None


class Transformer(TransformerBase):
    id: PyUUID
    num_meters: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MeterBase(BaseModel):
    name: str
    description: str


class MeterCreate(MeterBase):
    transformer_id: PyUUID


class Meter(MeterBase):
    id: PyUUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MeterUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    coverage_area_id: Optional[PyUUID] = None


class CoverageAreaType(Enum):
    COUNTRY = "country"
    PROVINCE = "province"
    DISTRICT = "district"
    SUB_DISTRICT = "sub-district"
    VILLAGE = "village"


class CoverageAreaBase(BaseModel):
    type: CoverageAreaType
    name: str
    description: str


class CoverageAreaCreate(CoverageAreaBase):
    parent_id: Optional[PyUUID] = None


class CoverageAreaUpdate(BaseModel):
    type: Optional[CoverageAreaType] = None
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[PyUUID] = None


class CoverageAreaOut(CoverageAreaBase):
    num_transformers: int
    num_meters: int


class CoverageArea(CoverageAreaOut):
    id: PyUUID
    parent_id: Optional[PyUUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CoverageAreaWithSubAreas(CoverageAreaOut):
    """Coverage area with nested sub-areas"""

    id: PyUUID
    parent_id: Optional[PyUUID] = None
    sub_areas: List[CoverageArea] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
