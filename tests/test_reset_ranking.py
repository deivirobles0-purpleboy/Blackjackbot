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


def test_reset_selector_and_user_are_optional_and_staff_only():
    command = Admin.reset
    parameters = {parameter.name: parameter for parameter in command.parameters}
    assert command.guild_only and command.checks
    assert parameters["idioma"].required
    assert not parameters["opcao"].required
    assert parameters["opcao"].default == "user"
    assert {choice.value for choice in parameters["opcao"].choices} == {"user", "all"}
    assert not parameters["user"].required
    assert parameters["user"].type == discord.AppCommandOptionType.user


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("explicit", [False, True])
async def test_user_option_preserves_individual_reset(language, explicit):
    cog, interaction = command_context()
    user = SimpleNamespace(id=11)
    kwargs = {"opcao": "user"} if explicit else {}
    await Admin.reset.callback(cog, interaction, language, user=user, **kwargs)
    cog.bot.repo.adjust.assert_awaited_once_with(GUILD, 11, language, "reset", 0, STAFF)
    cog.bot.repo.reset_ranking.assert_not_awaited()
    assert interaction.followup.send.call_args.kwargs["ephemeral"]


@pytest.mark.parametrize("language", list(Language))
async def test_all_option_resets_only_selected_ranking(language):
    cog, interaction = command_context()
    await Admin.reset.callback(cog, interaction, language, opcao="all")
    cog.bot.repo.reset_ranking.assert_awaited_once_with(GUILD, language, STAFF)
    cog.bot.repo.adjust.assert_not_awaited()
    assert f"Ranking {language.value}" in interaction.followup.send.call_args.args[0]
    assert interaction.followup.send.call_args.kwargs["ephemeral"]


@pytest.mark.parametrize(
    "option,user", [("user", None), ("all", SimpleNamespace(id=11)), ("invalid", None)]
)
async def test_invalid_selection_never_changes_any_scores(option, user):
    cog, interaction = command_context()
    with pytest.raises(ValueError):
        await Admin.reset.callback(cog, interaction, Language.BR, opcao=option, user=user)
    cog.bot.repo.adjust.assert_not_awaited()
    cog.bot.repo.reset_ranking.assert_not_awaited()
    interaction.response.defer.assert_not_awaited()


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
