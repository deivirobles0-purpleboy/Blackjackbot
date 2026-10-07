from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.admin import Admin
from config.constants import STAFF_ROLE_IDS
from halloween.models import Language
from tests.test_postgres import GUILD, STAFF, ready


def command_context():
    repo = SimpleNamespace(
        adjust=AsyncMock(return_value=0), reset_ranking=AsyncMock(return_value=3)
    )
    member = SimpleNamespace(id=11, display_name="Cached user")
    admin = MagicMock(spec=discord.Member)
    admin.id = STAFF
    admin.roles = [SimpleNamespace(id=next(iter(STAFF_ROLE_IDS)))]
    guild = SimpleNamespace(
        id=GUILD,
        members=[member],
        get_member=lambda user_id: member if user_id == 11 else None,
        fetch_member=AsyncMock(return_value=member),
    )
    interaction = SimpleNamespace(
        guild_id=GUILD,
        guild=guild,
        user=admin,
        response=SimpleNamespace(defer=AsyncMock(), is_done=lambda: True),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    return Admin(
        SimpleNamespace(repo=repo, http=SimpleNamespace(request=AsyncMock(return_value=[])))
    ), interaction


def test_reset_has_only_language_and_autocomplete_destination_and_staff_check():
    command = Admin.reset
    parameters = {parameter.name: parameter for parameter in command.parameters}
    assert command.guild_only and command.checks
    assert command.name == "reset_doces"
    assert set(parameters) == {"idioma", "destino"}
    assert all(parameter.required for parameter in parameters.values())
    assert parameters["destino"].type == discord.AppCommandOptionType.string
    assert parameters["destino"].autocomplete


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("destination", ["11", "<@11>", "<@!11>"])
async def test_user_destination_preserves_individual_reset(language, destination):
    cog, interaction = command_context()
    await Admin.reset.callback(cog, interaction, language, destination)
    cog.bot.repo.adjust.assert_awaited_once_with(GUILD, 11, language, "reset", 0, STAFF)
    cog.bot.repo.reset_ranking.assert_not_awaited()
    assert interaction.followup.send.call_args.kwargs["ephemeral"]
    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("destination", ["all", " ALL "])
async def test_all_destination_resets_only_selected_ranking(language, destination):
    cog, interaction = command_context()
    await Admin.reset.callback(cog, interaction, language, destination)
    cog.bot.repo.reset_ranking.assert_awaited_once_with(GUILD, language, STAFF)
    cog.bot.repo.adjust.assert_not_awaited()
    assert f"Ranking {language.value}" in interaction.followup.send.call_args.args[0]
    assert interaction.followup.send.call_args.kwargs["ephemeral"]


@pytest.mark.parametrize(
    "destination",
    ["", "user", "invalid", "all user", "<@&11>", "0", "9223372036854775808", "11junk"],
)
async def test_invalid_selection_never_changes_any_scores(destination):
    cog, interaction = command_context()
    with pytest.raises(ValueError):
        await Admin.reset.callback(cog, interaction, Language.BR, destination)
    cog.bot.repo.adjust.assert_not_awaited()
    cog.bot.repo.reset_ranking.assert_not_awaited()
    interaction.response.defer.assert_not_awaited()


async def test_selected_member_not_cached_is_fetched_before_reset():
    cog, interaction = command_context()
    interaction.guild.get_member = lambda _: None
    await Admin.reset.callback(cog, interaction, Language.ES, "11")
    interaction.guild.fetch_member.assert_awaited_once_with(11)
    cog.bot.repo.adjust.assert_awaited_once_with(GUILD, 11, Language.ES, "reset", 0, STAFF)


async def test_missing_member_never_falls_back_to_reset_all():
    cog, interaction = command_context()
    interaction.guild.fetch_member.side_effect = discord.NotFound(
        SimpleNamespace(status=404, reason="Not Found"), "Unknown Member"
    )
    with pytest.raises(discord.NotFound):
        await Admin.reset.callback(cog, interaction, Language.ES, "12")
    cog.bot.repo.adjust.assert_not_awaited()
    cog.bot.repo.reset_ranking.assert_not_awaited()


async def test_autocomplete_has_all_and_members_in_one_field():
    cog, interaction = command_context()
    choices = await cog.reset_destinations(interaction, "")
    assert [choice.value for choice in choices] == ["all", "11"]
    assert "Cached user" in choices[1].name


async def test_autocomplete_queries_members_outside_cache():
    cog, interaction = command_context()
    cog.bot.http.request.return_value = [
        {"user": {"id": "12", "username": "other"}, "nick": "Search user"}
    ]
    choices = await cog.reset_destinations(interaction, "Search")
    assert [choice.value for choice in choices] == ["12"]
    assert "Search user" in choices[0].name
    assert cog.bot.http.request.call_args.args[0].path == "/guilds/{guild_id}/members/search"
    assert cog.bot.http.request.call_args.kwargs["params"] == {"query": "Search", "limit": 24}


async def test_autocomplete_snowflake_resolves_exact_member():
    cog, interaction = command_context()
    choices = await cog.reset_destinations(interaction, "<@11>")
    assert [choice.value for choice in choices] == ["11"]
    interaction.guild.fetch_member.assert_awaited_once_with(11)


async def test_autocomplete_limits_choices_and_name_lengths():
    cog, interaction = command_context()
    interaction.guild.members = [
        SimpleNamespace(id=i, display_name="x" * 120) for i in range(1, 41)
    ]
    choices = await cog.reset_destinations(interaction, "")
    assert len(choices) == 25
    assert choices[0].value == "all"
    assert all(len(choice.name) <= 100 for choice in choices)


async def test_autocomplete_failure_keeps_cached_choices():
    cog, interaction = command_context()
    cog.bot.http.request.side_effect = TimeoutError
    choices = await cog.reset_destinations(interaction, "Cached")
    assert [choice.value for choice in choices] == ["11"]


async def test_autocomplete_requires_staff_access():
    cog, interaction = command_context()
    interaction.user.roles = []
    assert await cog.reset_destinations(interaction, "Search") == []
    cog.bot.http.request.assert_not_awaited()


@pytest.mark.postgres
@pytest.mark.parametrize("language", list(Language))
async def test_all_reset_covers_users_outside_top15_and_isolates_guild_language(repo, language):
    other_language = Language.BR if language == Language.ES else Language.ES
    await ready(repo, language)
    config_before = await repo.config(GUILD, language)
    for user_id in range(1, 21):
        await repo.adjust(GUILD, user_id, language, "add", 5, STAFF)
    await repo.adjust(GUILD, 1, other_language, "add", 7, STAFF)
    await repo.adjust(GUILD + 1, 1, language, "add", 9, STAFF)
    assert len(await repo.ranking(GUILD, language)) == 15
    assert await repo.reset_ranking(GUILD, language, STAFF) == 20
    assert await repo.ranking(GUILD, language) == []
    assert (await repo.ranking(GUILD, other_language))[0]["candies"] == 7
    assert (await repo.ranking(GUILD + 1, language))[0]["candies"] == 9
    assert await repo.config(GUILD, language) == config_before
    audit = await repo.pool.fetchrow("SELECT * FROM admin_logs WHERE action='reset_all'")
    assert audit["guild_id"] == GUILD
    assert audit["admin_id"] == STAFF
    assert audit["language"] == language
    assert audit["amount"] == 20
    assert audit["target_user_id"] is None
    assert await repo.reset_ranking(GUILD, language, STAFF) == 0


@pytest.mark.postgres
async def test_bulk_reset_rolls_back_when_audit_fails(repo, monkeypatch):
    await repo.adjust(GUILD, 11, Language.BR, "add", 5, STAFF)
    await repo.adjust(GUILD, 12, Language.BR, "add", 8, STAFF)
    before = [dict(row) for row in await repo.ranking(GUILD, Language.BR)]
    monkeypatch.setattr(repo, "_audit", AsyncMock(side_effect=OSError("audit unavailable")))
    with pytest.raises(OSError, match="audit unavailable"):
        await repo.reset_ranking(GUILD, Language.BR, STAFF)
    assert [dict(row) for row in await repo.ranking(GUILD, Language.BR)] == before
    assert await repo.pool.fetchval("SELECT count(*) FROM admin_logs WHERE action='reset_all'") == 0
