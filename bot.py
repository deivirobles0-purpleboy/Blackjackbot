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
        self.tree.on_error = respond_error

    async def setup_hook(self) -> None:
        await self.database.open()
        self.repo = Repository(self.database.pool)
        self.manager = DoorManager(self)
        self.scheduler = Scheduler(self)
        self.add_view(RegistrationView())
        self.add_dynamic_items(DoorButton)
        for extension in ("cogs.rankings", "cogs.admin", "cogs.registration", "cogs.configuration"):
            await self.load_extension(extension)
            log.info("Cog cargado: %s", extension)
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
                log.info("Comandos registrados: %s", len(synced))
                break
            except discord.HTTPException:
                log.exception("No se pudieron sincronizar comandos intento=%s", attempt + 1)
                if attempt == 2:
                    raise
                await asyncio.sleep(5 * (attempt + 1))
        for language, images in self.settings.images.items():
            missing = [
                phase for phase in ("closed", "waiting", "result") if not getattr(images, phase)
            ]
            if missing:
                log.warning(
                    "GIFs pendientes language=%s phases=%s; se usan embeds sin imagen",
                    language,
                    missing,
                )
        self.scheduler.start()

    async def on_ready(self) -> None:
        log.info("Bot conectado id=%s; servidores=%s", self.user.id, len(self.guilds))

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
    log.info("Iniciando Evento Halloween ES/BR")
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
