"""
Async database configuration and session management
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import create_engine, text
from typing import AsyncGenerator
from fastapi import Request

from src.config import settings

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Lazy synchronous engine for Celery tasks (cannot use async sessions in Celery).
# Deferred so that importing this module doesn't crash when DATABASE_URL isn't
# a PostgreSQL asyncpg URL (e.g. in test environments using SQLite).
_sync_engine = None
_sync_session_factory = None


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        db_url = settings.DATABASE_URL
        if not db_url.startswith("postgresql+asyncpg://"):
            raise ValueError(
                f"DATABASE_URL must use the 'postgresql+asyncpg://' driver prefix, "
                f"got: {db_url.split('://')[0]}://"
            )
        _sync_engine = create_engine(
            db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"),
            echo=settings.DEBUG,
            pool_pre_ping=True,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
        )
    return _sync_engine


def SyncSessionLocal():
    """Synchronous session factory for Celery tasks — lazily creates the engine."""
    global _sync_session_factory
    if _sync_session_factory is None:
        _sync_session_factory = sessionmaker(
            bind=_get_sync_engine(),
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _sync_session_factory()


# Base class for SQLAlchemy models
Base = declarative_base()


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database sessions with tenant context.

    This dependency:
    1. Creates a new database session
    2. If request.state.tenant_id is set, configures PostgreSQL RLS context
    3. Sets app.tenant_id session variable for Row-Level Security policies
    4. Yields the session for use in route handlers
    5. Commits or rolls back based on success/failure

    Usage:
        @app.get("/projects")
        async def list_projects(db: AsyncSession = Depends(get_db)):
            # RLS policies will automatically filter by tenant_id
            result = await db.execute(select(Project))
            return result.scalars().all()

    Args:
        request: FastAPI request (injected by FastAPI automatically)
    """
    async with AsyncSessionLocal() as session:
        try:
            # Arm tenant context for RLS if available. Armed (event-based), not
            # a one-shot SET LOCAL: mid-request commits (e.g. the global
            # usage-metering dependency) end the transaction, which reverts the
            # custom GUC to defined-but-empty ('') and makes every later RLS
            # policy evaluation raise `invalid input syntax for type uuid: ""`
            # (issue #302). The event re-issues SET LOCAL on every begin.
            if hasattr(request.state, 'tenant_id') and request.state.tenant_id:
                arm_tenant_context(session, str(request.state.tenant_id))

            yield session
            await session.commit()
        except ValueError:
            # Invalid tenant_id format — treat as auth failure
            from fastapi import HTTPException, status
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid tenant context",
            )
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Alias for backwards compatibility
async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    Backwards compatible alias for get_db_session.

    This allows existing code to continue using get_db as the dependency name.
    """
    async for session in get_db_session(request):
        yield session


def get_streaming_session_factory() -> async_sessionmaker[AsyncSession]:
    """Session factory for work that outlives the request scope (e.g. SSE).

    Returns ``AsyncSessionLocal`` so callers can open a fresh, short-lived
    session per iteration instead of holding the request-scoped session for the
    life of a long stream (issue #220). Exposed as a FastAPI dependency so tests
    can override it to bind to the test engine — otherwise the SSE generator
    would open connections on the module-global engine, leaking asyncpg pools
    across pytest's per-test event loops.
    """
    return AsyncSessionLocal


def arm_tenant_context(db: AsyncSession, tenant_id: str) -> None:
    """
    Keep ``app.tenant_id`` set for EVERY transaction of this session.

    ``SET LOCAL`` only lives until the current transaction ends, and any
    mid-request commit leaves the custom GUC defined-but-empty (``''``) on the
    pooled connection — after which RLS policies raise
    ``invalid input syntax for type uuid: ""`` on every filtered SELECT
    (issue #302). Registering an ``after_begin`` listener re-issues SET LOCAL
    at the start of each transaction, so tenant context survives commits for
    the life of the request session. The listener dies with the session.

    Args:
        db: Async database session (request-scoped)
        tenant_id: UUID of the tenant (as string)

    Raises:
        ValueError: If tenant_id is not a valid UUID format
    """
    from uuid import UUID

    from sqlalchemy import event

    # Validate AND normalize: UUID() accepts forms Postgres' ::uuid cast
    # rejects (urn:uuid: prefix, surrounding whitespace) — interpolating the
    # raw input would make every later RLS evaluation raise the exact
    # `invalid input syntax for type uuid` this helper exists to prevent.
    # str(parsed) is always the canonical hex-with-dashes form, which also
    # closes SQL injection (SET LOCAL cannot take bind parameters).
    try:
        parsed = str(UUID(tenant_id))
    except (ValueError, TypeError):
        raise ValueError(f"Invalid tenant_id format: {tenant_id}")

    # Re-arming the same session must not stack duplicate listeners.
    if db.sync_session.info.get("armed_tenant_id") == parsed:
        return
    db.sync_session.info["armed_tenant_id"] = parsed

    # Sync listener on the sync_session is intentional: after_begin fires
    # inside the AsyncSession greenlet bridge, where exec_driver_sql on the
    # (sync) Connection is the supported SQLAlchemy 2.0 pattern — do not
    # convert this to an await.
    @event.listens_for(db.sync_session, "after_begin")
    def _set_tenant(sync_session, transaction, connection) -> None:
        connection.exec_driver_sql(f"SET LOCAL app.tenant_id = '{parsed}'")


async def set_tenant_context(db: AsyncSession, tenant_id: str) -> None:
    """
    Manually set the tenant_id in PostgreSQL session for Row-Level Security.

    This is typically not needed as get_db() handles it automatically.
    Use this only for manual session management outside of request context.

    PostgreSQL's SET LOCAL command doesn't support bind parameters, so we
    validate the tenant_id is a valid UUID before using it in the query.

    Args:
        db: Async database session
        tenant_id: UUID of the tenant (as string)

    Raises:
        ValueError: If tenant_id is not a valid UUID format
    """
    from uuid import UUID

    # Validate and normalize (see arm_tenant_context for why str(UUID(...))).
    try:
        parsed = str(UUID(tenant_id))
    except (ValueError, TypeError):
        raise ValueError(f"Invalid tenant_id format: {tenant_id}")

    # Arm future transactions too, so a later commit on this session cannot
    # silently strip RLS context (#302) — one-shot and armed behavior stay
    # uniform by construction.
    arm_tenant_context(db, parsed)

    # And set the CURRENT transaction: callers invoke this mid-transaction
    # (e.g. auth register flow), where after_begin has already fired.
    # PostgreSQL SET LOCAL doesn't support bind parameters; parsed is a
    # canonical UUID string.
    await db.execute(text(f"SET LOCAL app.tenant_id = '{parsed}'"))
