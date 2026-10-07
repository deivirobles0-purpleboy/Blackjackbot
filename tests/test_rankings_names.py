from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from cogs.rankings import Rankings
from halloween.embeds import ranking_embed
from halloween.models import Language


@pytest.mark.parametrize("language", list(Language))
async def test_ranking_uses_nick_and_visible_name_without_mentions(language):
    missing = discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "Unknown Member")
    rows = [{"user_id": i, "candies": 10 - i} for i in range(1, 5)]
    cached = SimpleNamespace(nick="Ho**zzi", display_name="username")

    async def fetch_member(user_id):
        if user_id == 2:
            return SimpleNamespace(nick=None, display_name="Nombre visible")
        raise missing

    bot = SimpleNamespace(
        repo=SimpleNamespace(ranking=AsyncMock(return_value=rows)),
        get_user=Mock(
            side_effect=lambda user_id: (
                SimpleNamespace(display_name="Ex miembro") if user_id == 3 else None
            )
        ),
        fetch_user=AsyncMock(side_effect=missing),
    )
    guild = SimpleNamespace(
        get_member=Mock(side_effect=lambda user_id: cached if user_id == 1 else None),
        fetch_member=AsyncMock(side_effect=fetch_member),
    )
    interaction = SimpleNamespace(
        guild_id=1,
        guild=guild,
        user=SimpleNamespace(id=99),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    await Rankings(bot).show(interaction, language)
    assert interaction.followup.send.call_args.kwargs["wait"] is True
    interaction.followup.send.return_value.delete.assert_awaited_once_with(delay=60)
    embed = interaction.followup.send.call_args.kwargs["embed"]
    assert "Ho\\*\\*zzi" in embed.description
    assert "Nombre visible" in embed.description
    assert "Ex miembro" in embed.description
    assert (
        "Usuario desconocido" if language == Language.ES else "Usuário desconhecido"
    ) in embed.description
    assert "<@" not in embed.description
    assert embed.description.count("<:doce:1556451862969065512>") == 4
    guild.fetch_member.assert_any_await(2)
    assert guild.fetch_member.await_count == 3
    bot.fetch_user.assert_awaited_once_with(4)


async def test_name_lookup_only_fetches_top_fifteen():
    rows = [{"user_id": i, "candies": 20 - i} for i in range(1, 17)]
    guild = SimpleNamespace(
        get_member=lambda _: None,
        fetch_member=AsyncMock(
            side_effect=lambda i: SimpleNamespace(nick=f"Nick {i}", display_name=f"User {i}")
        ),
    )
    interaction = SimpleNamespace(guild=guild, user=SimpleNamespace(id=99))
    names = await Rankings(SimpleNamespace()).display_names(interaction, rows)
    assert set(names) == set(range(1, 16))
    assert guild.fetch_member.await_count == 15


@pytest.mark.parametrize("language", list(Language))
def test_ranking_name_cannot_insert_mentions_or_extra_lines(language):
    embed = ranking_embed(
        language, [{"user_id": 1, "candies": 4}], display_names={1: "@everyone\n<@123> **name**"}
    )
    assert "@everyone" not in embed.description
    assert "<@123>" not in embed.description
    assert "\n" not in embed.description
    assert "\\*\\*name\\*\\*" in embed.description
