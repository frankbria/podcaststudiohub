"""
RSS feed validation router.

Endpoints:
  POST /projects/{project_id}/rss-feed/validate  - Run validation and store results
  GET  /projects/{project_id}/rss-feed/validation - Return last stored results
"""

import logging
import xml.etree.ElementTree as ET
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies import get_current_user
from ..models.user import User
from ..schemas.rss_feed import ValidationStatusUpdate
from ..services.rss_validation_service import RSSFetchError, RSSValidationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["RSS Validation"])


class ValidateRequest(BaseModel):
	"""Optional request body for the validate endpoint.

	Supplying rss_content bypasses S3/URL fetching and validates
	the provided XML directly. Useful for testing and direct validation.
	"""

	rss_content: Optional[str] = None


@router.post(
	"/{project_id}/rss-feed/validate",
	response_model=ValidationStatusUpdate,
	summary="Validate RSS feed against podcast directories",
)
async def validate_rss_feed(
	project_id: UUID,
	body: ValidateRequest = ValidateRequest(),
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Validate the project's RSS feed against Apple Podcasts, Spotify, and Google Podcasts
	requirements.

	Fetches the generated feed from RSSFeed.public_url or RSSFeed.s3_key unless
	rss_content is supplied in the request body (for direct validation without storage).

	Results are persisted in RSSFeed.validation_status.

	Returns 404 if no RSS feed has been generated yet for this project.
	Returns 422 if the RSS content is not valid XML.
	"""
	service = RSSValidationService()
	try:
		result = await service.validate_rss_feed(
			db=db,
			project_id=project_id,
			tenant_id=current_user.tenant_id,
			rss_content=body.rss_content,
		)
		return result
	except RSSFetchError as exc:
		logger.error("RSS feed fetch failed for project %s: %s", project_id, exc)
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail=str(exc),
		)
	except ValueError as exc:
		msg = str(exc)
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=msg,
		)
	except ET.ParseError as exc:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail=f"Invalid RSS feed: {exc}",
		)
	except Exception as exc:
		logger.error("RSS validation failed for project %s: %s", project_id, exc)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="RSS validation failed",
		)


@router.get(
	"/{project_id}/rss-feed/validation",
	response_model=ValidationStatusUpdate,
	summary="Get last RSS feed validation results",
)
async def get_rss_validation(
	project_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Return the last stored validation results for the project's RSS feed.

	Results are populated by calling POST /projects/{project_id}/rss-feed/validate.

	Returns 404 if no validation has been run yet or if no RSS feed exists.
	"""
	service = RSSValidationService()
	try:
		result = await service.get_validation_status(
			db=db,
			project_id=project_id,
			tenant_id=current_user.tenant_id,
		)
		return result
	except ValueError as exc:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=str(exc),
		)
	except Exception as exc:
		logger.error("Failed to retrieve validation status for project %s: %s", project_id, exc)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to retrieve validation status",
		)
