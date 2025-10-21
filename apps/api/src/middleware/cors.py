"""
CORS middleware configuration for separate frontend deployment
"""
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI

from src.config import settings


def setup_cors(app: FastAPI) -> None:
    """
    Configure CORS middleware for the FastAPI application.

    This allows the frontend (deployed at a different URL) to make
    requests to the backend API.

    Args:
        app: FastAPI application instance
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )
