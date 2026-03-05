"""DistributionTarget model for platform connections and webhooks"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from ..database import Base


class DistributionTarget(Base):
    """DistributionTarget model for podcast distribution platforms and webhooks"""

    __tablename__ = "distribution_targets"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Target type: 'spotify', 'apple_podcasts', 'webhook'
    target_type = Column(Text, nullable=False, index=True)

    # Configuration data (platform-specific or webhook details)
    # For Spotify: {
    #   "show_id": "...",
    #   "oauth_tokens": {
    #     "access_token": "encrypted_value",
    #     "refresh_token": "encrypted_value",
    #     "expires_at": "2025-10-20T00:00:00Z"
    #   }
    # }
    # For Apple Podcasts: {
    #   "show_id": "...",
    #   "credentials": {
    #     "api_key": "encrypted_value"
    #   }
    # }
    # For Webhook: {
    #   "name": "n8n Production",
    #   "url": "https://n8n.example.com/webhook/...",
    #   "method": "POST",
    #   "headers": {"Authorization": "Bearer ..."}
    # }
    config = Column(JSONB, nullable=False, default=dict)

    # Status
    is_active = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="distribution_targets")
    project = relationship("Project", back_populates="distribution_targets")

    def __repr__(self) -> str:
        return f"<DistributionTarget(id={self.id}, type={self.target_type}, active={self.is_active})>"
