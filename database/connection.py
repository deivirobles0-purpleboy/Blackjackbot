from __future__ import annotations

import asyncio
import logging
import ssl
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import asyncpg

from config.settings import Settings
from database.schema import SCHEMA_SQL

log = logging.getLogger(__name__)


def connection_options(settings: Settings) -> dict:
    parts = urlsplit(settings.database_url)
    query = dict(parse_qsl(parts.query))
    if settings.ca_file or settings.ca_pem:
        context = ssl.create_default_context(
            cafile=settings.ca_file or None, cadata=settings.ca_pem or None
        )
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        # An explicit context always verifies certificate AND hostname.
        query.pop("sslmode", None)
        query.pop("sslrootcert", None)
        ssl_option = context
    else:
        ssl_option = query.get("sslmode", "require")
    dsn = urlunsplit(parts._replace(query=urlencode(query)))
    return {
        "dsn": dsn,
        "ssl": ssl_option,
        "timeout": 15,
        "command_timeout": 30,
        "server_settings": {"timezone": "UTC"},
    }


class Database:
    def __init__(self, settings: Settings) -> None:
        self.options = connection_options(settings)
        self.pool: asyncpg.Pool | None = None

    async def open(self) -> None:
        delay = 1
        while True:
            try:
                self.pool = await asyncpg.create_pool(
                    min_size=1, max_size=6, max_inactive_connection_lifetime=120, **self.options
                )
                async with self.pool.acquire() as connection:
                    async with connection.transaction():
                        await connection.execute("SELECT pg_advisory_xact_lock($1)", 7378146625502)
                        await connection.execute(SCHEMA_SQL)
                log.info("PostgreSQL conectado; esquema preparado")
                return
            except (OSError, TimeoutError, asyncpg.PostgresConnectionError):
                if self.pool is not None:
                    self.pool.terminate()
                    self.pool = None
                log.warning("PostgreSQL no disponible; reintento en %ss", delay, exc_info=True)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    async def connect_dedicated(self) -> asyncpg.Connection:
        return await asyncpg.connect(**self.options)

    async def close(self) -> None:
        if self.pool is not None:
            try:
                await asyncio.wait_for(self.pool.close(), timeout=10)
            except TimeoutError:
                self.pool.terminate()
