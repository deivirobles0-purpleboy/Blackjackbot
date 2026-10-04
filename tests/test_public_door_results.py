from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from config.constants import PARTICIPANT_ROLE_ID
from config.settings import DEFAULT_DOOR_IMAGES
from halloween.models import DoorDrop, DropStatus, Language
from halloween.texts import TEXTS
from halloween.views import DoorView
from tests.test_flow import FakeChannel, manager
from tests.test_postgres import CHANNEL, GUILD, STAFF, ready


@pytest.mark.postgres
@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("candy_win", [True, False])
@pytest.mark.parametrize("real", [True, False])
async def test_button_flow_reveals_only_in_original_public_embed(
    repo, monkeypatch, language, candy_win, real
):
    await ready(repo, language)
    await repo.set_probabilities(
        GUILD, language, 100 if candy_win else 0, 0 if candy_win else 100, STAFF
    )
    if not candy_win:
        for user in (11, 12):
            await repo.adjust(GUILD, user, language, "add", 10, STAFF)
    amounts = iter([2, 5] if candy_win else [3, 4])
    monkeypatch.setattr(
        "database.repositories.roll_reward" if candy_win else "database.repositories.roll_loss",
        lambda: next(amounts),
    )
    channel = FakeChannel()
    mgr = manager(repo, channel)
    drop = await repo.prepare_drop(GUILD, language, CHANNEL, is_test=True, rewards_enabled=real)
    await mgr.run_drop(drop.id)
    drop = await repo.drop(drop.id)
    original_id = drop.message_id
    message = channel.messages[original_id]
    button = DoorView(language, drop.id).children[0]
    started = []

    def capture_job(key, work):
        started.append(key)
        work.close()

    mgr.start_job = capture_job
    interactions = []
    for user in (11, 12, 13):
        member = SimpleNamespace(
            id=user,
            guild=SimpleNamespace(id=GUILD),
            roles=[SimpleNamespace(id=PARTICIPANT_ROLE_ID)],
        )
        monkeypatch.setattr("halloween.manager.get_member", AsyncMock(return_value=member))
        interaction = SimpleNamespace(
            client=SimpleNamespace(manager=mgr),
            message=message,
            channel_id=CHANNEL,
            response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
            edit_original_response=AsyncMock(),
        )
        await button.callback(interaction)
        interactions.append(interaction)
    for accepted in interactions[:2]:
        accepted.response.defer.assert_awaited_once_with()
        accepted.followup.send.assert_not_awaited()
    interactions[2].followup.send.assert_awaited_once_with(
        TEXTS[language].unavailable, ephemeral=True
    )
    assert started == [f"resolve:{drop.id}", f"resolve:{drop.id}"]
    assert [row["user_id"] for row in await repo.winners(drop.id)] == [11, 12]
    processing = await repo.drop(drop.id)
    assert processing.status == DropStatus.PROCESSING
    mgr._wait_until = AsyncMock()
    await mgr.run_drop(drop.id)
    mgr._wait_until.assert_awaited_once_with(processing.processing_at + timedelta(seconds=4))
    assert channel.sends == 1
    assert list(channel.messages) == [original_id]
    assert (await repo.drop(drop.id)).message_id == original_id
    assert len(message.edits) == 2
    waiting, final = [edit["embed"] for edit in message.edits]
    assert message.embed.image.url == DEFAULT_DOOR_IMAGES[language].closed
    assert waiting.description == TEXTS[language].waiting
    assert waiting.image.url == DEFAULT_DOOR_IMAGES[language].waiting
    assert message.edits[0]["view"].children[0].disabled
    assert message.edits[1]["view"] is None
    if candy_win:
        assert final.title == (
            "Dulce o Truco ?" if language == Language.ES else "Doces ou Travessuras ?"
        )
        assert final.description == (
            f"{TEXTS[language].candy_win}\n\n"
            f"🎃 <@11>: 2 {TEXTS[language].candy}\n"
            f"🎃 <@12>: 5 {TEXTS[language].candy}"
        )
        assert final.image.url == DEFAULT_DOOR_IMAGES[language].candy_win
    else:
        assert final.title == TEXTS[language].lose_title
        assert final.description == f"{TEXTS[language].candy_lose}\n\n<@11>: -3\n<@12>: -4"
        assert final.image.url == DEFAULT_DOOR_IMAGES[language].candy_lose
    assert final.footer.text == (
        "Consulta /dulces para revisar el Top!"
        if language == Language.ES
        else "Confira o /doces para consultar o top"
    )
    assert (await repo.drop(drop.id)).delete_at is not None
    balances = {row["user_id"]: row["candies"] for row in await repo.ranking(GUILD, language)}
    expected = (
        ({11: 2, 12: 5} if candy_win else {11: 7, 12: 6})
        if real
        else ({} if candy_win else {11: 10, 12: 10})
    )
    assert balances == expected


@pytest.mark.parametrize("restarting", [False, True])
async def test_result_countdown_uses_first_click_timestamp_without_reset(restarting):
    started = datetime.now(timezone.utc) - timedelta(seconds=30 if restarting else 0)
    drop = DoorDrop(
        uuid4(), 1, Language.ES, 2, 3, DropStatus.PROCESSING, False, True, started, started, None
    )
    mgr = manager(None, FakeChannel())
    mgr._wait_until = AsyncMock()
    await mgr._wait_for_result(drop)
    mgr._wait_until.assert_awaited_once_with(started + timedelta(seconds=4))
