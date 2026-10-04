import logging
import os
import re
import traceback
from urllib.parse import unquote, urlsplit


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
        return re.sub(r"postgres(?:ql)?://[^\s]+", "[REDACTED_DATABASE_URL]", text)

    def formatException(self, exc_info) -> str:
        # Do not dump source lines: a third-party traceback can contain a literal credential.
        frames = traceback.extract_tb(exc_info[2])
        stack = "\n".join(f"  {frame.filename}:{frame.lineno} in {frame.name}" for frame in frames)
        return f"Traceback:\n{stack}\n{exc_info[0].__name__}: {exc_info[1]}"


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(SecretFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=getattr(logging, level, logging.INFO), handlers=[handler], force=True)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
