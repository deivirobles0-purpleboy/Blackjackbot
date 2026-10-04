from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping
from uuid import UUID


class Language(StrEnum):
    ES = "ES"
    BR = "BR"


class DropStatus(StrEnum):
    PUBLISHING = "publishing"
    OPEN = "open"
    PROCESSING = "processing"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class ClaimStatus(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    CLOSED = "closed"
    UNREGISTERED = "unregistered"


@dataclass(frozen=True)
class EventConfig:
    guild_id: int
    language: Language
    channel_id: int | None
    min_minutes: int | None
    max_minutes: int | None
    enabled: bool
    next_drop_at: datetime | None
    last_drop_at: datetime | None
    updated_at: datetime
    win_percent: int = 100

    @property
    def lose_percent(self) -> int:
        return 100 - self.win_percent

    @classmethod
    def from_record(cls, row: Mapping[str, Any]) -> EventConfig:
        return cls(**{**dict(row), "language": Language(row["language"])})

    @property
    def complete(self) -> bool:
        return bool(
            self.channel_id
            and self.min_minutes
            and self.max_minutes
            and 0 < self.min_minutes <= self.max_minutes
        )


@dataclass(frozen=True)
class DoorDrop:
    id: UUID
    guild_id: int
    language: Language
    channel_id: int
    message_id: int | None
    status: DropStatus
    is_test: bool
    rewards_enabled: bool
    created_at: datetime
    processing_at: datetime | None
    finished_at: datetime | None
    candy_win: bool = True

    @classmethod
    def from_record(cls, row: Mapping[str, Any]) -> DoorDrop:
        return cls(
            **{
                **dict(row),
                "language": Language(row["language"]),
                "status": DropStatus(row["status"]),
            }
        )


@dataclass(frozen=True)
class ClaimResult:
    status: ClaimStatus
    candies: int = 0
    count: int = 0


def validate_minutes(minimum: int, maximum: int) -> None:
    if isinstance(minimum, bool) or isinstance(maximum, bool):
        raise ValueError("Los minutos deben ser números enteros")
    if not isinstance(minimum, int) or not isinstance(maximum, int):
        raise ValueError("Los minutos deben ser números enteros")
    if not 0 < minimum <= maximum <= 2_147_483_647:
        raise ValueError("Mínimo y máximo deben ser positivos y máximo >= mínimo")


def validate_probabilities(win: int, lose: int) -> None:
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (win, lose)):
        raise ValueError("Los porcentajes deben ser enteros")
    if not (0 <= win <= 100 and 0 <= lose <= 100 and win + lose == 100):
        raise ValueError("Los porcentajes deben estar entre 0 y 100 y sumar 100")


def adjust_balance(current: int, action: str, amount: int = 0) -> int:
    if action == "reset":
        return 0
    if amount <= 0 or action not in {"add", "remove"}:
        raise ValueError("La cantidad debe ser positiva y la acción válida")
    return current + amount if action == "add" else max(0, current - amount)
