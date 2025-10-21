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


@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers"""
    return {"status": "healthy", "version": settings.APP_VERSION}


@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Custom 404 handler"""
    return JSONResponse(
        status_code=404,
        content={"detail": "Endpoint not found"}
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
from src.routers import auth, projects, episodes, content, generation

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(episodes.router)
app.include_router(content.router)
app.include_router(generation.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
