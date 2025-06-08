from enum import Enum
from typing import List, Optional
from uuid import UUID as PyUUID
from datetime import datetime

from pydantic import BaseModel


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

    class Config:
        from_attributes = True


class MeterBase(BaseModel):
    name: str
    description: str


class MeterCreate(MeterBase):
    coverage_area_id: PyUUID


class Meter(MeterBase):
    id: PyUUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


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
    num_transformers: int
    num_meters: int


class CoverageAreaCreate(CoverageAreaBase):
    parent_id: Optional[PyUUID] = None


class CoverageAreaUpdate(BaseModel):
    type: Optional[CoverageAreaType] = None
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[PyUUID] = None
    num_transformers: Optional[int] = None
    num_meters: Optional[int] = None


class CoverageArea(CoverageAreaBase):
    id: PyUUID
    parent_id: Optional[PyUUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CoverageAreaWithSubAreas(CoverageAreaBase):
    """Coverage area with nested sub-areas"""

    id: PyUUID
    parent_id: Optional[PyUUID] = None
    sub_areas: List["CoverageAreaWithSubAreas"] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CoverageAreaWithParent(CoverageAreaBase):
    """Coverage area with parent information"""

    id: PyUUID
    parent_id: Optional[PyUUID] = None
    parent_area: Optional["CoverageArea"] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


CoverageAreaWithSubAreas.model_rebuild()
CoverageAreaWithParent.model_rebuild()
