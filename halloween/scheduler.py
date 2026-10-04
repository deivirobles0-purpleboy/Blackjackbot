from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from config.constants import INSTANCE_LOCK_KEY
from halloween.models import DropStatus
from utils.startup import log_ready_status

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, bot) -> None:
        self.bot = bot
        self.manager = bot.manager
        self.task: asyncio.Task | None = None
        self._open_checked: dict = {}

    def start(self) -> None:
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._supervise(), name="halloween-scheduler")

    async def close(self) -> None:
        self.manager.leader.clear()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        await self.manager.stop_jobs()

    async def _supervise(self) -> None:
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            connection = None
            try:
                connection = await self.bot.database.connect_dedicated()
                locked = await connection.fetchval(
                    "SELECT pg_try_advisory_lock($1)", INSTANCE_LOCK_KEY
                )
                if not locked:
                    log.warning("Otro proceso posee el scheduler; este proceso espera")
                    await asyncio.sleep(30)
                    continue
                self.manager.leader.set()
                self._open_checked.clear()
                reported = False
                while not self.bot.is_closed():
                    await connection.fetchval("SELECT 1")
                    if self.bot.is_ready():
                        await self._tick()
                        if not reported or self.bot.status_requested:
                            log.info(
                                "✅ Scheduler: activo | ES/BR independientes | Estado recuperado"
                            )
                            await log_ready_status(self.bot)
                            self.bot.status_requested = False
                            reported = True
                    await asyncio.sleep(5)
            except Exception:
                log.exception("Scheduler/DB no disponible; pausa y reconexión en 10s")
            finally:
                self.manager.leader.clear()
                await self.manager.stop_jobs()
                if connection and not connection.is_closed():
                    try:
                        await connection.close(timeout=5)
                    except (OSError, TimeoutError):
                        log.warning("Conexión de liderazgo cerrada forzosamente")
                        connection.terminate()
            await asyncio.sleep(10)

    async def _tick(self) -> None:
        drops = await self.bot.repo.live_drops()
        live_ids = {drop.id for drop in drops}
        self._open_checked = {
            key: value for key, value in self._open_checked.items() if key in live_ids
        }
        for drop in drops:
            self.manager.schedule_expiration(drop)
            check_open = time.monotonic() - self._open_checked.get(drop.id, -100) >= 60
            if drop.status != DropStatus.OPEN or check_open:
                self.manager.start_job(
                    f"resolve:{drop.id}" if drop.status == DropStatus.PROCESSING else str(drop.id),
                    self.manager.run_drop(drop.id, check_open=check_open),
                )
                if check_open:
                    self._open_checked[drop.id] = time.monotonic()
        for drop in await self.bot.repo.pending_cleanup():
            if drop.status == DropStatus.EXPIRED and drop.delete_at is None:
                self.manager.start_job(str(drop.id), self.manager.run_drop(drop.id))
            else:
                self.manager.schedule_deletion(drop)
        now = datetime.now(timezone.utc)
        for cfg in await self.bot.repo.enabled_configs():
            if not cfg.complete:
                log.warning("Configuración incompleta guild=%s lang=%s", cfg.guild_id, cfg.language)
                continue
            if cfg.next_drop_at is None:
                await self.bot.repo.repair_schedule(cfg.guild_id, cfg.language)
            elif cfg.next_drop_at <= now:
                key = f"timer:{cfg.guild_id}:{cfg.language}"
                self.manager.start_job(key, self.manager.due(cfg.guild_id, cfg.language))
