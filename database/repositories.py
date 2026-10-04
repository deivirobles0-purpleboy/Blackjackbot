from __future__ import annotations

import logging
import random
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import asyncpg

from config.constants import MAX_WINNERS
from halloween.models import (
    ClaimResult,
    ClaimStatus,
    DoorDrop,
    EventConfig,
    Language,
    validate_minutes,
)
from halloween.rewards import roll_reward

log = logging.getLogger(__name__)


class Repository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def ensure_config(self, guild_id: int) -> None:
        await self.pool.executemany(
            "INSERT INTO event_config (guild_id, language) VALUES ($1,$2) ON CONFLICT DO NOTHING",
            [(guild_id, language.value) for language in Language],
        )

    async def config(self, guild_id: int, language: Language) -> EventConfig:
        await self.ensure_config(guild_id)
        row = await self.pool.fetchrow(
            "SELECT * FROM event_config WHERE guild_id=$1 AND language=$2", guild_id, language
        )
        return EventConfig.from_record(row)

    async def enabled_configs(self) -> list[EventConfig]:
        rows = await self.pool.fetch(
            "SELECT * FROM event_config WHERE enabled ORDER BY guild_id,language"
        )
        return [EventConfig.from_record(row) for row in rows]

    async def guild_configs(self, guild_ids: list[int]) -> list[EventConfig]:
        rows = await self.pool.fetch(
            "SELECT * FROM event_config WHERE guild_id=ANY($1::bigint[]) ORDER BY guild_id,language",
            guild_ids,
        )
        return [EventConfig.from_record(row) for row in rows]

    async def suspend(self, guild_id: int, language: Language) -> None:
        await self.pool.execute(
            "UPDATE event_config SET enabled=FALSE,next_drop_at=NULL,updated_at=now() "
            "WHERE guild_id=$1 AND language=$2",
            guild_id,
            language,
        )

    async def set_channel(
        self, guild_id: int, language: Language, channel_id: int, admin_id: int
    ) -> None:
        await self.ensure_config(guild_id)
        async with self.pool.acquire() as con, con.transaction():
            await con.execute(
                "UPDATE event_config SET channel_id=$3,updated_at=now() WHERE guild_id=$1 AND language=$2",
                guild_id,
                language,
                channel_id,
            )
            await self._audit(con, guild_id, admin_id, language, "channel", amount=channel_id)

    async def set_minutes(
        self, guild_id: int, language: Language, minimum: int, maximum: int, admin_id: int
    ) -> None:
        validate_minutes(minimum, maximum)
        await self.ensure_config(guild_id)
        async with self.pool.acquire() as con, con.transaction():
            await con.execute(
                "UPDATE event_config SET min_minutes=$3,max_minutes=$4,updated_at=now() "
                "WHERE guild_id=$1 AND language=$2",
                guild_id,
                language,
                minimum,
                maximum,
            )
            await self._audit(con, guild_id, admin_id, language, "minutes_min", amount=minimum)
            await self._audit(con, guild_id, admin_id, language, "minutes_max", amount=maximum)

    async def set_enabled(self, guild_id: int, enabled: bool, admin_id: int) -> list[Language]:
        await self.ensure_config(guild_id)
        changed = []
        async with self.pool.acquire() as con, con.transaction():
            rows = await con.fetch(
                "SELECT * FROM event_config WHERE guild_id=$1 ORDER BY language FOR UPDATE",
                guild_id,
            )
            for row in rows:
                cfg = EventConfig.from_record(row)
                if enabled and not cfg.complete:
                    continue
                await con.execute(
                    "UPDATE event_config SET enabled=$3, "
                    "next_drop_at=CASE WHEN NOT $3 THEN NULL ELSE next_drop_at END, "
                    "updated_at=now() WHERE guild_id=$1 AND language=$2",
                    guild_id,
                    cfg.language,
                    enabled,
                )
                if enabled:
                    await self._schedule_if_idle(con, guild_id, cfg.language)
                else:
                    await con.execute(
                        "UPDATE door_drops SET status='cancelled',finished_at=now() "
                        "WHERE guild_id=$1 AND language=$2 AND NOT is_test AND status='publishing'",
                        guild_id,
                        cfg.language,
                    )
                changed.append(cfg.language)
                await self._audit(
                    con, guild_id, admin_id, cfg.language, "enable" if enabled else "disable"
                )
        return changed

    async def _schedule_if_idle(
        self, con: asyncpg.Connection, guild_id: int, language: Language
    ) -> None:
        row = await con.fetchrow(
            "SELECT * FROM event_config WHERE guild_id=$1 AND language=$2 FOR UPDATE",
            guild_id,
            language,
        )
        cfg = EventConfig.from_record(row)
        if not cfg.enabled or not cfg.complete or cfg.next_drop_at is not None:
            return
        live = await con.fetchval(
            "SELECT EXISTS(SELECT 1 FROM door_drops WHERE guild_id=$1 AND language=$2 "
            "AND NOT is_test AND status IN ('publishing','open','processing'))",
            guild_id,
            language,
        )
        if not live:
            delay = random.randint(cfg.min_minutes, cfg.max_minutes)
            next_drop = await con.fetchval(
                "UPDATE event_config SET next_drop_at=now()+make_interval(mins => $3),updated_at=now() "
                "WHERE guild_id=$1 AND language=$2 RETURNING next_drop_at",
                guild_id,
                language,
                delay,
            )
            log.info(
                "Próxima aparición guild=%s language=%s delay=%s min next=%s",
                guild_id,
                language,
                delay,
                next_drop,
            )

    async def repair_schedule(self, guild_id: int, language: Language) -> None:
        async with self.pool.acquire() as con, con.transaction():
            await self._schedule_if_idle(con, guild_id, language)

    async def prepare_drop(
        self,
        guild_id: int,
        language: Language,
        channel_id: int | None = None,
        *,
        is_test: bool = False,
        rewards_enabled: bool = True,
    ) -> DoorDrop | None:
        await self.ensure_config(guild_id)
        async with self.pool.acquire() as con, con.transaction():
            row = await con.fetchrow(
                "SELECT *, next_drop_at <= now() AS due FROM event_config "
                "WHERE guild_id=$1 AND language=$2 FOR UPDATE",
                guild_id,
                language,
            )
            if not is_test:
                if not row["enabled"] or not row["due"]:
                    return None
                if await con.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM door_drops WHERE guild_id=$1 AND language=$2 "
                    "AND NOT is_test AND status IN ('publishing','open','processing'))",
                    guild_id,
                    language,
                ):
                    return None
                channel_id = row["channel_id"]
            if channel_id is None:
                raise ValueError("Configura primero el canal de drops")
            drop = await con.fetchrow(
                "INSERT INTO door_drops (id,guild_id,language,channel_id,status,is_test,rewards_enabled) "
                "VALUES ($1,$2,$3,$4,'publishing',$5,$6) RETURNING *",
                uuid4(),
                guild_id,
                language,
                channel_id,
                is_test,
                rewards_enabled,
            )
            if not is_test:
                await con.execute(
                    "UPDATE event_config SET next_drop_at=NULL WHERE guild_id=$1 AND language=$2",
                    guild_id,
                    language,
                )
            return DoorDrop.from_record(drop)

    async def drop(self, drop_id: UUID) -> DoorDrop | None:
        row = await self.pool.fetchrow("SELECT * FROM door_drops WHERE id=$1", drop_id)
        return DoorDrop.from_record(row) if row else None

    async def live_drops(self) -> list[DoorDrop]:
        rows = await self.pool.fetch(
            "SELECT * FROM door_drops WHERE status IN ('publishing','open','processing') ORDER BY created_at"
        )
        return [DoorDrop.from_record(row) for row in rows]

    @asynccontextmanager
    async def publication(self, drop_id: UUID):
        async with self.pool.acquire() as con, con.transaction():
            drop = await con.fetchrow("SELECT * FROM door_drops WHERE id=$1", drop_id)
            if not drop:
                yield con, None
                return
            cfg = await con.fetchrow(
                "SELECT * FROM event_config WHERE guild_id=$1 AND language=$2 FOR UPDATE",
                drop["guild_id"],
                drop["language"],
            )
            drop = await con.fetchrow("SELECT * FROM door_drops WHERE id=$1 FOR UPDATE", drop_id)
            if drop["status"] != "publishing" or (not drop["is_test"] and not cfg["enabled"]):
                yield con, None
                return
            # Hold both locks across Discord publication so disable cannot race a pending send.
            yield con, DoorDrop.from_record(drop)

    async def bind_message(
        self, drop_id: UUID, message_id: int, connection: asyncpg.Connection | None = None
    ) -> None:
        if connection is None:
            async with self.publication(drop_id) as (con, drop):
                if drop:
                    await self.bind_message(drop_id, message_id, con)
            return
        result = await connection.fetchrow(
            "UPDATE door_drops SET message_id=$2,status='open' "
            "WHERE id=$1 AND status='publishing' RETURNING *",
            drop_id,
            message_id,
        )
        if result and not result["is_test"]:
            await connection.execute(
                "UPDATE event_config SET last_drop_at=$3,updated_at=now() "
                "WHERE guild_id=$1 AND language=$2",
                result["guild_id"],
                result["language"],
                result["created_at"],
            )

    async def claim(
        self,
        drop_id: UUID,
        user_id: int,
        eligible: bool,
        *,
        guild_id: int,
        channel_id: int,
        message_id: int,
        language: Language,
    ) -> ClaimResult:
        if not eligible:
            return ClaimResult(ClaimStatus.UNREGISTERED)
        async with self.pool.acquire() as con, con.transaction():
            row = await con.fetchrow("SELECT * FROM door_drops WHERE id=$1 FOR UPDATE", drop_id)
            if (
                not row
                or row["guild_id"] != guild_id
                or row["channel_id"] != channel_id
                or row["message_id"] != message_id
                or row["language"] != language
            ):
                return ClaimResult(ClaimStatus.CLOSED)
            if await con.fetchval(
                "SELECT EXISTS(SELECT 1 FROM door_winners WHERE drop_id=$1 AND user_id=$2)",
                drop_id,
                user_id,
            ):
                return ClaimResult(ClaimStatus.DUPLICATE)
            count = await con.fetchval(
                "SELECT count(*) FROM door_winners WHERE drop_id=$1", drop_id
            )
            if row["status"] != "open" or count >= MAX_WINNERS:
                return ClaimResult(ClaimStatus.CLOSED)
            candies = roll_reward()
            await con.execute(
                "INSERT INTO door_winners (drop_id,user_id,slot,candies) VALUES ($1,$2,$3,$4)",
                drop_id,
                user_id,
                count + 1,
                candies,
            )
            if row["rewards_enabled"]:
                await con.execute(
                    "INSERT INTO user_candies (guild_id,user_id,language,candies) VALUES ($1,$2,$3,$4) "
                    "ON CONFLICT (guild_id,user_id,language) DO UPDATE "
                    "SET candies=user_candies.candies+EXCLUDED.candies,updated_at=now()",
                    guild_id,
                    user_id,
                    language,
                    candies,
                )
            if count + 1 == MAX_WINNERS:
                await con.execute(
                    "UPDATE door_drops SET status='processing',processing_at=now() WHERE id=$1",
                    drop_id,
                )
            return ClaimResult(ClaimStatus.ACCEPTED, candies, count + 1)

    async def winners(self, drop_id: UUID) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            "SELECT user_id,candies,slot FROM door_winners WHERE drop_id=$1 ORDER BY slot", drop_id
        )

    async def finish(self, drop_id: UUID, *, cancelled: bool = False) -> None:
        async with self.pool.acquire() as con, con.transaction():
            row = await con.fetchrow("SELECT * FROM door_drops WHERE id=$1", drop_id)
            if not row:
                return
            await con.fetchrow(
                "SELECT guild_id FROM event_config WHERE guild_id=$1 AND language=$2 FOR UPDATE",
                row["guild_id"],
                row["language"],
            )
            updated = await con.fetchrow(
                "UPDATE door_drops SET status=$2,finished_at=now() "
                "WHERE id=$1 AND status IN ('publishing','open','processing') RETURNING *",
                drop_id,
                "cancelled" if cancelled else "finished",
            )
            if updated and not updated["is_test"]:
                await self._schedule_if_idle(
                    con, updated["guild_id"], Language(updated["language"])
                )

    async def ranking(self, guild_id: int, language: Language) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            "SELECT user_id,candies FROM user_candies WHERE guild_id=$1 AND language=$2 "
            "AND candies>0 ORDER BY candies DESC,user_id ASC LIMIT 15",
            guild_id,
            language,
        )

    async def adjust(
        self,
        guild_id: int,
        user_id: int,
        language: Language,
        action: str,
        amount: int,
        admin_id: int,
    ) -> int:
        if action not in {"add", "remove", "reset"}:
            raise ValueError("Acción inválida")
        if action != "reset" and not 0 < amount <= 9_223_372_036_854_775_807:
            raise ValueError("La cantidad debe ser positiva y válida")
        async with self.pool.acquire() as con, con.transaction():
            await con.execute(
                "INSERT INTO user_candies (guild_id,user_id,language) VALUES ($1,$2,$3) "
                "ON CONFLICT DO NOTHING",
                guild_id,
                user_id,
                language,
            )
            total = await con.fetchval(
                "UPDATE user_candies SET candies=CASE $4::text "
                "WHEN 'reset' THEN 0 WHEN 'add' THEN candies+$5::bigint "
                "ELSE greatest(0,candies-$5::bigint) END,updated_at=now() "
                "WHERE guild_id=$1 AND user_id=$2 AND language=$3 RETURNING candies",
                guild_id,
                user_id,
                language,
                action,
                amount,
            )
            await self._audit(con, guild_id, admin_id, language, action, user_id, amount)
            return total

    @staticmethod
    async def _audit(
        con: asyncpg.Connection,
        guild_id: int,
        admin_id: int,
        language: Language,
        action: str,
        target_id: int | None = None,
        amount: int | None = None,
    ) -> None:
        await con.execute(
            "INSERT INTO admin_logs (guild_id,admin_id,target_user_id,language,action,amount) "
            "VALUES ($1,$2,$3,$4,$5,$6)",
            guild_id,
            admin_id,
            target_id,
            language,
            action,
            amount,
        )
