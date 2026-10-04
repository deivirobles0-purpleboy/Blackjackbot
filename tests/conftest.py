from __future__ import annotations

import os
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

from database.repositories import Repository
from database.schema import SCHEMA_SQL


@pytest_asyncio.fixture
async def repo():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL no configurada; usa una PostgreSQL de pruebas")
    schema = "test_halloween_" + uuid4().hex
    con = await asyncpg.connect(url)
    await con.execute(f'CREATE SCHEMA "{schema}"')
    pool = None
    try:
        pool = await asyncpg.create_pool(
            url, min_size=1, max_size=8, server_settings={"search_path": schema, "timezone": "UTC"}
        )
        await pool.execute(SCHEMA_SQL)
        yield Repository(pool)
    finally:
        if pool:
            await pool.close()
        await con.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await con.close()
