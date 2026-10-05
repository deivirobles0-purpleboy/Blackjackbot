import logging

import discord
from discord import app_commands
from discord.ext import commands

from halloween.models import Language
from utils.permissions import staff_only

log = logging.getLogger(__name__)


class Admin(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @app_commands.command(name="ativar_doces", description="Ativa os sistemas ES/BR configurados")
    @app_commands.guild_only()
    @staff_only()
    async def activate(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        for language in Language:
            cfg = await self.bot.repo.config(interaction.guild_id, language)
            if not cfg.complete:
                log.warning(
                    "No se activa configuración incompleta guild=%s language=%s",
                    interaction.guild_id,
                    language,
                )
        languages = await self.bot.repo.set_enabled(interaction.guild_id, True, interaction.user.id)
        log.info(
            "Activación guild=%s admin=%s languages=%s",
            interaction.guild_id,
            interaction.user.id,
            languages,
        )
        message = (
            "**SISTEMA DE DOCES ATIVADO:**" if languages else "**SISTEMA DE DOCES NÃO ATIVADO:**"
        )
        for language in (Language.BR, Language.ES):
            status = (
                "<:check:1532500942237339728>" if language in languages else "Configuração pendente"
            )
            message += f"\n**{language.value}:** {status}"
        missing = [language.value for language in Language if language not in languages]
        if missing:
            message += "\n\nConfigura Canal y CD en /config_doces: " + ", ".join(missing)
        await interaction.followup.send(message)

    @app_commands.command(
        name="desativar_doces", description="Desativa próximos drops automáticos ES/BR"
    )
    @app_commands.guild_only()
    @staff_only()
    async def deactivate(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        await self.bot.repo.set_enabled(interaction.guild_id, False, interaction.user.id)
        log.info("Desactivación guild=%s admin=%s", interaction.guild_id, interaction.user.id)
        await interaction.followup.send(
            "Sistemas ES/BR desativados. Próximas aparições canceladas. "
            "As portas já publicadas continuam disponíveis para concluir a participação."
        )

    async def _adjust(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        language: Language,
        action: str,
        amount: int,
        *,
        ephemeral: bool = False,
    ) -> None:
        await interaction.response.defer(ephemeral=ephemeral, thinking=True)
        total = await self.bot.repo.adjust(
            interaction.guild_id, user.id, language, action, amount, interaction.user.id
        )
        log.info(
            "Modificación candies guild=%s admin=%s user=%s language=%s action=%s amount=%s total=%s",
            interaction.guild_id,
            interaction.user.id,
            user.id,
            language,
            action,
            amount,
            total,
        )
        await interaction.followup.send(
            f"{language.value}: <@{user.id}> → **{total}**. ({action}: {amount})",
            ephemeral=ephemeral,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(
        name="resetar_doces", description="Zera os doces de um usuário no idioma escolhido"
    )
    @app_commands.guild_only()
    @staff_only()
    async def reset(
        self, interaction: discord.Interaction, user: discord.Member, idioma: Language
    ) -> None:
        await self._adjust(interaction, user, idioma, "reset", 0, ephemeral=True)

    @app_commands.command(
        name="adicionar_doces", description="Adiciona doces ao usuário e registra a alteração"
    )
    @app_commands.guild_only()
    @staff_only()
    async def add(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        quantidade: app_commands.Range[int, 1],
        idioma: Language,
    ) -> None:
        await self._adjust(interaction, user, idioma, "add", quantidade)

    @app_commands.command(
        name="tirar_doces", description="Remove doces sem permitir saldo negativo"
    )
    @app_commands.guild_only()
    @staff_only()
    async def remove(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        quantidade: app_commands.Range[int, 1],
        idioma: Language,
    ) -> None:
        await self._adjust(interaction, user, idioma, "remove", quantidade)

    @app_commands.command(
        name="porta_de_teste", description="Publica uma porta sem alterar o timer automático"
    )
    @app_commands.guild_only()
    @staff_only()
    async def test_door(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        idioma: Language,
        recompensa_real: bool = False,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        if canal.guild.id != interaction.guild_id:
            raise ValueError("El canal debe pertenecer a este servidor")
        drop = await self.bot.manager.create_test(
            interaction.guild_id, idioma, canal.id, recompensa_real
        )
        log.info(
            "Puerta prueba admin=%s drop=%s real=%s", interaction.user.id, drop.id, recompensa_real
        )
        # Acknowledge the slash command, then remove its temporary loading response.
        try:
            await interaction.delete_original_response()
        except discord.NotFound:
            pass


async def setup(bot) -> None:
    await bot.add_cog(Admin(bot))
