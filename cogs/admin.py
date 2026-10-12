import logging
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from halloween.daily_schedule import EVENT_TIMEZONE, parse_daily_time, validate_daily_window
from halloween.models import Language
from utils.permissions import staff_only

log = logging.getLogger(__name__)


class Admin(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="ativar_doces", description="Programa drops ES/BR em um horário diário de São Paulo"
    )
    @app_commands.describe(
        inicio="Hora de início em São Paulo, formato 24h: 09:00",
        fim="Hora de pausa em São Paulo, formato 24h: 22:00",
    )
    @app_commands.guild_only()
    @staff_only()
    async def activate(self, interaction: discord.Interaction, inicio: str, fim: str) -> None:
        start, end = parse_daily_time(inicio), parse_daily_time(fim)
        validate_daily_window(start, end)
        await interaction.response.defer(thinking=True)
        for language in Language:
            cfg = await self.bot.repo.config(interaction.guild_id, language)
            if not cfg.complete:
                log.warning(
                    "No se activa configuración incompleta guild=%s language=%s",
                    interaction.guild_id,
                    language,
                )
        languages = await self.bot.repo.set_enabled(
            interaction.guild_id, True, interaction.user.id, start=start, end=end
        )
        log.info(
            "Activación guild=%s admin=%s languages=%s horario=%s-%s timezone=%s",
            interaction.guild_id,
            interaction.user.id,
            languages,
            start.strftime("%H:%M"),
            end.strftime("%H:%M"),
            EVENT_TIMEZONE,
        )
        message = (
            "**SISTEMA DE DOCES ATIVADO:**" if languages else "**SISTEMA DE DOCES NÃO ATIVADO:**"
        )
        for language in (Language.BR, Language.ES):
            status = (
                "<:check:1532500942237339728>" if language in languages else "Configuração pendente"
            )
            message += f"\n**{language.value}:** {status}"
        if languages:
            message += (
                f"\n\n**Horário diário:** {start:%H:%M} às {end:%H:%M} (São Paulo)."
                "\nAtivação e pausa automáticas todos os dias, respeitando o CD configurado."
            )
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
            "Programação diária desativada; os drops não serão retomados automaticamente. "
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
        if not interaction.response.is_done():
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

    @app_commands.command(name="reset_doces", description="Zera todo o ranking ES, BR ou ambos")
    @app_commands.describe(
        idioma="ES, BR ou all para zerar ambos os rankings",
    )
    @app_commands.guild_only()
    @staff_only()
    async def reset(
        self,
        interaction: discord.Interaction,
        idioma: Literal["ES", "BR", "all"],
    ) -> None:
        if idioma not in {"ES", "BR", "all"}:
            raise ValueError("Selecione ES, BR ou all.")
        language = None if idioma == "all" else Language(idioma)
        await interaction.response.defer(ephemeral=True, thinking=True)
        count = await self.bot.repo.reset_ranking(
            interaction.guild_id, language, interaction.user.id
        )
        log.info(
            "Ranking reseteado guild=%s admin=%s language=%s records=%s",
            interaction.guild_id,
            interaction.user.id,
            idioma,
            count,
        )
        if idioma == "all":
            message = "Rankings ES/BR deste servidor zerados."
        elif idioma == "ES":
            message = f"Ranking ES reseteado: {count} usuarios con saldo puestos a cero."
        else:
            message = f"Ranking BR zerado: {count} usuários com saldo tiveram os doces zerados."
        await interaction.followup.send(message, ephemeral=True)

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
        await self.bot.manager.create_test(interaction.guild_id, idioma, canal.id, recompensa_real)
        # Acknowledge the slash command, then remove its temporary loading response.
        try:
            await interaction.delete_original_response()
        except discord.NotFound:
            pass


async def setup(bot) -> None:
    await bot.add_cog(Admin(bot))
