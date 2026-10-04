from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence

import discord

from config.settings import Settings
from halloween.models import DoorDrop, EventConfig, Language
from halloween.texts import TEXTS


def door_embed(
    drop: DoorDrop, phase: str, settings: Settings, winners: Sequence[Mapping] = ()
) -> discord.Embed:
    text = TEXTS[drop.language]
    image_phase = ("candy_win" if drop.candy_win else "candy_lose") if phase == "result" else phase
    description = getattr(text, image_phase)
    title = text.lose_title if phase == "result" and not drop.candy_win else text.title
    if phase == "result":
        description += "\n\n" + "\n".join(
            (
                f"🎃 <@{winner['user_id']}>: {winner['candies']} {text.candy}"
                if drop.candy_win
                else f"<@{winner['user_id']}>: {winner['candies']}"
            )
            for winner in winners
        )
    embed = discord.Embed(title=title, description=description, color=0xF28C28)
    embed.set_footer(text=text.footer)
    image = getattr(settings.images[drop.language], image_phase)
    if image:
        embed.set_image(url=image)
    if drop.is_test:
        embed.add_field(
            name="Prueba / Teste",
            value="Recompensas reales / reais"
            if drop.rewards_enabled
            else "Simulación / Simulação — no modifica el ranking",
            inline=False,
        )
    return embed


def ranking_embed(language: Language, rows: Sequence[Mapping]) -> discord.Embed:
    text = TEXTS[language]
    description = (
        "\n".join(
            f"**{index}.** <@{row['user_id']}> — **{row['candies']} {text.candy}**"
            for index, row in enumerate(rows[:15], start=1)
        )
        or text.empty_ranking
    )
    return discord.Embed(
        title="🎃 Ranking Evento de Halloween! 🎃", description=description, color=0xF28C28
    )


def configuration_embed(language: Language) -> discord.Embed:
    text = TEXTS[language]
    return discord.Embed(
        title=text.settings_title, description=text.settings_description, color=0xF28C28
    )


def state_embed(cfg: EventConfig) -> discord.Embed:
    es = cfg.language == Language.ES
    now = datetime.now(timezone.utc)
    embed = discord.Embed(
        title=f"Estado — {'Dulce o Truco' if es else 'Doces ou Travessuras'}", color=0xF28C28
    )
    labels = (
        (
            "Estado del sistema",
            "Canal configurado",
            "CD mínimo de puertas",
            "CD máximo de puertas",
            "Próxima aparición",
            "Última Puerta",
        )
        if es
        else (
            "Estado do sistema",
            "Canal configurado",
            "CD mínimo das portas",
            "CD máximo das portas",
            "Próxima aparição",
            "Última Porta",
        )
    )
    unknown = "No configurado" if es else "Não configurado"
    active = "🟢 Activo" if es else "🟢 Ativo"
    inactive = "🔴 Inactivo" if es else "🔴 Inativo"
    if cfg.next_drop_at:
        seconds = max(0, round((cfg.next_drop_at - now).total_seconds()))
        next_text = (
            f"≈ {seconds // 60} min {seconds % 60} s (<t:{int(cfg.next_drop_at.timestamp())}:R>)"
        )
    else:
        next_text = "No programada" if es else "Não programada"
    if cfg.last_drop_at:
        minutes = max(0, int((now - cfg.last_drop_at).total_seconds() // 60))
        last_text = f"Hace {minutes} minutos" if es else f"Faz {minutes} minutos"
    else:
        last_text = "Sin registros" if es else "Sem registros"
    values = (
        active if cfg.enabled else inactive,
        f"<#{cfg.channel_id}>" if cfg.channel_id else unknown,
        f"{cfg.min_minutes} minutos" if cfg.min_minutes else unknown,
        f"{cfg.max_minutes} minutos" if cfg.max_minutes else unknown,
        next_text,
        last_text,
    )
    for label, value in zip(labels, values):
        embed.add_field(name=label, value=value, inline=False)
    embed.add_field(
        name=TEXTS[cfg.language].probability_button,
        value=(
            f"Ganar: {cfg.win_percent}% | Perder: {cfg.lose_percent}%"
            if es
            else f"Ganhar: {cfg.win_percent}% | Perder: {cfg.lose_percent}%"
        ),
        inline=False,
    )
    if not cfg.complete:
        embed.add_field(
            name="Configuración / Configuração",
            value="Configura Canal y CD / Configure Canal e CD",
            inline=False,
        )
    return embed
