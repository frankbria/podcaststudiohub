"""
Distribution Target schemas for request/response validation.

Defines Pydantic models for DistributionTarget CRUD operations with
validation for webhook URLs, OAuth flows, and pagination support.
"""

from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime, timezone
from typing import Optional, Literal


class WebhookDistributionCreate(BaseModel):
	"""Schema for creating a webhook distribution target."""

	name: str = Field(
		...,
		min_length=1,
		max_length=255,
		description="Human-readable name for the webhook"
	)
	url: str = Field(
		...,
		max_length=500,
		description="HTTPS URL for the webhook endpoint"
	)
	method: Literal["POST", "GET"] = Field(
		default="POST",
		description="HTTP method (POST or GET)"
	)
	project_id: Optional[UUID] = Field(
		None,
		description="Optional project to scope this target to"
	)
	headers: Optional[dict[str, str]] = Field(
		None,
		description="Optional HTTP headers to include in webhook requests"
	)

	@field_validator("url")
	@classmethod
	def validate_https_url(cls, v: str) -> str:
		"""Validate that URL uses HTTPS and is well-formed."""
		if not v.startswith("https://"):
			raise ValueError("Webhook URL must use HTTPS (not HTTP)")
		if len(v) > 500:
			raise ValueError("Webhook URL must not exceed 500 characters")
		return v

	@field_validator("headers")
	@classmethod
	def validate_headers(cls, v: Optional[dict]) -> Optional[dict]:
		"""Validate header count and value lengths."""
		if v is None:
			return v
		if len(v) > 10:
			raise ValueError("Maximum 10 headers allowed per webhook")
		for key, value in v.items():
			if len(str(value)) > 500:
				raise ValueError(f"Header value for '{key}' exceeds 500 characters")
		return v


class AppleDistributionCreate(BaseModel):
	"""Schema for creating an Apple Podcasts distribution target."""

	show_id: str = Field(
		...,
		min_length=1,
		max_length=255,
		description="Apple Podcasts show identifier"
	)
	api_key: str = Field(
		...,
		min_length=1,
		description="Apple Podcasts Connect API key"
	)
	project_id: Optional[UUID] = Field(
		None,
		description="Optional project to scope this target to"
	)


class DistributionTargetUpdate(BaseModel):
	"""Schema for updating a distribution target. All fields optional."""

	is_active: Optional[bool] = Field(
		None,
		description="Activation status of the distribution target"
	)


class DistributionTargetResponse(BaseModel):
	"""Schema for distribution target response data."""

	id: UUID
	user_id: UUID
	tenant_id: UUID
	project_id: Optional[UUID]
	target_type: str
	is_active: bool
	created_at: datetime
	updated_at: datetime

	# Derived from config JSONB (safe, non-credential fields only)
	show_id: Optional[str] = None
	platform_name: Optional[str] = None
	token_expires_at: Optional[datetime] = None
	token_valid: Optional[bool] = None

	model_config = {"from_attributes": True}

	@classmethod
	def from_orm_model(cls, target) -> "DistributionTargetResponse":
		"""
		Create response from ORM model, extracting safe config fields.

		Never returns encrypted credentials. Only safe metadata fields
		(show_id, platform_name, token expiration) are included.
		"""
		config = target.config or {}

		# Extract show_id (safe, non-credential)
		show_id = config.get("show_id")

		# Derive platform name from type and config
		if target.target_type == "spotify":
			show_name = config.get("show_name", "")
			platform_name = f"Spotify: {show_name}" if show_name else "Spotify"
		elif target.target_type == "apple_podcasts":
			show_name = config.get("show_name", "")
			platform_name = f"Apple Podcasts: {show_name}" if show_name else "Apple Podcasts"
		elif target.target_type == "webhook":
			platform_name = config.get("name", "Webhook")
		else:
			platform_name = target.target_type

		# Extract token expiration for Spotify (never the token itself)
		token_expires_at = None
		token_valid = None
		if target.target_type == "spotify":
			oauth_tokens = config.get("oauth_tokens", {})
			expires_str = oauth_tokens.get("expires_at")
			if expires_str:
				try:
					# Parse ISO format, handle Z suffix
					expires_str_clean = expires_str.replace("Z", "+00:00")
					token_expires_at = datetime.fromisoformat(expires_str_clean)
					token_valid = token_expires_at > datetime.now(timezone.utc)
				except (ValueError, TypeError):
					pass

		return cls(
			id=target.id,
			user_id=target.user_id,
			tenant_id=target.tenant_id,
			project_id=target.project_id,
			target_type=target.target_type,
			is_active=target.is_active,
			created_at=target.created_at,
			updated_at=target.updated_at,
			show_id=show_id,
			platform_name=platform_name,
			token_expires_at=token_expires_at,
			token_valid=token_valid,
		)


class DistributionTargetListResponse(BaseModel):
	"""Schema for paginated distribution target list response."""

	targets: list[DistributionTargetResponse]
	total: int = Field(..., description="Total count of distribution targets")
	page: int = Field(..., description="Current page number")
	page_size: int = Field(..., description="Items per page")
	total_pages: int = Field(..., description="Total number of pages")


class SpotifyAuthorizeResponse(BaseModel):
	"""Schema for Spotify OAuth authorization URL response."""

	authorize_url: str = Field(
		...,
		description="Spotify OAuth authorization URL for user to visit"
	)
	state: str = Field(
		...,
		description="CSRF state token (store and validate on callback)"
	)


class AppleAuthorizeResponse(BaseModel):
	"""Schema for Apple Podcasts setup instructions response."""

	message: str = Field(
		...,
		description="Instructions for setting up Apple Podcasts connection"
	)
	podcasts_connect_url: str = Field(
		...,
		description="URL for Apple Podcasts Connect portal"
	)
	setup_instructions: str = Field(
		...,
		description="Link to detailed setup documentation"
	)


class TestConnectionResponse(BaseModel):
	"""Schema for connection test result."""

	success: bool = Field(
		...,
		description="Whether the connection test was successful"
	)
	platform: str = Field(
		...,
		description="Platform type that was tested"
	)
	message: str = Field(
		...,
		description="Human-readable result message"
	)
	show_details: Optional[dict] = Field(
		None,
		description="Platform-specific show details (if available)"
	)
	error: Optional[str] = Field(
		None,
		description="Error message if test failed"
	)
