import asyncio
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config.settings import DEFAULT_DOOR_IMAGES
from halloween.models import EventConfig, Language
from utils.logger import DiscordNoiseFilter, SecretFormatter
from utils.startup import log_gifs, log_ready_status


@pytest.mark.parametrize(
    "message",
    [
        "PyNaCl is not installed, voice will NOT be supported",
        "davey is not installed, voice will NOT be supported",
    ],
)
def test_unneeded_voice_warning_filtered_but_errors_retained(message):
    record = logging.LogRecord("discord.client", logging.WARNING, __file__, 1, message, (), None)
    assert not DiscordNoiseFilter().filter(record)
    record.levelno = logging.ERROR
    assert DiscordNoiseFilter().filter(record)
    record.levelno = logging.WARNING
    record.msg = "Gateway connection failed"
    assert DiscordNoiseFilter().filter(record)


def test_compact_log_keeps_error_traceback_and_redacts_token(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "test-secret-token")
    record = logging.LogRecord(
        "source.internal",
        logging.INFO,
        __file__,
        1,
        "✅ Comandos Slash: %s sincronizados",
        (10,),
        None,
    )
    formatter = SecretFormatter("%(message)s")
    assert formatter.format(record) == "✅ Comandos Slash: 10 sincronizados"
    try:
        raise RuntimeError("Falló la conexión con test-secret-token")
    except RuntimeError as error:
        record.levelno = logging.ERROR
        record.msg = "Error de servicio"
        record.args = ()
        record.exc_info = (type(error), error, error.__traceback__)
    text = formatter.format(record)
    assert text.startswith("❌ Error de servicio")
    assert "Traceback:" in text
    assert "RuntimeError" in text
    assert "test-secret-token" not in text


class Role:
    def __init__(self, position):
        self.position = position
        self.managed = False

    def __le__(self, other):
        return self.position <= other.position

    def is_default(self):
        return False


def ready_bot(*, guild_installed=True, complete=True, manage_roles=True):
    leader = asyncio.Event()
    leader.set()
    member = SimpleNamespace(
        guild_permissions=SimpleNamespace(manage_roles=manage_roles), top_role=Role(2)
    )
    channel = SimpleNamespace(
        name="drops",
        permissions_for=lambda _: SimpleNamespace(
            view_channel=True, send_messages=True, embed_links=True, read_message_history=True
        ),
    )
    guild = SimpleNamespace(
        id=123,
        name="Servidor de prueba",
        me=member,
        get_role=lambda _: Role(1),
        get_channel=lambda _: channel,
    )
    now = datetime.now(timezone.utc)
    configs = (
        [EventConfig(guild.id, lang, 555, 1, 5, False, None, None, now) for lang in Language]
        if complete
        else []
    )
    return SimpleNamespace(
        is_ready=lambda: True,
        manager=SimpleNamespace(leader=leader),
        synced_command_count=10,
        settings=SimpleNamespace(images=DEFAULT_DOOR_IMAGES),
        guilds=[guild] if guild_installed else [],
        repo=SimpleNamespace(guild_configs=AsyncMock(return_value=configs)),
    )


async def test_zero_guilds_does_not_report_success(caplog):
    bot = ready_bot(guild_installed=False)
    with caplog.at_level(logging.INFO):
        await log_ready_status(bot)
    assert "ningún servidor" in caplog.text
    assert "Blackjack Conectado - configuración pendiente" in caplog.text
    assert "100%" not in caplog.text
    bot.repo.guild_configs.assert_not_awaited()


@pytest.mark.parametrize("complete,manage_roles", [(False, True), (True, False)])
async def test_missing_event_config_or_role_permission_does_not_report_success(
    caplog,
    complete,
    manage_roles,
):
    bot = ready_bot(complete=complete, manage_roles=manage_roles)
    with caplog.at_level(logging.INFO):
        await log_ready_status(bot)
    assert "configuración pendiente" in caplog.text
    assert "100%" not in caplog.text


async def test_verified_startup_summary_is_logged_after_config_details(caplog):
    bot = ready_bot()
    with caplog.at_level(logging.INFO):
        assert log_gifs(bot)
        await log_ready_status(bot)
    assert "GIFs configurados: ES 4/4 | BR 4/4" in caplog.text
    assert "ES: Inactivo" in caplog.text
    assert "BR: Inactivo" in caplog.text
    assert caplog.records[-1].getMessage() == "✅ Blackjack Conectado - 100% del inicio verificado"


async def test_scheduler_unavailable_does_not_report_success(caplog):
    bot = ready_bot()
    bot.manager.leader.clear()
    with caplog.at_level(logging.INFO):
        await log_ready_status(bot)
    assert "scheduler todavía no disponible" in caplog.text
    assert "100%" not in caplog.text
