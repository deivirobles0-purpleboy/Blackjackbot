from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import discord
import pytest

from cogs.admin import Admin
from halloween.models import Language


def command_context():
    manager = SimpleNamespace(create_test=AsyncMock(return_value=SimpleNamespace(id=uuid4())))
    cog = Admin(SimpleNamespace(manager=manager))
    interaction = SimpleNamespace(
        guild_id=1,
        user=SimpleNamespace(id=123),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
        delete_original_response=AsyncMock(),
    )
    channel = SimpleNamespace(id=456, guild=SimpleNamespace(id=1))
    return cog, interaction, channel


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("real_rewards", [False, True])
async def test_test_door_leaves_only_public_door(language, real_rewards):
    cog, interaction, channel = command_context()

    async def publish(*args):
        interaction.delete_original_response.assert_not_awaited()
        return SimpleNamespace(id=uuid4())

    cog.bot.manager.create_test.side_effect = publish
    await Admin.test_door.callback(cog, interaction, channel, language, real_rewards)

    cog.bot.manager.create_test.assert_awaited_once_with(1, language, 456, real_rewards)
    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    interaction.delete_original_response.assert_awaited_once_with()
    interaction.followup.send.assert_not_awaited()


async def test_publication_failure_remains_available_to_error_handler():
    cog, interaction, channel = command_context()
    cog.bot.manager.create_test.side_effect = OSError("Publication failed")

    with pytest.raises(OSError, match="Publication failed"):
        await Admin.test_door.callback(cog, interaction, channel, Language.ES)

    interaction.delete_original_response.assert_not_awaited()
    interaction.followup.send.assert_not_awaited()


async def test_foreign_channel_rejected_before_publication():
    cog, interaction, channel = command_context()
    channel.guild.id = 2

    with pytest.raises(ValueError, match="El canal debe pertenecer a este servidor"):
        await Admin.test_door.callback(cog, interaction, channel, Language.BR)

    cog.bot.manager.create_test.assert_not_awaited()
    interaction.delete_original_response.assert_not_awaited()


async def test_already_removed_loading_response_is_harmless():
    cog, interaction, channel = command_context()
    interaction.delete_original_response.side_effect = discord.NotFound(
        SimpleNamespace(status=404, reason="Not Found"), "Unknown Message"
    )

    await Admin.test_door.callback(cog, interaction, channel, Language.ES)

    cog.bot.manager.create_test.assert_awaited_once()
    interaction.followup.send.assert_not_awaited()
