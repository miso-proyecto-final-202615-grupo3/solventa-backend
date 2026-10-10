from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autoflush=False,
)
