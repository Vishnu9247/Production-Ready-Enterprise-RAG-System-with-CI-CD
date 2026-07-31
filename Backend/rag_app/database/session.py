"""PostgreSQL engine and session construction."""

from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import Settings


def create_postgres_engine(settings: Settings) -> Engine:
    settings.require_database()
    url = URL.create(
        drivername="postgresql+psycopg",
        username=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_database,
        query={"sslmode": settings.postgres_sslmode},
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
    )


def create_session_factory(settings: Settings) -> sessionmaker[Session]:
    return sessionmaker(
        bind=create_postgres_engine(settings),
        class_=Session,
        expire_on_commit=False,
    )
