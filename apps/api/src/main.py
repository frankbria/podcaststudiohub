"""
Main FastAPI application for Podcastfy GUI API
"""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import logging

from src.config import settings
from src.middleware.cors import setup_cors
from src.middleware.tenant import TenantContextMiddleware

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Multi-tenant SaaS platform for AI-generated podcasts",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Setup CORS middleware
setup_cors(app)

# Add tenant context middleware
app.add_middleware(TenantContextMiddleware)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Podcastfy API",
        "version": settings.APP_VERSION,
        "docs": "/docs"
    }


@app.on_event("startup")
async def verify_dependencies():
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


@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers"""
    return {"status": "healthy", "version": settings.APP_VERSION}


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
    """Custom 500 handler"""
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
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
