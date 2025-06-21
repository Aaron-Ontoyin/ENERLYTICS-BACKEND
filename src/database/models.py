"""
This module provides the base model for all database models.
"""

from datetime import datetime
from collections.abc import Sequence
from typing import Any, Dict, Literal, Generic, List, Optional, Self, TypeVar, Tuple
from uuid import UUID as PyUUID, uuid4

from pydantic import BaseModel
from sqlalchemy import DateTime, MetaData, Select
from sqlalchemy import inspect, select, String, Column
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import or_
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    selectinload,
)

from src.core.config import settings
from src.core.exceptions import NotFoundError
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
SelectInloadT = str | Tuple[str, ...]


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
        at_props: bool = False,
        include_relations: bool = False,
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

        if include_relations:
            for relation in self.__mapper__.relationships:
                if exclude and relation.key in exclude:
                    continue
                if include and relation.key not in include:
                    continue

                try:
                    value = getattr(self, relation.key)
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    result[relation.key] = value
                except MissingGreenlet:
                    raise ValueError(
                        f"Relation {relation.key} not loaded. Please use selectinloads to load the relation."
                    )

        if at_props:
            for attr_name in dir(self):
                if not attr_name.startswith("_") and isinstance(
                    getattr(type(self), attr_name, None), property
                ):
                    if exclude and attr_name in exclude:
                        continue

                    if include and attr_name not in include:
                        continue

                    try:
                        value = getattr(self, attr_name)
                        if isinstance(value, datetime):
                            value = value.isoformat()
                        result[attr_name] = value
                    except MissingGreenlet:
                        raise ValueError(
                            f"Property {attr_name} not loaded. Please use selectinloads to load the property."
                        )

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
    def apply_selectinloads(
        cls,
        query: Select[Any],
        selectinloads: Sequence[SelectInloadT],
    ) -> Select[Any]:
        for load in selectinloads:
            if isinstance(load, str):
                query = query.options(selectinload(getattr(cls, load)))
            else:
                current_attr = getattr(cls, load[0])
                current_load = selectinload(current_attr)
                for sil in load[1:]:
                    current_attr = getattr(current_attr.property.mapper.class_, sil)
                    current_load = current_load.selectinload(current_attr)
                query = query.options(current_load)
        return query

    @classmethod
    async def create(
        cls,
        db: AsyncSession,
        obj_in: CreateSchemaType | Dict[str, Any],
        selectinloads: Optional[Sequence[SelectInloadT]] = None,
    ) -> Self:
        if isinstance(obj_in, dict):
            obj = cls(**obj_in)
        else:
            obj = cls(**obj_in.model_dump())
        db.add(obj)
        await db.commit()
        await db.refresh(obj)

        return await cls.get_one(
            db,
            filters=[Filter(field="id", operator="==", value=obj.id)],
            selectinloads=selectinloads,
        )

    @classmethod
    async def bulk_create(
        cls, db: AsyncSession, objs_in: Sequence[CreateSchemaType | Dict[str, Any]]
    ) -> None:
        objs = map(
            lambda x: cls(**x) if isinstance(x, dict) else cls(**x.model_dump()),
            objs_in,
        )
        db.add_all(objs)
        await db.commit()
        return

    @classmethod
    async def get_by_id(
        cls,
        db: AsyncSession,
        id: PyUUID,
        raise_: bool = False,
        selectinloads: Optional[Sequence[SelectInloadT]] = None,
    ) -> Self | None:
        query = select(cls).where(cls.id == id)
        if selectinloads:
            query = cls.apply_selectinloads(query, selectinloads)

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
        search_filters: Optional[List[Filter]] = None,
        page_params: PageParams = PageParams(),
        selectinloads: Optional[Sequence[SelectInloadT]] = None,
    ) -> PaginatedResponse["Base[CreateSchemaType, UpdateSchemaType]"]:
        query = select(cls)
        query = cls.apply_filter(query, filters)
        if search_filters is not None:
            query = cls.apply_filter(query, search_filters, as_or=True)
        if selectinloads:
            query = cls.apply_selectinloads(query, selectinloads)
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
        cls,
        db: AsyncSession,
        obj_in: CreateSchemaType,
        identifier: str | None = None,
        selectinloads: Optional[Sequence[SelectInloadT]] = None,
    ) -> Self:
        if not identifier:
            obj = await cls.get_by_id(db, getattr(obj_in, cls.pk_field()))
        else:
            try:
                stmt = select(cls).where(
                    getattr(cls, identifier) == getattr(obj_in, identifier)
                )
                if selectinloads:
                    stmt = cls.apply_selectinloads(stmt, selectinloads)
                result = await db.execute(stmt)
                obj = result.scalars().first()
            except AttributeError:
                raise ValueError(f"Identifier {identifier} not found in {cls.__name__}")

        if obj is None:
            return await cls.create(db, obj_in)
        return obj

    @classmethod
    async def create_with_user(
        cls,
        db: AsyncSession,
        obj_in: CreateSchemaType,
        user_id: str,
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
        cls,
        db: AsyncSession,
        filters: List[Filter] | Filter,
        selectinloads: Optional[Sequence[SelectInloadT]] = None,
    ) -> Self | None:
        filters = filters if isinstance(filters, list) else [filters]
        query = select(cls)
        query = cls.apply_filter(query, filters)
        if selectinloads:
            query = cls.apply_selectinloads(query, selectinloads)
        result = await db.execute(query)
        return result.scalars().first()

    @classmethod
    async def get_one(
        cls,
        db: AsyncSession,
        filters: List[Filter] | Filter,
        selectinloads: Optional[Sequence[SelectInloadT]] = None,
    ) -> Self:
        res = await cls.get_one_or_none(db, filters, selectinloads)
        if not res:
            raise NotFoundError(f"{cls.__name__} with filters {filters} not found")
        return res

    @classmethod
    def apply_filter(
        cls,
        query: Select[Any],
        filters: List[Filter],
        as_or: bool = False,
    ) -> Select[Any]:
        if not filters:
            return query

        conditions: List[Any] = []

        for filter in filters:
            field: Column[Any] = getattr(cls, filter.field)
            if filter.operator == "==":
                conditions.append(field == filter.value)
            elif filter.operator == "!=":
                conditions.append(field != filter.value)
            elif filter.operator == ">":
                conditions.append(field > filter.value)
            elif filter.operator == ">=":
                conditions.append(field >= filter.value)
            elif filter.operator == "<":
                conditions.append(field < filter.value)
            elif filter.operator == "<=":
                conditions.append(field <= filter.value)
            elif filter.operator == "in":
                conditions.append(field.in_(filter.value))
            elif filter.operator == "not in":
                conditions.append(~field.in_(filter.value))
            elif filter.operator == "is":
                conditions.append(field.is_(filter.value))
            elif filter.operator == "is not":
                conditions.append(field.is_not(filter.value))
            elif filter.operator == "like":
                conditions.append(field.like(filter.value))
            elif filter.operator == "ilike":
                conditions.append(field.ilike(filter.value))
            elif filter.operator == "between":
                conditions.append(field.between(filter.value[0], filter.value[1]))
            elif filter.operator == "not between":
                conditions.append(~field.between(filter.value[0], filter.value[1]))
            else:
                raise ValueError(f"Invalid operator: {filter.operator}")

        if as_or:
            query = query.where(or_(*conditions))
        else:
            query = query.where(*conditions)

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
    user_id: Mapped[PyUUID] = mapped_column(PGUUID, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
