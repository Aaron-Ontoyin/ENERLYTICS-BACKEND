from typing import Generic, Literal, TypeVar, List, Any, TYPE_CHECKING
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from src.database.models import Base

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int
    pages: int
    has_next: bool
    has_prev: bool

    model_config = ConfigDict(from_attributes=True)


class PageParams:
    def __init__(
        self,
        page: int = 1,
        size: int = 100,
        sort_by: Literal["created_at", "updated_at"] | str = "created_at",
        sort_order: Literal["asc", "desc"] = "desc",
    ):
        self.page = page
        self.size = size
        self.offset = (page - 1) * size
        self.sort_by = sort_by
        self.sort_order = sort_order


async def paginate_query(
    db: AsyncSession,
    query: Select[Any],
    page_params: PageParams,
) -> PaginatedResponse["Base[Any, Any]"]:
    count_query: Select[Any] = select(func.count()).select_from(query.subquery())
    total: int = (await db.execute(count_query)).scalar() or 0
    total_pages: int = max((total + page_params.size - 1) // page_params.size, 1)

    query = query.order_by(text(f"{page_params.sort_by} {page_params.sort_order}"))
    query = query.offset(page_params.offset).limit(page_params.size)

    items: List[Any] = list((await db.execute(query)).scalars().all())
    return PaginatedResponse[Any](
        items=items,
        total=total,
        page=page_params.page,
        size=page_params.size,
        pages=total_pages,
        has_next=page_params.page < total_pages,
        has_prev=page_params.page > 1,
    )
