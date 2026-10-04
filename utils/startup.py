from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from config.constants import PARTICIPANT_ROLE_ID
from halloween.models import EventConfig, Language

if TYPE_CHECKING:
    from bot import HalloweenBot

log = logging.getLogger(__name__)
CHANNEL_PERMISSIONS = {
    "view_channel": "View Channels",
    "send_messages": "Send Messages",
    "embed_links": "Embed Links",
    "read_message_history": "Read Message History",
}


def log_gifs(bot: HalloweenBot) -> bool:
    counts = {
        language: sum(bool(getattr(images, phase)) for phase in ("closed", "waiting", "result"))
        for language, images in bot.settings.images.items()
    }
    if all(counts.get(language) == 3 for language in Language):
        log.info("✅ GIFs configurados: ES 3/3 | BR 3/3")
        return True
    log.warning(
        "GIFs incompletos: ES %s/3 | BR %s/3",
        counts.get(Language.ES, 0),
        counts.get(Language.BR, 0),
    )
    return False


def _guild_issues(guild) -> list[str]:
    member = guild.me
    role = guild.get_role(PARTICIPANT_ROLE_ID)
    if member is None:
        return ["No se pudieron verificar los permisos del bot"]
    if role is None:
        return [f"No existe el rol participante {PARTICIPANT_ROLE_ID}"]
    issues = []
    if not member.guild_permissions.manage_roles:
        issues.append("Falta Manage Roles")
    if role.managed or role.is_default() or member.top_role <= role:
        issues.append("El rol del bot debe estar por encima de un rol participante asignable")
    return issues


def _config_status(guild, cfg: EventConfig | None, language: Language) -> list[str]:
    if cfg is None or not cfg.complete:
        return [f"{language}: Canal y CD pendientes; configura /config_doces"]
    channel = guild.get_channel(cfg.channel_id)
    state = "Activo" if cfg.enabled else "Inactivo"
    next_drop = (
        cfg.next_drop_at.strftime("%Y-%m-%d %H:%M:%S UTC") if cfg.next_drop_at else "no programada"
    )
    log.info(
        "🎃 %s | %s: %s | Canal: #%s | CD: %s–%s min | Próxima: %s",
        guild.name,
        language,
        state,
        channel.name if channel else cfg.channel_id,
        cfg.min_minutes,
        cfg.max_minutes,
        next_drop,
    )
    if channel is None:
        return [f"{language}: canal configurado no encontrado"]
    if guild.me is None:
        return [f"{language}: no se pudieron comprobar permisos del canal"]
    permissions = channel.permissions_for(guild.me)
    missing = [
        label for name, label in CHANNEL_PERMISSIONS.items() if not getattr(permissions, name)
    ]
    return [f"{language}: faltan permisos de canal ({', '.join(missing)})"] if missing else []


async def log_ready_status(bot: HalloweenBot) -> None:
    issues = []
    if not bot.is_ready():
        log.warning("Blackjack todavía espera la conexión a Discord")
        return
    if not bot.manager.leader.is_set():
        log.warning("Blackjack conectado a Discord; scheduler todavía no disponible")
        return
    if bot.synced_command_count == 0:
        issues.append("No hay comandos sincronizados")
    if any(
        not getattr(bot.settings.images[language], phase)
        for language in Language
        for phase in ("closed", "waiting", "result")
    ):
        issues.append("Faltan recursos gráficos")
    guilds = list(bot.guilds)
    configs = await bot.repo.guild_configs([guild.id for guild in guilds]) if guilds else []
    by_guild = {(cfg.guild_id, cfg.language): cfg for cfg in configs}
    if not guilds:
        issues.append(
            "El bot no está instalado en ningún servidor; invítalo con bot y applications.commands"
        )
    for guild in guilds:
        guild_issues = _guild_issues(guild)
        if not guild_issues:
            log.info("✅ %s: Manage Roles y jerarquía del rol Halloween verificados", guild.name)
        for language in Language:
            guild_issues.extend(_config_status(guild, by_guild.get((guild.id, language)), language))
        for issue in guild_issues:
            issues.append(f"{guild.name}: {issue}")
    if issues:
        for issue in issues:
            log.warning("Pendiente: %s", issue)
        log.warning(
            "Blackjack Conectado - configuración pendiente | Comprobaciones por revisar: %s",
            len(issues),
        )
    else:
        # This describes only the checks above, not a guarantee about all future operations.
        log.info("✅ Blackjack Conectado - 100% del inicio verificado")
