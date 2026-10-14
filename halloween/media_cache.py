from __future__ import annotations

import asyncio
import hashlib
import logging
from io import BytesIO
from urllib.parse import urlsplit, urlunsplit

import aiohttp
import discord

from config.settings import DoorImages

log = logging.getLogger(__name__)
PHASES = ("closed", "waiting", "candy_win", "candy_lose", "timeout")
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def source_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def discord_image_url(url: str) -> str:
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.netloc != "cdn.discordapp.com"
        or not parts.path.startswith("/attachments/")
    ):
        raise ValueError("El adjunto no contiene una URL válida del CDN de Discord")
    # Discord refreshes unsigned attachment URLs when they are used in embed image fields.
    return urlunsplit(parts._replace(query="", fragment=""))


def image_extension(data: bytes) -> str:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        if int.from_bytes(data[4:8], "little") + 8 != len(data):
            raise ValueError("La descarga WebP está incompleta")
        return "webp"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    raise ValueError("La descarga no contiene una imagen WebP, PNG, GIF o JPEG")


class DiscordMediaCache:
    def __init__(self, bot) -> None:
        self.bot = bot
        self.sources = dict(bot.settings.images)
        self.prepared = False
        self.cached_count = 0
        self.expected_count = len(
            {
                getattr(images, phase)
                for images in self.sources.values()
                for phase in PHASES
                if getattr(images, phase)
            }
        )
        self.enabled = bot.settings.media_cache_channel_id is not None

    async def prepare(self) -> None:
        if self.prepared:
            return
        channel_id = self.bot.settings.media_cache_channel_id
        if channel_id is None:
            self.prepared = True
            return
        try:
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(channel_id)
            self._check_channel(channel)
            await self._prepare_images(channel)
        except (discord.HTTPException, OSError, TimeoutError, ValueError):
            log.warning(
                "No se pudo preparar el almacenamiento de imágenes en Discord; se conserva R2",
                exc_info=True,
            )
        self.prepared = True

    def _check_channel(self, channel) -> None:
        if not isinstance(channel, discord.TextChannel):
            raise ValueError("El canal de imágenes debe ser un canal de texto")
        member = channel.guild.me
        if member is None:
            raise ValueError("El bot no está disponible en el servidor del canal de imágenes")
        permissions = channel.permissions_for(member)
        if not all(
            getattr(permissions, name)
            for name in ("view_channel", "send_messages", "attach_files", "read_message_history")
        ):
            raise ValueError(
                "Faltan View Channel, Send Messages, Attach Files o Read Message History"
            )

    async def _prepare_images(self, channel) -> None:
        unique = dict.fromkeys(
            getattr(images, phase)
            for images in self.sources.values()
            for phase in PHASES
            if getattr(images, phase)
        )
        urls = {}
        uploaded = 0
        history = None
        timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(
            timeout=timeout, headers={"User-Agent": "Blackjack-media-cache/1.0"}
        ) as session:
            for source in unique:
                try:
                    key = source_hash(source)
                    row = await self.bot.repo.media_asset(self.bot.user.id, channel.id, key)
                    refresh = self.bot.settings.media_cache_refresh_key
                    if row and (not refresh or row["refresh_key"] == refresh):
                        try:
                            message = await channel.fetch_message(row["message_id"])
                        except discord.NotFound:
                            message = None
                        if message is not None:
                            attachment = self._attachment(message, row["attachment_id"])
                            if attachment is not None:
                                urls[source] = discord_image_url(attachment.url)
                                continue
                    # Recover uploads whose database save was interrupted before a restart.
                    marker = f"Blackjack media | {key} | {source_hash(refresh)}"
                    if history is None:
                        history = [message async for message in channel.history(limit=100)]
                    message = next(
                        (
                            message
                            for message in history
                            if (
                                message.author.id == self.bot.user.id
                                and message.content == marker
                                and message.attachments
                            )
                        ),
                        None,
                    )
                    new_upload = message is None
                    if new_upload:
                        data = await self._download(session, source, channel.guild.filesize_limit)
                        extension = image_extension(data)
                        file = discord.File(
                            BytesIO(data), filename=f"blackjack-{key[:16]}.{extension}"
                        )
                        try:
                            async with asyncio.timeout(30):
                                message = await channel.send(
                                    content=marker,
                                    file=file,
                                    allowed_mentions=discord.AllowedMentions.none(),
                                )
                        finally:
                            file.close()
                    attachment = self._attachment(message)
                    if attachment is None:
                        raise ValueError("Discord no devolvió un adjunto válido")
                    url = discord_image_url(attachment.url)
                    await self.bot.repo.save_media_asset(
                        self.bot.user.id,
                        channel.id,
                        key,
                        message.id,
                        attachment.id,
                        url,
                        refresh,
                    )
                    urls[source] = url
                    uploaded += int(new_upload)
                except (
                    discord.HTTPException,
                    aiohttp.ClientError,
                    OSError,
                    TimeoutError,
                    ValueError,
                ):
                    log.warning(
                        "Imagen %s no disponible en el almacenamiento Discord; se conserva R2",
                        source_hash(source)[:12],
                        exc_info=True,
                    )
        self.cached_count = len(urls)
        for language, images in self.sources.items():
            self.bot.settings.images[language] = DoorImages(
                **{
                    phase: urls.get(getattr(images, phase), getattr(images, phase))
                    for phase in PHASES
                }
            )
        log.info(
            "✅ Imágenes en Discord: %s/%s listas | Nuevas: %s | Reutilizadas: %s",
            len(urls),
            len(unique),
            uploaded,
            len(urls) - uploaded,
        )

    def _attachment(self, message, attachment_id=None):
        if message.author.id != self.bot.user.id:
            return None
        return next(
            (
                attachment
                for attachment in message.attachments
                if (attachment_id is None or attachment.id == attachment_id)
            ),
            None,
        )

    async def _download(self, session, source: str, guild_limit: int) -> bytes:
        limit = min(MAX_IMAGE_BYTES, guild_limit)
        async with session.get(source) as response:
            response.raise_for_status()
            if response.content_length is not None and response.content_length > limit:
                raise ValueError("La imagen supera el límite de adjuntos del servidor")
            data = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError("La imagen supera el límite de adjuntos del servidor")
            if not data:
                raise ValueError("La descarga de imagen está vacía")
            return bytes(data)
