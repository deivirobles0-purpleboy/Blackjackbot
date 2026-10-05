from __future__ import annotations

import re
from uuid import UUID

import discord

from halloween.models import Language
from utils.errors import SafeView, respond_error


def door_custom_id(language: Language, drop_id: UUID) -> str:
    return f"halloween:door:{language.value}:{drop_id.hex}:open"


class DoorButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"halloween:door:(?P<language>ES|BR):(?P<drop_id>[0-9a-f]{32}):open",
):
    def __init__(self, language: Language, drop_id: UUID) -> None:
        self.language = language
        self.drop_id = drop_id
        super().__init__(
            discord.ui.Button(
                label="Abrir",
                style=discord.ButtonStyle.green,
                custom_id=door_custom_id(language, drop_id),
            )
        )

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Item, match: re.Match[str]
    ) -> DoorButton:
        return cls(Language(match["language"]), UUID(hex=match["drop_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            await interaction.client.manager.claim(interaction, self.drop_id, self.language)
        except Exception as error:
            await respond_error(interaction, error)


class DoorView(SafeView):
    def __init__(
        self, language: Language, drop_id: UUID, *, disabled: bool = False, expired: bool = False
    ) -> None:
        super().__init__(timeout=None)
        if disabled or expired:
            self.add_item(
                discord.ui.Button(
                    label="Que pena" if expired else "Abrir",
                    style=discord.ButtonStyle.red,
                    disabled=True,
                    custom_id=door_custom_id(language, drop_id),
                )
            )
        else:
            self.add_item(DoorButton(language, drop_id))
