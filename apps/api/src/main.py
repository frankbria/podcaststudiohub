"""
Main FastAPI application for Podcastfy GUI API
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
import logging

from src.config import settings
from src.dependencies import meter_api_call
from src.logging_config import REQUEST_ID_HEADER, init_sentry, setup_logging
from src.middleware.correlation import CorrelationIdMiddleware
from src.middleware.cors import setup_cors
from src.middleware.tenant import TenantContextMiddleware

# Structured logging + error tracking (issue #320). setup_logging replaces the
# old basicConfig; init_sentry is a no-op unless SENTRY_DSN is set.
setup_logging()
init_sentry()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify critical dependencies are available at startup"""
    try:
        from podcastfy.client import generate_podcast  # noqa: F401
        from podcastfy.content_generator import ContentGenerator  # noqa: F401
        from podcastfy.content_parser.website_extractor import WebsiteExtractor  # noqa: F401
        from podcastfy.content_parser.pdf_extractor import PDFExtractor  # noqa: F401
        logger.info("Podcastfy dependencies verified")
    except ImportError as e:
        logger.critical(f"Failed to import podcastfy: {e}")
        logger.critical("Run: uv sync to install dependencies")
        raise RuntimeError("Podcastfy not installed") from e
    yield


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Multi-tenant SaaS platform for AI-generated podcasts",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    # Boundary metering: count + enforce per-period API quota on every request
    # (no-op for public/unauthenticated paths). See dependencies.meter_api_call.
    dependencies=[Depends(meter_api_call)],
    lifespan=lifespan,
)

# Setup CORS middleware
setup_cors(app)

# Add tenant context middleware
app.add_middleware(TenantContextMiddleware)

# Correlation ID middleware is added LAST so it is OUTERMOST: Starlette applies
# add_middleware in LIFO order, and the request id must be bound before CORS and
# tenant resolution run so their log lines carry it too (issue #320).
app.add_middleware(CorrelationIdMiddleware)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Podcastfy API",
        "version": settings.APP_VERSION,
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Liveness probe: is this process up?

    Deliberately checks nothing external. A dependency outage must not make this
    fail, or a supervisor would restart a perfectly healthy process and turn a
    Redis blip into an API outage. Use /ready to gate traffic (issue #320).
    """
    return {"status": "healthy", "version": settings.APP_VERSION}


async def _check_database() -> None:
    """Round-trip the DB. Raises on failure."""
    from sqlalchemy import text

    from src.database import engine

    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _check_redis() -> None:
    """Round-trip Redis. Raises on failure."""
    # redis>=5 ships redis.asyncio, so this needs no new dependency.
    from redis.asyncio import from_url

    client = from_url(settings.REDIS_URL)
    try:
        await client.ping()
    finally:
        await client.aclose()


@app.get("/ready")
async def readiness_check():
    """Readiness probe: can this process actually serve traffic?

    Checks the dependencies a request needs (Postgres, Redis) and returns 503 if
    either is unreachable, so the deploy gate and uptime monitoring fail loudly
    instead of reporting green through a brownout (issue #320).
    """
    checks: dict[str, str] = {}
    for name, check in (("database", _check_database), ("redis", _check_redis)):
        try:
            # A hung dependency must fail the probe fast rather than hang it:
            # without this the probe blocks until the caller's own timeout and
            # the gate can't tell "slow" from "down".
            await asyncio.wait_for(
                check(), timeout=settings.READINESS_CHECK_TIMEOUT_SECONDS
            )
            checks[name] = "ok"
        except Exception as e:
            # Log the cause (the response deliberately doesn't carry it: /ready
            # is unauthenticated, and connection errors quote DSNs/hostnames).
            logger.error("Readiness check failed for %s: %s", name, e, exc_info=True)
            checks[name] = "error"

    if all(status == "ok" for status in checks.values()):
        return {"status": "ready", "version": settings.APP_VERSION, "checks": checks}

    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "version": settings.APP_VERSION, "checks": checks},
    )


@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Custom 404 handler"""
    # Preserve the detail from HTTPException raised by route handlers.
    # Starlette uses detail="Not Found" for unmatched routes; remap that to
    # our user-facing message so endpoint-raised 404s pass their own detail.
    detail = getattr(exc, 'detail', 'Endpoint not found')
    if detail == "Not Found":
        detail = "Endpoint not found"
    return JSONResponse(
        status_code=404,
        content={"detail": detail}
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Custom 500 handler.

    Re-stamps X-Request-ID because this handler runs in Starlette's
    ServerErrorMiddleware, which sits OUTSIDE CorrelationIdMiddleware: an
    unhandled exception propagates past that middleware before it can set the
    header, so a 500 would otherwise be the one response with no id — exactly
    the response a user needs an id for when reporting the failure. The
    contextvar is already unwound by here, so read request.state (set before
    call_next) and pass the id explicitly to the log record (issue #320).
    """
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "Internal server error: %s", exc, exc_info=True,
        extra={"request_id": request_id} if request_id else {},
    )
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers=headers,
    )


# Register routers - User Story 1 (Basic Podcast Generation)
from src.routers import auth, projects, episodes, content, generation, episode_layouts, audio_snippets, conversation_templates  # noqa: E402
from src.routers.rss_feed import router as rss_feed_router, public_router as rss_public_router  # noqa: E402
# Register routers - User Story 2 (Distribution Target Management, GAP-010)
from src.routers import distribution_targets  # noqa: E402
# Register routers - TTS Configuration CRUD (GAP-006)
from src.routers import tts_configurations  # noqa: E402
# Register routers - Quality Metrics, GAP-014
from src.routers import quality_metrics  # noqa: E402
# Register routers - Team Collaboration, GAP-051
from src.routers import teams  # noqa: E402
# Register routers - Billing & Subscriptions, GAP-050
from src.routers import billing  # noqa: E402
# Register routers - Analytics & Usage Tracking, GAP-049
from src.routers import analytics  # noqa: E402

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(episodes.router)
app.include_router(content.router)
app.include_router(generation.router)
app.include_router(distribution_targets.router)
app.include_router(episode_layouts.router)
app.include_router(audio_snippets.router)
app.include_router(conversation_templates.router)
app.include_router(tts_configurations.router)
app.include_router(quality_metrics.router)
app.include_router(teams.router)
app.include_router(billing.router)
app.include_router(analytics.router)

# RSS Feed routers - GAP-011
app.include_router(rss_feed_router)
app.include_router(rss_public_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
