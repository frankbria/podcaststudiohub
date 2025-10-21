"""ConversationTemplate model for podcast conversation styles"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from ..database import Base


class ConversationTemplate(Base):
    """ConversationTemplate model for conversation configuration"""

    __tablename__ = "conversation_templates"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Template info
    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    is_system_template = Column(Boolean, default=False, nullable=False)  # Built-in vs user-created

    # Conversation configuration
    # Structure follows existing conversation_config.yaml format:
    # {
    #   "word_count": 300,
    #   "conversation_style": ["casual", "formal", "humorous"],
    #   "roles_person1": "main summarizer",
    #   "roles_person2": "questioner",
    #   "dialogue_structure": ["Introduction", "Main Content", "Conclusion"],
    #   "podcast_name": "Tech Insights",
    #   "podcast_tagline": "Deep dives into technology",
    #   "output_language": "English",
    #   "engagement_techniques": ["rhetorical questions", "anecdotes"],
    #   "creativity": 0.7
    # }
    config = Column(JSONB, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User")

    def __repr__(self) -> str:
        return f"<ConversationTemplate(id={self.id}, name={self.name})>"
