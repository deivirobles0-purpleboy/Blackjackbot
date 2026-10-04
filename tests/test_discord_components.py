from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import discord
import pytest

from bot import HalloweenBot
from cogs.configuration import ChannelView, ConfigurationPanel, LanguagePanel, MinutesModal
from config.constants import (
    PARTICIPANT_ROLE_ID,
    REGISTRATION_CUSTOM_ID,
    VERIFIED_ROLE_IDS,
)
from config.settings import DoorImages, Settings
from halloween.embeds import door_embed, state_embed
from halloween.models import DoorDrop, DropStatus, EventConfig, Language
from halloween.registration import RegistrationView
from halloween.views import DoorView, door_custom_id


def settings():
    return Settings(
        token="test",
        database_url="postgresql://test@localhost/test?sslmode=require",
        images={
            language: DoorImages(
                **{
                    phase: f"https://example.com/{language.value}/{phase}.gif"
                    for phase in ("closed", "waiting", "candy_win", "candy_lose", "timeout")
                }
            )
            for language in Language
        },
    )


async def test_load_all_cogs_and_slash_choices_offline():
    bot = HalloweenBot(settings())
    bot.repo = SimpleNamespace()
    async with bot:
        for extension in ("cogs.rankings", "cogs.admin", "cogs.registration", "cogs.configuration"):
            await bot.load_extension(extension)
        expected = {
            "doces",
            "dulces",
            "abrir_registro_halloween",
            "ativar_doces",
            "desativar_doces",
            "resetar_doces",
            "adicionar_doces",
            "tirar_doces",
            "porta_de_teste",
            "config_doces",
        }
        assert {command.name for command in bot.tree.get_commands()} == expected
        for command in bot.tree.get_commands():
            assert command.guild_only
            if command.name not in {"doces", "dulces"}:
                assert command.checks
            for parameter in command.parameters:
                if parameter.name == "idioma":
                    assert {choice.value for choice in parameter.choices} == {"ES", "BR"}
        assert bot.intents.guilds
        assert not bot.intents.message_content
        assert not bot.intents.members


async def test_persistent_views_ids_and_channel_select():
    registration = RegistrationView()
    assert registration.is_persistent()
    assert registration.children[0].custom_id == REGISTRATION_CUSTOM_ID
    drop_id = uuid4()
    for language in Language:
        view = DoorView(language, drop_id)
        assert view.is_persistent()
        assert view.children[0].custom_id == door_custom_id(language, drop_id)
        disabled = DoorView(language, drop_id, disabled=True).children[0]
        assert disabled.disabled
        assert disabled.style == discord.ButtonStyle.red
    owner = 123
    bot = SimpleNamespace()
    panel = ConfigurationPanel(bot, owner)
    assert len(panel.children) == 2
    for language in Language:
        language_panel = LanguagePanel(bot, owner, language)
        assert len(language_panel.children) == 4
        picker = ChannelView(bot, owner, language).children[0]
        assert picker.channel_types == [discord.ChannelType.text]
        modal = MinutesModal(bot, owner, language, 1, 5)
        assert len(modal.children) == 2


def test_gifs_language_phase_and_exact_embeds():
    for language in Language:
        drop = DoorDrop(
            uuid4(),
            1,
            language,
            2,
            3,
            DropStatus.OPEN,
            False,
            True,
            datetime.now(timezone.utc),
            None,
            None,
        )
        for phase in ("closed", "waiting", "result", "expired"):
            embed = door_embed(drop, phase, settings(), [{"user_id": 123, "candies": 4}])
            image_phase = {"result": "candy_win", "expired": "timeout"}.get(phase, phase)
            assert embed.image.url == f"https://example.com/{language.value}/{image_phase}.gif"
            if phase == "result":
                assert "<@123>: 4" in embed.description


def test_state_dynamic_last_drop_and_missing_config():
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    cfg = EventConfig(
        1,
        Language.ES,
        2,
        5,
        10,
        True,
        now + timedelta(minutes=4),
        now - timedelta(minutes=127),
        now,
    )
    embed = state_embed(cfg)
    assert embed.fields[5].value == "Hace 127 minutos"
    missing = EventConfig(1, Language.BR, None, None, None, False, None, None, now)
    embed = state_embed(missing)
    assert embed.fields[4].value == "Não programada"
    assert embed.fields[5].value == "Sem registros"


@pytest.mark.parametrize(
    "roles,already,allowed",
    [
        ([], False, False),
        ([next(iter(VERIFIED_ROLE_IDS))], False, True),
        ([PARTICIPANT_ROLE_ID], True, False),
    ],
)
async def test_registration_checks_roles_before_assignment(monkeypatch, roles, already, allowed):
    role = SimpleNamespace(id=PARTICIPANT_ROLE_ID, managed=False, is_default=lambda: False)
    bot_member = SimpleNamespace(guild_permissions=SimpleNamespace(manage_roles=True), top_role=2)

    # Compare hierarchy with an integer stand-in only in this mock.
    class TestRole:
        id = role.id
        managed = False

        def __ge__(self, value):
            return 1 >= value

        def is_default(self):
            return False

    guild = SimpleNamespace(id=1, get_role=lambda _: TestRole(), me=bot_member)
    member = SimpleNamespace(
        id=123,
        roles=[SimpleNamespace(id=value) for value in roles],
        guild=guild,
        add_roles=AsyncMock(),
    )
    monkeypatch.setattr("halloween.registration.get_member", AsyncMock(return_value=member))
    interaction = SimpleNamespace(
        response=SimpleNamespace(defer=AsyncMock()), followup=SimpleNamespace(send=AsyncMock())
    )
    view = RegistrationView()
    await view.children[0].callback(interaction)
    assert member.add_roles.await_count == int(allowed)
    assert interaction.followup.send.call_args.kwargs["ephemeral"]
    if already:
        assert "Ya tienes" in interaction.followup.send.call_args.args[0]


async def test_registration_permission_failure_is_controlled(monkeypatch):
    guild = SimpleNamespace(
        id=1,
        get_role=lambda _: SimpleNamespace(managed=False),
        me=SimpleNamespace(guild_permissions=SimpleNamespace(manage_roles=False)),
    )
    member = SimpleNamespace(
        id=123,
        roles=[SimpleNamespace(id=next(iter(VERIFIED_ROLE_IDS)))],
        guild=guild,
        add_roles=AsyncMock(),
    )
    monkeypatch.setattr("halloween.registration.get_member", AsyncMock(return_value=member))
    interaction = SimpleNamespace(
        response=SimpleNamespace(defer=AsyncMock()), followup=SimpleNamespace(send=AsyncMock())
    )
    await RegistrationView().children[0].callback(interaction)
    member.add_roles.assert_not_awaited()
    assert "Manage Roles" in interaction.followup.send.call_args.args[0]
