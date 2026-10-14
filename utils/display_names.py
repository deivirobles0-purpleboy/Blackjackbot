from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping

import discord

from halloween.models import Language


def display_name_label(language: Language, user_id: int, names: Mapping[int, str]) -> str:
    unknown = "Usuario desconocido" if language == Language.ES else "Usuário desconhecido"
    name = " ".join((names.get(user_id) or "").splitlines()).strip() or unknown
    return discord.utils.escape_markdown(name).replace("@", "@\u200b")


async def resolve_display_names(
    bot, guild, user_ids: Iterable[int], *, member=None
) -> dict[int, str]:
    limit = asyncio.Semaphore(5)

    async def resolve(user_id: int) -> tuple[int, str]:
        async with limit:
            cached = (
                member if member is not None and member.id == user_id else guild.get_member(user_id)
            )
            if cached is not None:
                return user_id, cached.nick or cached.display_name
            user = bot.get_user(user_id)
            fallback = user.display_name if user is not None else ""
            try:
                # Names are cosmetic: an unavailable API must not hold up results.
                async with asyncio.timeout(3):
                    try:
                        fetched = await guild.fetch_member(user_id)
                    except (discord.HTTPException, OSError, TimeoutError):
                        fetched = None
                    if fetched is not None:
                        return user_id, fetched.nick or fetched.display_name
                    if user is None:
                        user = await bot.fetch_user(user_id)
                    return user_id, user.display_name if user is not None else fallback
            except (discord.HTTPException, OSError, TimeoutError):
                return user_id, fallback

    return dict(await asyncio.gather(*(resolve(user_id) for user_id in dict.fromkeys(user_ids))))
