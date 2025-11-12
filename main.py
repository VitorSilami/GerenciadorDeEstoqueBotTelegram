import asyncio
import logging
import os
import threading

from app.bot import EosBot
from app.config import SettingsError, get_settings
from dashboard import app as flask_app


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

    # Permite desabilitar o bot no ambiente de dev/deploy
    if os.getenv("DISABLE_BOT", "0") == "1":
        logging.info("DISABLE_BOT=1 — Bot desativado. Apenas Flask será executado.")
        return

    bot = EosBot(settings)
    await bot.run()


if __name__ == "__main__":
    # Inicia Flask em thread separada para compartilhar o mesmo processo
    def run_flask():
        port = int(os.getenv("PORT", "5000"))
        flask_app.run(host="0.0.0.0", port=port, debug=False)

    t = threading.Thread(target=run_flask, daemon=False)
    t.start()
    # Executa o bot no loop principal; mantém Flask mesmo se o bot falhar
    try:
        asyncio.run(main())
    except Exception as exc:
        logging.error("Bot finalizou com erro: %s", exc)
        logging.info("Mantendo Flask ativo. Pressione Ctrl+C para encerrar.")
        t.join()
