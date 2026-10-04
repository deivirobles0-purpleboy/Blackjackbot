import discord
from discord import app_commands

from config.constants import STAFF_USER_IDS


class StaffOnly(app_commands.CheckFailure):
    pass


def is_staff(user_id: int) -> bool:
    return user_id in STAFF_USER_IDS


def staff_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not is_staff(interaction.user.id):
            raise StaffOnly("Este comando está reservado al Staff autorizado.")
        return True

    return app_commands.check(predicate)


async def panel_allowed(interaction: discord.Interaction, owner_id: int) -> bool:
    if interaction.user.id != owner_id or not is_staff(interaction.user.id):
        await interaction.response.send_message(
            "Este panel está reservado al Staff que lo abrió.", ephemeral=True
        )
        return False
    return True
