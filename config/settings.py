from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from dotenv import load_dotenv

from halloween.models import Language


@dataclass(frozen=True)
class DoorImages:
    closed: str = ""
    waiting: str = ""
    candy_win: str = ""
    candy_lose: str = ""
    timeout: str = ""


DEFAULT_DOOR_GIF_URL = "https://pub-a09b3609b6b34dfab5c7aa7742cd1a8a.r2.dev/Puerta%201.gif"
DEFAULT_CANDY_WIN_GIF_URL = "https://pub-a09b3609b6b34dfab5c7aa7742cd1a8a.r2.dev/DulcesGIF.gif"
DEFAULT_CANDY_LOSE_GIF_URL = "https://pub-a09b3609b6b34dfab5c7aa7742cd1a8a.r2.dev/RobaGIF.gif"
DEFAULT_DOOR_TIMEOUT_URL = "https://pub-a09b3609b6b34dfab5c7aa7742cd1a8a.r2.dev/Vencida.png"
DEFAULT_DOOR_IMAGES = {
    language: DoorImages(
        closed=DEFAULT_DOOR_GIF_URL,
        waiting=DEFAULT_DOOR_GIF_URL,
        candy_win=DEFAULT_CANDY_WIN_GIF_URL,
        candy_lose=DEFAULT_CANDY_LOSE_GIF_URL,
        timeout=DEFAULT_DOOR_TIMEOUT_URL,
    )
    for language in Language
}


def validate_image_url(value: str, name: str) -> str:
    value = value.strip()
    if value:
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.netloc or parts.username or parts.password:
            raise ValueError(f"{name} debe ser una URL HTTPS pública válida")
    return value


@dataclass(frozen=True)
class Settings:
    token: str = field(repr=False)
    database_url: str = field(repr=False)
    images: dict[Language, DoorImages]
    ca_file: str = ""
    ca_pem: str = field(default="", repr=False)
    log_level: str = "INFO"
    command_guild_id: int | None = None

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
        for name in ("DISCORD_TOKEN", "DATABASE_URL"):
            if not os.getenv(name, "").strip():
                raise ValueError(f"Missing required environment variable: {name}")
        url = os.environ["DATABASE_URL"].strip()
        parts = urlsplit(url)
        if parts.scheme not in {"postgres", "postgresql"} or not parts.hostname:
            raise ValueError("DATABASE_URL debe ser una URL PostgreSQL válida")
        sslmode = parse_qs(parts.query).get("sslmode", ["require"])[0]
        if sslmode not in {"require", "verify-ca", "verify-full"}:
            raise ValueError("DATABASE_URL debe utilizar sslmode=require, verify-ca o verify-full")
        images = {}
        for language in Language:
            values = {}
            for phase in ("closed", "waiting", "candy_win", "candy_lose", "timeout"):
                suffix = "TIMEOUT" if phase == "timeout" else f"{phase.upper()}_GIF"
                name = f"{language.value}_DOOR_{suffix}"
                value = os.getenv(name, "").strip()
                # Keep existing deployments working while RESULT is renamed to CANDY_WIN.
                if phase == "candy_win" and not value:
                    value = os.getenv(f"{language.value}_DOOR_RESULT_GIF", "").strip()
                value = value or getattr(DEFAULT_DOOR_IMAGES[language], phase)
                values[phase] = validate_image_url(value, name)
            images[language] = DoorImages(**values)
        guild = os.getenv("COMMAND_GUILD_ID", "").strip()
        return cls(
            token=os.environ["DISCORD_TOKEN"].strip(),
            database_url=url,
            images=images,
            ca_file=os.getenv("DATABASE_CA_FILE", "").strip(),
            ca_pem=os.getenv("DATABASE_CA_PEM", "").replace("\\n", "\n").strip(),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            command_guild_id=int(guild) if guild else None,
        )
