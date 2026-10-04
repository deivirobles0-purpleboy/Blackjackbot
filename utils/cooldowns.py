import time
from collections.abc import Callable

from config.constants import RANKING_COOLDOWN_SECONDS


class Cooldowns:
    def __init__(
        self, seconds: float = RANKING_COOLDOWN_SECONDS, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.seconds = seconds
        self.clock = clock
        self._expires: dict[tuple[int, int, str], float] = {}

    def take(self, guild_id: int, user_id: int, command: str) -> float:
        now = self.clock()
        key = (guild_id, user_id, command)
        remaining = self._expires.get(key, 0) - now
        if remaining > 0:
            return remaining
        if len(self._expires) > 4096:
            self._expires = {k: expiry for k, expiry in self._expires.items() if expiry > now}
        self._expires[key] = now + self.seconds
        return 0

    def release(self, guild_id: int, user_id: int, command: str) -> None:
        self._expires.pop((guild_id, user_id, command), None)
