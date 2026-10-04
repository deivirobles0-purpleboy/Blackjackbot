import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from cogs.configuration import LanguagePanel, ProbabilityModal
from config.settings import DEFAULT_DOOR_IMAGES, Settings
from database.repositories import Repository
from database.schema import SCHEMA_SQL
from halloween.embeds import door_embed, state_embed
from halloween.models import ClaimStatus, DoorDrop, DropStatus, Language, validate_probabilities
from halloween.rewards import roll_candy_win, roll_loss
from halloween.texts import TEXTS
from tests.test_postgres import GUILD, STAFF, claim, door, ready


@pytest.mark.parametrize("win,lose", [(100, 0), (0, 100), (50, 50), (27, 73)])
def test_valid_probabilities(win, lose):
    validate_probabilities(win, lose)


@pytest.mark.parametrize(
    "win,lose",
    [(-1, 101), (101, -1), (50, 49), (0, 0), (100, 100), (True, 99), (50.5, 49.5), ("100", 0)],
)
def test_invalid_probabilities(win, lose):
    with pytest.raises(ValueError):
        validate_probabilities(win, lose)


def test_exact_probability_boundaries_and_loss_range(monkeypatch):
    for win in (0, 1, 37, 99, 100):
        outcomes = []
        for ticket in range(100):
            monkeypatch.setattr(
                "halloween.rewards.secrets.randbelow", lambda n, ticket=ticket: ticket
            )
            outcomes.append(roll_candy_win(win))
        assert sum(outcomes) == win
    losses = []
    for ticket in range(4):
        monkeypatch.setattr("halloween.rewards.secrets.randbelow", lambda n, ticket=ticket: ticket)
        losses.append(roll_loss())
    assert losses == [2, 3, 4, 5]


@pytest.mark.parametrize("language", list(Language))
async def test_probability_modal_labels_validation_permissions_and_save(monkeypatch, language):
    bot = SimpleNamespace(repo=SimpleNamespace(set_probabilities=AsyncMock()))
    panel = LanguagePanel(bot, 123, language)
    assert panel.probability.label == TEXTS[language].probability_button
    interaction = SimpleNamespace(
        guild_id=1,
        user=SimpleNamespace(id=123),
        response=SimpleNamespace(
            send_modal=AsyncMock(), send_message=AsyncMock(), defer=AsyncMock()
        ),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    await panel.probability.callback(interaction)
    modal = interaction.response.send_modal.call_args.args[0]
    assert isinstance(modal, ProbabilityModal)
    assert [child.label for child in modal.children] == [
        TEXTS[language].win_label,
        TEXTS[language].lose_label,
    ]
    monkeypatch.setattr("cogs.configuration.panel_allowed", AsyncMock(return_value=True))
    modal.win._value, modal.lose._value = "70", "20"
    await modal.on_submit(interaction)
    bot.repo.set_probabilities.assert_not_awaited()
    assert interaction.response.send_message.call_args.kwargs["ephemeral"]
    modal.win._value, modal.lose._value = "70", "30"
    await modal.on_submit(interaction)
    bot.repo.set_probabilities.assert_awaited_once_with(1, language, 70, 30, 123)
    assert interaction.followup.send.call_args.kwargs["ephemeral"]
    bot.repo.set_probabilities.reset_mock()
    monkeypatch.setattr("cogs.configuration.panel_allowed", AsyncMock(return_value=False))
    await modal.on_submit(interaction)
    bot.repo.set_probabilities.assert_not_awaited()


@pytest.mark.parametrize("language", list(Language))
def test_legacy_gif_migration_and_new_name_priority(monkeypatch, language):
    monkeypatch.setattr("config.settings.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("DISCORD_TOKEN", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test?sslmode=require")
    monkeypatch.delenv("COMMAND_GUILD_ID", raising=False)
    new_name = f"{language}_DOOR_CANDY_WIN_GIF"
    monkeypatch.delenv(new_name, raising=False)
    monkeypatch.setenv(f"{language}_DOOR_RESULT_GIF", "https://example.com/legacy.gif")
    assert Settings.from_env().images[language].candy_win == "https://example.com/legacy.gif"
    monkeypatch.setenv(new_name, "https://example.com/win.gif")
    assert Settings.from_env().images[language].candy_win == "https://example.com/win.gif"


@pytest.mark.parametrize("language", list(Language))
def test_loss_embed_with_zero_balance_and_matching_footer(language):
    drop = DoorDrop(
        uuid4(),
        1,
        language,
        2,
        3,
        DropStatus.PROCESSING,
        False,
        True,
        datetime.now(timezone.utc),
        None,
        None,
        candy_win=False,
    )
    settings = Settings("test", "postgresql://test@localhost/test", DEFAULT_DOOR_IMAGES)
    embed = door_embed(
        drop, "result", settings, [{"user_id": 11, "candies": 0}, {"user_id": 12, "candies": -4}]
    )
    assert "<@11>: 0\n<@12>: -4" in embed.description
    assert embed.image.url == DEFAULT_DOOR_IMAGES[language].candy_lose
    assert (
        embed.footer.text
        == door_embed(replace(drop, candy_win=True), "result", settings).footer.text
    )


@pytest.mark.postgres
async def test_independent_probabilities_persist_and_existing_door_keeps_outcome(repo):
    original = await door(repo)
    assert original.candy_win
    await repo.set_probabilities(GUILD, Language.ES, 0, 100, STAFF)
    restarted = Repository(repo.pool)
    es = await restarted.config(GUILD, Language.ES)
    br = await restarted.config(GUILD, Language.BR)
    assert (es.win_percent, es.lose_percent) == (0, 100)
    assert (br.win_percent, br.lose_percent) == (100, 0)
    assert (await restarted.drop(original.id)).candy_win
    assert not (await door(restarted)).candy_win
    assert "Ganar: 0% | Perder: 100%" == state_embed(es).fields[6].value
    with pytest.raises(ValueError):
        await repo.set_probabilities(GUILD, Language.BR, 40, 40, STAFF)
    assert (await repo.config(GUILD, Language.BR)).win_percent == 100


@pytest.mark.postgres
@pytest.mark.parametrize("language", list(Language))
async def test_individual_losses_clamped_balances_and_duplicate_restart(
    repo, monkeypatch, language
):
    await repo.set_probabilities(GUILD, language, 0, 100, STAFF)
    drop = await door(repo, language)
    await repo.adjust(GUILD, 11, language, "add", 3, STAFF)
    await repo.adjust(GUILD, 12, language, "add", 10, STAFF)
    await repo.adjust(
        GUILD, 11, Language.BR if language == Language.ES else Language.ES, "add", 8, STAFF
    )
    losses = iter([5, 4])
    monkeypatch.setattr("database.repositories.roll_loss", lambda: next(losses))
    assert (await claim(repo, drop, 11)).candies == -3
    assert (await claim(repo, drop, 12)).candies == -4
    assert [dict(row) for row in await repo.ranking(GUILD, language)] == [
        {"user_id": 12, "candies": 6}
    ]
    restarted = Repository(repo.pool)
    duplicates = await asyncio.gather(*(claim(restarted, drop, 11) for _ in range(20)))
    assert all(result.status == ClaimStatus.DUPLICATE for result in duplicates)
    assert not (await restarted.drop(drop.id)).candy_win
    assert [w["candies"] for w in await restarted.winners(drop.id)] == [-3, -4]
    await restarted.finish(drop.id)
    await restarted.finish(drop.id)
    assert (await restarted.ranking(GUILD, language))[0]["candies"] == 6
    other = Language.BR if language == Language.ES else Language.ES
    assert (await repo.ranking(GUILD, other))[0]["candies"] == 8


@pytest.mark.postgres
async def test_concurrent_losing_doors_cannot_overdraw_same_balance(repo, monkeypatch):
    await repo.set_probabilities(GUILD, Language.ES, 0, 100, STAFF)
    first, second = await door(repo), await door(repo)
    await repo.adjust(GUILD, 11, Language.ES, "add", 3, STAFF)
    monkeypatch.setattr("database.repositories.roll_loss", lambda: 5)
    results = await asyncio.gather(claim(repo, first, 11), claim(repo, second, 11))
    assert sorted(result.candies for result in results) == [-3, 0]
    assert await repo.ranking(GUILD, Language.ES) == []


@pytest.mark.postgres
async def test_losing_simulation_preserves_balances(repo, monkeypatch):
    await repo.set_probabilities(GUILD, Language.ES, 0, 100, STAFF)
    await repo.adjust(GUILD, 11, Language.ES, "add", 3, STAFF)
    drop = await door(repo, real=False)
    monkeypatch.setattr("database.repositories.roll_loss", lambda: 5)
    assert (await claim(repo, drop, 11)).candies == -5
    assert (await repo.ranking(GUILD, Language.ES))[0]["candies"] == 3


@pytest.mark.postgres
async def test_loss_is_rolled_back_if_participation_cannot_be_saved(repo, monkeypatch):
    import asyncpg

    await repo.set_probabilities(GUILD, Language.ES, 0, 100, STAFF)
    drop = await door(repo)
    await repo.adjust(GUILD, 11, Language.ES, "add", 10, STAFF)
    monkeypatch.setattr("database.repositories.roll_loss", lambda: 5)
    await repo.pool.execute(
        "CREATE FUNCTION reject_claim() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN RAISE EXCEPTION 'test claim failure'; END $$; "
        "CREATE TRIGGER reject_claim BEFORE INSERT ON door_winners "
        "FOR EACH ROW EXECUTE FUNCTION reject_claim()"
    )
    with pytest.raises(asyncpg.RaiseError):
        await claim(repo, drop, 11)
    assert (await repo.ranking(GUILD, Language.ES))[0]["candies"] == 10
    assert await repo.winners(drop.id) == []
    assert (await repo.drop(drop.id)).status == DropStatus.OPEN


@pytest.mark.postgres
async def test_schema_upgrade_preserves_legacy_scores_and_active_doors(repo):
    await ready(repo)
    drop = await door(repo)
    await claim(repo, drop, 11)
    before = [dict(row) for row in await repo.ranking(GUILD, Language.ES)]
    await repo.pool.execute(
        "ALTER TABLE event_config DROP COLUMN win_percent; ALTER TABLE door_drops DROP COLUMN candy_win; "
        "ALTER TABLE door_winners DROP CONSTRAINT door_winners_candies_check; "
        "ALTER TABLE door_winners ADD CONSTRAINT door_winners_candies_check CHECK (candies BETWEEN 1 AND 5)"
    )
    await repo.pool.execute(SCHEMA_SQL)
    await repo.pool.execute(SCHEMA_SQL)
    assert [dict(row) for row in await repo.ranking(GUILD, Language.ES)] == before
    assert (await repo.drop(drop.id)).candy_win
    assert (await repo.config(GUILD, Language.ES)).win_percent == 100
    assert (await claim(repo, await repo.drop(drop.id), 12)).status == ClaimStatus.ACCEPTED
    await repo.set_probabilities(GUILD, Language.ES, 0, 100, STAFF)
    losing = await door(repo)
    assert not losing.candy_win
    assert (await claim(repo, losing, 13)).candies == 0
