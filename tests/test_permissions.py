from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot import HalloweenBot
from config.constants import PARTICIPANT_ROLE_ID, STAFF_ROLE_IDS
from tests.test_discord_components import settings
from utils.permissions import StaffOnly, has_staff_role, is_staff_member, panel_allowed


def interaction(user_id: int = 123, role_ids=()):
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.roles = [SimpleNamespace(id=value) for value in role_ids]
    return SimpleNamespace(user=member, response=SimpleNamespace(send_message=AsyncMock()))


@pytest.mark.parametrize("role_id", sorted(STAFF_ROLE_IDS))
def test_any_allowed_role_grants_staff_access(role_id):
    assert has_staff_role([role_id])
    assert is_staff_member(interaction(role_ids=[role_id]).user)
    assert not has_staff_role([PARTICIPANT_ROLE_ID])
    assert not has_staff_role([])


@pytest.mark.parametrize("user_id", sorted(STAFF_ROLE_IDS))
def test_matching_user_id_does_not_grant_staff_access(user_id):
    assert not is_staff_member(interaction(user_id).user)


@pytest.mark.parametrize("role_id", sorted(STAFF_ROLE_IDS))
async def test_all_staff_commands_allow_management_role_and_reject_unlisted_members(role_id):
    bot = HalloweenBot(settings())
    bot.repo = SimpleNamespace()
    async with bot:
        for extension in ("cogs.admin", "cogs.registration", "cogs.configuration"):
            await bot.load_extension(extension)
        allowed = interaction(role_ids=[role_id])
        denied = interaction(role_ids=[PARTICIPANT_ROLE_ID])
        for command in bot.tree.get_commands():
            for check in command.checks:
                assert await check(allowed)
                with pytest.raises(StaffOnly):
                    await check(denied)


async def test_role_holder_can_use_own_panel_and_loses_access_when_role_removed():
    allowed = interaction(role_ids=STAFF_ROLE_IDS)
    assert await panel_allowed(allowed, allowed.user.id)
    allowed.response.send_message.assert_not_awaited()
    allowed.user.roles = []
    assert not await panel_allowed(allowed, allowed.user.id)
    assert allowed.response.send_message.call_args.kwargs["ephemeral"]


async def test_other_authorized_member_cannot_take_over_panel():
    other = interaction(user_id=456, role_ids=STAFF_ROLE_IDS)
    assert not await panel_allowed(other, owner_id=123)
    assert other.response.send_message.call_args.kwargs["ephemeral"]
