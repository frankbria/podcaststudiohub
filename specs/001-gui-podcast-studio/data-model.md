# Data Model: GUI Podcast Studio

**Feature**: 001-gui-podcast-studio
**Database**: PostgreSQL 15+ with JSONB
**Date**: 2025-10-20

---

## Overview

This data model supports a multi-tenant SaaS podcast generation platform. The design uses:
- **PostgreSQL with Row-Level Security (RLS)** for tenant isolation
- **JSONB columns** for flexible episode metadata and distribution status
- **Foreign key constraints** for referential integrity
- **Column-level encryption (pgcrypto)** for sensitive credentials
- **Optimized indexes** for <100ms episode library queries

---

## Entity Relationship Diagram

```
┌─────────────┐
│   users     │
└──────┬──────┘
       │
       │ 1:N
       ▼
┌─────────────┐
│  projects   │
└──────┬──────┘
       │
       │ 1:N
       ▼
┌─────────────┐      ┌──────────────────┐
│  episodes   │◄─────│ content_sources  │
└──────┬──────┘ 1:N  └──────────────────┘
       │
       │ 1:N
       ▼
┌──────────────────────┐
│ distribution_targets │
└──────────────────────┘


Additional Entities:
- conversation_templates (1:N with projects)
- tts_configurations (1:N with projects/episodes)
- rss_feeds (1:1 with projects)
```

---

## Schema Definitions

### Core Tables

#### 1. users

**Purpose**: User accounts with authentication and encrypted API credentials

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,  -- Multi-tenant isolation

    -- Authentication
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,  -- bcrypt hashed

    -- Profile
    full_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login TIMESTAMPTZ,

    -- Encrypted API credentials (pgcrypto)
    encrypted_api_keys JSONB DEFAULT '{}'::jsonb,
    -- Example structure:
    -- {
    --   "openai_key": "pgp_sym_encrypted_value",
    --   "elevenlabs_key": "pgp_sym_encrypted_value",
    --   "gemini_key": "pgp_sym_encrypted_value",
    --   "s3_access_key": "pgp_sym_encrypted_value",
    --   "s3_secret_key": "pgp_sym_encrypted_value"
    -- }

    -- Account status
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_verified BOOLEAN NOT NULL DEFAULT false,

    CONSTRAINT users_email_check CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

-- Indexes
CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_active ON users(is_active) WHERE is_active = true;

-- Row-Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_users ON users
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

**Validation Rules** (from FR-016):
- Email must be valid format
- Password must be bcrypt hashed (Argon2 alternative)
- API credentials must be encrypted using pgcrypto

---

#### 2. projects

**Purpose**: Collection of related podcast episodes with shared configuration

```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Project metadata
    name TEXT NOT NULL,
    description TEXT,

    -- Podcast metadata (FR-014)
    podcast_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Expected structure:
    -- {
    --   "show_title": "My Podcast",
    --   "author": "Author Name",
    --   "description": "Podcast description",
    --   "category": "Technology",
    --   "language": "en-US",
    --   "explicit": false,
    --   "copyright": "© 2025 Author",
    --   "artwork_url": "https://s3.../artwork.jpg"
    -- }

    -- Default TTS configuration
    default_tts_config_id UUID REFERENCES tts_configurations(id) ON DELETE SET NULL,

    -- Default conversation template
    default_template_id UUID REFERENCES conversation_templates(id) ON DELETE SET NULL,

    -- Status
    is_archived BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT projects_name_length CHECK (char_length(name) >= 1 AND char_length(name) <= 255)
);

-- Indexes
CREATE INDEX idx_projects_tenant ON projects(tenant_id);
CREATE INDEX idx_projects_user ON projects(user_id);
CREATE INDEX idx_projects_active ON projects(is_archived) WHERE is_archived = false;
CREATE INDEX idx_projects_created ON projects(created_at DESC);

-- Row-Level Security
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_projects ON projects
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

**Validation Rules**:
- Project name required, 1-255 characters
- Podcast metadata must include at minimum: show_title, author, description
- Artwork must be square 1400x1400 to 3000x3000 pixels (validated in application layer)

---

#### 3. episodes

**Purpose**: Individual podcast episodes with content sources, transcripts, and distribution status

```sql
CREATE TABLE episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Episode metadata (FR-008)
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Expected structure:
    -- {
    --   "title": "Episode Title",
    --   "description": "Episode description",
    --   "episode_number": 1,
    --   "season_number": 1,
    --   "publication_date": "2025-10-20T00:00:00Z",
    --   "tags": ["tech", "ai", "podcast"],
    --   "duration_seconds": 300,
    --   "file_size_bytes": 5242880,
    --   "format": "conversation" // or "solo", "interview"
    -- }

    -- Generated content
    transcript TEXT,  -- Generated transcript (XML format from existing CLI)
    audio_file_path TEXT,  -- Local file path (before S3 upload)
    audio_s3_key TEXT,  -- S3 object key (after upload)
    audio_s3_url TEXT,  -- Public S3 URL

    -- Generation status
    generation_status TEXT NOT NULL DEFAULT 'draft',
    -- Enum: draft, queued, processing, completed, failed, published
    generation_task_id UUID,  -- Celery task ID

    -- Generation progress (updated via Celery task)
    generation_progress JSONB DEFAULT '{}'::jsonb,
    -- {
    --   "stage": "extraction" | "transcript" | "audio" | "complete",
    --   "progress": 0-100,
    --   "message": "Extracting content...",
    --   "error": null | "error message"
    -- }

    -- Distribution status (FR-010, FR-011)
    distribution_status JSONB DEFAULT '{}'::jsonb,
    -- {
    --   "s3": {"status": "uploaded", "uploaded_at": "2025-10-20T00:00:00Z"},
    --   "spotify": {"status": "published", "published_at": "...", "platform_id": "..."},
    --   "apple": {"status": "pending", "submitted_at": "..."},
    --   "webhooks": {
    --     "n8n_webhook_1": {"status": "sent", "sent_at": "..."}
    --   }
    -- }

    -- TTS configuration used
    tts_config_id UUID REFERENCES tts_configurations(id) ON DELETE SET NULL,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,

    CONSTRAINT episodes_status_check CHECK (
        generation_status IN ('draft', 'queued', 'processing', 'completed', 'failed', 'published')
    ),
    CONSTRAINT episodes_title_required CHECK (
        metadata->>'title' IS NOT NULL AND char_length(metadata->>'title') >= 1
    )
);

-- Indexes for performance (SC-004: <100ms for 1000+ episodes)
CREATE INDEX idx_episodes_tenant ON episodes(tenant_id);
CREATE INDEX idx_episodes_user ON episodes(user_id);
CREATE INDEX idx_episodes_project ON episodes(project_id);
CREATE INDEX idx_episodes_status ON episodes(generation_status);

-- JSONB indexes for metadata queries
CREATE INDEX idx_episodes_metadata_gin ON episodes USING GIN(metadata jsonb_path_ops);
CREATE INDEX idx_episodes_title ON episodes((metadata->>'title'));
CREATE INDEX idx_episodes_episode_number ON episodes((metadata->>'episode_number'));
CREATE INDEX idx_episodes_publication_date ON episodes((metadata->>'publication_date'));

-- Sorting and filtering
CREATE INDEX idx_episodes_created ON episodes(created_at DESC);
CREATE INDEX idx_episodes_updated ON episodes(updated_at DESC);

-- Distribution status queries
CREATE INDEX idx_episodes_distribution_gin ON episodes USING GIN(distribution_status jsonb_path_ops);

-- Row-Level Security
ALTER TABLE episodes ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_episodes ON episodes
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

**Validation Rules**:
- Episode title required in metadata
- Generation status must be one of defined enum values
- Episode number must be positive integer if provided
- Duration must be positive integer (seconds)

---

#### 4. content_sources

**Purpose**: Input sources (URLs, documents, text) for episode generation

```sql
CREATE TABLE content_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,

    -- Source type and location
    source_type TEXT NOT NULL,  -- 'url', 'pdf', 'text'
    source_data JSONB NOT NULL,
    -- For URL: {"url": "https://...", "title": "Article Title"}
    -- For PDF: {"filename": "doc.pdf", "s3_key": "uploads/...", "page_count": 10}
    -- For text: {"content": "Raw text content..."}

    -- Extraction status
    extraction_status TEXT NOT NULL DEFAULT 'pending',
    -- Enum: pending, processing, completed, failed
    extracted_content TEXT,  -- Extracted text content
    extraction_error TEXT,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT content_sources_type_check CHECK (
        source_type IN ('url', 'pdf', 'text')
    ),
    CONSTRAINT content_sources_status_check CHECK (
        extraction_status IN ('pending', 'processing', 'completed', 'failed')
    )
);

-- Indexes
CREATE INDEX idx_content_sources_tenant ON content_sources(tenant_id);
CREATE INDEX idx_content_sources_episode ON content_sources(episode_id);
CREATE INDEX idx_content_sources_status ON content_sources(extraction_status);
CREATE INDEX idx_content_sources_type ON content_sources(source_type);

-- Row-Level Security
ALTER TABLE content_sources ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_content_sources ON content_sources
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

**Validation Rules** (from FR-002):
- URL must be valid HTTP(S) format
- PDF must be valid file (validated via PyMuPDF)
- Text content must be non-empty

---

#### 5. conversation_templates

**Purpose**: Podcast format structure (speaker roles, conversation style, custom prompts)

```sql
CREATE TABLE conversation_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Template metadata
    name TEXT NOT NULL,
    description TEXT,

    -- Template configuration (FR-017)
    config JSONB NOT NULL,
    -- Expected structure:
    -- {
    --   "format": "solo" | "conversation" | "interview",
    --   "speakers": [
    --     {
    --       "role": "host",
    --       "name": "Alex",
    --       "personality": "curious and engaging",
    --       "voice_settings": {"provider": "elevenlabs", "voice_id": "..."}
    --     },
    --     {
    --       "role": "guest",
    --       "name": "Sam",
    --       "personality": "expert and thoughtful",
    --       "voice_settings": {"provider": "openai", "voice": "onyx"}
    --     }
    --   ],
    --   "conversation_style": {
    --     "tone": "casual",
    --     "pacing": "moderate",
    --     "custom_prompts": ["Focus on practical examples", "Keep it under 10 minutes"]
    --   }
    -- }

    -- Usage
    is_default BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT templates_name_length CHECK (char_length(name) >= 1 AND char_length(name) <= 255)
);

-- Indexes
CREATE INDEX idx_templates_tenant ON conversation_templates(tenant_id);
CREATE INDEX idx_templates_user ON conversation_templates(user_id);
CREATE INDEX idx_templates_default ON conversation_templates(is_default) WHERE is_default = true;

-- Row-Level Security
ALTER TABLE conversation_templates ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_templates ON conversation_templates
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

**Validation Rules**:
- Template name required
- Format must be one of: solo, conversation, interview
- At least one speaker required
- Voice settings must match available TTS providers

---

#### 6. tts_configurations

**Purpose**: TTS provider settings and speaker assignments

```sql
CREATE TABLE tts_configurations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Configuration metadata
    name TEXT NOT NULL,
    description TEXT,

    -- TTS settings (FR-003)
    config JSONB NOT NULL,
    -- Expected structure:
    -- {
    --   "provider": "openai" | "elevenlabs" | "gemini" | "edge",
    --   "voice_settings": {
    --     "voice_id": "...",  // or "voice": "onyx" for OpenAI
    --     "model": "tts-1-hd",
    --     "stability": 0.5,  // ElevenLabs
    --     "similarity_boost": 0.75  // ElevenLabs
    --   },
    --   "speaker_assignments": {
    --     "Person1": {"provider": "openai", "voice": "alloy"},
    --     "Person2": {"provider": "elevenlabs", "voice_id": "..."}
    --   }
    -- }

    -- Usage
    is_default BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT tts_name_length CHECK (char_length(name) >= 1 AND char_length(name) <= 255)
);

-- Indexes
CREATE INDEX idx_tts_configs_tenant ON tts_configurations(tenant_id);
CREATE INDEX idx_tts_configs_user ON tts_configurations(user_id);
CREATE INDEX idx_tts_configs_default ON tts_configurations(is_default) WHERE is_default = true;

-- Row-Level Security
ALTER TABLE tts_configurations ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_tts_configs ON tts_configurations
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

**Validation Rules**:
- Provider must be one of: openai, elevenlabs, gemini, edge
- Voice settings must match provider requirements

---

#### 7. distribution_targets

**Purpose**: Platform connections (Spotify, Apple Podcasts) and automation webhooks

```sql
CREATE TABLE distribution_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,  -- Optional project-level

    -- Target type
    target_type TEXT NOT NULL,  -- 'platform' or 'webhook'

    -- Platform/webhook details
    config JSONB NOT NULL,
    -- For platform:
    -- {
    --   "platform": "spotify" | "apple_podcasts",
    --   "platform_id": "show_id",
    --   "oauth_tokens": {
    --     "access_token": "encrypted_value",
    --     "refresh_token": "encrypted_value",
    --     "expires_at": "2025-10-20T00:00:00Z"
    --   }
    -- }
    -- For webhook:
    -- {
    --   "name": "n8n Production",
    --   "url": "https://n8n.example.com/webhook/...",
    --   "method": "POST",
    --   "headers": {"Authorization": "Bearer ..."}
    -- }

    -- Status
    is_active BOOLEAN NOT NULL DEFAULT true,
    last_sync_at TIMESTAMPTZ,
    last_sync_status TEXT,  -- 'success', 'failed'
    last_sync_error TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT targets_type_check CHECK (
        target_type IN ('platform', 'webhook')
    )
);

-- Indexes
CREATE INDEX idx_targets_tenant ON distribution_targets(tenant_id);
CREATE INDEX idx_targets_user ON distribution_targets(user_id);
CREATE INDEX idx_targets_project ON distribution_targets(project_id);
CREATE INDEX idx_targets_type ON distribution_targets(target_type);
CREATE INDEX idx_targets_active ON distribution_targets(is_active) WHERE is_active = true;

-- Row-Level Security
ALTER TABLE distribution_targets ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_targets ON distribution_targets
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

**Validation Rules** (from FR-010, FR-011):
- Platform OAuth tokens must be encrypted
- Webhook URL must be valid HTTPS
- Platform must be one of supported options

---

#### 8. rss_feeds

**Purpose**: Generated RSS feed metadata and S3 URLs

```sql
CREATE TABLE rss_feeds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,

    -- Feed URLs
    s3_key TEXT NOT NULL,  -- S3 object key
    public_url TEXT NOT NULL,  -- Public S3 URL

    -- Feed metadata
    last_generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    episode_count INT NOT NULL DEFAULT 0,

    -- Validation status (FR-013)
    validation_status JSONB DEFAULT '{}'::jsonb,
    -- {
    --   "last_validated_at": "2025-10-20T00:00:00Z",
    --   "apple_podcasts": {"valid": true, "errors": []},
    --   "spotify": {"valid": true, "errors": []},
    --   "google_podcasts": {"valid": true, "errors": []}
    -- }

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT rss_episode_count_check CHECK (episode_count >= 0)
);

-- Indexes
CREATE INDEX idx_rss_feeds_tenant ON rss_feeds(tenant_id);
CREATE INDEX idx_rss_feeds_project ON rss_feeds(project_id);

-- Row-Level Security
ALTER TABLE rss_feeds ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_rss_feeds ON rss_feeds
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

**Validation Rules** (from FR-012, FR-013):
- RSS feed must be valid RSS 2.0 format
- Public URL must be HTTPS
- Validation against Apple Podcasts, Spotify standards

---

#### 9. audio_snippets

**Purpose**: Reusable audio files (intros, outros, midrolls, ads, music) for podcast composition

```sql
CREATE TABLE audio_snippets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,  -- Optional project-level snippets

    -- Snippet metadata (FR-024)
    name TEXT NOT NULL,
    snippet_type TEXT NOT NULL,  -- 'intro', 'outro', 'midroll', 'ad', 'music'
    description TEXT,

    -- Audio file information
    file_path TEXT NOT NULL,  -- Local file path (before S3 upload)
    s3_key TEXT,  -- S3 object key (after upload)
    s3_url TEXT,  -- Public or signed S3 URL

    -- Audio properties (extracted after upload)
    duration_seconds DECIMAL(10, 2),  -- Precise duration
    file_size_bytes BIGINT,
    file_format TEXT,  -- 'mp3', 'wav', 'ogg', etc.
    sample_rate INTEGER,  -- e.g., 44100, 48000
    bit_rate INTEGER,  -- e.g., 128000, 256000
    channels INTEGER DEFAULT 2,  -- 1 (mono), 2 (stereo)

    -- Audio metadata (ID3 tags if available)
    audio_metadata JSONB DEFAULT '{}'::jsonb,
    -- {
    --   "artist": "...",
    --   "title": "...",
    --   "album": "...",
    --   "genre": "..."
    -- }

    -- Usage tracking
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT snippets_type_check CHECK (
        snippet_type IN ('intro', 'outro', 'midroll', 'ad', 'music', 'other')
    ),
    CONSTRAINT snippets_name_length CHECK (char_length(name) >= 1 AND char_length(name) <= 255),
    CONSTRAINT snippets_duration_positive CHECK (duration_seconds > 0)
);

-- Indexes
CREATE INDEX idx_snippets_tenant ON audio_snippets(tenant_id);
CREATE INDEX idx_snippets_user ON audio_snippets(user_id);
CREATE INDEX idx_snippets_project ON audio_snippets(project_id);
CREATE INDEX idx_snippets_type ON audio_snippets(snippet_type);
CREATE INDEX idx_snippets_name ON audio_snippets(name);
CREATE INDEX idx_snippets_created ON audio_snippets(created_at DESC);

-- Row-Level Security
ALTER TABLE audio_snippets ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_audio_snippets ON audio_snippets
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

**Validation Rules** (from FR-023, FR-024):
- Snippet name required, 1-255 characters
- Snippet type must be one of defined enum values
- Audio file must be valid format (MP3, WAV, OGG)
- Duration must be positive (extracted via FFmpeg/PyDub)
- File size reasonable (<50MB recommended)

---

#### 10. episode_layouts

**Purpose**: Composition templates defining snippet positions for episodes

```sql
CREATE TABLE episode_layouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,

    -- Layout metadata
    name TEXT NOT NULL,
    description TEXT,

    -- Layout configuration (FR-025, FR-029)
    layout_config JSONB NOT NULL,
    -- Expected structure:
    -- {
    --   "segments": [
    --     {
    --       "type": "snippet",
    --       "snippet_id": "uuid",
    --       "position": "pre-roll",  // or timestamp in seconds
    --       "order": 1
    --     },
    --     {
    --       "type": "main_content",
    --       "position": "auto",
    --       "order": 2
    --     },
    --     {
    --       "type": "snippet",
    --       "snippet_id": "uuid",
    --       "position": "50%",  // mid-roll at 50% of main content
    --       "order": 3
    --     },
    --     {
    --       "type": "snippet",
    --       "snippet_id": "uuid",
    --       "position": "post-roll",
    --       "order": 4
    --     }
    --   ],
    --   "auto_normalize": true,  // Normalize audio levels
    --   "crossfade_duration": 0.5  // Crossfade between segments in seconds
    -- }

    -- Usage
    is_default BOOLEAN NOT NULL DEFAULT false,
    usage_count INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT layouts_name_length CHECK (char_length(name) >= 1 AND char_length(name) <= 255)
);

-- Indexes
CREATE INDEX idx_layouts_tenant ON episode_layouts(tenant_id);
CREATE INDEX idx_layouts_user ON episode_layouts(user_id);
CREATE INDEX idx_layouts_project ON episode_layouts(project_id);
CREATE INDEX idx_layouts_default ON episode_layouts(is_default) WHERE is_default = true;

-- Row-Level Security
ALTER TABLE episode_layouts ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_episode_layouts ON episode_layouts
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

**Validation Rules**:
- Layout name required
- At least one segment must be defined
- All referenced snippet_ids must exist and be accessible
- Positions must be valid (pre-roll, post-roll, timestamp, percentage)

---

#### 11. episode_compositions

**Purpose**: Final composition state for episodes with snippet timeline

```sql
CREATE TABLE episode_compositions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    episode_id UUID NOT NULL UNIQUE REFERENCES episodes(id) ON DELETE CASCADE,
    layout_id UUID REFERENCES episode_layouts(id) ON DELETE SET NULL,

    -- Composition timeline (FR-027, FR-028)
    timeline JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Expected structure (generated after merging):
    -- [
    --   {
    --     "segment_type": "snippet",
    --     "snippet_id": "uuid",
    --     "snippet_name": "Intro Music",
    --     "start_time": 0.0,
    --     "end_time": 5.0,
    --     "duration": 5.0,
    --     "audio_source": "s3://bucket/snippets/intro.mp3"
    --   },
    --   {
    --     "segment_type": "main_content",
    --     "start_time": 5.0,
    --     "end_time": 305.0,
    --     "duration": 300.0,
    --     "audio_source": "generated_podcast.mp3"
    --   },
    --   {
    --     "segment_type": "snippet",
    --     "snippet_id": "uuid",
    --     "snippet_name": "Outro",
    --     "start_time": 305.0,
    --     "end_time": 315.0,
    --     "duration": 10.0,
    --     "audio_source": "s3://bucket/snippets/outro.mp3"
    --   }
    -- ]

    -- Final composition metadata
    total_duration_seconds DECIMAL(10, 2),
    final_audio_path TEXT,  -- Path to merged audio file
    final_audio_s3_key TEXT,
    final_audio_s3_url TEXT,

    -- Composition status
    composition_status TEXT NOT NULL DEFAULT 'draft',
    -- Enum: draft, merging, completed, failed

    -- Processing metadata
    merge_task_id UUID,  -- Celery task ID for audio merging
    merge_error TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT compositions_status_check CHECK (
        composition_status IN ('draft', 'merging', 'completed', 'failed')
    ),
    CONSTRAINT compositions_duration_positive CHECK (total_duration_seconds > 0 OR total_duration_seconds IS NULL)
);

-- Indexes
CREATE INDEX idx_compositions_tenant ON episode_compositions(tenant_id);
CREATE INDEX idx_compositions_episode ON episode_compositions(episode_id);
CREATE INDEX idx_compositions_layout ON episode_compositions(layout_id);
CREATE INDEX idx_compositions_status ON episode_compositions(composition_status);

-- Row-Level Security
ALTER TABLE episode_compositions ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_compositions ON episode_compositions
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

**Validation Rules**:
- One composition per episode
- Timeline segments must be ordered chronologically
- Total duration must match sum of segment durations
- Composition status must be one of defined enum values

---

## Database Extensions

```sql
-- Enable pgcrypto for credential encryption
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Enable uuid-ossp for UUID generation (alternative to gen_random_uuid)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

---

## Encryption Functions

```sql
-- Encrypt API credentials
CREATE OR REPLACE FUNCTION encrypt_credential(plaintext TEXT, key TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN encode(pgp_sym_encrypt(plaintext, key), 'base64');
END;
$$ LANGUAGE plpgsql;

-- Decrypt API credentials
CREATE OR REPLACE FUNCTION decrypt_credential(encrypted TEXT, key TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN pgp_sym_decrypt(decode(encrypted, 'base64'), key);
END;
$$ LANGUAGE plpgsql;

-- Usage example:
-- INSERT INTO users (encrypted_api_keys)
-- VALUES (jsonb_build_object(
--     'openai_key', encrypt_credential('sk-...', current_setting('app.encryption_key'))
-- ));
```

---

## Triggers for Updated Timestamps

```sql
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all tables with updated_at column
CREATE TRIGGER users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER projects_updated_at BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER episodes_updated_at BEFORE UPDATE ON episodes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER content_sources_updated_at BEFORE UPDATE ON content_sources
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER templates_updated_at BEFORE UPDATE ON conversation_templates
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER tts_configs_updated_at BEFORE UPDATE ON tts_configurations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER targets_updated_at BEFORE UPDATE ON distribution_targets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER rss_feeds_updated_at BEFORE UPDATE ON rss_feeds
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

---

## Indexes Summary

**Total indexes**: 45+
- **Tenant isolation**: All tables have `tenant_id` index for RLS
- **Foreign keys**: All foreign key columns indexed
- **JSONB**: GIN indexes on `metadata`, `distribution_status` for containment queries
- **B-tree expression indexes**: On JSONB keys for exact lookups (title, episode_number)
- **Partial indexes**: On `is_active`, `is_archived`, `is_default` columns
- **Sorting indexes**: On `created_at DESC`, `updated_at DESC`

**Performance target**: <100ms for episode library queries with 1000+ episodes per user (SC-004)

---

## State Transitions

### Episode Generation Status

```
draft → queued → processing → completed/failed → published
                      ↓
                (can retry on failure)
```

**Valid transitions**:
- `draft` → `queued` (user clicks "Generate Podcast")
- `queued` → `processing` (Celery worker picks up task)
- `processing` → `completed` (generation successful)
- `processing` → `failed` (generation error, can retry)
- `completed` → `published` (S3 upload complete)
- `failed` → `queued` (user retries)

### Distribution Status

Per-platform status in `distribution_status` JSONB:
- `pending` → `processing` → `published` / `failed`
- Platforms operate independently (one can be published while another is pending)

---

## Data Integrity Rules

1. **Cascade Deletes**:
   - Delete user → cascade delete projects → cascade delete episodes → cascade delete content_sources
   - Delete project → cascade delete episodes, distribution_targets, rss_feed
   - Delete episode → cascade delete content_sources

2. **Soft Deletes** (where applicable):
   - Projects have `is_archived` flag (not hard deleted)
   - Distribution targets have `is_active` flag

3. **Referential Integrity**:
   - All foreign keys enforced with CASCADE or SET NULL
   - Cannot create episode without valid project
   - Cannot create content_source without valid episode

4. **Tenant Isolation**:
   - All tables have `tenant_id` column
   - Row-Level Security policies enforce tenant isolation
   - `SET LOCAL app.tenant_id` in FastAPI middleware

---

## Performance Optimizations

1. **JSONB Indexing Strategy**:
   - GIN `jsonb_path_ops` for containment queries (`@>`, `?`)
   - B-tree expression indexes for specific known keys (title, episode_number)
   - Partial indexes for frequently filtered subsets

2. **Connection Pooling**:
   - PgBouncer in transaction mode (compatible with `SET LOCAL`)
   - Pool size: 25 connections
   - Max client connections: 1000

3. **Vacuum & Analyze**:
   - Autovacuum enabled
   - Manual VACUUM ANALYZE after bulk operations

4. **Query Optimization**:
   - Use prepared statements
   - Batch inserts for content_sources
   - Lazy loading for JSONB fields when not needed

---

## Migration Strategy

Using Alembic for schema migrations:

```python
# alembic/versions/001_initial_schema.py
def upgrade():
    # Create extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(), nullable=False),
        # ... rest of columns
    )

    # Create indexes
    op.create_index('idx_users_tenant', 'users', ['tenant_id'])

    # Enable RLS
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_users ON users
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    """)

    # ... repeat for all tables

def downgrade():
    # Drop in reverse order
    op.drop_table('rss_feeds')
    op.drop_table('distribution_targets')
    # ...
```

---

## Testing Data

Sample test data for development:

```sql
-- Test tenant
INSERT INTO users (tenant_id, email, password_hash, full_name)
VALUES (
    '123e4567-e89b-12d3-a456-426614174000'::uuid,
    'test@example.com',
    '$2b$12$...',  -- bcrypt hash of 'password'
    'Test User'
);

-- Test project
INSERT INTO projects (tenant_id, user_id, name, podcast_metadata)
VALUES (
    '123e4567-e89b-12d3-a456-426614174000'::uuid,
    (SELECT id FROM users WHERE email = 'test@example.com'),
    'My Test Podcast',
    jsonb_build_object(
        'show_title', 'Tech Insights',
        'author', 'Test User',
        'description', 'A podcast about technology',
        'category', 'Technology'
    )
);

-- Test episode
INSERT INTO episodes (tenant_id, user_id, project_id, metadata, generation_status)
VALUES (
    '123e4567-e89b-12d3-a456-426614174000'::uuid,
    (SELECT id FROM users WHERE email = 'test@example.com'),
    (SELECT id FROM projects WHERE name = 'My Test Podcast'),
    jsonb_build_object(
        'title', 'Episode 1: Introduction to AI',
        'description', 'An introduction to artificial intelligence',
        'episode_number', 1,
        'format', 'conversation'
    ),
    'draft'
);
```

---

## Compliance & Security

1. **GDPR Compliance**:
   - User data deletion cascades to all related records
   - Encrypted API credentials at rest
   - Audit trail via created_at/updated_at timestamps

2. **Data Encryption**:
   - API credentials encrypted using pgcrypto
   - Encryption key stored in environment variable
   - TLS/SSL for database connections in production

3. **Access Control**:
   - Row-Level Security enforces tenant isolation
   - No cross-tenant data access possible
   - Database-level security (defense in depth)

---

## Next Steps

With data model defined:
1. ✅ Generate API contracts (OpenAPI spec)
2. ✅ Implement SQLAlchemy models
3. ✅ Create Alembic migrations
4. ✅ Set up FastAPI database dependency injection
5. ✅ Implement service layer with RLS middleware
