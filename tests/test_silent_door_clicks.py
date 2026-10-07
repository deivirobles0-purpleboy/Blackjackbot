from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from halloween.models import ClaimResult, ClaimStatus, Language
from halloween.views import DoorView
from tests.test_flow import FakeChannel, manager


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("status", [ClaimStatus.CLOSED, ClaimStatus.EXPIRED, ClaimStatus.DUPLICATE])
async def test_inactive_and_repeated_clicks_do_not_send_private_messages(
    monkeypatch, language, status
):
    repo = SimpleNamespace(claim=AsyncMock(return_value=ClaimResult(status)))
    mgr = manager(repo, FakeChannel())
    member = SimpleNamespace(id=123, guild=SimpleNamespace(id=1), roles=[])
    monkeypatch.setattr("halloween.manager.get_member", AsyncMock(return_value=member))
    interaction = SimpleNamespace(
        client=SimpleNamespace(manager=mgr),
        message=SimpleNamespace(id=100),
        channel_id=2,
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    await DoorView(language, uuid4()).children[0].callback(interaction)
    interaction.response.defer.assert_awaited_once_with()
    interaction.response.send_message.assert_not_awaited()
    interaction.followup.send.assert_not_awaited()


async def test_door_reconnecting_failure_is_silent_and_logged(monkeypatch, caplog):
    mgr = manager(SimpleNamespace(), FakeChannel())
    mgr.leader.clear()
    member = SimpleNamespace(id=123, guild=SimpleNamespace(id=1), roles=[])
    monkeypatch.setattr("halloween.manager.get_member", AsyncMock(return_value=member))
    interaction = SimpleNamespace(
        client=SimpleNamespace(manager=mgr),
        message=SimpleNamespace(id=100),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    await DoorView(Language.ES, uuid4()).children[0].callback(interaction)
    interaction.response.defer.assert_awaited_once_with()
    interaction.followup.send.assert_not_awaited()
    assert "Error procesando clic de puerta" in caplog.text
