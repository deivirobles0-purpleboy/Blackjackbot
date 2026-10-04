from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config.settings import DEFAULT_DOOR_IMAGES, Settings
from halloween.manager import DoorManager
from halloween.models import DropStatus, Language
from halloween.views import door_custom_id
from tests.test_postgres import CHANNEL, GUILD, STAFF, claim, ready

pytestmark = pytest.mark.postgres


class FakeMessage:
    def __init__(self, message_id, custom_id, embed, author_id):
        self.id = message_id
        self.author = SimpleNamespace(id=author_id)
        self.components = [SimpleNamespace(children=[SimpleNamespace(custom_id=custom_id)])]
        self.edits = []
        self.embed = embed
        self.deletes = 0

    async def edit(self, **kwargs):
        self.edits.append(kwargs)
        return self

    async def delete(self):
        self.deletes += 1


class FakeChannel:
    def __init__(self):
        self.messages = {}
        self.sends = 0

    def history(self, **kwargs):
        async def items():
            for message in self.messages.values():
                yield message

        return items()

    async def send(self, **kwargs):
        self.sends += 1
        message = FakeMessage(
            100 + self.sends, kwargs["view"].children[0].custom_id, kwargs["embed"], 55
        )
        self.messages[message.id] = message
        return message

    async def fetch_message(self, message_id):
        return self.messages[message_id]


def manager(repo, channel, *, schedule_timers=False):
    settings = Settings(
        "test",
        "postgresql://test@localhost/test?sslmode=require",
        DEFAULT_DOOR_IMAGES.copy(),
    )
    bot = SimpleNamespace(repo=repo, settings=settings, user=SimpleNamespace(id=55))
    mgr = DoorManager(bot)
    mgr.leader.set()
    mgr._channel = AsyncMock(return_value=channel)
    if not schedule_timers:
        # These tests drive each stage explicitly; timer execution has separate tests.
        def discard_job(key, work):
            work.close()

        mgr.start_job = discard_job
    return mgr


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("candy_win", [True, False])
async def test_three_phases_same_message_and_processing_recovery(
    repo, monkeypatch, language, candy_win
):
    await ready(repo, language)
    await repo.set_probabilities(
        GUILD, language, 100 if candy_win else 0, 0 if candy_win else 100, STAFF
    )
    if not candy_win:
        await repo.adjust(GUILD, 11, language, "add", 10, STAFF)
        await repo.adjust(GUILD, 12, language, "add", 10, STAFF)
        losses = iter([3, 4])
        monkeypatch.setattr("database.repositories.roll_loss", lambda: next(losses))
    channel = FakeChannel()
    mgr = manager(repo, channel)
    drop = await repo.prepare_drop(GUILD, language, CHANNEL, is_test=True)
    await mgr.run_drop(drop.id)
    drop = await repo.drop(drop.id)
    await claim(repo, drop, 11)
    await claim(repo, drop, 12)
    balances = [dict(row) for row in await repo.ranking(GUILD, language)]
    restarted = manager(repo, channel)
    monkeypatch.setattr("halloween.manager.asyncio.sleep", AsyncMock())
    await restarted.run_drop(drop.id)
    await restarted.run_drop(drop.id)
    message = channel.messages[drop.message_id]
    assert channel.sends == 1
    assert len(message.edits) == 2
    assert message.edits[0]["view"].children[0].disabled
    assert message.edits[1]["view"] is None
    assert message.embed.image.url == DEFAULT_DOOR_IMAGES[language].closed
    assert message.edits[0]["embed"].image.url == DEFAULT_DOOR_IMAGES[language].waiting
    result_embed = message.edits[1]["embed"]
    assert result_embed.image.url == getattr(
        DEFAULT_DOOR_IMAGES[language], "candy_win" if candy_win else "candy_lose"
    )
    if not candy_win:
        assert "<@11>: -3\n<@12>: -4" in result_embed.description
        assert result_embed.title == (
            "Que mal! Truco..." if language == Language.ES else "Foi mal! Travessuras..."
        )
    assert (await repo.drop(drop.id)).status == DropStatus.FINISHED
    finished = await repo.drop(drop.id)
    assert 19 <= (finished.delete_at - finished.finished_at).total_seconds() <= 21
    assert [dict(row) for row in await repo.ranking(GUILD, language)] == balances
    await repo.pool.execute(
        "UPDATE door_drops SET delete_at=now()-interval '1 second' WHERE id=$1", drop.id
    )
    await restarted.delete_drop_message(drop.id)
    await restarted.delete_drop_message(drop.id)
    assert message.deletes == 1
    assert (await repo.drop(drop.id)).deleted_at is not None
    assert [dict(row) for row in await repo.ranking(GUILD, language)] == balances


async def test_recover_send_before_message_id_commit_without_duplicate(repo):
    await ready(repo)
    channel = FakeChannel()
    mgr = manager(repo, channel)
    drop = await repo.prepare_drop(GUILD, Language.ES, CHANNEL, is_test=True)
    # Discord accepted the message; the process crashed before the DB commit.
    message = FakeMessage(888, door_custom_id(Language.ES, drop.id), None, 55)
    channel.messages[888] = message
    await mgr.run_drop(drop.id)
    assert channel.sends == 0
    recovered = await repo.drop(drop.id)
    assert recovered.message_id == 888
    assert recovered.status == DropStatus.OPEN


async def test_disable_cancels_unpublished_automatic_door(repo):
    await ready(repo)
    await repo.set_enabled(GUILD, True, STAFF)
    await repo.pool.execute(
        "UPDATE event_config SET next_drop_at=now()-interval '1 second' WHERE guild_id=$1", GUILD
    )
    drop = await repo.prepare_drop(GUILD, Language.ES)
    await repo.set_enabled(GUILD, False, STAFF)
    channel = FakeChannel()
    await manager(repo, channel).run_drop(drop.id)
    assert channel.sends == 0
    assert (await repo.drop(drop.id)).status == DropStatus.CANCELLED


async def test_disable_waits_for_inflight_publication(repo):
    import asyncio

    await ready(repo)
    await repo.set_enabled(GUILD, True, STAFF)
    await repo.pool.execute(
        "UPDATE event_config SET next_drop_at=now()-interval '1 second' WHERE guild_id=$1", GUILD
    )
    drop = await repo.prepare_drop(GUILD, Language.ES)
    async with repo.publication(drop.id) as (connection, current):
        assert current is not None
        disabling = asyncio.create_task(repo.set_enabled(GUILD, False, STAFF))
        await asyncio.sleep(0.02)
        assert not disabling.done()
        await repo.bind_message(drop.id, 777, connection)
    await disabling
    assert (await repo.drop(drop.id)).status == DropStatus.OPEN
    assert not (await repo.config(GUILD, Language.ES)).enabled
    await repo.finish(drop.id)
    assert (await repo.config(GUILD, Language.ES)).next_drop_at is None
