import asyncio
import logging

from app.bot import EosBot
from app.config import SettingsError, get_settings


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


async def main() -> None:
    try:
        settings = get_settings()
    except SettingsError as exc:
        logging.error("Configuração inválida: %s", exc)
        return

    bot = EosBot(settings)
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
