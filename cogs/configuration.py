from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from halloween.embeds import configuration_embed, state_embed
from halloween.models import Language, validate_minutes, validate_probabilities
from halloween.texts import TEXTS
from utils.errors import SafeModal, SafeView
from utils.permissions import panel_allowed, staff_only

log = logging.getLogger(__name__)


def main_menu_embed() -> discord.Embed:
    return discord.Embed(title="🎃 Configuración / Configuração Halloween", color=0xF28C28)


async def return_to_main_menu(interaction: discord.Interaction, bot, owner_id: int) -> None:
    # A deferred message update keeps edits on the original ephemeral panel.
    await interaction.edit_original_response(
        content=None, embed=main_menu_embed(), view=ConfigurationPanel(bot, owner_id)
    )


class StaffView(SafeView):
    def __init__(self, bot, owner_id: int) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await panel_allowed(interaction, self.owner_id)


class ChannelPicker(discord.ui.ChannelSelect):
    def __init__(self) -> None:
        super().__init__(
            placeholder="Canal de drops",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        await interaction.response.defer()
        channel = self.values[0]
        await view.bot.repo.set_channel(
            interaction.guild_id, view.language, channel.id, interaction.user.id
        )
        log.info(
            "Canal configurado guild=%s language=%s channel=%s admin=%s",
            interaction.guild_id,
            view.language,
            channel.id,
            interaction.user.id,
        )
        await return_to_main_menu(interaction, view.bot, view.owner_id)
        await interaction.followup.send(
            f"Canal de drops configurado: <#{channel.id}>", ephemeral=True
        )


class ChannelView(StaffView):
    def __init__(self, bot, owner_id: int, language: Language) -> None:
        super().__init__(bot, owner_id)
        self.language = language
        self.add_item(ChannelPicker())


class MinutesModal(SafeModal):
    def __init__(
        self, bot, owner_id: int, language: Language, minimum: int | None, maximum: int | None
    ) -> None:
        super().__init__(title=TEXTS[language].cd_button, timeout=600)
        self.bot = bot
        self.owner_id = owner_id
        self.language = language
        self.minimum = discord.ui.TextInput(
            label="Mínimo",
            placeholder="Minutos",
            default=str(minimum) if minimum else None,
            max_length=10,
        )
        self.maximum = discord.ui.TextInput(
            label="Máximo",
            placeholder="Minutos",
            default=str(maximum) if maximum else None,
            max_length=10,
        )
        self.add_item(self.minimum)
        self.add_item(self.maximum)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await panel_allowed(interaction, self.owner_id):
            return
        try:
            minimum, maximum = int(self.minimum.value), int(self.maximum.value)
            validate_minutes(minimum, maximum)
        except ValueError:
            await interaction.response.send_message(
                TEXTS[self.language].invalid_minutes, ephemeral=True
            )
            return
        await interaction.response.defer()
        await self.bot.repo.set_minutes(
            interaction.guild_id, self.language, minimum, maximum, interaction.user.id
        )
        log.info(
            "CD configurado guild=%s language=%s min=%s max=%s admin=%s",
            interaction.guild_id,
            self.language,
            minimum,
            maximum,
            interaction.user.id,
        )
        await return_to_main_menu(interaction, self.bot, self.owner_id)
        await interaction.followup.send(
            f"{self.language.value}: CD = {minimum}–{maximum} minutos.", ephemeral=True
        )


class ProbabilityModal(SafeModal):
    def __init__(self, bot, owner_id: int, language: Language) -> None:
        text = TEXTS[language]
        super().__init__(title=text.probability_button, timeout=600)
        self.bot = bot
        self.owner_id = owner_id
        self.language = language
        self.win = discord.ui.TextInput(label=text.win_label, placeholder="0–100", max_length=3)
        self.lose = discord.ui.TextInput(label=text.lose_label, placeholder="0–100", max_length=3)
        self.add_item(self.win)
        self.add_item(self.lose)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await panel_allowed(interaction, self.owner_id):
            return
        text = TEXTS[self.language]
        try:
            win, lose = int(self.win.value), int(self.lose.value)
            validate_probabilities(win, lose)
        except ValueError:
            await interaction.response.send_message(text.invalid_probabilities, ephemeral=True)
            return
        await interaction.response.defer()
        await self.bot.repo.set_probabilities(
            interaction.guild_id, self.language, win, lose, interaction.user.id
        )
        log.info(
            "Probabilidad configurada guild=%s language=%s win=%s lose=%s admin=%s",
            interaction.guild_id,
            self.language,
            win,
            lose,
            interaction.user.id,
        )
        await return_to_main_menu(interaction, self.bot, self.owner_id)
        await interaction.followup.send(
            text.probabilities_saved.format(win=win, lose=lose), ephemeral=True
        )


class LanguagePanel(StaffView):
    def __init__(self, bot, owner_id: int, language: Language) -> None:
        super().__init__(bot, owner_id)
        self.language = language
        self.cd.label = TEXTS[language].cd_button
        self.probability.label = TEXTS[language].probability_button

    @discord.ui.button(label="Canal", style=discord.ButtonStyle.primary)
    async def channel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            content="Selecciona / Selecione o canal:",
            embed=None,
            view=ChannelView(self.bot, self.owner_id, self.language),
        )

    @discord.ui.button(label="CD puertas", style=discord.ButtonStyle.primary)
    async def cd(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # A modal must be the initial response. Keep DB access out of this path.
        await interaction.response.send_modal(
            MinutesModal(self.bot, self.owner_id, self.language, None, None)
        )

    @discord.ui.button(label="Probabilidad", style=discord.ButtonStyle.primary)
    async def probability(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            ProbabilityModal(self.bot, self.owner_id, self.language)
        )

    @discord.ui.button(label="Estado", style=discord.ButtonStyle.secondary)
    async def state(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        cfg = await self.bot.repo.config(interaction.guild_id, self.language)
        await interaction.followup.send(embed=state_embed(cfg), ephemeral=True)


class ConfigurationPanel(StaffView):
    async def show(self, interaction: discord.Interaction, language: Language) -> None:
        await interaction.response.edit_message(
            embed=configuration_embed(language),
            view=LanguagePanel(self.bot, self.owner_id, language),
        )

    @discord.ui.button(label="🇪🇸 Español", style=discord.ButtonStyle.primary)
    async def spanish(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.show(interaction, Language.ES)

    @discord.ui.button(label="🇧🇷 Português", style=discord.ButtonStyle.primary)
    async def portuguese(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.show(interaction, Language.BR)


class Configuration(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="config_doces", description="Abre o painel Staff de configuração ES/BR"
    )
    @app_commands.guild_only()
    @staff_only()
    async def configure(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=main_menu_embed(),
            view=ConfigurationPanel(self.bot, interaction.user.id),
            ephemeral=True,
        )


async def setup(bot) -> None:
    await bot.add_cog(Configuration(bot))
