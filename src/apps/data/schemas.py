from datetime import datetime
from typing import Self
from uuid import UUID as PyUUID
from enum import Enum

from pydantic import BaseModel, model_validator


class ReadingType(str, Enum):
    CURRENT = "current"
    VOLTAGE = "voltage"
    POWER = "power"
    POWER_FACTOR = "power_factor"
    TEMPERATURE = "temperature"
    ENERGY_CONSUMPTION = "energy_consumption"


class BaseReading(BaseModel):
    meter_id: PyUUID | None = None
    transformer_id: PyUUID | None = None
    value: float
    timestamp: datetime
    reading_type: ReadingType
    is_estimated: bool = False
    confidence_score: float | None = None
    source_info: str | None = None

    @model_validator(mode="after")
    def validate_meter_or_transformer(self) -> Self:
        if self.meter_id is None and self.transformer_id is None:
            raise ValueError("A reading must be associated with a meter or transformer")

        if self.meter_id is not None and self.transformer_id is not None:
            raise ValueError(
                "A reading cannot be associated with both a meter and a transformer"
            )

        return self


class ReadingUpdate(BaseReading):
    id: PyUUID
    value: float | None = None  # type: ignore


class ReadingCreate(BaseReading): ...


class Reading(BaseReading):
    id: PyUUID
    created_at: datetime
    updated_at: datetime
