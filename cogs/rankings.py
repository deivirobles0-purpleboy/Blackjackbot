import math

import discord
from discord import app_commands
from discord.ext import commands

from halloween.embeds import ranking_embed
from halloween.models import Language
from halloween.texts import TEXTS
from utils.cooldowns import Cooldowns


class Rankings(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.cooldowns = Cooldowns()

    async def show(self, interaction: discord.Interaction, language: Language) -> None:
        command = "dulces" if language == Language.ES else "doces"
        remaining = self.cooldowns.take(interaction.guild_id, interaction.user.id, command)
        if remaining:
            await interaction.response.send_message(
                TEXTS[language].cooldown.format(seconds=math.ceil(remaining)), ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True)
        try:
            rows = await self.bot.repo.ranking(interaction.guild_id, language)
            await interaction.followup.send(
                embed=ranking_embed(language, rows), allowed_mentions=discord.AllowedMentions.none()
            )
        except Exception:
            self.cooldowns.release(interaction.guild_id, interaction.user.id, command)
            raise

    @app_commands.command(name="doces", description="Confira o ranking BR do Evento Halloween")
    @app_commands.guild_only()
    async def doces(self, interaction: discord.Interaction) -> None:
        await self.show(interaction, Language.BR)

    @app_commands.command(name="dulces", description="Consulta el ranking ES del Evento Halloween")
    @app_commands.guild_only()
    async def dulces(self, interaction: discord.Interaction) -> None:
        await self.show(interaction, Language.ES)


async def setup(bot) -> None:
    await bot.add_cog(Rankings(bot))
