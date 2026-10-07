import asyncio
import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from halloween.models import Language
from utils.permissions import is_staff_member, staff_only

log = logging.getLogger(__name__)


def reset_user_id(value: str) -> int | None:
    match = re.fullmatch(r"(?:<@!?([0-9]{1,19})>|([0-9]{1,19}))", value.strip())
    if match:
        user_id = int(match[1] or match[2])
        if 0 < user_id <= 9_223_372_036_854_775_807:
            return user_id
    return None


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

    @app_commands.command(
        name="reset_doces", description="Zera os doces de um usuário ou todo o ranking do idioma"
    )
    @app_commands.describe(
        idioma="Idioma do ranking a resetar",
        destino="Selecione um usuário ou all para zerar todo o ranking do idioma",
    )
    @app_commands.guild_only()
    @staff_only()
    async def reset(
        self,
        interaction: discord.Interaction,
        idioma: Language,
        destino: str,
    ) -> None:
        target = destino.strip()
        user_id = reset_user_id(target)
        if target.casefold() != "all" and user_id is None:
            raise ValueError("Selecione um usuário na lista, informe uma menção/ID ou escolha all.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        if user_id is not None:
            member = interaction.guild.get_member(user_id)
            if member is None:
                member = await interaction.guild.fetch_member(user_id)
            await self._adjust(interaction, member, idioma, "reset", 0, ephemeral=True)
            return
        count = await self.bot.repo.reset_ranking(interaction.guild_id, idioma, interaction.user.id)
        log.info(
            "Ranking reseteado guild=%s admin=%s language=%s users=%s",
            interaction.guild_id,
            interaction.user.id,
            idioma,
            count,
        )
        message = (
            f"Ranking ES reseteado: {count} usuarios con saldo puestos a cero."
            if idioma == Language.ES
            else f"Ranking BR zerado: {count} usuários com saldo tiveram os doces zerados."
        )
        await interaction.followup.send(message, ephemeral=True)

    @reset.autocomplete("destino")
    async def reset_destinations(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        # Autocomplete doesn't run the command's Staff check automatically.
        if interaction.guild is None or not is_staff_member(interaction.user):
            return []
        query = current.strip()
        choices = []
        if not query or "all".startswith(query.casefold()):
            choices.append(app_commands.Choice(name="all — Todo o ranking", value="all"))
        members = {}
        for member in interaction.guild.members:
            if not query or query.casefold() in member.display_name.casefold():
                members[member.id] = member.display_name
        user_id = reset_user_id(query)
        try:
            if user_id is not None:
                member = await asyncio.wait_for(
                    interaction.guild.fetch_member(user_id), timeout=1.5
                )
                members[member.id] = member.display_name
            elif query and query.casefold() != "all":
                # Official Search Guild Members endpoint, using discord.py's rate limiting.
                rows = await asyncio.wait_for(
                    self.bot.http.request(
                        discord.http.Route(
                            "GET",
                            "/guilds/{guild_id}/members/search",
                            guild_id=interaction.guild_id,
                        ),
                        params={"query": query, "limit": 24},
                    ),
                    timeout=1.5,
                )
                for row in rows:
                    user = row["user"]
                    members[int(user["id"])] = (
                        row.get("nick") or user.get("global_name") or user["username"]
                    )
        except (discord.HTTPException, OSError, TimeoutError):
            log.debug("No se pudo completar búsqueda de usuarios guild=%s", interaction.guild_id)
        for member_id, name in members.items():
            if len(choices) >= 25:
                break
            label = f"{name} — {member_id}"
            choices.append(app_commands.Choice(name=label[:100], value=str(member_id)))
        return choices

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
