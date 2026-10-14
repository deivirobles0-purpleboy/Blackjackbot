import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from config.settings import DEFAULT_DOOR_IMAGES, Settings
from halloween.embeds import door_embed
from halloween.models import DoorDrop, DropStatus, Language
from utils.display_names import resolve_display_names


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("candy_win", [True, False])
def test_door_names_are_readable_even_when_missing_or_contain_mentions(language, candy_win):
    drop = DoorDrop(
        uuid4(),
        1,
        language,
        2,
        3,
        DropStatus.PROCESSING,
        False,
        True,
        datetime.now(timezone.utc),
        None,
        None,
        candy_win=candy_win,
    )
    settings = Settings("test", "postgresql://test@localhost/test", DEFAULT_DOOR_IMAGES)
    embed = door_embed(
        drop,
        "result",
        settings,
        [{"user_id": 123, "candies": 4}, {"user_id": 456, "candies": 0}],
        display_names={123: "@everyone\n<@789> **Nick**"},
    )
    assert "@everyone" not in embed.description
    assert "<@789>" not in embed.description
    assert "\\*\\*Nick\\*\\*: 4" in embed.description
    assert (
        "Usuario desconocido" if language == Language.ES else "Usuário desconhecido"
    ) in embed.description
    assert "456" not in embed.description
    assert embed.description.count("\n") == 3


async def test_slow_name_lookup_falls_back_without_blocking_rewards_forever():
    async def slow_member(_):
        await asyncio.Event().wait()

    guild = SimpleNamespace(
        get_member=lambda _: None, fetch_member=AsyncMock(side_effect=slow_member)
    )
    bot = SimpleNamespace(
        get_user=lambda user_id: (
            SimpleNamespace(display_name="Visible name") if user_id == 1 else None
        ),
        fetch_user=AsyncMock(),
    )
    async with asyncio.timeout(4):
        names = await resolve_display_names(bot, guild, [1, 2])
    assert names == {1: "Visible name", 2: ""}
    bot.fetch_user.assert_not_awaited()
