"""
This module provides the base model for all database models.
"""

from datetime import datetime, timezone
from typing import (
    Any,
    Dict,
    Generic,
    List,
    Literal,
    Optional,
    Self,
    TypeVar,
)
from uuid import UUID as PyUUID, uuid4

from pydantic import BaseModel
from sqlalchemy import (
    DateTime,
    MetaData,
    Select,
    inspect,
    select,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.core.config import settings
from core.exceptions import NotFoundError
from src.database.pagination import PageParams, PaginatedResponse, paginate_query
from .schemas import TokenBlacklist as TokenBlacklistSchema


class Filter(BaseModel):
    field: str
    operator: Literal[
        "==",
        "!=",
        ">",
        ">=",
        "<",
        "<=",
        "in",
        "not in",
        "is",
        "is not",
        "like",
        "ilike",
        "between",
        "not between",
    ]
    value: Any


naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class Base(DeclarativeBase, Generic[CreateSchemaType, UpdateSchemaType]):
    metadata = MetaData(naming_convention=naming_convention)

    id: Mapped[PyUUID] = mapped_column(PGUUID, primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
    )

    def to_dict(
        self,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if include is not None and exclude is not None:
            raise ValueError("Cannot specify both include and exclude")

        result = {}

        for column in self.__table__.columns:
            if exclude and column.name in exclude:
                continue

            if include and column.name not in include:
                continue

            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value

        return result  # type: ignore

    @property
    def pk(self) -> PyUUID:
        return self.id

    @classmethod
    def pk_field(cls) -> str:
        return inspect(cls).primary_key[0].name

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(**data)

    @classmethod
    def from_list(cls, data: List[Dict[str, Any]]) -> List[Self]:
        return [cls.from_dict(item) for item in data]

    @classmethod
    async def create(cls, db: AsyncSession, obj_in: CreateSchemaType) -> Self:
        obj = cls(**obj_in.model_dump())
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj

    @classmethod
    async def bulk_create(
        cls, db: AsyncSession, objs_in: List[CreateSchemaType]
    ) -> List[Self]:
        objs = [cls(**obj_in.model_dump()) for obj_in in objs_in]
        db.add_all(objs)
        await db.commit()
        return objs

    @classmethod
    async def get_by_id(
        cls, db: AsyncSession, id: PyUUID, raise_: bool = False
    ) -> Self | None:
        query = select(cls).where(cls.id == id)
        result = await db.execute(query)
        res = result.scalars().first()
        if not res and raise_:
            raise NotFoundError(f"{cls.__name__} with ID {id} not found")
        return res

    @classmethod
    async def list(
        cls,
        db: AsyncSession,
        filters: List[Filter],
        page_params: PageParams,
    ) -> PaginatedResponse["Base[CreateSchemaType, UpdateSchemaType]"]:
        query = select(cls)
        query = cls.apply_filter(query, filters)
        return await paginate_query(db, query, page_params)

    async def update(self, db: AsyncSession, obj_in: UpdateSchemaType) -> Self:
        for key, value in obj_in.model_dump().items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)

        await db.commit()
        await db.refresh(self)
        return self

    async def delete(self, db: AsyncSession) -> None:
        await db.delete(self)
        await db.commit()

    @classmethod
    async def get_or_create(
        cls, db: AsyncSession, obj_in: CreateSchemaType, identifier: str | None = None
    ) -> Self:
        if not identifier:
            obj = await cls.get_by_id(db, getattr(obj_in, cls.pk_field()))
        else:
            try:
                stmt = select(cls).where(
                    getattr(cls, identifier) == getattr(obj_in, identifier)
                )
                result = await db.execute(stmt)
                obj = result.scalars().first()
            except AttributeError:
                raise ValueError(f"Identifier {identifier} not found in {cls.__name__}")

        if obj is None:
            return await cls.create(db, obj_in)
        return obj

    @classmethod
    async def create_with_user(
        cls, db: AsyncSession, obj_in: CreateSchemaType, user_id: str
    ) -> Self:
        obj = cls(**obj_in.model_dump())
        if hasattr(obj, "user_id"):
            obj.user_id = user_id  # type: ignore
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj

    @classmethod
    async def get_one_or_none(
        cls, db: AsyncSession, filters: List[Filter] | Filter
    ) -> Self | None:
        filters = filters if isinstance(filters, list) else [filters]
        query = select(cls)
        query = cls.apply_filter(query, filters)
        result = await db.execute(query)
        return result.scalars().first()

    @classmethod
    async def get_one(cls, db: AsyncSession, filters: List[Filter] | Filter) -> Self:
        res = await cls.get_one_or_none(db, filters)
        if not res:
            raise NotFoundError(f"{cls.__name__} with filters {filters} not found")
        return res

    @classmethod
    def apply_filter(cls, query: Select[Any], filters: List[Filter]) -> Select[Any]:
        for filter in filters:
            field = getattr(cls, filter.field)
            if filter.operator == "==":
                query = query.where(field == filter.value)
            elif filter.operator == "!=":
                query = query.where(field != filter.value)
            elif filter.operator == ">":
                query = query.where(field > filter.value)
            elif filter.operator == ">=":
                query = query.where(field >= filter.value)
            elif filter.operator == "<":
                query = query.where(field < filter.value)
            elif filter.operator == "<=":
                query = query.where(field <= filter.value)
            elif filter.operator == "in":
                query = query.where(field.in_(filter.value))
            elif filter.operator == "not in":
                query = query.where(~field.in_(filter.value))
            elif filter.operator == "is":
                query = query.where(field.is_(filter.value))
            elif filter.operator == "is not":
                query = query.where(field.is_not(filter.value))
            elif filter.operator == "like":
                query = query.where(field.like(filter.value))
            elif filter.operator == "ilike":
                query = query.where(field.ilike(filter.value))
            elif filter.operator == "between":
                query = query.where(field.between(filter.value[0], filter.value[1]))
            elif filter.operator == "not between":
                query = query.where(~field.between(filter.value[0], filter.value[1]))
            else:
                raise ValueError(f"Invalid operator: {filter.operator}")
        return query

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.to_dict()})"

    def __str__(self) -> str:
        return self.__repr__()


class TokenBlacklist(Base[TokenBlacklistSchema, TokenBlacklistSchema]):
    __tablename__ = f"{settings.API_NAME.lower()}__token_blacklist"

    jti: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    token_type: Mapped[Literal["access", "refresh"]] = mapped_column(
        String, nullable=False
    )
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    blacklisted_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
