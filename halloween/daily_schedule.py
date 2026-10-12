from __future__ import annotations

import re
from datetime import datetime, time, timedelta

EVENT_TIMEZONE = "America/Sao_Paulo"


def parse_daily_time(value: str) -> time:
    value = value.strip()
    if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
        raise ValueError("Use HH:MM no formato de 24 horas, por exemplo 09:00 ou 22:00.")
    return time(int(value[:2]), int(value[3:]))


def validate_daily_window(start: time | None, end: time | None) -> None:
    if start is None and end is None:
        return
    if any(
        not isinstance(value, time) or value.tzinfo is not None or value.second or value.microsecond
        for value in (start, end)
    ):
        raise ValueError("Informe as duas horas no formato HH:MM.")
    if start == end:
        raise ValueError("O início e o fim devem ser diferentes.")


def window_is_open(local_now: datetime, start: time | None, end: time | None) -> bool:
    if start is None and end is None:
        return True  # Existing configurations keep their original continuous operation.
    current = local_now.time()
    if start < end:
        return start <= current < end
    return current >= start or current < end


def next_allowed_time(local_now: datetime, start: time | None, end: time | None) -> datetime:
    if window_is_open(local_now, start, end):
        return local_now
    opening = datetime.combine(local_now.date(), start)
    if opening <= local_now:
        opening += timedelta(days=1)
    return opening


def next_drop_time(
    local_now: datetime, delay_minutes: int, start: time | None, end: time | None
) -> datetime:
    base = next_allowed_time(local_now, start, end)
    candidate = base + timedelta(minutes=delay_minutes)
    # A cooldown that crosses closing moves to the next opening, without a catch-up burst.
    return next_allowed_time(candidate, start, end)
