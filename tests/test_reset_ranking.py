from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from cogs.admin import Admin
from halloween.models import Language
from tests.test_postgres import GUILD, STAFF, ready


def command_context():
    repo = SimpleNamespace(
        adjust=AsyncMock(return_value=0), reset_ranking=AsyncMock(return_value=3)
    )
    interaction = SimpleNamespace(
        guild_id=GUILD,
        user=SimpleNamespace(id=STAFF),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    return Admin(SimpleNamespace(repo=repo)), interaction


def test_reset_has_only_language_with_all_choice_and_staff_check():
    command = Admin.reset
    assert command.guild_only and command.checks
    assert command.name == "reset_doces"
    assert len(command.parameters) == 1
    parameter = command.parameters[0]
    assert parameter.name == "idioma"
    assert parameter.required
    assert parameter.type == discord.AppCommandOptionType.string
    assert {choice.value for choice in parameter.choices} == {"ES", "BR", "all"}
    assert not parameter.autocomplete


@pytest.mark.parametrize("option", ["ES", "BR", "all"])
async def test_command_resets_selected_language_or_both(option):
    cog, interaction = command_context()
    await Admin.reset.callback(cog, interaction, option)
    language = None if option == "all" else Language(option)
    cog.bot.repo.reset_ranking.assert_awaited_once_with(GUILD, language, STAFF)
    cog.bot.repo.adjust.assert_not_awaited()
    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    assert interaction.followup.send.await_count == 1
    message = interaction.followup.send.call_args.args[0]
    assert ("ES/BR" if option == "all" else f"Ranking {option}") in message
    assert interaction.followup.send.call_args.kwargs["ephemeral"]


@pytest.mark.parametrize("option", ["", "user", "invalid", "ALL", "<@11>"])
async def test_invalid_selection_never_changes_any_scores(option):
    cog, interaction = command_context()
    with pytest.raises(ValueError):
        await Admin.reset.callback(cog, interaction, option)
    cog.bot.repo.adjust.assert_not_awaited()
    cog.bot.repo.reset_ranking.assert_not_awaited()
    interaction.response.defer.assert_not_awaited()


async def test_failed_reset_does_not_send_success():
    cog, interaction = command_context()
    cog.bot.repo.reset_ranking.side_effect = OSError("database unavailable")
    with pytest.raises(OSError, match="database unavailable"):
        await Admin.reset.callback(cog, interaction, "all")
    interaction.followup.send.assert_not_awaited()


@pytest.mark.postgres
@pytest.mark.parametrize("language", list(Language))
async def test_reset_covers_users_outside_top15_and_isolates_guild_language(repo, language):
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
async def test_all_resets_both_languages_beyond_top15_without_affecting_other_guild(repo):
    configs_before = {}
    for language in Language:
        await ready(repo, language)
        configs_before[language] = await repo.config(GUILD, language)
        for user_id in range(1, 21):
            await repo.adjust(GUILD, user_id, language, "add", 5, STAFF)
        await repo.adjust(GUILD + 1, 1, language, "add", 9, STAFF)
        assert len(await repo.ranking(GUILD, language)) == 15
    assert await repo.reset_ranking(GUILD, None, STAFF) == 40
    for language in Language:
        assert await repo.ranking(GUILD, language) == []
        assert (await repo.ranking(GUILD + 1, language))[0]["candies"] == 9
        assert await repo.config(GUILD, language) == configs_before[language]
    audit = await repo.pool.fetchrow("SELECT * FROM admin_logs WHERE action='reset_all'")
    assert audit["guild_id"] == GUILD
    assert audit["admin_id"] == STAFF
    assert audit["language"] is None
    assert audit["amount"] == 40
    assert audit["target_user_id"] is None
    assert await repo.reset_ranking(GUILD, None, STAFF) == 0


@pytest.mark.postgres
@pytest.mark.parametrize("language", [Language.BR, None])
async def test_bulk_reset_rolls_back_when_audit_fails(repo, monkeypatch, language):
    before = {}
    for selected in Language:
        await repo.adjust(GUILD, 11, selected, "add", 5, STAFF)
        await repo.adjust(GUILD, 12, selected, "add", 8, STAFF)
        before[selected] = [dict(row) for row in await repo.ranking(GUILD, selected)]
    monkeypatch.setattr(repo, "_audit", AsyncMock(side_effect=OSError("audit unavailable")))
    with pytest.raises(OSError, match="audit unavailable"):
        await repo.reset_ranking(GUILD, language, STAFF)
    for selected in Language:
        assert [dict(row) for row in await repo.ranking(GUILD, selected)] == before[selected]
    assert await repo.pool.fetchval("SELECT count(*) FROM admin_logs WHERE action='reset_all'") == 0
