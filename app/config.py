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
    db_sslmode: str
    database_url: Optional[str]
    groq_api_key: str

    def as_dsn_kwargs(self) -> dict[str, str]:
        return {
            "user": self.db_user,
            "password": self.db_password,
            "host": self.db_host,
            "dbname": self.db_name,
            "port": str(self.db_port),
            "sslmode": self.db_sslmode,
        }


class SettingsError(RuntimeError):
    """Raised when required environment variables are missing."""


def _get_env(name: str, *, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None or value.strip() == "":
        raise SettingsError(f"Variável de ambiente {name} não definida.")
    return value


def get_settings() -> Settings:
    # Accept both DB_PASS and DB_PASSWORD for convenience
    db_password_value = os.getenv("DB_PASS") or os.getenv("DB_PASSWORD") or ""
    return Settings(
        telegram_token=_get_env("TOKEN_TELEGRAM"),
        db_user=os.getenv("DB_USER", ""),
        db_password=db_password_value,
        db_host=os.getenv("DB_HOST", ""),
        db_name=os.getenv("DB_NAME", ""),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_sslmode=os.getenv("DB_SSLMODE", os.getenv("RENDER", "") and "require" or "disable"),
        database_url=os.getenv("DATABASE_URL"),
        groq_api_key=_get_env("GROQ_API_KEY"),
    )
