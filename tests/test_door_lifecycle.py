import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import discord
import pytest

from config.settings import DEFAULT_DOOR_TIMEOUT_URL
from halloween.models import ClaimStatus, DoorDrop, DropStatus, Language
from halloween.scheduler import Scheduler
from halloween.texts import TEXTS
from halloween.views import DoorView
from tests.test_flow import FakeChannel, manager
from tests.test_postgres import CHANNEL, GUILD, STAFF, claim, door, ready


async def make_overdue(repo, drop):
    await repo.pool.execute(
        "UPDATE door_drops SET expires_at=clock_timestamp()-interval '1 microsecond' WHERE id=$1",
        drop.id,
    )


@pytest.mark.postgres
@pytest.mark.parametrize("language", list(Language))
async def test_six_second_deadline_starts_on_publication_and_survives_reload(repo, language):
    await ready(repo, language)
    drop = await repo.prepare_drop(GUILD, language, CHANNEL, is_test=True)
    assert drop.expires_at is None
    published = datetime.now(timezone.utc)
    await repo.bind_message(drop.id, 100, published_at=published)
    assert (await repo.drop(drop.id)).expires_at == published + timedelta(seconds=6)
    await repo.pool.execute("SELECT 1")
    assert (await repo.drop(drop.id)).expires_at == published + timedelta(seconds=6)


@pytest.mark.postgres
@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("win", [True, False])
async def test_late_first_click_never_changes_scores_even_before_timer_runs(repo, language, win):
    await repo.set_probabilities(GUILD, language, 100 if win else 0, 0 if win else 100, STAFF)
    await repo.adjust(GUILD, 11, language, "add", 10, STAFF)
    drop = await door(repo, language)
    await make_overdue(repo, drop)
    assert (await claim(repo, drop, 11)).status == ClaimStatus.EXPIRED
    assert (await repo.ranking(GUILD, language))[0]["candies"] == 10
    assert await repo.winners(drop.id) == []
    assert (await repo.drop(drop.id)).status == DropStatus.OPEN


@pytest.mark.postgres
async def test_first_click_collects_until_second_click_starts_waiting(repo):
    drop = await door(repo)
    assert drop.expires_at is not None
    assert (await claim(repo, drop, 11)).status == ClaimStatus.ACCEPTED
    collecting = await repo.drop(drop.id)
    assert collecting.expires_at == drop.expires_at
    assert collecting.processing_at is None
    assert await repo.begin_waiting(drop.id) is None
    assert await repo.expire_unopened(drop.id) is None
    assert (await claim(repo, drop, 12)).status == ClaimStatus.ACCEPTED
    assert (await repo.drop(drop.id)).status == DropStatus.PROCESSING
    waiting = await repo.drop(drop.id)
    assert waiting.expires_at is None
    assert waiting.processing_at is not None
    assert (await repo.begin_waiting(drop.id)).processing_at == waiting.processing_at


@pytest.mark.postgres
@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("win", [True, False])
async def test_collecting_single_participant_recovers_then_disables_waiting_button(
    repo, monkeypatch, language, win
):
    await ready(repo, language)
    await repo.set_probabilities(GUILD, language, 100 if win else 0, 0 if win else 100, STAFF)
    if not win:
        await repo.adjust(GUILD, 11, language, "add", 10, STAFF)
    channel = FakeChannel()
    mgr = manager(repo, channel)
    drop = await repo.prepare_drop(GUILD, language, CHANNEL, is_test=True)
    await mgr.run_drop(drop.id)
    drop = await repo.drop(drop.id)
    await claim(repo, drop, 11)
    balances = [dict(row) for row in await repo.ranking(GUILD, language)]

    restarted = manager(repo, channel)
    scheduled = []

    def capture(key, work):
        scheduled.append(key)
        work.close()

    restarted.start_job = capture
    await restarted.run_drop(drop.id)
    assert scheduled == [f"collect:{drop.id}"]
    assert channel.messages[drop.message_id].edits == []
    assert (await repo.drop(drop.id)).expires_at == drop.expires_at
    await make_overdue(repo, drop)
    waiting = await repo.begin_waiting(drop.id)
    assert waiting.processing_at is not None
    assert (await claim(repo, drop, 12)).status == ClaimStatus.CLOSED
    restarted._wait_for_result = AsyncMock()
    await restarted.run_drop(drop.id)
    message = channel.messages[drop.message_id]
    assert message.edits[0]["embed"].description == TEXTS[language].waiting
    assert message.edits[0]["view"].children[0].disabled
    assert message.edits[1]["view"] is None
    assert "<@11>" in message.edits[1]["embed"].description
    assert "<@12>" not in message.edits[1]["embed"].description
    assert [dict(row) for row in await repo.ranking(GUILD, language)] == balances
    assert channel.sends == 1


@pytest.mark.postgres
async def test_unregistered_click_does_not_stop_expiration(repo):
    drop = await door(repo)
    assert (await claim(repo, drop, 11, False)).status == ClaimStatus.UNREGISTERED
    assert (await repo.drop(drop.id)).expires_at == drop.expires_at
    await make_overdue(repo, drop)
    assert (await claim(repo, drop, 11, False)).status == ClaimStatus.EXPIRED
    assert (await repo.expire_unopened(drop.id)).status == DropStatus.EXPIRED
    assert await repo.winners(drop.id) == []


@pytest.mark.postgres
async def test_expiration_and_late_claim_race_cannot_award_candies(repo):
    drop = await door(repo)
    await make_overdue(repo, drop)
    results = await asyncio.gather(
        repo.expire_unopened(drop.id), *(claim(repo, drop, 11 + i) for i in range(10))
    )
    assert all(result.status == ClaimStatus.EXPIRED for result in results)
    assert await repo.ranking(GUILD, Language.ES) == []
    assert await repo.winners(drop.id) == []
    assert await repo.expire_unopened(drop.id) is None


@pytest.mark.postgres
async def test_expired_automatic_door_releases_timer_once(repo):
    drop = await door(repo, is_test=False)
    await make_overdue(repo, drop)
    assert (await repo.config(GUILD, Language.ES)).next_drop_at is None
    await repo.expire_unopened(drop.id)
    next_drop = (await repo.config(GUILD, Language.ES)).next_drop_at
    assert next_drop is not None
    await repo.expire_unopened(drop.id)
    assert (await repo.config(GUILD, Language.ES)).next_drop_at == next_drop
    assert await repo.live_drops() == []


@pytest.mark.postgres
@pytest.mark.parametrize("language", list(Language))
async def test_expired_notice_and_ten_second_cleanup_recover_after_restart(
    repo, monkeypatch, language
):
    await ready(repo, language)
    channel = FakeChannel()
    mgr = manager(repo, channel)
    drop = await repo.prepare_drop(GUILD, language, CHANNEL, is_test=True)
    await mgr.run_drop(drop.id)
    drop = await repo.drop(drop.id)
    await make_overdue(repo, drop)
    await repo.expire_unopened(drop.id)  # Crash before the Discord edit.
    pending = await repo.pending_cleanup()
    assert pending[0].delete_at is None
    restarted = manager(repo, channel)
    await restarted.run_drop(drop.id)
    expired = await repo.drop(drop.id)
    message = channel.messages[drop.message_id]
    assert message.edits[0]["embed"].description == TEXTS[language].expired
    assert message.edits[0]["embed"].image.url == DEFAULT_DOOR_TIMEOUT_URL
    button = message.edits[0]["view"].children[0]
    assert button.style == discord.ButtonStyle.red
    assert button.disabled
    assert button.label == "Que pena"
    assert 9 <= (expired.delete_at - expired.finished_at).total_seconds() <= 11
    await restarted.run_drop(drop.id)
    assert (await repo.drop(drop.id)).delete_at == expired.delete_at
    assert len(message.edits) == 1
    member = SimpleNamespace(id=11, guild=SimpleNamespace(id=GUILD), roles=[])
    monkeypatch.setattr("halloween.manager.get_member", AsyncMock(return_value=member))
    interaction = SimpleNamespace(
        client=SimpleNamespace(manager=restarted),
        message=message,
        channel_id=CHANNEL,
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    # A click sent before the edit can still arrive; the database rejects it.
    await DoorView(language, drop.id).children[0].callback(interaction)
    interaction.followup.send.assert_not_awaited()
    assert await repo.winners(drop.id) == []
    await repo.pool.execute(
        "UPDATE door_drops SET delete_at=now()-interval '1 second' WHERE id=$1", drop.id
    )
    cleaner = manager(repo, channel)
    await cleaner.delete_drop_message(drop.id)
    await cleaner.delete_drop_message(drop.id)
    assert message.deletes == 1
    assert (await repo.drop(drop.id)).deleted_at is not None
    assert await repo.pending_cleanup() == []


@pytest.mark.postgres
async def test_cleanup_not_found_finishes_and_forbidden_remains_pending(repo):
    drop = await door(repo)
    await claim(repo, drop, 11)
    await claim(repo, drop, 12)
    await repo.finish(drop.id, delete_after=20)
    await repo.pool.execute(
        "UPDATE door_drops SET delete_at=now()-interval '1 second' WHERE id=$1", drop.id
    )
    channel = FakeChannel()
    forbidden = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "test")
    channel.fetch_message = AsyncMock(side_effect=forbidden)
    cleaner = manager(repo, channel)
    with pytest.raises(discord.Forbidden):
        await cleaner.delete_drop_message(drop.id)
    assert (await repo.drop(drop.id)).deleted_at is None
    assert len(await repo.pending_cleanup()) == 1
    channel.fetch_message.side_effect = discord.NotFound(
        SimpleNamespace(status=404, reason="Not Found"), "test"
    )
    await cleaner.delete_drop_message(drop.id)
    assert (await repo.drop(drop.id)).deleted_at is not None
    assert await repo.pending_cleanup() == []


async def test_scheduler_recovers_open_expiration_and_pending_deletions():
    now = datetime.now(timezone.utc)
    open_drop = DoorDrop(
        uuid4(),
        1,
        Language.ES,
        2,
        3,
        DropStatus.OPEN,
        False,
        True,
        now,
        None,
        None,
        expires_at=now + timedelta(seconds=6),
    )
    expired = DoorDrop(
        uuid4(), 1, Language.ES, 2, 4, DropStatus.EXPIRED, False, True, now, None, now
    )
    final = DoorDrop(
        uuid4(),
        1,
        Language.BR,
        2,
        5,
        DropStatus.FINISHED,
        False,
        True,
        now,
        now,
        now,
        delete_at=now + timedelta(seconds=20),
    )

    def discard(key, coroutine):
        coroutine.close()

    mgr = SimpleNamespace(
        schedule_expiration=Mock(),
        schedule_deletion=Mock(),
        start_job=Mock(side_effect=discard),
        run_drop=AsyncMock(),
    )
    repo = SimpleNamespace(
        live_drops=AsyncMock(return_value=[open_drop]),
        pending_cleanup=AsyncMock(return_value=[expired, final]),
        enabled_configs=AsyncMock(return_value=[]),
    )
    await Scheduler(SimpleNamespace(manager=mgr, repo=repo))._tick()
    mgr.schedule_expiration.assert_called_once_with(open_drop)
    mgr.schedule_deletion.assert_called_once_with(final)
    assert str(expired.id) in [call.args[0] for call in mgr.start_job.call_args_list]


async def test_runtime_expiration_waits_for_persisted_deadline():
    mgr = manager(None, FakeChannel())
    mgr.repo = SimpleNamespace(
        expire_unopened=AsyncMock(return_value=SimpleNamespace(status=DropStatus.EXPIRED))
    )
    mgr._wait_until = AsyncMock()
    mgr.run_drop = AsyncMock()
    drop_id = uuid4()
    deadline = datetime.now(timezone.utc) + timedelta(seconds=6)
    await mgr._expire_at(drop_id, deadline)
    mgr._wait_until.assert_awaited_once_with(deadline)
    mgr.run_drop.assert_awaited_once_with(drop_id)


@pytest.mark.postgres
async def test_runtime_jobs_arm_at_publication_and_after_final_embed(repo):
    await ready(repo)
    channel = FakeChannel()
    mgr = manager(repo, channel, schedule_timers=True)
    hold = asyncio.Event()
    reached = asyncio.Queue()

    async def wait(deadline):
        reached.put_nowait(deadline)
        await hold.wait()

    mgr._wait_until = AsyncMock(side_effect=wait)
    try:
        drop = await repo.prepare_drop(GUILD, Language.ES, CHANNEL, is_test=True)
        await mgr.run_drop(drop.id)
        drop = await repo.drop(drop.id)
        assert await asyncio.wait_for(reached.get(), timeout=5) == drop.expires_at
        assert f"expire:{drop.id}" in mgr.jobs
        mgr._wait_until.assert_awaited_with(drop.expires_at)
        await claim(repo, drop, 11)
        await claim(repo, drop, 12)
        await mgr.stop_jobs()
        mgr._wait_for_result = AsyncMock()
        await mgr.run_drop(drop.id)
        finished = await repo.drop(drop.id)
        assert await asyncio.wait_for(reached.get(), timeout=5) == finished.delete_at
        assert f"delete:{drop.id}" in mgr.jobs
        mgr._wait_until.assert_awaited_with(finished.delete_at)
        assert len(channel.messages[drop.message_id].edits) == 2
    finally:
        await mgr.stop_jobs()
