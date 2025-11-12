#!/usr/bin/env python3
import asyncio
from sqlalchemy import text
from src.database import engine

async def check_indexes():
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT tablename, indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND tablename IN ('users', 'projects', 'episodes')
            ORDER BY tablename, indexname
        """))
        rows = list(result)
        for row in rows:
            print(f"{row[0]}: {row[1]}")

asyncio.run(check_indexes())
