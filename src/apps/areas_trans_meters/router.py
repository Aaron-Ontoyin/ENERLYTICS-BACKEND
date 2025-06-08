from typing import List

from fastapi import APIRouter, Depends, Path, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from uuid import UUID as PyUUID

from .models import (
    CoverageArea as CoverageAreaDB,
    Transformer as TransformerDB,
    Meter as MeterDB,
)
from .schemas import (
    CoverageArea,
    CoverageAreaCreate,
    CoverageAreaUpdate,
    CoverageAreaWithSubAreas,
    CoverageAreaWithParent,
    Transformer,
    TransformerCreate,
    TransformerUpdate,
    Meter,
    MeterCreate,
    MeterUpdate,
)
from src.database import aget_db, PaginatedResponse, PageParams
from src.core.dependencies import get_current_user, CurrentUser
from src.core.query_parser import parse_filters, build_search_filters
from src.database import Filter


router = APIRouter(prefix="/arsenal", tags=["Areas, Transformers, Meters"])


@router.get("/coverage-area/{id}", response_model=CoverageArea)
async def get_coverage_area(
    id: PyUUID = Path(..., description="The ID of the coverage area"),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    coverage_area = await CoverageAreaDB.get_by_id(db, id)
    if not coverage_area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coverage area not found"
        )
    return coverage_area


@router.get(
    "/coverage-area/{id}/with-sub-areas", response_model=CoverageAreaWithSubAreas
)
async def get_coverage_area_with_sub_areas(
    id: PyUUID = Path(..., description="The ID of the coverage area"),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a coverage area with all its sub-areas (nested hierarchy)"""
    query = (
        select(CoverageAreaDB)
        .options(selectinload(CoverageAreaDB.sub_areas))
        .where(CoverageAreaDB.id == id)
    )

    result = await db.execute(query)
    coverage_area = result.scalar_one_or_none()

    if not coverage_area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coverage area not found"
        )
    return coverage_area


@router.get("/coverage-area/{id}/with-parent", response_model=CoverageAreaWithParent)
async def get_coverage_area_with_parent(
    id: PyUUID = Path(..., description="The ID of the coverage area"),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a coverage area with its parent information"""
    query = (
        select(CoverageAreaDB)
        .options(selectinload(CoverageAreaDB.parent_area))
        .where(CoverageAreaDB.id == id)
    )

    result = await db.execute(query)
    coverage_area = result.scalar_one_or_none()

    if not coverage_area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coverage area not found"
        )
    return coverage_area


@router.get("/coverage-areas", response_model=PaginatedResponse[CoverageArea])
async def get_coverage_areas(
    request: Request,
    page_params: PageParams = Depends(),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
    search: str | None = Query(
        None, description="Search across name, description, and type"
    ),
):
    """
    Get all coverage areas with flexible filtering.

    ## Simple Usage:
    - `?name=Tongo` - Exact name match
    - `?type=country` - Filter by type
    - `?search=Tongo` - Search across name, description, and type
    - `?parent_id=uuid` - Filter by parent ID
    - `?parent_id__is=null` - Get only top-level areas (no parent)

    ## Advanced Filtering (field__operator=value):
    - `?name__ilike=%Tongo%` - Case-insensitive partial match
    - `?type__in=country,province` - Multiple values (comma-separated)
    - `?created_at__gte=2024-01-01` - Date greater than or equal
    - `?parent_id__is_not=null` - Get only sub-areas (has parent)

    ## Supported Operators:
    `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not in`, `is`, `is not`,
    `like`, `ilike`, `between`, `not between`

    ## Examples:
    - `?name__ilike=Tongo&type=country` - Coverage areas with 'Tongo' in name and type is country
    - `?parent_id__is=null&type=country` - Top-level countries only
    - `?parent_id=uuid&type=province` - Provinces under a specific country
    """

    query_params = dict(request.query_params)
    allowed_fields = [
        "id",
        "name",
        "description",
        "type",
        "parent_id",
        "created_at",
        "updated_at",
    ]
    filters: List[Filter] = parse_filters(query_params, allowed_fields)

    if search:
        filters.extend(build_search_filters(search, ["name", "description", "type"]))

    coverage_areas = await CoverageAreaDB.list(db, filters, page_params)
    return PaginatedResponse[CoverageArea](
        items=[
            CoverageArea.model_validate(coverage_area)
            for coverage_area in coverage_areas.items
        ],
        **coverage_areas.model_dump(exclude={"items"}),
    )


@router.get(
    "/coverage-areas/top-level",
    response_model=PaginatedResponse[CoverageAreaWithSubAreas],
)
async def get_top_level_coverage_areas(
    page_params: PageParams = Depends(),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get all top-level coverage areas (those without a parent) with their immediate sub-areas"""
    filters = [Filter(field="parent_id", operator="is", value=None)]
    coverage_areas = await CoverageAreaDB.list(db, filters, page_params)
    return PaginatedResponse[CoverageAreaWithSubAreas](
        items=[
            CoverageAreaWithSubAreas.model_validate(coverage_area)
            for coverage_area in coverage_areas.items
        ],
        **coverage_areas.model_dump(exclude={"items"}),
    )


@router.post("/coverage-area", response_model=CoverageArea)
async def create_coverage_area(
    coverage_area: CoverageAreaCreate,
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if coverage_area.parent_id:
        parent = await CoverageAreaDB.get_by_id(db, coverage_area.parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent coverage area not found",
            )

    return await CoverageAreaDB.create(db, coverage_area)


@router.put("/coverage-area/{id}", response_model=CoverageArea)
async def update_coverage_area(
    coverage_area_update: CoverageAreaUpdate,
    id: PyUUID = Path(..., description="The ID of the coverage area"),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    coverage_area = await CoverageAreaDB.get_by_id(db, id)
    if not coverage_area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coverage area not found"
        )

    if coverage_area_update.parent_id:
        parent = await CoverageAreaDB.get_by_id(db, coverage_area_update.parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent coverage area not found",
            )

        if coverage_area_update.parent_id == id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Coverage area cannot be its own parent",
            )

    return await coverage_area.update(db, coverage_area_update)


@router.delete("/coverage-area/{id}")
async def delete_coverage_area(
    id: PyUUID = Path(..., description="The ID of the coverage area"),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    coverage_area = await CoverageAreaDB.get_by_id(db, id)
    if not coverage_area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coverage area not found"
        )

    await coverage_area.delete(db)
    return {"message": "Coverage area deleted successfully"}


### Transformers


@router.get("/transformer/{id}", response_model=Transformer)
async def get_transformer(
    id: PyUUID = Path(..., description="The ID of the transformer"),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    transformer = await TransformerDB.get_by_id(db, id)
    if not transformer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transformer not found"
        )
    return transformer


@router.get("/transformers", response_model=PaginatedResponse[Transformer])
async def get_transformers(
    request: Request,
    page_params: PageParams = Depends(),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
    search: str | None = Query(
        None, description="Search across name, description, and coverage area"
    ),
):
    query_params = dict(request.query_params)
    allowed_fields = [
        "id",
        "name",
        "description",
        "coverage_area_id",
        "created_at",
        "updated_at",
    ]
    filters: List[Filter] = parse_filters(query_params, allowed_fields)

    if search:
        filters.extend(build_search_filters(search, ["name", "description"]))

    transformers = await TransformerDB.list(db, filters, page_params)
    return PaginatedResponse[Transformer](
        items=[
            Transformer.model_validate(transformer)
            for transformer in transformers.items
        ],
        **transformers.model_dump(exclude={"items"}),
    )


@router.post("/transformer", response_model=Transformer)
async def create_transformer(
    transformer: TransformerCreate,
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await TransformerDB.create(db, transformer)


@router.put("/transformer/{id}", response_model=Transformer)
async def update_transformer(
    transformer_update: TransformerUpdate,
    id: PyUUID = Path(..., description="The ID of the transformer"),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    transformer = await TransformerDB.get_by_id(db, id)
    if not transformer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transformer not found"
        )
    return await transformer.update(db, transformer_update)


@router.delete("/transformer/{id}")
async def delete_transformer(
    id: PyUUID = Path(..., description="The ID of the transformer"),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    transformer = await TransformerDB.get_by_id(db, id)
    if not transformer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transformer not found"
        )
    await transformer.delete(db)
    return {"message": "Transformer deleted successfully"}


### Meters


@router.get("/meter/{id}", response_model=Meter)
async def get_meter(
    id: PyUUID = Path(..., description="The ID of the meter"),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    meter = await MeterDB.get_by_id(db, id)
    if not meter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Meter not found"
        )
    return meter


@router.get("/meters", response_model=PaginatedResponse[Meter])
async def get_meters(
    request: Request,
    page_params: PageParams = Depends(),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
    search: str | None = Query(
        None, description="Search across name, description, and transformer"
    ),
):
    query_params = dict(request.query_params)
    allowed_fields = [
        "id",
        "name",
        "description",
        "transformer_id",
        "created_at",
        "updated_at",
    ]
    filters: List[Filter] = parse_filters(query_params, allowed_fields)

    if search:
        filters.extend(build_search_filters(search, ["name", "description"]))

    db_meters = await MeterDB.list(db, filters, page_params)
    return PaginatedResponse[Meter](
        items=[Meter.model_validate(meter) for meter in db_meters.items],
        **db_meters.model_dump(exclude={"items"}),
    )


@router.post("/meter", response_model=Meter)
async def create_meter(
    meter: MeterCreate,
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await MeterDB.create(db, meter)


@router.put("/meter/{id}", response_model=Meter)
async def update_meter(
    meter_update: MeterUpdate,
    id: PyUUID = Path(..., description="The ID of the meter"),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    meter = await MeterDB.get_by_id(db, id)
    if not meter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Meter not found"
        )
    return await meter.update(db, meter_update)


@router.delete("/meter/{id}")
async def delete_meter(
    id: PyUUID = Path(..., description="The ID of the meter"),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    meter = await MeterDB.get_by_id(db, id)
    if not meter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Meter not found"
        )
    await meter.delete(db)
    return {"message": "Meter deleted successfully"}
