from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import async_scoped_session
from sqlalchemy import text
from contextlib import asynccontextmanager
from asyncio import current_task

from uuid import uuid4
from tenacity import retry, wait_fixed, stop_after_attempt, retry_if_exception_type

from src.core.config import settings
from src.database.models import Base


class DatabaseSessionManager:
    def __init__(self, database_url: str):
        self.engine = create_async_engine(
            database_url,
            pool_size=20,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=60 * 30,
            pool_pre_ping=True,
            connect_args={
                "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
            },
            echo=True if settings.ENVIRONMENT == "development" else False,
        )

        self.session_maker = async_sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine, expire_on_commit=False
        )

        self.session = async_scoped_session(self.session_maker, scopefunc=current_task)

    @retry(
        wait=wait_fixed(2),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def init_db(self):
        async with self.engine.begin() as conn:
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent;"))
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Yield a session for use with FastAPI dependency injection.
        Session commits automatically if no exceptions are raised.
        """
        db_session = self.session()
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise
        finally:
            await db_session.close()

    async def close(self):
        """Close the database engine (used during app shutdown)."""
        await self.engine.dispose()


asession_manager = DatabaseSessionManager(database_url=settings.APOSTGRES_DATABASE_URL)


async def aget_db() -> AsyncGenerator[AsyncSession, None]:
    async with asession_manager.get_session() as session:
        yield session
