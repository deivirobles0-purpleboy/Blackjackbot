import logging
import os
import re
import traceback
from urllib.parse import unquote, urlsplit


class DiscordNoiseFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "discord.client" and record.levelno < logging.ERROR:
            message = record.getMessage()
            if any(
                fragment in message
                for fragment in (
                    "PyNaCl is not installed",
                    "davey is not installed",
                )
            ):
                return False
        return True


class SecretFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        secrets = [os.getenv("DISCORD_TOKEN", ""), os.getenv("DATABASE_URL", "")]
        try:
            password = urlsplit(os.getenv("DATABASE_URL", "")).password
            if password:
                secrets.extend([password, unquote(password)])
        except ValueError:
            pass
        for secret in sorted(filter(None, secrets), key=len, reverse=True):
            text = text.replace(secret, "[REDACTED]")
        text = re.sub(r"postgres(?:ql)?://[^\s]+", "[REDACTED_DATABASE_URL]", text)
        if record.levelno >= logging.ERROR and not text.startswith("❌"):
            text = f"❌ {text}"
        elif record.levelno >= logging.WARNING and not text.startswith("⚠️"):
            text = f"⚠️ {text}"
        return text

    def formatException(self, exc_info) -> str:
        # Do not dump source lines: a third-party traceback can contain a literal credential.
        frames = traceback.extract_tb(exc_info[2])
        stack = "\n".join(f"  {frame.filename}:{frame.lineno} in {frame.name}" for frame in frames)
        return f"Traceback:\n{stack}\n{exc_info[0].__name__}: {exc_info[1]}"


def configure_logging(level: str = "INFO") -> None:
    debug = level.upper() == "DEBUG"
    handler = logging.StreamHandler()
    handler.addFilter(DiscordNoiseFilter())
    handler.setFormatter(
        SecretFormatter(
            "%(asctime)s [%(levelname)s] %(name)s | %(message)s" if debug else "%(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logging.basicConfig(level=getattr(logging, level, logging.INFO), handlers=[handler], force=True)
    logging.getLogger("discord").setLevel(logging.DEBUG if debug else logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
