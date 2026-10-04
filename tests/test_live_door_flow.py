import asyncio
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config.constants import PARTICIPANT_ROLE_ID
from config.settings import DEFAULT_DOOR_IMAGES
from halloween.models import DropStatus, Language
from halloween.texts import TEXTS
from halloween.views import DoorView
from tests.test_flow import FakeChannel, manager
from tests.test_postgres import CHANNEL, GUILD, STAFF, ready


async def click(mgr, message, drop, user_id):
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=user_id),
        client=SimpleNamespace(manager=mgr),
        message=message,
        channel_id=CHANNEL,
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
        edit_original_response=AsyncMock(side_effect=message.edit),
    )
    await DoorView(drop.language, drop.id).children[0].callback(interaction)
    return interaction


@pytest.mark.postgres
@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("candy_win", [True, False])
@pytest.mark.parametrize("participants", [1, 2])
async def test_live_first_click_progresses_without_manual_run_or_fake_timers(
    repo, monkeypatch, language, candy_win, participants
):
    await ready(repo, language)
    await repo.set_probabilities(
        GUILD, language, 100 if candy_win else 0, 0 if candy_win else 100, STAFF
    )
    if not candy_win:
        for user in (11, 12):
            await repo.adjust(GUILD, user, language, "add", 10, STAFF)

    async def member(interaction):
        return SimpleNamespace(
            id=interaction.user.id,
            guild=SimpleNamespace(id=GUILD),
            roles=[SimpleNamespace(id=PARTICIPANT_ROLE_ID)],
        )

    monkeypatch.setattr("halloween.manager.get_member", member)
    monkeypatch.setattr("database.repositories.roll_reward", lambda: 2)
    monkeypatch.setattr("database.repositories.roll_loss", lambda: 3)
    channel = FakeChannel()
    mgr = manager(repo, channel, schedule_timers=True)
    try:
        drop = await repo.prepare_drop(GUILD, language, CHANNEL, is_test=True)
        await mgr.run_drop(drop.id)  # Only the initial publication is driven explicitly.
        drop = await repo.drop(drop.id)
        message = channel.messages[drop.message_id]
        final_displayed_at = None
        original_edit = message.edit

        async def record_edit(**kwargs):
            nonlocal final_displayed_at
            result = await original_edit(**kwargs)
            if kwargs.get("embed") and kwargs.get("view", True) is None:
                final_displayed_at = datetime.now(timezone.utc)
            return result

        message.edit = record_edit

        async def pending_open_check():
            await asyncio.Event().wait()

        # A still-running OPEN poll must not absorb the first-click resolution job.
        mgr.start_job(str(drop.id), pending_open_check())
        started = time.monotonic()
        first = await click(mgr, message, drop, 11)
        async with asyncio.timeout(1.5):
            while not any(
                edit.get("embed") and edit["embed"].description == TEXTS[language].waiting
                for edit in message.edits
            ):
                await asyncio.sleep(0.02)
        first.followup.send.assert_not_awaited()
        if participants == 2:
            second = await click(mgr, message, drop, 12)
            second.followup.send.assert_not_awaited()
        async with asyncio.timeout(6):
            while (await repo.drop(drop.id)).status != DropStatus.FINISHED:
                await asyncio.sleep(0.03)
        elapsed = time.monotonic() - started
        assert 4.8 <= elapsed < 6.5
        final = [edit["embed"] for edit in message.edits if edit.get("embed")][-1]
        assert final.image.url == getattr(
            DEFAULT_DOOR_IMAGES[language], "candy_win" if candy_win else "candy_lose"
        )
        assert f"<@11>: {'2' if candy_win else '-3'}" in final.description
        assert ("<@12>" in final.description) == (participants == 2)
        assert final.footer.text == TEXTS[language].footer
        assert channel.sends == 1
        assert list(channel.messages) == [drop.message_id]
        assert len(await repo.winners(drop.id)) == participants
        finished = await repo.drop(drop.id)
        assert final_displayed_at is not None
        assert 20 <= (finished.delete_at - final_displayed_at).total_seconds() < 21
        assert message.deletes == 0
    finally:
        await mgr.stop_jobs()


@pytest.mark.postgres
async def test_second_participant_does_not_restart_five_second_deadline(repo):
    from tests.test_postgres import claim, door

    drop = await door(repo)
    await claim(repo, drop, 11)
    started = (await repo.drop(drop.id)).processing_at
    await claim(repo, drop, 12)
    assert (await repo.drop(drop.id)).processing_at == started
    assert len(await repo.winners(drop.id)) == 2


@pytest.mark.postgres
async def test_late_second_click_is_rejected_even_when_result_job_is_delayed(repo):
    from halloween.models import ClaimStatus
    from tests.test_postgres import claim, door

    drop = await door(repo)
    first = await claim(repo, drop, 11)
    await repo.pool.execute(
        "UPDATE door_drops SET processing_at=clock_timestamp()-interval '5 seconds' WHERE id=$1",
        drop.id,
    )
    assert (await claim(repo, drop, 12)).status == ClaimStatus.CLOSED
    assert [row["user_id"] for row in await repo.winners(drop.id)] == [11]
    assert (await repo.ranking(GUILD, Language.ES))[0]["candies"] == first.candies


@pytest.mark.postgres
@pytest.mark.parametrize("language", list(Language))
async def test_second_click_after_four_seconds_is_still_accepted(repo, language):
    from halloween.models import ClaimStatus
    from tests.test_postgres import claim, door

    drop = await door(repo, language)
    await claim(repo, drop, 11)
    await repo.pool.execute(
        "UPDATE door_drops SET processing_at=clock_timestamp()-interval '4.1 seconds' WHERE id=$1",
        drop.id,
    )
    assert (await claim(repo, drop, 12)).status == ClaimStatus.ACCEPTED
    assert len(await repo.winners(drop.id)) == 2


@pytest.mark.postgres
@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("candy_win", [True, False])
async def test_schema_recovers_former_open_door_with_one_participant_without_repaying(
    repo, monkeypatch, language, candy_win
):
    from database.schema import SCHEMA_SQL
    from tests.test_postgres import claim

    await ready(repo, language)
    await repo.set_probabilities(
        GUILD, language, 100 if candy_win else 0, 0 if candy_win else 100, STAFF
    )
    if not candy_win:
        await repo.adjust(GUILD, 11, language, "add", 10, STAFF)
    channel = FakeChannel()
    mgr = manager(repo, channel)
    drop = await repo.prepare_drop(GUILD, language, CHANNEL, is_test=True)
    await mgr.run_drop(drop.id)
    drop = await repo.drop(drop.id)
    await claim(repo, drop, 11)
    balances = [dict(row) for row in await repo.ranking(GUILD, language)]
    await repo.pool.execute(
        "UPDATE door_winners SET claimed_at=clock_timestamp()-interval '10 seconds' WHERE drop_id=$1",
        drop.id,
    )
    await repo.pool.execute(
        "UPDATE door_drops SET status='open',processing_at=NULL,expires_at=NULL WHERE id=$1",
        drop.id,
    )
    await repo.pool.execute(SCHEMA_SQL)
    await repo.pool.execute(SCHEMA_SQL)
    recovered = await repo.drop(drop.id)
    assert recovered.status == DropStatus.PROCESSING
    assert recovered.processing_at is not None
    await mgr.run_drop(drop.id)
    await mgr.run_drop(drop.id)
    assert (await repo.drop(drop.id)).status == DropStatus.FINISHED
    assert [dict(row) for row in await repo.ranking(GUILD, language)] == balances
    final = channel.messages[drop.message_id].edits[-1]["embed"]
    assert "<@11>" in final.description
    assert final.image.url == getattr(
        DEFAULT_DOOR_IMAGES[language], "candy_win" if candy_win else "candy_lose"
    )
    assert channel.sends == 1
