from __future__ import annotations

import os
from functools import lru_cache
from typing import Generator
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

DEFAULT_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
ETENDERS_SOURCE_ID = UUID("00000000-0000-0000-0000-000000000002")


def normalize_database_url(database_url: str) -> str:
    """Use the installed psycopg 3 driver for common hosted PostgreSQL URLs."""
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url[len("postgres://"):]
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://"):]
    return database_url


@lru_cache(maxsize=4)
def engine_for_url(database_url: str) -> Engine:
    return create_engine(normalize_database_url(database_url), pool_pre_ping=True, pool_size=5, max_overflow=5, connect_args={"connect_timeout": 3})


def configured_database_url() -> str | None:
    value = os.getenv("DATABASE_URL") or os.getenv("ARLETION_TEST_DATABASE_URL")
    return normalize_database_url(value) if value else None


def get_session() -> Generator[Session, None, None]:
    database_url = configured_database_url()
    if not database_url:
        raise HTTPException(
            status_code=503,
            detail="Database is not configured. Set DATABASE_URL and apply migrations, or explicitly enable ARLETION_DEMO_MODE for fixtures.",
        )
    try:
        factory = sessionmaker(bind=engine_for_url(database_url), expire_on_commit=False)
        with factory() as session:
            session.execute(text("SELECT 1"))
            yield session
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable or not migrated: {error.__class__.__name__}. Verify DATABASE_URL and run `alembic upgrade head`.",
        ) from error


def db_health() -> dict[str, str | bool]:
    url = configured_database_url()
    if not url:
        return {"configured": False, "connected": False, "detail": "DATABASE_URL is not configured"}
    try:
        with engine_for_url(url).connect() as connection:
            tables = set(inspect(connection).get_table_names())
            missing = set(Base.metadata.tables) - tables
            if missing:
                return {"configured": True, "connected": False, "detail": f"Database schema is incomplete; missing tables: {', '.join(sorted(missing))}. Run `alembic upgrade head`."}
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
            if version != "0002_seed_reference_rows":
                return {"configured": True, "connected": False, "detail": f"Database migration revision is {version or 'unset'}; expected 0002_seed_reference_rows. Run `alembic upgrade head`."}
        return {"configured": True, "connected": True, "detail": "PostgreSQL connection, schema and migration revision verified"}
    except SQLAlchemyError as error:
        return {"configured": True, "connected": False, "detail": f"{error.__class__.__name__}: verify database credentials and migrations"}
