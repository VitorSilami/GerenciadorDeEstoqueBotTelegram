import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    telegram_token: str
    db_user: str
    db_password: str
    db_host: str
    db_name: str
    db_port: int
    groq_api_key: str

    def as_dsn_kwargs(self) -> dict[str, str]:
        return {
            "user": self.db_user,
            "password": self.db_password,
            "host": self.db_host,
            "dbname": self.db_name,
            "port": str(self.db_port),
        }


class SettingsError(RuntimeError):
    """Raised when required environment variables are missing."""


def _get_env(name: str, *, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None or value.strip() == "":
        raise SettingsError(f"Variável de ambiente {name} não definida.")
    return value


def get_settings() -> Settings:
    return Settings(
        telegram_token=_get_env("TOKEN_TELEGRAM"),
        db_user=_get_env("DB_USER"),
        db_password=_get_env("DB_PASS"),
        db_host=_get_env("DB_HOST"),
        db_name=_get_env("DB_NAME"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        groq_api_key=_get_env("GROQ_API_KEY"),
    )
