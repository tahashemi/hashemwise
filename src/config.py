"""Hashemwise - runtime configuration.

Everything is read from the environment (or a local `.env` when running outside
Docker). Nothing here has a default that could quietly produce a working-looking
but wrong deployment: `BOT_TOKEN` and `SUPER_ADMIN_ID` are required, and startup
fails loudly if either is missing.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(..., alias="BOT_TOKEN")

    # The single account allowed to authorize groups and to view or modify
    # history, in every group. See the plan's permission decision.
    super_admin_id: int = Field(..., alias="SUPER_ADMIN_ID")

    # Inside the container this is the bind-mounted volume; the same path works
    # relative to the repo root when running from a venv.
    db_path: Path = Field(default=Path("data/ledger.db"), alias="DB_PATH")

    # api.telegram.org is not reachable from every network. Empty means direct.
    # Accepts http://, socks5://, or an authenticated http://user:pass@host:port.
    telegram_proxy: str = Field(default="", alias="TELEGRAM_PROXY")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("bot_token")
    @classmethod
    def _token_shape(cls, v: str) -> str:
        # Catches the common mistakes (pasted placeholder, quotes left on,
        # whole `BOT_TOKEN=...` line pasted) at startup instead of as an
        # opaque 401 from Telegram several seconds later.
        v = v.strip().strip("'\"")
        if ":" not in v or not v.split(":", 1)[0].isdigit():
            raise ValueError("BOT_TOKEN does not look like a Telegram token (<digits>:<secret>)")
        return v

    @field_validator("super_admin_id")
    @classmethod
    def _admin_is_a_user(cls, v: int) -> int:
        # Telegram user ids are positive; negative ids are chats. Getting this
        # backwards would lock every admin command out silently.
        if v <= 0:
            raise ValueError("SUPER_ADMIN_ID must be a positive Telegram user id, not a chat id")
        return v

    @field_validator("log_level")
    @classmethod
    def _known_level(cls, v: str) -> str:
        level = v.strip().upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"unknown LOG_LEVEL: {v!r}")
        return level


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once per process."""
    return Settings()  # type: ignore[call-arg]  # values come from the environment
