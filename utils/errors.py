import logging

import asyncpg
import discord
from discord import app_commands

from utils.permissions import StaffOnly

log = logging.getLogger(__name__)


async def respond_error(interaction: discord.Interaction, error: Exception) -> None:
    original = getattr(error, "original", error)
    if isinstance(original, StaffOnly):
        message = str(original)
    elif isinstance(original, ValueError):
        message = str(original)
    elif isinstance(original, (asyncpg.PostgresError, OSError, TimeoutError)):
        message = "Servicio temporalmente no disponible. Inténtalo de nuevo en unos momentos."
        log.error("Error de servicio", exc_info=original)
    elif isinstance(original, discord.Forbidden):
        message = "El bot no tiene los permisos necesarios para realizar esta acción."
        log.error("Permisos Discord insuficientes", exc_info=original)
    elif isinstance(original, discord.NotFound):
        message = "El canal, mensaje o rol ya no está disponible."
        log.warning("Recurso Discord eliminado", exc_info=original)
    elif isinstance(original, app_commands.CheckFailure):
        message = "No puedes utilizar este comando aquí."
    else:
        message = "No se pudo completar la acción. El error quedó registrado; vuelve a intentarlo."
        log.error("Error de interacción", exc_info=original)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        log.warning("No se pudo responder a la interacción", exc_info=True)


class SafeView(discord.ui.View):
    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item
    ) -> None:
        await respond_error(interaction, error)


class SafeModal(discord.ui.Modal):
    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await respond_error(interaction, error)
