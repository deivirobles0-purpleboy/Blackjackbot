from dataclasses import replace
from datetime import datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncpg
import discord
import pytest

from cogs.admin import Admin
from database.repositories import Repository
from database.schema import SCHEMA_SQL
from halloween.daily_schedule import next_drop_time, parse_daily_time, window_is_open
from halloween.embeds import state_embed
from halloween.models import DropStatus, Language
from tests.test_flow import FakeChannel, manager
from tests.test_postgres import CHANNEL, GUILD, STAFF, claim, ready


@pytest.mark.parametrize("value", ["00:00", "09:00", "22:00", "23:59"])
def test_24h_times(value):
    assert parse_daily_time(value).strftime("%H:%M") == value


@pytest.mark.parametrize("value", ["9:00", "24:00", "22:60", "-1:00", "09:00:00", "9pm", ""])
def test_invalid_times(value):
    with pytest.raises(ValueError, match="HH:MM"):
        parse_daily_time(value)


@pytest.mark.parametrize(
    "start,end,current,expected",
    [
        ("09:00", "22:00", "08:59", False),
        ("09:00", "22:00", "09:00", True),
        ("09:00", "22:00", "21:59", True),
        ("09:00", "22:00", "22:00", False),
        ("22:00", "03:00", "21:59", False),
        ("22:00", "03:00", "22:00", True),
        ("22:00", "03:00", "00:00", True),
        ("22:00", "03:00", "02:59", True),
        ("22:00", "03:00", "03:00", False),
    ],
)
def test_window_boundaries(start, end, current, expected):
    local_now = datetime.combine(datetime(2026, 10, 12).date(), parse_daily_time(current))
    assert window_is_open(local_now, parse_daily_time(start), parse_daily_time(end)) == expected


@pytest.mark.parametrize(
    "now,start,end,delay,expected",
    [
        ("2026-10-12T08:00", "09:00", "22:00", 1, "2026-10-12T09:01"),
        ("2026-10-12T14:00", "09:00", "22:00", 2, "2026-10-12T14:02"),
        ("2026-10-12T21:59", "09:00", "22:00", 2, "2026-10-13T09:00"),
        ("2026-10-12T22:00", "09:00", "22:00", 1, "2026-10-13T09:01"),
        ("2026-10-12T23:59", "22:00", "03:00", 2, "2026-10-13T00:01"),
        ("2026-10-12T02:59", "22:00", "03:00", 2, "2026-10-12T22:00"),
        ("2026-10-12T03:00", "22:00", "03:00", 1, "2026-10-12T22:01"),
    ],
)
def test_cooldown_never_schedules_outside_window(now, start, end, delay, expected):
    assert next_drop_time(
        datetime.fromisoformat(now), delay, parse_daily_time(start), parse_daily_time(end)
    ) == datetime.fromisoformat(expected)


def command_context():
    repo = SimpleNamespace(
        config=AsyncMock(return_value=SimpleNamespace(complete=True)),
        set_enabled=AsyncMock(return_value=list(Language)),
    )
    interaction = SimpleNamespace(
        guild_id=GUILD,
        user=SimpleNamespace(id=STAFF),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    return Admin(SimpleNamespace(repo=repo)), interaction


def test_activation_requires_two_time_parameters_and_staff_access():
    command = Admin.activate
    assert command.guild_only and command.checks
    assert [parameter.name for parameter in command.parameters] == ["inicio", "fim"]
    assert all(parameter.required for parameter in command.parameters)
    assert all(
        parameter.type == discord.AppCommandOptionType.string for parameter in command.parameters
    )


async def test_daily_activation_and_full_disable_keep_command_notifications(caplog):
    caplog.set_level("INFO", logger="cogs.admin")
    cog, interaction = command_context()
    await Admin.activate.callback(cog, interaction, "09:00", "22:00")
    cog.bot.repo.set_enabled.assert_awaited_once_with(
        GUILD, True, STAFF, start=time(9), end=time(22)
    )
    message = interaction.followup.send.call_args.args[0]
    assert "09:00 às 22:00 (São Paulo)" in message
    assert "SISTEMA DE DOCES ATIVADO" in message
    assert message.count("<:check:1532500942237339728>") == 2
    await Admin.deactivate.callback(cog, interaction)
    assert cog.bot.repo.set_enabled.call_args.args == (GUILD, False, STAFF)
    assert "não serão retomados automaticamente" in interaction.followup.send.call_args.args[0]
    assert "Activación" in caplog.text and "Desactivación" in caplog.text


@pytest.mark.parametrize("start,end", [("09:00", "09:00"), ("24:00", "22:00"), ("09:00", "")])
async def test_invalid_activation_never_changes_existing_schedule(start, end):
    cog, interaction = command_context()
    with pytest.raises(ValueError):
        await Admin.activate.callback(cog, interaction, start, end)
    cog.bot.repo.set_enabled.assert_not_awaited()
    interaction.response.defer.assert_not_awaited()


async def enable_daily(repo, monkeypatch, now, start=time(9), end=time(22)):
    monkeypatch.setattr(repo, "_local_now", AsyncMock(return_value=now))
    for language in Language:
        await ready(repo, language)
    return await repo.set_enabled(GUILD, True, STAFF, start=start, end=end)


async def make_due(repo, language=Language.ES):
    await repo.pool.execute(
        "UPDATE event_config SET next_drop_at=now()-interval '1 second' WHERE guild_id=$1 AND language=$2",
        GUILD,
        language,
    )


@pytest.mark.postgres
async def test_daily_window_persists_for_both_languages_and_uses_sao_paulo_timezone(
    repo, monkeypatch
):
    assert set(await enable_daily(repo, monkeypatch, datetime(2026, 10, 12, 8))) == set(Language)
    restarted = Repository(repo.pool)
    for language in Language:
        cfg = await restarted.config(GUILD, language)
        assert cfg.enabled and (cfg.daily_start, cfg.daily_end) == (time(9), time(22))
        assert cfg.next_drop_at == datetime(2026, 10, 12, 12, 1, tzinfo=timezone.utc)
        assert state_embed(cfg).fields[0].value == "🕒 Programado diariamente"
        assert state_embed(cfg).fields[-1].value == "09:00 – 22:00 (São Paulo)"
        inactive = "Inactivo" if language == Language.ES else "Inativo"
        assert inactive in state_embed(replace(cfg, enabled=False)).fields[0].value
    rows = await repo.pool.fetch(
        "SELECT language,action,amount FROM admin_logs WHERE action LIKE 'daily_%'"
    )
    assert len(rows) == 4
    assert {row["amount"] for row in rows} == {540, 1320}


@pytest.mark.postgres
@pytest.mark.parametrize(
    "now,allowed",
    [
        (datetime(2026, 10, 12, 8, 59), False),
        (datetime(2026, 10, 12, 9), True),
        (datetime(2026, 10, 12, 22), False),
    ],
)
async def test_due_drop_rechecks_daily_window(repo, monkeypatch, now, allowed):
    await enable_daily(repo, monkeypatch, now)
    await make_due(repo)
    drop = await repo.prepare_drop(GUILD, Language.ES)
    assert (drop is not None) == allowed
    if not allowed:
        cfg = await repo.config(GUILD, Language.ES)
        assert cfg.enabled and cfg.next_drop_at is not None
        assert await repo.live_drops() == []


@pytest.mark.postgres
async def test_close_between_prepare_and_send_cancels_pending_door(repo, monkeypatch, caplog):
    caplog.set_level("INFO")
    await enable_daily(repo, monkeypatch, datetime(2026, 10, 12, 21, 59))
    await make_due(repo)
    drop = await repo.prepare_drop(GUILD, Language.ES)
    repo._local_now.return_value = datetime(2026, 10, 12, 22)
    channel = FakeChannel()
    await manager(repo, channel).run_drop(drop.id)
    assert channel.sends == 0
    assert (await repo.drop(drop.id)).status == DropStatus.CANCELLED
    assert (await repo.config(GUILD, Language.ES)).next_drop_at == datetime(
        2026, 10, 13, 12, 1, tzinfo=timezone.utc
    )
    assert not any(record.name == "halloween.manager" for record in caplog.records)


@pytest.mark.postgres
async def test_published_participants_finish_after_close_and_next_day_recovers(repo, monkeypatch):
    await enable_daily(repo, monkeypatch, datetime(2026, 10, 12, 21, 59))
    await make_due(repo)
    drop = await repo.prepare_drop(GUILD, Language.ES)
    await repo.bind_message(drop.id, 12345)
    drop = await repo.drop(drop.id)
    repo._local_now.return_value = datetime(2026, 10, 12, 22)
    assert (await claim(repo, drop, 11)).count == 1
    await repo.finish(drop.id)
    assert (await repo.config(GUILD, Language.ES)).enabled
    cfg = await repo.config(GUILD, Language.ES)
    assert cfg.next_drop_at == datetime(2026, 10, 13, 12, 1, tzinfo=timezone.utc)
    restarted = Repository(repo.pool)
    monkeypatch.setattr(
        restarted, "_local_now", AsyncMock(return_value=datetime(2026, 10, 13, 9, 1))
    )
    await make_due(restarted)
    assert await restarted.prepare_drop(GUILD, Language.ES) is not None


@pytest.mark.postgres
@pytest.mark.parametrize(
    "current,allowed", [("23:00", True), ("02:59", True), ("03:00", False), ("21:59", False)]
)
async def test_overnight_window_in_database(repo, monkeypatch, current, allowed):
    local_now = datetime.combine(datetime(2026, 10, 12).date(), parse_daily_time(current))
    await enable_daily(repo, monkeypatch, local_now, time(22), time(3))
    await make_due(repo)
    assert (await repo.prepare_drop(GUILD, Language.ES) is not None) == allowed


@pytest.mark.postgres
async def test_full_disable_clears_daily_schedule_and_never_resumes(repo, monkeypatch):
    await enable_daily(repo, monkeypatch, datetime(2026, 10, 12, 9))
    await make_due(repo)
    pending = await repo.prepare_drop(GUILD, Language.ES)
    await repo.set_enabled(GUILD, False, STAFF)
    assert (await repo.drop(pending.id)).status == DropStatus.CANCELLED
    repo._local_now.return_value = datetime(2026, 10, 13, 9)
    for language in Language:
        await repo.repair_schedule(GUILD, language)
        cfg = await repo.config(GUILD, language)
        assert not cfg.enabled and cfg.daily_start is None and cfg.daily_end is None
        assert cfg.next_drop_at is None
        await make_due(repo, language)
        assert await repo.prepare_drop(GUILD, language) is None
    assert await repo.enabled_configs() == []


@pytest.mark.postgres
async def test_manual_test_door_is_available_outside_daily_window(repo, monkeypatch):
    await enable_daily(repo, monkeypatch, datetime(2026, 10, 12, 23))
    before = await repo.config(GUILD, Language.ES)
    channel = FakeChannel()
    mgr = manager(repo, channel)
    drop = await mgr.create_test(GUILD, Language.ES, CHANNEL, False)
    assert drop.status == DropStatus.OPEN and channel.sends == 1
    assert await repo.config(GUILD, Language.ES) == before


@pytest.mark.postgres
async def test_changing_window_replaces_future_timer(repo, monkeypatch):
    await enable_daily(repo, monkeypatch, datetime(2026, 10, 12, 8))
    before = await repo.config(GUILD, Language.ES)
    await repo.set_enabled(GUILD, True, STAFF, start=time(15), end=time(20))
    after = await repo.config(GUILD, Language.ES)
    assert after.next_drop_at > before.next_drop_at
    assert after.next_drop_at == datetime(2026, 10, 12, 18, 1, tzinfo=timezone.utc)


@pytest.mark.postgres
async def test_activation_rolls_back_both_languages_if_audit_fails(repo, monkeypatch):
    for language in Language:
        await ready(repo, language)
    before = [await repo.config(GUILD, language) for language in Language]
    monkeypatch.setattr(repo, "_audit", AsyncMock(side_effect=OSError("audit unavailable")))
    with pytest.raises(OSError):
        await repo.set_enabled(GUILD, True, STAFF, start=time(9), end=time(22))
    assert [await repo.config(GUILD, language) for language in Language] == before


@pytest.mark.postgres
async def test_schema_upgrade_preserves_schedule_and_legacy_continuous_operation(repo, monkeypatch):
    await ready(repo)
    await repo.set_enabled(GUILD, True, STAFF)
    legacy = await repo.config(GUILD, Language.ES)
    await repo.pool.execute(
        "ALTER TABLE event_config DROP COLUMN daily_start; ALTER TABLE event_config DROP COLUMN daily_end"
    )
    await repo.pool.execute(SCHEMA_SQL)
    assert await repo.config(GUILD, Language.ES) == legacy
    await enable_daily(repo, monkeypatch, datetime(2026, 10, 12, 8))
    before = await repo.config(GUILD, Language.ES)
    await repo.pool.execute(SCHEMA_SQL)
    await repo.pool.execute(SCHEMA_SQL)
    assert await repo.config(GUILD, Language.ES) == before


@pytest.mark.postgres
@pytest.mark.parametrize("start,end", [(time(9), None), (time(9), time(9))])
async def test_database_rejects_partial_or_equal_windows(repo, start, end):
    await ready(repo)
    with pytest.raises(asyncpg.CheckViolationError):
        await repo.pool.execute("UPDATE event_config SET daily_start=$1,daily_end=$2", start, end)
