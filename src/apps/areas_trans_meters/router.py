from typing import List

from fastapi import APIRouter, Depends, Path, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
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
    Transformer,
    TransformerCreate,
    TransformerUpdate,
    Meter,
    MeterCreate,
    MeterUpdate,
)
from src.database import aget_db, PaginatedResponse, PageParams
from src.core.dependencies import get_current_user, CurrentUser, get_page_params
from src.core.query_parser import parse_filters, build_search_filters
from src.database import Filter


router = APIRouter()


@router.get("/coverage-area/{id}", response_model=CoverageArea, tags=["Coverage Areas"])
async def get_coverage_area(
    id: PyUUID = Path(..., description="The ID of the coverage area"),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    coverage_area = await CoverageAreaDB.get_by_id(
        db, id, selectinloads=[("transformers", "meters")]
    )
    if not coverage_area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coverage area not found"
        )
    return coverage_area


@router.get(
    "/coverage-area/{id}/with-sub-areas",
    response_model=CoverageAreaWithSubAreas,
    tags=["Coverage Areas"],
)
async def get_coverage_area_with_sub_areas(
    id: PyUUID = Path(..., description="The ID of the coverage area"),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a coverage area with all its sub-areas (nested hierarchy)"""
    coverage_area = await CoverageAreaDB.get_by_id(
        db,
        id,
        selectinloads=[
            ("transformers", "meters"),
            ("sub_areas", "transformers", "meters"),
        ],
    )
    if not coverage_area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coverage area not found"
        )

    return CoverageAreaWithSubAreas.model_validate(coverage_area)


@router.put("/coverage-area/{id}", response_model=CoverageArea, tags=["Coverage Areas"])
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


@router.delete("/coverage-area/{id}", tags=["Coverage Areas"])
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


@router.post("/coverage-area", response_model=CoverageArea, tags=["Coverage Areas"])
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

    try:
        db_area = await CoverageAreaDB.create(
            db,
            {
                **coverage_area.model_dump(exclude={"type"}),
                "type": coverage_area.type.value,
            },
            selectinloads=["transformers"],
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Coverage area already exists with this name({coverage_area.name}) and type({coverage_area.type.value})",
        )
    return CoverageArea.model_validate(db_area)


@router.get(
    "/coverage-areas",
    response_model=PaginatedResponse[CoverageArea],
    tags=["Coverage Areas"],
)
async def get_coverage_areas(
    request: Request,
    page_params: PageParams = Depends(get_page_params),
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
    - `?parent_id_a_is_not=null` - Get only sub-areas (has parent)

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

    search_filters: List[Filter] = []
    if search:
        search_filters.extend(
            build_search_filters(search, ["name", "description", "type"])
        )

    coverage_areas = await CoverageAreaDB.list(
        db,
        filters,
        search_filters,
        page_params,
        selectinloads=[("transformers", "meters")],
    )
    return PaginatedResponse[CoverageArea](
        items=[
            CoverageArea.model_validate(coverage_area)
            for coverage_area in coverage_areas.items
        ],
        **coverage_areas.model_dump(exclude={"items"}),
    )


### Transformers


@router.get("/transformer/{id}", response_model=Transformer, tags=["Transformers"])
async def get_transformer(
    id: PyUUID = Path(..., description="The ID of the transformer"),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    transformer = await TransformerDB.get_by_id(db, id, selectinloads=["meters"])
    if not transformer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transformer not found"
        )
    return Transformer(**transformer.to_dict(at_props=True))


@router.put("/transformer/{id}", response_model=Transformer, tags=["Transformers"])
async def update_transformer(
    transformer_update: TransformerUpdate,
    id: PyUUID = Path(..., description="The ID of the transformer"),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    transformer = await TransformerDB.get_by_id(db, id, selectinloads=["meters"])
    if not transformer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transformer not found"
        )
    return (await transformer.update(db, transformer_update)).to_dict(at_props=True)


@router.delete("/transformer/{id}", tags=["Transformers"])
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


@router.get(
    "/transformers",
    response_model=PaginatedResponse[Transformer],
    tags=["Transformers"],
)
async def get_transformers(
    request: Request,
    page_params: PageParams = Depends(get_page_params),
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

    search_filters: List[Filter] = []
    if search:
        search_filters.extend(build_search_filters(search, ["name", "description"]))

    transformers = await TransformerDB.list(
        db, filters, search_filters, page_params, selectinloads=["meters"]
    )
    return PaginatedResponse[Transformer](
        items=[
            Transformer(**transformer.to_dict(at_props=True))
            for transformer in transformers.items
        ],
        **transformers.model_dump(exclude={"items"}),
    )


@router.post(
    "/transformers",
    response_model=Transformer,
    tags=["Transformers"],
)
async def create_transformers(
    transformer: TransformerCreate,
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return (
            await TransformerDB.create(
                db, transformer.model_dump(), selectinloads=["meters"]
            )
        ).to_dict(at_props=True)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transformer with name ({transformer.name}) already exists",
        )


### Meters


@router.get("/meter/{id}", response_model=Meter, tags=["Meters"])
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


@router.put("/meter/{id}", response_model=Meter, tags=["Meters"])
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


@router.delete("/meter/{id}", tags=["Meters"])
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


@router.get("/meters", response_model=PaginatedResponse[Meter], tags=["Meters"])
async def get_meters(
    request: Request,
    page_params: PageParams = Depends(get_page_params),
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

    search_filters: List[Filter] = []
    if search:
        search_filters.extend(build_search_filters(search, ["name", "description"]))

    return await MeterDB.list(db, filters, search_filters, page_params)


@router.post(
    "/meter",
    response_model=Meter,
    tags=["Meters"],
)
async def create_meter(
    meter: MeterCreate,
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return await MeterDB.create(db, meter)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Meter with name ({meter.name}) already exists",
        )
