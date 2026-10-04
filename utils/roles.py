from collections.abc import Iterable

import discord

from config.constants import PARTICIPANT_ROLE_ID, VERIFIED_ROLE_IDS


def is_participant(role_ids: Iterable[int]) -> bool:
    return PARTICIPANT_ROLE_ID in role_ids


def is_verified(role_ids: Iterable[int]) -> bool:
    return bool(VERIFIED_ROLE_IDS.intersection(role_ids))


async def get_member(interaction: discord.Interaction) -> discord.Member:
    if interaction.guild is None:
        raise ValueError("Esta interacción solo está disponible en un servidor")
    # Discord includes current member roles in guild interactions; no members intent is required.
    if isinstance(interaction.user, discord.Member):
        return interaction.user
    return await interaction.guild.fetch_member(interaction.user.id)
