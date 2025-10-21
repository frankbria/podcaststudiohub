"""TTSConfiguration model for text-to-speech settings"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from ..database import Base


class TTSConfiguration(Base):
    """TTSConfiguration model for TTS provider settings"""

    __tablename__ = "tts_configurations"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Configuration info
    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    is_system_template = Column(Boolean, default=False, nullable=False)  # Built-in vs user-created

    # TTS provider: 'openai', 'elevenlabs', 'gemini', 'geminimulti', 'edge'
    provider = Column(String(50), nullable=False, index=True)

    # TTS configuration
    # Structure varies by provider:
    # OpenAI: {
    #   "model": "tts-1-hd",
    #   "voice_1": "alloy",
    #   "voice_2": "echo",
    #   "speed": 1.0
    # }
    # ElevenLabs: {
    #   "model": "eleven_multilingual_v2",
    #   "voice_1_id": "21m00Tcm4TlvDq8ikWAM",
    #   "voice_2_id": "AZnzlk1XvdvUeBnXmlld",
    #   "stability": 0.5,
    #   "similarity_boost": 0.75
    # }
    # Gemini: {
    #   "model": "en-US-Studio-MultiSpeaker",
    #   "language_code": "en-US"
    # }
    # Edge: {
    #   "voice_1": "en-US-AriaNeural",
    #   "voice_2": "en-US-GuyNeural",
    #   "rate": "+0%",
    #   "volume": "+0%"
    # }
    config = Column(JSONB, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User")

    def __repr__(self) -> str:
        return f"<TTSConfiguration(id={self.id}, name={self.name}, provider={self.provider})>"
