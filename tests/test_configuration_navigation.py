from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.configuration import ChannelView, ConfigurationPanel, LanguagePanel, main_menu_embed
from halloween.models import Language


class PanelInteraction:
    def __init__(self, panel):
        self.guild_id = 1
        self.user = SimpleNamespace(id=123)
        self.message = SimpleNamespace(id=777, content=None, embed=main_menu_embed(), view=panel)
        self.events = []
        self.response = SimpleNamespace(
            defer=AsyncMock(),
            edit_message=AsyncMock(side_effect=self.edit_panel),
            send_message=AsyncMock(),
            send_modal=AsyncMock(),
        )
        self.followup = SimpleNamespace(send=AsyncMock())
        self.edit_original_response = AsyncMock(side_effect=self.edit_panel)

    async def edit_panel(self, **kwargs):
        self.events.append("edit")
        for key, value in kwargs.items():
            setattr(self.message, key, value)
        return self.message


async def open_setting(bot, language, setting):
    root = ConfigurationPanel(bot, 123)
    interaction = PanelInteraction(root)
    await root.show(interaction, language)
    panel = interaction.message.view
    assert isinstance(panel, LanguagePanel)
    if setting == "channel":
        await panel.channel.callback(interaction)
        assert isinstance(interaction.message.view, ChannelView)
        picker = interaction.message.view.children[0]
        picker._values = [SimpleNamespace(id=456)]
        submit = partial(picker.callback, interaction)
    else:
        await getattr(panel, "cd" if setting == "minutes" else "probability").callback(interaction)
        modal = interaction.response.send_modal.call_args.args[0]
        if setting == "minutes":
            modal.minimum._value, modal.maximum._value = "2", "5"
        else:
            modal.win._value, modal.lose._value = "70", "30"
        submit = partial(modal.on_submit, interaction)
    interaction.events.clear()
    interaction.response.edit_message.reset_mock()
    interaction.edit_original_response.reset_mock()
    return interaction, submit


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("setting", ["channel", "minutes", "probabilities"])
async def test_saved_setting_returns_same_ephemeral_panel_to_main_menu(
    monkeypatch, language, setting
):
    monkeypatch.setattr("cogs.configuration.panel_allowed", AsyncMock(return_value=True))
    repo = SimpleNamespace(
        **{f"set_{name}": AsyncMock() for name in ("channel", "minutes", "probabilities")}
    )
    bot = SimpleNamespace(repo=repo)
    interaction, submit = await open_setting(bot, language, setting)

    async def saved(*args):
        interaction.events.append("save")

    method = getattr(repo, f"set_{setting}")
    method.side_effect = saved
    await submit()
    assert interaction.events == ["save", "edit"]
    assert interaction.message.id == 777
    assert interaction.message.content is None
    assert interaction.message.embed.to_dict() == main_menu_embed().to_dict()
    menu = interaction.message.view
    assert isinstance(menu, ConfigurationPanel)
    assert menu.owner_id == 123
    assert [child.label for child in menu.children] == ["🇪🇸 Español", "🇧🇷 Português"]
    interaction.response.defer.assert_awaited_once_with()
    interaction.edit_original_response.assert_awaited_once()
    interaction.response.send_message.assert_not_awaited()
    assert interaction.followup.send.call_args.kwargs["ephemeral"]
    expected = {"channel": (456,), "minutes": (2, 5), "probabilities": (70, 30)}[setting]
    method.assert_awaited_once_with(1, language, *expected, 123)


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("setting", ["channel", "minutes", "probabilities"])
async def test_save_failure_does_not_reset_panel(monkeypatch, language, setting):
    monkeypatch.setattr("cogs.configuration.panel_allowed", AsyncMock(return_value=True))
    repo = SimpleNamespace(
        **{f"set_{name}": AsyncMock() for name in ("channel", "minutes", "probabilities")}
    )
    bot = SimpleNamespace(repo=repo)
    interaction, submit = await open_setting(bot, language, setting)
    before = interaction.message.view
    getattr(repo, f"set_{setting}").side_effect = OSError("database unavailable")
    with pytest.raises(OSError):
        await submit()
    assert interaction.message.view is before
    interaction.edit_original_response.assert_not_awaited()
    interaction.followup.send.assert_not_awaited()


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("setting", ["minutes", "probabilities"])
async def test_invalid_modal_keeps_language_panel(monkeypatch, language, setting):
    monkeypatch.setattr("cogs.configuration.panel_allowed", AsyncMock(return_value=True))
    repo = SimpleNamespace(set_minutes=AsyncMock(), set_probabilities=AsyncMock())
    interaction, submit = await open_setting(SimpleNamespace(repo=repo), language, setting)
    modal = interaction.response.send_modal.call_args.args[0]
    if setting == "minutes":
        modal.minimum._value = "9"
    else:
        modal.lose._value = "20"
    before = interaction.message.view
    await submit()
    getattr(repo, f"set_{setting}").assert_not_awaited()
    interaction.edit_original_response.assert_not_awaited()
    assert interaction.message.view is before
    assert interaction.response.send_message.call_args.kwargs["ephemeral"]
