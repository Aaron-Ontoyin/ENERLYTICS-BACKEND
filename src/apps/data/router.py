from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID as PyUUID

from .models import Reading as ReadingDB
from .schemas import Reading, ReadingCreate, ReadingUpdate, ReadingType
from src.database import aget_db, PaginatedResponse, PageParams, Filter
from src.core.dependencies import get_current_user, CurrentUser
from src.core.query_parser import parse_filters

router = APIRouter(prefix="/readings", tags=["readings"])


def get_unit_for_type(reading_type: ReadingType) -> Optional[str]:
    """Get the standard unit for each reading type"""
    unit_map = {
        ReadingType.CURRENT: "A",
        ReadingType.VOLTAGE: "V",
        ReadingType.POWER: "W",
        ReadingType.POWER_FACTOR: None,
        ReadingType.TEMPERATURE: "°C",
        ReadingType.ENERGY_CONSUMPTION: "kWh",
    }
    return unit_map.get(reading_type)


@router.post("/", response_model=Reading)
async def create_reading(
    reading_create: ReadingCreate,
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a single reading"""
    reading = await ReadingDB.create(db, reading_create)
    return reading


@router.post("/bulk", response_model=Dict[str, Any])
async def bulk_create_readings(
    readings_create: List[ReadingCreate],
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Bulk create readings (up to 500 at once for optimal performance).
    Returns summary statistics instead of all created objects.
    """
    if len(readings_create) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 500 readings allowed per bulk request",
        )

    if not readings_create:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one reading is required",
        )

    readings = await ReadingDB.bulk_create(db, readings_create)

    reading_types: dict[ReadingType, int] = {}
    sources: dict[str, set[str]] = {"meters": set(), "transformers": set()}

    for reading in readings:
        reading_types[reading.reading_type] = (
            reading_types.get(reading.reading_type, 0) + 1
        )
        if reading.meter_id:
            sources["meters"].add(str(reading.meter_id))
        if reading.transformer_id:
            sources["transformers"].add(str(reading.transformer_id))

    return {
        "message": f"Successfully created {len(readings)} readings",
        "total_created": len(readings),
        "reading_types": reading_types,
        "sources_affected": {
            "meters": len(sources["meters"]),
            "transformers": len(sources["transformers"]),
        },
        "time_range": {
            "earliest": min(r.timestamp for r in readings).isoformat(),
            "latest": max(r.timestamp for r in readings).isoformat(),
        },
    }


@router.get("/", response_model=PaginatedResponse[Reading])
async def get_readings(
    request: Request,
    page_params: PageParams = Depends(),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get readings with flexible filtering.

    ## Query Examples:
    - `?reading_type=voltage` - Filter by reading type
    - `?meter_id=uuid` - Filter by meter
    - `?transformer_id=uuid` - Filter by transformer
    - `?timestamp__gte=2024-01-01T00:00:00Z` - Readings after date
    - `?timestamp__between=2024-01-01T00:00:00Z,2024-01-02T00:00:00Z` - Date range
    - `?value__gte=100` - Value greater than 100
    - `?reading_type__in=voltage,current` - Multiple types
    - `?is_estimated=false` - Only actual readings
    """
    query_params = dict(request.query_params)
    allowed_fields = [
        "id",
        "meter_id",
        "transformer_id",
        "reading_type",
        "value",
        "timestamp",
        "is_estimated",
        "confidence_score",
        "created_at",
        "updated_at",
    ]

    filters: List[Filter] = parse_filters(query_params, allowed_fields)
    readings = await ReadingDB.list(db, filters, page_params)
    return PaginatedResponse[Reading](
        items=[Reading.model_validate(reading) for reading in readings.items],
        **readings.model_dump(exclude={"items"}),
    )


@router.put("/", response_model=List[Reading])
async def update_readings(
    reading_updates: List[ReadingUpdate],
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update multiple readings"""
    if len(reading_updates) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 500 readings allowed per bulk request",
        )

    in_ids = [reading.id for reading in reading_updates]
    readings = (
        await ReadingDB.list(
            db,
            filters=[Filter(field="id", operator="in", value=in_ids)],
            page_params=PageParams(size=len(reading_updates)),
        )
    ).items
    if len(readings) != len(reading_updates):
        not_found_ids = set(in_ids) - set(r.id for r in readings)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Some readings not found: {not_found_ids}",
        )

    for reading_update in reading_updates:
        db_reading = next((r for r in readings if r.id == reading_update.id), None)
        if db_reading is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reading with ID {reading_update.id} not found",
            )
        for key, value in reading_update.model_dump().items():
            if hasattr(db_reading, key) and value is not None:
                setattr(db_reading, key, value)

    db.add_all(readings)
    await db.commit()

    return readings


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_readings(
    reading_ids: List[PyUUID],
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete multiple readings"""
    readings = (
        await ReadingDB.list(
            db,
            filters=[Filter(field="id", operator="in", value=reading_ids)],
            page_params=PageParams(size=len(reading_ids)),
        )
    ).items
    for reading in readings:
        await db.delete(reading)

    await db.commit()
