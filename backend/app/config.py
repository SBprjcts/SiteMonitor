from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """App settings, read from environment variables or the repo-root `.env`.

    See the Configuration table in CLAUDE.md. Add new settings to `.env.example` too.
    """

    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    # Anchored to backend/, so every command uses the same DB whatever folder it runs from.
    database_url: str = f"sqlite+aiosqlite:///{(BACKEND_DIR / 'sitemonitor.db').as_posix()}"
    monitor_enabled: bool = True
    default_hot_interval_s: int = 15
    default_sweep_interval_s: int = 60
    domain_min_request_gap_s: float = 2
    alert_cooldown_s: int = 300
    session_secret: str
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
