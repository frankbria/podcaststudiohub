#!/usr/bin/env python3
"""
Schema verification script for Task 2.2
Verifies all 11 tables, indexes, RLS policies, and triggers are created correctly
"""
import asyncio
from sqlalchemy import text
from src.database import engine

async def verify_schema():
    """Verify complete schema creation"""

    async with engine.connect() as conn:
        # 1. Verify all 11 tables exist
        print("\n=== VERIFYING TABLES ===")
        result = await conn.execute(text("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """))
        tables = [row[0] for row in result]

        expected_tables = [
            'alembic_version',
            'audio_snippets',
            'content_sources',
            'conversation_templates',
            'distribution_targets',
            'episode_compositions',
            'episode_layouts',
            'episodes',
            'projects',
            'rss_feeds',
            'tts_configurations',
            'users'
        ]

        print(f"Found {len(tables)} tables:")
        for table in tables:
            status = "✓" if table in expected_tables or table == 'alembic_version' else "✗"
            print(f"  {status} {table}")

        missing = set(expected_tables) - set(tables)
        if missing:
            print(f"\n❌ Missing tables: {missing}")
        else:
            print(f"\n✅ All 11 core tables created successfully")

        # 2. Verify indexes
        print("\n=== VERIFYING INDEXES ===")
        result = await conn.execute(text("""
            SELECT
                schemaname,
                tablename,
                indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            ORDER BY tablename, indexname
        """))
        indexes = [(row[1], row[2]) for row in result]
        print(f"Found {len(indexes)} indexes")

        # Sample critical indexes
        critical_indexes = [
            ('users', 'ix_users_email'),
            ('users', 'ix_users_tenant_id'),
            ('projects', 'ix_projects_tenant_id'),
            ('episodes', 'ix_episodes_project_id'),
            ('episodes', 'ix_episodes_tenant_id'),
        ]

        for table, index in critical_indexes:
            if (table, index) in indexes:
                print(f"  ✓ {table}.{index}")
            else:
                print(f"  ✗ {table}.{index} MISSING")

        # 3. Verify RLS policies
        print("\n=== VERIFYING ROW-LEVEL SECURITY ===")
        result = await conn.execute(text("""
            SELECT
                schemaname,
                tablename,
                policyname,
                cmd,
                qual
            FROM pg_policies
            WHERE schemaname = 'public'
            ORDER BY tablename, policyname
        """))
        policies = list(result)
        print(f"Found {len(policies)} RLS policies")

        if len(policies) > 0:
            for policy in policies[:10]:  # Show first 10
                print(f"  ✓ {policy[1]}.{policy[2]} ({policy[3]})")
            if len(policies) > 10:
                print(f"  ... and {len(policies) - 10} more")
        else:
            print("  ⚠️  No RLS policies found")

        # 4. Verify triggers
        print("\n=== VERIFYING TRIGGERS ===")
        result = await conn.execute(text("""
            SELECT
                event_object_table,
                trigger_name,
                action_statement
            FROM information_schema.triggers
            WHERE trigger_schema = 'public'
            ORDER BY event_object_table, trigger_name
        """))
        triggers = list(result)
        print(f"Found {len(triggers)} triggers")

        for trigger in triggers:
            print(f"  ✓ {trigger[0]}.{trigger[1]}")

        # 5. Verify functions
        print("\n=== VERIFYING FUNCTIONS ===")
        result = await conn.execute(text("""
            SELECT
                routine_name,
                routine_type
            FROM information_schema.routines
            WHERE routine_schema = 'public'
            AND routine_type = 'FUNCTION'
            ORDER BY routine_name
        """))
        functions = list(result)
        print(f"Found {len(functions)} functions")

        critical_functions = ['encrypt_api_key', 'set_updated_at', 'update_updated_at_column']
        for func in functions:
            status = "✓" if func[0] in critical_functions else "•"
            print(f"  {status} {func[0]}")

        # 6. Verify current migration version
        print("\n=== VERIFYING MIGRATION VERSION ===")
        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        version = result.scalar()
        print(f"Current revision: {version}")
        if version == '002':
            print("✅ Database is at latest revision (002)")
        else:
            print(f"⚠️  Expected revision 002, got {version}")

        # 7. Check table row counts
        print("\n=== CHECKING TABLE ROW COUNTS ===")
        for table in [t for t in expected_tables if t != 'alembic_version']:
            result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            print(f"  {table}: {count} rows")

if __name__ == "__main__":
    asyncio.run(verify_schema())
