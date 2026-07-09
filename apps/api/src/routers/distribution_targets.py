"""
Distribution Target router for RESTful API endpoints.

Provides CRUD operations and OAuth flows for podcast distribution platforms.
Supports Spotify OAuth, Apple Podcasts API key management, webhooks, and
connection testing. All endpoints require authentication and enforce tenant
isolation via RLS.
"""

import logging
import urllib.parse
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import arm_tenant_context, get_db, set_tenant_context
from ..middleware.auth import get_current_user
from ..models import User
from ..schemas.distribution_target import (
	WebhookDistributionCreate,
	AppleDistributionCreate,
	DistributionTargetUpdate,
	DistributionTargetResponse,
	DistributionTargetListResponse,
	SpotifyAuthorizeResponse,
	AppleAuthorizeResponse,
	TestConnectionResponse,
)
from ..services.distribution_target_service import (
	create_webhook_target,
	create_apple_target,
	create_spotify_target,
	get_distribution_targets,
	get_distribution_target_by_id,
	update_distribution_target,
	delete_distribution_target,
	generate_oauth_state,
	validate_oauth_state,
	exchange_spotify_code,
	get_spotify_show_info,
	refresh_spotify_access_token,
	test_connection,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/distribution-targets", tags=["distribution-targets"])


# ============================================================================
# SPOTIFY OAUTH ENDPOINTS
# ============================================================================

@router.post(
	"/spotify/authorize",
	response_model=SpotifyAuthorizeResponse,
)
async def spotify_authorize(
	current_user: User = Depends(get_current_user),
):
	"""
	Initiate Spotify OAuth authorization flow.

	Generates an authorization URL with a CSRF state token.
	User should be redirected to the returned authorize_url to authenticate
	with Spotify. The state token must be preserved for callback validation.

	Args:
		current_user: Authenticated user (from JWT token)

	Returns:
		Authorization URL and state token for CSRF protection

	Raises:
		HTTPException: 503 if Spotify OAuth not configured
	"""
	client_id = settings.SPOTIFY_CLIENT_ID
	redirect_uri = settings.SPOTIFY_REDIRECT_URI

	if not client_id or not redirect_uri:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail="Spotify OAuth is not configured on this server"
		)

	state = generate_oauth_state(str(current_user.id))

	# Build Spotify authorization URL
	params = urllib.parse.urlencode({
		"client_id": client_id,
		"response_type": "code",
		"redirect_uri": redirect_uri,
		"scope": "user-read-email",
		"state": state,
	})
	authorize_url = f"https://accounts.spotify.com/authorize?{params}"

	return SpotifyAuthorizeResponse(
		authorize_url=authorize_url,
		state=state,
	)


@router.get("/spotify/callback")
async def spotify_callback(
	code: str = Query(..., description="Authorization code from Spotify"),
	state: str = Query(..., description="CSRF state token"),
	db: AsyncSession = Depends(get_db),
):
	"""
	Handle Spotify OAuth callback.

	Validates the CSRF state token, exchanges the authorization code for
	access and refresh tokens, encrypts them, and creates a DistributionTarget
	record. Redirects to a success page on completion.

	Args:
		code: Authorization code from Spotify
		state: CSRF state token (must match generated state)
		db: Database session

	Returns:
		Redirect to success page with target_id, or JSON response with target

	Raises:
		HTTPException: 400 if state is invalid or token exchange fails
	"""
	# Validate CSRF state token
	user_id_str = validate_oauth_state(state)
	if not user_id_str:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Invalid or expired OAuth state token"
		)

	client_id = settings.SPOTIFY_CLIENT_ID
	client_secret = settings.SPOTIFY_CLIENT_SECRET
	redirect_uri = settings.SPOTIFY_REDIRECT_URI

	if not client_id or not client_secret or not redirect_uri:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail="Spotify OAuth is not configured on this server"
		)

	# Exchange authorization code for tokens
	try:
		token_data = await exchange_spotify_code(
			client_id=client_id,
			client_secret=client_secret,
			redirect_uri=redirect_uri,
			code=code,
		)
	except Exception as e:
		logger.warning("Spotify token exchange failed: %s", type(e).__name__)
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Failed to exchange Spotify authorization code"
		)

	access_token = token_data.get("access_token")
	refresh_token = token_data.get("refresh_token")
	expires_in = token_data.get("expires_in", 3600)

	if not access_token or not refresh_token:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Incomplete token response from Spotify"
		)

	# Fetch show info to get show_id and name
	try:
		show_info = await get_spotify_show_info(access_token)
	except Exception:
		show_info = {"id": "", "name": ""}

	# Look up the user's tenant via the SECURITY DEFINER bootstrap (#304):
	# this callback is a browser redirect from Spotify with no JWT, so no
	# tenant context is armed and a plain users SELECT would see nothing.
	user_result = await db.execute(
		text("SELECT id, tenant_id FROM auth_lookup_user_by_id(:uid)"),
		{"uid": UUID(user_id_str)},
	)
	db_user = user_result.one_or_none()

	if not db_user:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="User not found",
		)

	# Arm + set the user's tenant so the distribution_targets INSERT below
	# passes the scoped WITH CHECK policy.
	arm_tenant_context(db, str(db_user.tenant_id))
	await set_tenant_context(db, str(db_user.tenant_id))

	# Create distribution target
	target = await create_spotify_target(
		db=db,
		user_id=db_user.id,
		tenant_id=db_user.tenant_id,
		access_token=access_token,
		refresh_token=refresh_token,
		expires_in=expires_in,
		show_id=show_info.get("id", ""),
		show_name=show_info.get("name", ""),
	)

	return DistributionTargetResponse.from_orm_model(target)


# ============================================================================
# APPLE PODCASTS ENDPOINTS
# ============================================================================

@router.post(
	"/apple/authorize",
	response_model=AppleAuthorizeResponse,
)
async def apple_authorize(
	current_user: User = Depends(get_current_user),
):
	"""
	Get Apple Podcasts connection setup instructions.

	Apple Podcasts requires manual API key generation through the
	Podcasts Connect portal. This endpoint returns instructions and links.

	Args:
		current_user: Authenticated user (from JWT token)

	Returns:
		Setup instructions and links for Apple Podcasts connection
	"""
	return AppleAuthorizeResponse(
		message=(
			"Apple Podcasts requires a manually generated API key from "
			"Podcasts Connect. Follow the setup instructions to obtain your "
			"API key, then use POST /distribution-targets/apple to connect."
		),
		podcasts_connect_url="https://podcastsconnect.apple.com",
		setup_instructions="https://help.apple.com/itc/podcasts_connect/#/itcb54353390",
	)


@router.post(
	"/apple",
	response_model=DistributionTargetResponse,
	status_code=status.HTTP_201_CREATED,
)
async def create_apple_target_endpoint(
	apple_data: AppleDistributionCreate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Create Apple Podcasts distribution target.

	Validates and encrypts the Apple Podcasts API key before storage.
	The API key is never returned in responses.

	Args:
		apple_data: Apple Podcasts connection data (show_id + api_key)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Created distribution target (without credentials)
	"""
	target = await create_apple_target(
		db=db,
		user_id=current_user.id,
		tenant_id=current_user.tenant_id,
		apple_data=apple_data,
	)
	return DistributionTargetResponse.from_orm_model(target)


# ============================================================================
# WEBHOOK ENDPOINT
# ============================================================================

@router.post(
	"/webhook",
	response_model=DistributionTargetResponse,
	status_code=status.HTTP_201_CREATED,
)
async def create_webhook_target_endpoint(
	webhook_data: WebhookDistributionCreate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Create webhook distribution target.

	Validates the webhook URL (must be HTTPS), method, and headers.
	The webhook configuration is stored securely.

	Args:
		webhook_data: Webhook creation data with URL, method, and optional headers
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Created distribution target (configuration not exposed in response)
	"""
	target = await create_webhook_target(
		db=db,
		user_id=current_user.id,
		tenant_id=current_user.tenant_id,
		webhook_data=webhook_data,
	)
	return DistributionTargetResponse.from_orm_model(target)


# ============================================================================
# CRUD ENDPOINTS
# ============================================================================

@router.get(
	"",
	response_model=DistributionTargetListResponse,
)
async def list_distribution_targets(
	page: int = Query(1, ge=1, description="Page number (1-indexed)"),
	page_size: int = Query(20, ge=1, le=100, description="Items per page"),
	target_type: Optional[str] = Query(None, description="Filter by platform type"),
	project_id: Optional[UUID] = Query(None, description="Filter by project ID"),
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	List distribution targets with pagination and optional filtering.

	Automatically filtered by user's tenant via RLS. Supports filtering
	by platform type (spotify, apple_podcasts, webhook) and project.

	Args:
		page: Page number (1-indexed)
		page_size: Items per page (1-100)
		target_type: Optional platform type filter
		project_id: Optional project filter
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Paginated list of distribution targets with metadata
	"""
	skip = (page - 1) * page_size
	targets, total = await get_distribution_targets(
		db=db,
		skip=skip,
		limit=page_size,
		target_type=target_type,
		project_id=project_id,
	)

	total_pages = (total + page_size - 1) // page_size if total > 0 else 0

	return DistributionTargetListResponse(
		targets=[DistributionTargetResponse.from_orm_model(t) for t in targets],
		total=total,
		page=page,
		page_size=page_size,
		total_pages=total_pages,
	)


@router.get(
	"/{target_id}",
	response_model=DistributionTargetResponse,
)
async def get_distribution_target(
	target_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Get distribution target details by ID.

	Returns 404 if target doesn't exist or belongs to different tenant.
	Never returns encrypted credentials in the response.

	Args:
		target_id: UUID of target to retrieve
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Distribution target details (without credentials)

	Raises:
		HTTPException: 404 if target not found or different tenant
	"""
	target = await get_distribution_target_by_id(db=db, target_id=target_id)

	if target is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Distribution target not found"
		)

	return DistributionTargetResponse.from_orm_model(target)


@router.put(
	"/{target_id}",
	response_model=DistributionTargetResponse,
)
async def update_distribution_target_endpoint(
	target_id: UUID,
	update_data: DistributionTargetUpdate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Update distribution target.

	Supports updating is_active status. Credential updates are not
	allowed through this endpoint - use platform re-authorization instead.

	Args:
		target_id: UUID of target to update
		update_data: Update data (only provided fields will be updated)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Updated distribution target

	Raises:
		HTTPException: 404 if target not found or different tenant
	"""
	target = await get_distribution_target_by_id(db=db, target_id=target_id)

	if target is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Distribution target not found"
		)

	updated = await update_distribution_target(
		db=db,
		target=target,
		update_data=update_data,
	)
	return DistributionTargetResponse.from_orm_model(updated)


@router.delete(
	"/{target_id}",
	status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_distribution_target_endpoint(
	target_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Delete/disconnect distribution target.

	Permanently deletes the distribution target record.
	For Spotify: OAuth token revocation is best-effort and may not always succeed.

	Args:
		target_id: UUID of target to delete
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		None (204 No Content)

	Raises:
		HTTPException: 404 if target not found or different tenant
	"""
	target = await get_distribution_target_by_id(db=db, target_id=target_id)

	if target is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Distribution target not found"
		)

	await delete_distribution_target(db=db, target=target)
	return None


@router.post(
	"/{target_id}/refresh-token",
	response_model=DistributionTargetResponse,
)
async def refresh_token_endpoint(
	target_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Refresh Spotify OAuth access token.

	Uses the stored refresh token to obtain a new access token from Spotify.
	Only applicable to Spotify distribution targets.

	Args:
		target_id: UUID of Spotify distribution target
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Updated distribution target with new token expiration

	Raises:
		HTTPException: 404 if target not found, 400 if not Spotify target
	"""
	target = await get_distribution_target_by_id(db=db, target_id=target_id)

	if target is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Distribution target not found"
		)

	if target.target_type != "spotify":
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Token refresh is only supported for Spotify distribution targets"
		)

	client_id = settings.SPOTIFY_CLIENT_ID
	client_secret = settings.SPOTIFY_CLIENT_SECRET

	if not client_id or not client_secret:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail="Spotify OAuth is not configured on this server"
		)

	try:
		updated = await refresh_spotify_access_token(
			db=db,
			target=target,
			client_id=client_id,
			client_secret=client_secret,
		)
	except ValueError as e:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=str(e)
		)
	except Exception:
		logger.warning("Spotify token refresh failed for target %s", target_id)
		raise HTTPException(
			status_code=status.HTTP_502_BAD_GATEWAY,
			detail="Failed to refresh Spotify access token"
		)

	return DistributionTargetResponse.from_orm_model(updated)


@router.post(
	"/{target_id}/test",
	response_model=TestConnectionResponse,
)
async def test_connection_endpoint(
	target_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Test connectivity to a distribution platform.

	For Spotify: Verifies token validity by fetching show information.
	For Apple Podcasts: Validates stored credentials are accessible.
	For webhooks: Sends a test payload to the configured URL.

	Args:
		target_id: UUID of distribution target to test
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Connection test result with success status and details

	Raises:
		HTTPException: 404 if target not found or different tenant
	"""
	target = await get_distribution_target_by_id(db=db, target_id=target_id)

	if target is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Distribution target not found"
		)

	result = await test_connection(
		db=db,
		target=target,
		spotify_client_id=settings.SPOTIFY_CLIENT_ID,
		spotify_client_secret=settings.SPOTIFY_CLIENT_SECRET,
	)

	return TestConnectionResponse(**result)
