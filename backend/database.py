"""
Riskism Database Connection & Session Management
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from backend.config import get_settings

settings = get_settings()

# Sync engine (for Celery tasks)
sync_engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=5)
SyncSessionLocal = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)

# Async engine (for FastAPI)
async_engine = create_async_engine(settings.async_database_url, pool_pre_ping=True, pool_size=10)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency for async DB sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def get_sync_db():
    """Sync DB session for Celery tasks."""
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()
