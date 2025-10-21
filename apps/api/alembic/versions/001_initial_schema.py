"""Initial schema with all 11 tables, RLS policies, and encryption functions

Revision ID: 001
Revises:
Create Date: 2025-10-20 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable required PostgreSQL extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # Create encryption helper functions
    op.execute("""
        CREATE OR REPLACE FUNCTION encrypt_credential(credential TEXT, key TEXT)
        RETURNS TEXT AS $$
        BEGIN
            RETURN encode(pgp_sym_encrypt(credential, key), 'base64');
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION decrypt_credential(encrypted_credential TEXT, key TEXT)
        RETURNS TEXT AS $$
        BEGIN
            RETURN pgp_sym_decrypt(decode(encrypted_credential, 'base64'), key);
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;
    """)

    # Create updated_at trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Table 1: users
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.Text(), nullable=False, unique=True),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('full_name', sa.Text()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('last_login', sa.TIMESTAMP(timezone=True)),
        sa.Column('encrypted_api_keys', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.CheckConstraint("email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'", name='users_email_check')
    )
    op.create_index('idx_users_tenant', 'users', ['tenant_id'])
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_active', 'users', ['is_active'], postgresql_where=sa.text('is_active = true'))
    op.execute("CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()")

    # Table 2: conversation_templates
    op.create_table(
        'conversation_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('config', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()'))
    )
    op.create_index('idx_conversation_templates_tenant', 'conversation_templates', ['tenant_id'])
    op.create_index('idx_conversation_templates_user', 'conversation_templates', ['user_id'])
    op.execute("CREATE TRIGGER update_conversation_templates_updated_at BEFORE UPDATE ON conversation_templates FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()")

    # Table 3: tts_configurations
    op.create_table(
        'tts_configurations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('config', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.CheckConstraint("provider IN ('openai', 'elevenlabs', 'gemini', 'gemini_multi', 'edge')", name='tts_config_provider_check')
    )
    op.create_index('idx_tts_configurations_tenant', 'tts_configurations', ['tenant_id'])
    op.create_index('idx_tts_configurations_user', 'tts_configurations', ['user_id'])
    op.execute("CREATE TRIGGER update_tts_configurations_updated_at BEFORE UPDATE ON tts_configurations FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()")

    # Table 4: projects
    op.create_table(
        'projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('podcast_metadata', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('default_tts_config_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tts_configurations.id', ondelete='SET NULL')),
        sa.Column('default_template_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conversation_templates.id', ondelete='SET NULL')),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()'))
    )
    op.create_index('idx_projects_tenant', 'projects', ['tenant_id'])
    op.create_index('idx_projects_user', 'projects', ['user_id'])
    op.create_index('idx_projects_active', 'projects', ['is_archived'], postgresql_where=sa.text('is_archived = false'))
    op.execute("CREATE TRIGGER update_projects_updated_at BEFORE UPDATE ON projects FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()")

    # Table 5: episodes
    op.create_table(
        'episodes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('episode_number', sa.Integer()),
        sa.Column('metadata', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('file_path', sa.Text()),
        sa.Column('s3_key', sa.Text()),
        sa.Column('s3_url', sa.Text()),
        sa.Column('duration_seconds', sa.Numeric(10, 2)),
        sa.Column('file_size_bytes', sa.BigInteger()),
        sa.Column('transcript_path', sa.Text()),
        sa.Column('generation_status', sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column('generation_progress', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column('tts_config_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tts_configurations.id', ondelete='SET NULL')),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conversation_templates.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.CheckConstraint("generation_status IN ('draft', 'queued', 'extracting', 'generating', 'synthesizing', 'complete', 'failed')", name='episodes_status_check')
    )
    op.create_index('idx_episodes_tenant', 'episodes', ['tenant_id'])
    op.create_index('idx_episodes_user', 'episodes', ['user_id'])
    op.create_index('idx_episodes_project', 'episodes', ['project_id'])
    op.create_index('idx_episodes_status', 'episodes', ['generation_status'])
    op.create_index('idx_episodes_metadata_gin', 'episodes', ['metadata'], postgresql_using='gin', postgresql_ops={'metadata': 'jsonb_path_ops'})
    op.create_index('idx_episodes_title', 'episodes', [sa.text("(metadata->>'title')")])
    op.execute("CREATE TRIGGER update_episodes_updated_at BEFORE UPDATE ON episodes FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()")

    # Table 6: content_sources
    op.create_table(
        'content_sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('episode_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('episodes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_type', sa.Text(), nullable=False),
        sa.Column('source_data', postgresql.JSONB(), nullable=False),
        sa.Column('extraction_status', sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('extracted_content', sa.Text()),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.CheckConstraint("source_type IN ('url', 'pdf', 'youtube', 'text', 'image', 'topic')", name='content_sources_type_check'),
        sa.CheckConstraint("extraction_status IN ('pending', 'extracting', 'complete', 'failed')", name='content_sources_status_check')
    )
    op.create_index('idx_content_sources_tenant', 'content_sources', ['tenant_id'])
    op.create_index('idx_content_sources_episode', 'content_sources', ['episode_id'])
    op.execute("CREATE TRIGGER update_content_sources_updated_at BEFORE UPDATE ON content_sources FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()")

    # Table 7: rss_feeds
    op.create_table(
        'rss_feeds',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('s3_key', sa.Text()),
        sa.Column('public_url', sa.Text()),
        sa.Column('validation_status', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column('last_generated', sa.TIMESTAMP(timezone=True)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()'))
    )
    op.create_index('idx_rss_feeds_tenant', 'rss_feeds', ['tenant_id'])
    op.create_index('idx_rss_feeds_project', 'rss_feeds', ['project_id'])
    op.execute("CREATE TRIGGER update_rss_feeds_updated_at BEFORE UPDATE ON rss_feeds FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()")

    # Table 8: distribution_targets
    op.create_table(
        'distribution_targets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE')),
        sa.Column('target_type', sa.Text(), nullable=False),
        sa.Column('config', postgresql.JSONB(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.CheckConstraint("target_type IN ('spotify', 'apple_podcasts', 'webhook')", name='distribution_targets_type_check')
    )
    op.create_index('idx_distribution_targets_tenant', 'distribution_targets', ['tenant_id'])
    op.create_index('idx_distribution_targets_user', 'distribution_targets', ['user_id'])
    op.create_index('idx_distribution_targets_project', 'distribution_targets', ['project_id'])
    op.execute("CREATE TRIGGER update_distribution_targets_updated_at BEFORE UPDATE ON distribution_targets FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()")

    # Table 9: audio_snippets
    op.create_table(
        'audio_snippets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE')),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('snippet_type', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('file_path', sa.Text(), nullable=False),
        sa.Column('s3_key', sa.Text()),
        sa.Column('s3_url', sa.Text()),
        sa.Column('duration_seconds', sa.Numeric(10, 2)),
        sa.Column('file_size_bytes', sa.BigInteger()),
        sa.Column('file_format', sa.Text()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.CheckConstraint("snippet_type IN ('intro', 'outro', 'midroll', 'ad', 'music', 'other')", name='snippets_type_check')
    )
    op.create_index('idx_audio_snippets_tenant', 'audio_snippets', ['tenant_id'])
    op.create_index('idx_audio_snippets_user', 'audio_snippets', ['user_id'])
    op.create_index('idx_audio_snippets_project', 'audio_snippets', ['project_id'])
    op.create_index('idx_audio_snippets_type', 'audio_snippets', ['snippet_type'])
    op.execute("CREATE TRIGGER update_audio_snippets_updated_at BEFORE UPDATE ON audio_snippets FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()")

    # Table 10: episode_layouts
    op.create_table(
        'episode_layouts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE')),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('layout_config', postgresql.JSONB(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()'))
    )
    op.create_index('idx_episode_layouts_tenant', 'episode_layouts', ['tenant_id'])
    op.create_index('idx_episode_layouts_user', 'episode_layouts', ['user_id'])
    op.create_index('idx_episode_layouts_project', 'episode_layouts', ['project_id'])
    op.execute("CREATE TRIGGER update_episode_layouts_updated_at BEFORE UPDATE ON episode_layouts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()")

    # Table 11: episode_compositions
    op.create_table(
        'episode_compositions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('episode_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('episodes.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('layout_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('episode_layouts.id', ondelete='SET NULL')),
        sa.Column('timeline', postgresql.JSONB(), nullable=False),
        sa.Column('composition_status', sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column('composed_file_path', sa.Text()),
        sa.Column('composed_s3_key', sa.Text()),
        sa.Column('composed_s3_url', sa.Text()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.CheckConstraint("composition_status IN ('draft', 'preview', 'final')", name='composition_status_check')
    )
    op.create_index('idx_episode_compositions_tenant', 'episode_compositions', ['tenant_id'])
    op.create_index('idx_episode_compositions_episode', 'episode_compositions', ['episode_id'])
    op.execute("CREATE TRIGGER update_episode_compositions_updated_at BEFORE UPDATE ON episode_compositions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()")

    # Enable Row-Level Security on all tables
    tables = [
        'users', 'conversation_templates', 'tts_configurations', 'projects',
        'episodes', 'content_sources', 'rss_feeds', 'distribution_targets',
        'audio_snippets', 'episode_layouts', 'episode_compositions'
    ]

    for table in tables:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
                USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """)


def downgrade() -> None:
    # Drop all tables in reverse order (respecting foreign key constraints)
    op.drop_table('episode_compositions')
    op.drop_table('episode_layouts')
    op.drop_table('audio_snippets')
    op.drop_table('distribution_targets')
    op.drop_table('rss_feeds')
    op.drop_table('content_sources')
    op.drop_table('episodes')
    op.drop_table('projects')
    op.drop_table('tts_configurations')
    op.drop_table('conversation_templates')
    op.drop_table('users')

    # Drop functions
    op.execute('DROP FUNCTION IF EXISTS update_updated_at_column()')
    op.execute('DROP FUNCTION IF EXISTS decrypt_credential(TEXT, TEXT)')
    op.execute('DROP FUNCTION IF EXISTS encrypt_credential(TEXT, TEXT)')

    # Drop extensions (optional - may want to keep them)
    # op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
    # op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
