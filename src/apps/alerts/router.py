from typing import List
from uuid import UUID as PyUUID

from fastapi import APIRouter, Depends, Request, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, CurrentUser
from src.core.query_parser import parse_filters, build_search_filters
from src.database import Filter
from src.database import aget_db, PageParams, PaginatedResponse
from .models import Alert as AlertDB
from .schemas import Alert, AlertCreate, AlertUpdate, AlertStatus

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/alerts/{alert_id}", response_model=Alert)
async def get_alert(
    alert_id: PyUUID,
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await AlertDB.get_by_id(db, alert_id)


@router.get("/alerts", response_model=PaginatedResponse[Alert])
async def get_alerts(
    request: Request,
    page_params: PageParams = Depends(),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
    search: str | None = Query(
        None, description="Search across title, message, and status"
    ),
    exclude_expired: bool = Query(
        True, description="Exclude expired alerts (default: True)"
    ),
):
    """
    Get all alerts with flexible filtering. Only accessible by admin users.

    ## Simple Usage:
    - `?title=john@example.com` - Exact title match
    - `?status=info` - Filter by status
    - `?search=john` - Search across multiple fields

    ## Advanced Filtering (field__operator=value):
    - `?title__ilike=%john%` - Case-insensitive partial match
    - `?status__in=info,warning` - Multiple values (comma-separated)
    - `?created_at__gte=2024-01-01` - Date greater than or equal
    - `?id__not_in=uuid1,uuid2` - Exclude specific IDs
    - `?title__like=John%` - Case-sensitive starts with
    - `?created_at__between=2024-01-01,2024-12-31` - Date range

    ## Supported Operators:
    `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not in`, `is`, `is not`,
    `like`, `ilike`, `between`, `not between`

    ## Examples:
    - `?title__ilike=john&status=info` - Alerts with 'john' in title and status info
    - `?created_at__between=2024-01-01,2024-12-31` - Alerts created in 2024
    - `?status__in=info,warning&title__not_in=test@example.com` - Complex filtering
    - `?title__ilike=john&message__ilike=doe` - Multiple field filtering
    """

    query_params = dict(request.query_params)
    allowed_fields = [
        "id",
        "title",
        "message",
        "status",
        "created_at",
        "updated_at",
    ]
    filters: List[Filter] = parse_filters(query_params, allowed_fields)

    if search:
        filters.extend(build_search_filters(search, ["title", "message", "status"]))

    if exclude_expired:
        filters.append(Filter(field="status", operator="!=", value=AlertStatus.EXPIRED))

    alerts = await AlertDB.list(db, filters, page_params)
    return PaginatedResponse[Alert](
        items=[Alert.model_validate(alert) for alert in alerts.items],
        **alerts.model_dump(exclude={"items"}),
    )


@router.post("/alerts", response_model=Alert)
async def create_alert(
    alert: AlertCreate,
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await AlertDB.create(db, alert)


@router.put("/alerts/{alert_id}", response_model=Alert)
async def update_alert(
    alert_id: PyUUID,
    alert_update: AlertUpdate,
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    alert = await AlertDB.get_by_id(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return await alert.update(db, alert_update)


@router.delete("/alerts/{alert_id}", response_model=Alert)
async def delete_alert(
    alert_id: PyUUID,
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    alert = await AlertDB.get_by_id(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return await alert.delete(db)
