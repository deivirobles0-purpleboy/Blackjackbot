from collections.abc import Iterable

import discord
from discord import app_commands

from config.constants import STAFF_ROLE_IDS


class StaffOnly(app_commands.CheckFailure):
    pass


def has_staff_role(role_ids: Iterable[int]) -> bool:
    return bool(STAFF_ROLE_IDS.intersection(role_ids))


def is_staff_member(user: discord.User | discord.Member) -> bool:
    roles = user.roles if isinstance(user, discord.Member) else ()
    return has_staff_role(role.id for role in roles)


def staff_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not is_staff_member(interaction.user):
            raise StaffOnly("Este comando está reservado al Staff autorizado.")
        return True

    return app_commands.check(predicate)


async def panel_allowed(interaction: discord.Interaction, owner_id: int) -> bool:
    if interaction.user.id != owner_id or not is_staff_member(interaction.user):
        await interaction.response.send_message(
            "Este panel está reservado al Staff que lo abrió.", ephemeral=True
        )
        return False
    return True
