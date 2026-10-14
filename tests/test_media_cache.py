from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from config.settings import DEFAULT_DOOR_IMAGES, Settings
from halloween.media_cache import (
    PHASES,
    DiscordMediaCache,
    discord_image_url,
    image_extension,
    source_hash,
)
from halloween.models import Language

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aF0kAAAAASUVORK5CYII="
)


class Assets:
    def __init__(self):
        self.rows = {}
        self.media_asset = AsyncMock(
            side_effect=lambda bot, channel, key: self.rows.get((bot, channel, key))
        )
        self.save_media_asset = AsyncMock(side_effect=self.save)

    async def save(self, bot, channel, key, message_id, attachment_id, url, refresh):
        self.rows[bot, channel, key] = dict(
            message_id=message_id,
            attachment_id=attachment_id,
            cdn_url=url,
            refresh_key=refresh,
        )


class Channel:
    id = 1556194178902396999

    def __init__(self):
        self.guild = SimpleNamespace(filesize_limit=20 * 1024 * 1024)
        self.messages = {}
        self.uploads = []
        self.send = AsyncMock(side_effect=self.upload)
        self.fetch_message = AsyncMock(side_effect=self.fetch)
        self.history_calls = 0

    async def upload(self, *, content, file, allowed_mentions):
        self.uploads.append(file.fp.read())
        message_id = 1000 + len(self.uploads)
        attachment = SimpleNamespace(
            id=message_id + 1000,
            filename=file.filename,
            url=f"https://cdn.discordapp.com/attachments/{self.id}/{message_id + 1000}/{file.filename}?ex=old&is=old&hm=signature",
        )
        message = SimpleNamespace(
            id=message_id, author=SimpleNamespace(id=55), content=content, attachments=[attachment]
        )
        self.messages[message_id] = message
        assert allowed_mentions.to_dict() == discord.AllowedMentions.none().to_dict()
        return message

    async def fetch(self, message_id):
        if message_id not in self.messages:
            raise discord.NotFound(
                SimpleNamespace(status=404, reason="Not Found"), "Unknown Message"
            )
        return self.messages[message_id]

    def history(self, *, limit):
        self.history_calls += 1

        async def messages():
            for message in reversed(list(self.messages.values())[-limit:]):
                yield message

        return messages()


def cache_context(repo=None, channel=None, **settings_options):
    repo = repo or Assets()
    channel = channel or Channel()
    settings = Settings(
        "test", "postgresql://test@localhost/test", DEFAULT_DOOR_IMAGES.copy(), **settings_options
    )
    bot = SimpleNamespace(
        settings=settings, repo=repo, user=SimpleNamespace(id=55), get_channel=lambda _: channel
    )
    cache = DiscordMediaCache(bot)
    cache._check_channel = Mock()
    cache._download = AsyncMock(return_value=PNG)
    return cache, repo, channel


async def test_startup_uploads_unique_images_and_reuses_them_without_r2_after_restart():
    cache, repo, channel = cache_context()
    await cache.prepare()
    assert cache.cached_count == 4
    assert cache._download.await_count == 4
    assert channel.send.await_count == 4
    assert len(repo.rows) == 4
    assert channel.history_calls == 1
    for language in Language:
        for phase in PHASES:
            url = getattr(cache.bot.settings.images[language], phase)
            assert url.startswith("https://cdn.discordapp.com/attachments/")
            assert "?" not in url
            assert "r2.dev" not in url
    assert cache.bot.settings.images[Language.ES] == cache.bot.settings.images[Language.BR]
    assert (
        cache.bot.settings.images[Language.ES].closed
        == cache.bot.settings.images[Language.ES].waiting
    )
    await cache.prepare()
    assert cache._download.await_count == 4

    restarted, _, _ = cache_context(repo, channel)
    await restarted.prepare()
    restarted._download.assert_not_awaited()
    assert channel.send.await_count == 4
    assert channel.fetch_message.await_count == 4
    assert restarted.bot.settings.images == cache.bot.settings.images


async def test_refresh_is_once_and_can_be_disabled_without_losing_discord_images():
    first, repo, channel = cache_context()
    await first.prepare()
    old_urls = dict(first.bot.settings.images)
    renewed, _, _ = cache_context(repo, channel, media_cache_refresh_key="next-version")
    await renewed.prepare()
    assert channel.send.await_count == 8
    assert renewed.bot.settings.images != old_urls
    assert len(channel.messages) == 8  # Older public embeds retain their existing attachments.
    again, _, _ = cache_context(repo, channel, media_cache_refresh_key="next-version")
    await again.prepare()
    again._download.assert_not_awaited()
    disabled_refresh, _, _ = cache_context(repo, channel, media_cache_refresh_key="")
    await disabled_refresh.prepare()
    disabled_refresh._download.assert_not_awaited()
    assert disabled_refresh.bot.settings.images == renewed.bot.settings.images
    assert channel.send.await_count == 8


async def test_missing_attachment_is_recreated_but_other_images_reuse_discord():
    first, repo, channel = cache_context()
    await first.prepare()
    del channel.messages[1001]
    restarted, _, _ = cache_context(repo, channel)
    await restarted.prepare()
    assert restarted._download.await_count == 1
    assert channel.send.await_count == 5
    assert restarted.cached_count == 4


async def test_upload_database_crash_is_recovered_from_own_messages_without_redownload():
    first, repo, channel = cache_context()
    await first.prepare()
    repo.rows.clear()
    restarted, _, _ = cache_context(repo, channel)
    await restarted.prepare()
    restarted._download.assert_not_awaited()
    assert len(repo.rows) == 4
    assert channel.send.await_count == 4


async def test_one_failed_image_falls_back_to_source_without_stopping_other_phases():
    cache, _, channel = cache_context()

    async def download(_, source, limit):
        if "RobaOpti" in source:
            raise OSError("R2 unavailable")
        return PNG

    cache._download.side_effect = download
    await cache.prepare()
    assert cache.cached_count == 3
    assert channel.send.await_count == 3
    for language in Language:
        assert (
            cache.bot.settings.images[language].candy_lose
            == DEFAULT_DOOR_IMAGES[language].candy_lose
        )
        assert cache.bot.settings.images[language].candy_win.startswith(
            "https://cdn.discordapp.com/"
        )


async def test_disabling_channel_uses_sources_without_any_network_calls():
    cache, repo, channel = cache_context(media_cache_channel_id=None)
    await cache.prepare()
    cache._download.assert_not_awaited()
    repo.media_asset.assert_not_awaited()
    channel.send.assert_not_awaited()
    assert cache.bot.settings.images == DEFAULT_DOOR_IMAGES


async def test_inaccessible_cache_channel_does_not_stop_bot_or_change_sources():
    cache, repo, channel = cache_context()
    cache.bot.get_channel = lambda _: None
    cache.bot.fetch_channel = AsyncMock(
        side_effect=discord.Forbidden(
            SimpleNamespace(status=403, reason="Forbidden"), "Missing Access"
        )
    )
    await cache.prepare()
    assert cache.prepared
    assert cache.cached_count == 0
    cache._download.assert_not_awaited()
    repo.media_asset.assert_not_awaited()
    assert cache.bot.settings.images == DEFAULT_DOOR_IMAGES


async def test_scheduler_prepares_images_before_enabling_drops(monkeypatch):
    import asyncio

    from halloween.scheduler import Scheduler

    leader = asyncio.Event()
    closed = False
    connection = SimpleNamespace(
        fetchval=AsyncMock(side_effect=[True, 1]),
        is_closed=lambda: False,
        close=AsyncMock(),
    )

    async def prepare():
        assert not leader.is_set()

    bot = SimpleNamespace(
        manager=SimpleNamespace(leader=leader, stop_jobs=AsyncMock()),
        media_cache=SimpleNamespace(prepare=AsyncMock(side_effect=prepare)),
        database=SimpleNamespace(connect_dedicated=AsyncMock(return_value=connection)),
        wait_until_ready=AsyncMock(),
        is_closed=lambda: closed,
        is_ready=lambda: True,
        status_requested=False,
    )
    scheduler = Scheduler(bot)

    async def tick():
        nonlocal closed
        bot.media_cache.prepare.assert_awaited_once()
        assert leader.is_set()
        closed = True

    scheduler._tick = tick
    monkeypatch.setattr("halloween.scheduler.asyncio.sleep", AsyncMock())
    monkeypatch.setattr("halloween.scheduler.log_ready_status", AsyncMock())
    await scheduler._supervise()
    assert not leader.is_set()
    connection.close.assert_awaited_once()


@pytest.mark.parametrize(
    "permission", ["view_channel", "send_messages", "attach_files", "read_message_history"]
)
def test_cache_permissions_must_allow_upload_and_history(permission):
    cache, _, _ = cache_context()
    channel = Mock(spec=discord.TextChannel)
    channel.guild.me = SimpleNamespace(id=55)
    channel.permissions_for.return_value = SimpleNamespace(
        **{
            name: name != permission
            for name in ("view_channel", "send_messages", "attach_files", "read_message_history")
        }
    )
    with pytest.raises(ValueError, match="Faltan"):
        DiscordMediaCache._check_channel(cache, channel)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/attachments/a",
        "http://cdn.discordapp.com/attachments/a",
        "https://cdn.discordapp.com/avatars/a",
    ],
)
def test_only_discord_attachment_urls_can_replace_sources(url):
    with pytest.raises(ValueError):
        discord_image_url(url)


@pytest.mark.parametrize("data", [b"", b"<html>Error</html>", b"RIFF\xff\xff\xff\xffWEBP"])
def test_empty_error_pages_and_truncated_webp_cannot_be_uploaded(data):
    with pytest.raises(ValueError):
        image_extension(data)


async def test_download_checks_file_size_and_magic(monkeypatch):
    cache, _, _ = cache_context()
    del cache._download

    class Content:
        async def iter_chunked(self, _):
            yield PNG[:10]
            yield PNG[10:]

    response = SimpleNamespace(content_length=None, content=Content(), raise_for_status=Mock())

    class Request:
        async def __aenter__(self):
            return response

        async def __aexit__(self, *args):
            pass

    session = SimpleNamespace(get=lambda _: Request())
    assert await cache._download(session, "https://example.com/test", len(PNG)) == PNG
    assert image_extension(PNG) == "png"
    with pytest.raises(ValueError, match="límite"):
        await cache._download(session, "https://example.com/test", len(PNG) - 1)
    response.content_length = len(PNG)
    with pytest.raises(ValueError, match="límite"):
        await cache._download(session, "https://example.com/test", 1)


@pytest.mark.postgres
async def test_media_metadata_persists_and_is_scoped_to_bot_channel_and_source(repo):
    key = source_hash("https://example.com/media.webp")
    await repo.save_media_asset(
        55, 66, key, 77, 88, "https://cdn.discordapp.com/attachments/66/88/media.webp", "first"
    )
    assert (await repo.media_asset(55, 66, key))["message_id"] == 77
    assert await repo.media_asset(54, 66, key) is None
    assert await repo.media_asset(55, 65, key) is None
    await repo.save_media_asset(
        55, 66, key, 99, 100, "https://cdn.discordapp.com/attachments/66/100/media.webp", "next"
    )
    row = await repo.media_asset(55, 66, key)
    assert row["message_id"] == 99
    assert row["refresh_key"] == "next"
    assert await repo.pool.fetchval("SELECT count(*) FROM discord_media_cache") == 1


@pytest.mark.postgres
@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("candy_win", [True, False])
async def test_real_door_phases_use_persisted_discord_images(repo, language, candy_win):
    from tests.test_flow import FakeChannel, manager
    from tests.test_postgres import CHANNEL, GUILD, STAFF, claim, ready

    await ready(repo, language)
    await repo.set_probabilities(
        GUILD, language, 100 if candy_win else 0, 0 if candy_win else 100, STAFF
    )
    public = FakeChannel()
    assets = Channel()
    mgr = manager(repo, public)
    mgr.bot.get_channel = lambda _: assets
    cache = DiscordMediaCache(mgr.bot)
    cache._check_channel = Mock()
    cache._download = AsyncMock(return_value=PNG)
    await cache.prepare()
    drop = await repo.prepare_drop(GUILD, language, CHANNEL, is_test=True)
    await mgr.run_drop(drop.id)
    drop = await repo.drop(drop.id)
    await claim(repo, drop, 11)
    await claim(repo, drop, 12)
    mgr._wait_for_result = AsyncMock()
    await mgr.run_drop(drop.id)
    message = public.messages[drop.message_id]
    for embed in [message.embed, *(edit["embed"] for edit in message.edits)]:
        assert embed.image.url.startswith("https://cdn.discordapp.com/attachments/")
        assert "r2.dev" not in embed.image.url
        assert "?" not in embed.image.url
    assert public.sends == 1
    assert message.edits[-1]["view"] is None
    assert (await repo.drop(drop.id)).delete_at is not None
    assert await repo.pool.fetchval("SELECT count(*) FROM discord_media_cache") == 4


@pytest.mark.parametrize("channel", ["0", "-1", "abc", str(2**63)])
def test_settings_reject_invalid_media_channel(monkeypatch, channel):
    monkeypatch.setattr("config.settings.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("DISCORD_TOKEN", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
    monkeypatch.setenv("DISCORD_MEDIA_CACHE_CHANNEL_ID", channel)
    with pytest.raises(ValueError, match="DISCORD_MEDIA_CACHE_CHANNEL_ID"):
        Settings.from_env()


def test_refresh_environment_accepts_empty_to_keep_cached_attachments(monkeypatch):
    monkeypatch.setattr("config.settings.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("DISCORD_TOKEN", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
    monkeypatch.setenv("DISCORD_MEDIA_CACHE_CHANNEL_ID", "1556194178902396999")
    monkeypatch.setenv("DISCORD_MEDIA_CACHE_REFRESH_KEY", "")
    settings = Settings.from_env()
    assert settings.media_cache_channel_id == 1556194178902396999
    assert settings.media_cache_refresh_key == ""
    monkeypatch.setenv("DISCORD_MEDIA_CACHE_CHANNEL_ID", "")
    assert Settings.from_env().media_cache_channel_id is None
