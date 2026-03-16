"""
CORS middleware configuration for separate frontend deployment
"""
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI

from src.config import settings


def setup_cors(app: FastAPI) -> None:
    """
    Configure CORS middleware with restricted, explicit permissions.

    Only the methods and headers required by the frontend are allowed.
    This follows the principle of least privilege and reduces the attack
    surface for cross-origin requests.

    Args:
        app: FastAPI application instance
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
        max_age=3600,  # Cache preflight requests for 1 hour
        expose_headers=[
            "X-Total-Count",
            "X-Page-Number",
            "Content-Disposition",
        ],
    )
