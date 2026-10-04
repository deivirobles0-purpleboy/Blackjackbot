from __future__ import annotations

import asyncio
import logging
import time
import weakref
from collections.abc import Coroutine
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import discord

from config.constants import MAX_WINNERS, RESULT_DELETE_SECONDS, RESULT_REVEAL_SECONDS
from halloween.embeds import door_embed
from halloween.models import ClaimStatus, DoorDrop, DropStatus, Language
from halloween.texts import TEXTS
from halloween.views import DoorView, door_custom_id
from utils.roles import get_member, is_participant

log = logging.getLogger(__name__)


class DoorManager:
    def __init__(self, bot) -> None:
        self.bot = bot
        self.repo = bot.repo
        self.settings = bot.settings
        self.leader = asyncio.Event()
        self._locks: weakref.WeakValueDictionary[UUID, asyncio.Lock] = weakref.WeakValueDictionary()
        self.jobs: dict[str, asyncio.Task] = {}
        self._retry_at: dict[str, float] = {}

    def _lock(self, drop_id: UUID) -> asyncio.Lock:
        lock = self._locks.get(drop_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[drop_id] = lock
        return lock

    def require_leader(self) -> None:
        if not self.leader.is_set():
            raise ValueError(
                "El sistema de puertas se está reconectando. Inténtalo en unos momentos."
            )

    def start_job(self, key: str, work: Coroutine[Any, Any, None]) -> None:
        if key in self.jobs or time.monotonic() < self._retry_at.get(key, 0):
            work.close()
            return

        def completed(task: asyncio.Task) -> None:
            self.jobs.pop(key, None)
            if task.cancelled():
                return
            error = task.exception()
            if error is not None:
                log.error(
                    "Error recuperable procesando puerta/timer %s; reintento en 60s",
                    key,
                    exc_info=error,
                )
                self._retry_at[key] = time.monotonic() + 60
            else:
                self._retry_at.pop(key, None)

        task = asyncio.create_task(work, name=f"door:{key}")
        self.jobs[key] = task
        task.add_done_callback(completed)

    async def stop_jobs(self) -> None:
        jobs = list(self.jobs.values())
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        self.jobs.clear()

    async def _wait_until(self, deadline: datetime) -> None:
        delay = max(0, (deadline - datetime.now(timezone.utc)).total_seconds())
        await asyncio.sleep(delay)

    async def _wait_for_result(self, drop: DoorDrop) -> None:
        # Continue the original four-second countdown after a restart.
        started = drop.processing_at or datetime.now(timezone.utc)
        await self._wait_until(started + timedelta(seconds=RESULT_REVEAL_SECONDS))

    def schedule_expiration(self, drop: DoorDrop) -> None:
        if drop.status == DropStatus.OPEN and drop.expires_at is not None:
            self.start_job(f"expire:{drop.id}", self._expire_at(drop.id, drop.expires_at))

    async def _expire_at(self, drop_id: UUID, deadline: datetime) -> None:
        await self._wait_until(deadline)
        await self.run_drop(drop_id)

    def schedule_deletion(self, drop: DoorDrop) -> None:
        if drop.delete_at is not None and drop.deleted_at is None:
            self.start_job(f"delete:{drop.id}", self.delete_drop_message(drop.id))

    async def delete_drop_message(self, drop_id: UUID) -> None:
        drop = await self.repo.drop(drop_id)
        if not drop or drop.delete_at is None or drop.deleted_at is not None:
            return
        await self._wait_until(drop.delete_at)
        self.require_leader()
        async with self._lock(drop_id):
            drop = await self.repo.drop(drop_id)
            if (
                not drop
                or drop.deleted_at is not None
                or drop.delete_at is None
                or drop.status
                not in {DropStatus.FINISHED, DropStatus.EXPIRED, DropStatus.CANCELLED}
            ):
                return
            # A restarted scheduler resumes the stored deadline, rather than a fresh countdown.
            if drop.delete_at > datetime.now(timezone.utc):
                return
            try:
                channel = await self._channel(drop)
                message = await channel.fetch_message(drop.message_id)
                self.require_leader()
                await message.delete()
            except discord.NotFound:
                pass  # Already deleted; complete cleanup idempotently.
            await self.repo.mark_deleted(drop.id)
            log.info("Mensaje de puerta eliminado drop=%s message=%s", drop.id, drop.message_id)

    async def _channel(self, drop: DoorDrop) -> discord.TextChannel:
        channel = self.bot.get_channel(drop.channel_id)
        if channel is None:
            channel = await self.bot.fetch_channel(drop.channel_id)
        if not isinstance(channel, discord.TextChannel) or channel.guild.id != drop.guild_id:
            raise ValueError("El canal configurado no es un canal de texto de este servidor")
        member = channel.guild.me
        if member is None:
            member = await channel.guild.fetch_member(self.bot.user.id)
        permissions = channel.permissions_for(member)
        if not all(
            (
                permissions.view_channel,
                permissions.send_messages,
                permissions.embed_links,
                permissions.read_message_history,
            )
        ):
            raise ValueError(
                "Faltan View Channel, Send Messages, Embed Links o Read Message History"
            )
        return channel

    async def _find_published(
        self, channel: discord.TextChannel, drop: DoorDrop
    ) -> discord.Message | None:
        custom_id = door_custom_id(drop.language, drop.id)
        # Recover the send/commit crash window by finding the persisted ID in message components.
        async for message in channel.history(
            limit=None, after=drop.created_at - timedelta(seconds=5)
        ):
            if message.author.id == self.bot.user.id and any(
                getattr(child, "custom_id", None) == custom_id
                for row in message.components
                for child in row.children
            ):
                return message
        return None

    async def run_drop(self, drop_id: UUID, *, check_open: bool = False) -> None:
        self.require_leader()
        async with self._lock(drop_id):
            drop = await self.repo.drop(drop_id)
            if not drop or drop.status in {DropStatus.FINISHED, DropStatus.CANCELLED}:
                return
            if drop.deleted_at is not None:
                return
            if drop.status == DropStatus.OPEN:
                expired = await self.repo.expire_unopened(drop.id)
                if expired:
                    drop = expired
                else:
                    self.schedule_expiration(drop)
            if drop.status == DropStatus.EXPIRED and drop.delete_at is not None:
                self.schedule_deletion(drop)
                return
            try:
                channel = await self._channel(drop)
            except (discord.NotFound, discord.Forbidden, ValueError) as error:
                if drop.status == DropStatus.EXPIRED:
                    if isinstance(error, discord.NotFound):
                        await self.repo.mark_deleted(drop.id)
                        return
                    raise
                log.exception("Canal de puerta inaccesible drop=%s", drop.id)
                if not drop.is_test:
                    await self.repo.suspend(drop.guild_id, drop.language)
                await self.repo.finish(drop.id, cancelled=True)
                return
            if drop.status == DropStatus.PUBLISHING:
                async with self.repo.publication(drop.id) as (connection, current):
                    if current is None:
                        return
                    message = await self._find_published(channel, current)
                    self.require_leader()
                    if message is None:
                        message = await channel.send(
                            embed=door_embed(current, "closed", self.settings),
                            view=DoorView(current.language, current.id),
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                    await self.repo.bind_message(
                        drop.id,
                        message.id,
                        connection,
                        published_at=getattr(message, "created_at", None),
                    )
                log.info(
                    "Puerta publicada id=%s language=%s channel=%s message=%s test=%s",
                    drop.id,
                    drop.language,
                    drop.channel_id,
                    message.id,
                    drop.is_test,
                )
                self.schedule_expiration(await self.repo.drop(drop.id))
                return
            if drop.message_id is None:
                await self.repo.finish(drop.id, cancelled=True)
                return
            if drop.status == DropStatus.OPEN and not check_open:
                return
            try:
                message = await channel.fetch_message(drop.message_id)
                if drop.status == DropStatus.OPEN:
                    return
                self.require_leader()
                if drop.status == DropStatus.EXPIRED:
                    await message.edit(
                        embed=door_embed(drop, "expired", self.settings),
                        view=DoorView(drop.language, drop.id, expired=True),
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    current = await self.repo.mark_expired_displayed(drop.id)
                    self.schedule_deletion(current)
                    log.info("Puerta vencida sin participantes drop=%s", drop.id)
                    return
                await message.edit(
                    embed=door_embed(drop, "waiting", self.settings),
                    view=DoorView(drop.language, drop.id, disabled=True),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                await self._wait_for_result(drop)
                winners = await self.repo.winners(drop.id)
                self.require_leader()
                await message.edit(
                    embed=door_embed(drop, "result", self.settings, winners),
                    view=None,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.NotFound:
                if drop.status == DropStatus.EXPIRED:
                    await self.repo.mark_deleted(drop.id)
                    return
                log.warning(
                    "Mensaje eliminado drop=%s; se conservan recompensas confirmadas", drop.id
                )
                await self.repo.finish(drop.id, cancelled=True)
                return
            except discord.Forbidden:
                if drop.status == DropStatus.EXPIRED:
                    raise
                log.exception("No se puede editar puerta drop=%s; suspensión controlada", drop.id)
                if not drop.is_test:
                    await self.repo.suspend(drop.guild_id, drop.language)
                await self.repo.finish(drop.id, cancelled=True)
                return
            await self.repo.finish(drop.id, delete_after=RESULT_DELETE_SECONDS)
            self.schedule_deletion(await self.repo.drop(drop.id))
            log.info("Puerta finalizada id=%s ganadores=%s", drop.id, [dict(w) for w in winners])

    async def due(self, guild_id: int, language: Language) -> None:
        self.require_leader()
        drop = await self.repo.prepare_drop(guild_id, language)
        if drop:
            await self.run_drop(drop.id)

    async def create_test(
        self, guild_id: int, language: Language, channel_id: int, rewards_enabled: bool
    ) -> DoorDrop:
        self.require_leader()
        drop = await self.repo.prepare_drop(
            guild_id, language, channel_id, is_test=True, rewards_enabled=rewards_enabled
        )
        await self.run_drop(drop.id)
        current = await self.repo.drop(drop.id)
        if current.status == DropStatus.CANCELLED:
            raise ValueError(
                "No se pudo publicar la puerta. Revisa el canal y los permisos del bot."
            )
        return current

    async def claim(
        self, interaction: discord.Interaction, drop_id: UUID, language: Language
    ) -> None:
        # Acknowledge the button silently: accepted claims reveal only in the public embed.
        await interaction.response.defer()
        member = await get_member(interaction)
        text = TEXTS[language]
        self.require_leader()
        if interaction.message is None:
            raise ValueError("La interacción no está vinculada a una puerta")
        async with self._lock(drop_id):
            self.require_leader()
            result = await self.repo.claim(
                drop_id,
                member.id,
                is_participant(role.id for role in member.roles),
                guild_id=member.guild.id,
                channel_id=interaction.channel_id,
                message_id=interaction.message.id,
                language=language,
            )
            if result.status == ClaimStatus.ACCEPTED:
                log.info(
                    "Claim confirmado drop=%s user=%s reward=%s slot=%s",
                    drop_id,
                    member.id,
                    result.candies,
                    result.count,
                )
                if result.count == MAX_WINNERS:
                    self.start_job(str(drop_id), self.run_drop(drop_id))
                return
            elif result.status == ClaimStatus.EXPIRED:
                message = text.expired
                self.start_job(str(drop_id), self.run_drop(drop_id))
            elif result.status == ClaimStatus.UNREGISTERED:
                log.info(
                    "Claim sin registro rechazado guild=%s user=%s drop=%s",
                    member.guild.id,
                    member.id,
                    drop_id,
                )
                await interaction.followup.send(
                    embed=discord.Embed(description=text.not_registered, color=0xF28C28),
                    ephemeral=True,
                )
                return
            elif result.status == ClaimStatus.DUPLICATE:
                message = text.duplicate
            else:
                message = text.unavailable
        await interaction.followup.send(message, ephemeral=True)
