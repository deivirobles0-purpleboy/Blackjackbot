import logging

import pytest

from config.settings import DoorImages, Settings, validate_image_url
from database.connection import connection_options
from halloween.models import Language, adjust_balance, validate_minutes
from utils.logger import SecretFormatter


@pytest.mark.parametrize(
    "minimum,maximum", [(0, 5), (-1, 5), (5, 4), (5, 0), (1.1, 4), (True, 5), (1, 2147483648)]
)
def test_invalid_minutes(minimum, maximum):
    with pytest.raises(ValueError):
        validate_minutes(minimum, maximum)


@pytest.mark.parametrize("minimum,maximum", [(1, 1), (15, 30), (30, 60)])
def test_valid_minutes(minimum, maximum):
    validate_minutes(minimum, maximum)


def test_balances_and_languages():
    assert adjust_balance(3, "remove", 10) == 0
    assert adjust_balance(3, "add", 5) == 8
    assert adjust_balance(3, "reset") == 0
    assert Language("ES") == Language.ES
    assert Language("BR") == Language.BR
    with pytest.raises(ValueError):
        Language("EN")
    with pytest.raises(ValueError):
        adjust_balance(3, "add", 0)


def test_settings_read_env_without_gifs(monkeypatch):
    monkeypatch.setattr("config.settings.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test?sslmode=require")
    monkeypatch.delenv("COMMAND_GUILD_ID", raising=False)
    for language in Language:
        for phase in ("CLOSED", "WAITING", "RESULT"):
            monkeypatch.delenv(f"{language}_DOOR_{phase}_GIF", raising=False)
    settings = Settings.from_env()
    assert settings.images[Language.ES] == DoorImages()
    assert "test-token" not in repr(settings)
    assert settings.database_url not in repr(settings)
    assert connection_options(settings)["ssl"] == "require"
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(ValueError, match="Missing required environment variable: DATABASE_URL"):
        Settings.from_env()


def test_reject_insecure_production_ssl(monkeypatch):
    monkeypatch.setattr("config.settings.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test?sslmode=disable")
    with pytest.raises(ValueError, match="sslmode"):
        Settings.from_env()


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/a.gif",
        "file:///a.gif",
        "not-a-url",
        "https://user:pass@example.com/a.gif",
    ],
)
def test_reject_invalid_images(url):
    with pytest.raises(ValueError):
        validate_image_url(url, "TEST_GIF")


def test_logs_redact_secrets(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "secret-token-test")
    monkeypatch.setenv("DATABASE_URL", "postgres://u:secret-password@host/db")
    record = logging.LogRecord(
        "test",
        logging.ERROR,
        __file__,
        1,
        "token=%s database=%s password=%s",
        ("secret-token-test", "postgres://u:secret-password@host/db", "secret-password"),
        None,
    )
    text = SecretFormatter().format(record)
    assert "secret-token-test" not in text
    assert "secret-password" not in text
