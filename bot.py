from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from config.settings import Settings
from database.connection import Database
from database.repositories import Repository
from halloween.manager import DoorManager
from halloween.registration import RegistrationView
from halloween.scheduler import Scheduler
from halloween.views import DoorButton
from utils.errors import respond_error
from utils.logger import configure_logging
from utils.startup import log_gifs

log = logging.getLogger(__name__)


class HalloweenBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.settings = settings
        self.database = Database(settings)
        self.repo: Repository | None = None
        self.manager: DoorManager | None = None
        self.scheduler: Scheduler | None = None
        self.synced_command_count = 0
        self.status_requested = True
        self._discord_connected_once = False
        self._discord_offline = False
        self.tree.on_error = respond_error

    async def setup_hook(self) -> None:
        await self.database.open()
        self.repo = Repository(self.database.pool)
        self.manager = DoorManager(self)
        self.scheduler = Scheduler(self)
        self.add_view(RegistrationView())
        self.add_dynamic_items(DoorButton)
        log.info("✅ Botones persistentes: registro Halloween y puertas preparados")
        for extension in ("cogs.rankings", "cogs.admin", "cogs.registration", "cogs.configuration"):
            await self.load_extension(extension)
            log.debug("Cog cargado: %s", extension)
        log.info("✅ Módulos cargados: rankings, administración, registro y configuración")
        guild = (
            discord.Object(id=self.settings.command_guild_id)
            if self.settings.command_guild_id
            else None
        )
        if guild:
            self.tree.copy_global_to(guild=guild)
        for attempt in range(3):
            try:
                synced = await self.tree.sync(guild=guild)
                self.synced_command_count = len(synced)
                log.info(
                    "✅ Comandos Slash: %s sincronizados | Alcance: %s",
                    len(synced),
                    f"servidor {guild.id}" if guild else "global",
                )
                break
            except discord.HTTPException:
                log.exception("No se pudieron sincronizar comandos intento=%s", attempt + 1)
                if attempt == 2:
                    raise
                await asyncio.sleep(5 * (attempt + 1))
        log_gifs(self)
        self.scheduler.start()

    async def on_ready(self) -> None:
        if not self._discord_connected_once or self._discord_offline:
            log.info(
                "✅ Discord: %s conectado | ID: %s | Servidores: %s",
                self.user.name,
                self.user.id,
                len(self.guilds),
            )
            self._discord_connected_once = True
            self._discord_offline = False
            self.status_requested = True

    async def on_disconnect(self) -> None:
        if not self.is_closed() and self._discord_connected_once and not self._discord_offline:
            self._discord_offline = True
            log.warning("Discord: conexión interrumpida; reconexión automática en curso")

    async def on_resumed(self) -> None:
        self._discord_offline = False
        self.status_requested = True
        log.info("✅ Discord: conexión recuperada")

    async def on_guild_join(self, guild: discord.Guild) -> None:
        log.info("✅ Servidor añadido: %s | ID: %s", guild.name, guild.id)
        self.status_requested = True

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        log.warning("Bot retirado del servidor: %s | ID: %s", guild.name, guild.id)
        self.status_requested = True

    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        log.exception("Error aislado en evento %s", event_method)

    async def close(self) -> None:
        if self.scheduler:
            await self.scheduler.close()
        await super().close()
        await self.database.close()


async def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    log.info("Inicializando Blackjack Bot........")
    log.info("✅ Variables obligatorias: DISCORD_TOKEN y DATABASE_URL configuradas")
    async with HalloweenBot(settings) as bot:
        await bot.start(settings.token)


if __name__ == "__main__":
    configure_logging()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Apagado solicitado")
    except ValueError as error:
        log.error("Configuración inválida: %s", error)
        raise SystemExit(1) from None
    except Exception:
        log.exception("No se pudo iniciar el bot")
        raise SystemExit(1) from None
