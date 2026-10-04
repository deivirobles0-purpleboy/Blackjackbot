import logging

import discord

from config.constants import PARTICIPANT_ROLE_ID, REGISTRATION_CUSTOM_ID
from utils.errors import SafeView
from utils.roles import get_member, is_participant, is_verified

log = logging.getLogger(__name__)


class RegistrationView(SafeView):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Entrar", style=discord.ButtonStyle.green, custom_id=REGISTRATION_CUSTOM_ID
    )
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        member = await get_member(interaction)
        role_ids = {role.id for role in member.roles}
        if is_participant(role_ids):
            await interaction.followup.send(
                "Ya tienes el rol del evento / Você já possui o cargo do evento.", ephemeral=True
            )
            return
        if not is_verified(role_ids):
            await interaction.followup.send(
                "Primero debes ser un usuario verificado / Primeiro você precisa ser um usuário verificado.",
                ephemeral=True,
            )
            return
        guild = member.guild
        role = guild.get_role(PARTICIPANT_ROLE_ID)
        bot_member = guild.me or await guild.fetch_member(interaction.client.user.id)
        if (
            role is None
            or role.managed
            or not bot_member.guild_permissions.manage_roles
            or bot_member.top_role <= role
            or role.is_default()
        ):
            log.error(
                "No se puede asignar rol Halloween guild=%s user=%s: permiso o jerarquía",
                guild.id,
                member.id,
            )
            await interaction.followup.send(
                "No puedo asignar el rol. Staff debe revisar Manage Roles y la jerarquía del bot. / "
                "Não consigo atribuir o cargo; o Staff precisa revisar as permissões e a hierarquia.",
                ephemeral=True,
            )
            return
        try:
            # atomic=True uses Discord's idempotent PUT role endpoint.
            await member.add_roles(
                role, reason="Registro Evento Halloween: usuario verificado", atomic=True
            )
        except discord.HTTPException:
            log.exception("Falló asignación de rol Halloween guild=%s user=%s", guild.id, member.id)
            await interaction.followup.send(
                "No se pudo asignar el rol; avisa al Staff. / Não foi possível atribuir o cargo; avise o Staff.",
                ephemeral=True,
            )
            return
        log.info("Rol Halloween asignado guild=%s user=%s", guild.id, member.id)
        await interaction.followup.send(
            f"Registro confirmado / Registro confirmado: <@&{role.id}>", ephemeral=True
        )
