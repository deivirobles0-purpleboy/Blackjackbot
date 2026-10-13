import discord
from discord import app_commands
from discord.ext import commands

from halloween.registration import RegistrationView
from utils.permissions import staff_only


class Registration(commands.Cog):
    @app_commands.command(
        name="abrir_registro_halloween", description="Publica el registro permanente Halloween"
    )
    @app_commands.guild_only()
    @staff_only()
    async def open_registration(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        if interaction.channel is None:
            raise ValueError("El canal ya no está disponible.")
        embed = discord.Embed(title="🎃 Evento Halloween Supersus SA Oficial 🎃", color=0xF28C28)
        await interaction.channel.send(embed=embed, view=RegistrationView())
        # Keep the public registration independent of the slash command response.
        try:
            await interaction.delete_original_response()
        except discord.NotFound:
            pass


async def setup(bot) -> None:
    await bot.add_cog(Registration())
