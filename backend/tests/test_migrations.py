from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config(db_path: Path) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    return config


def test_migrations_match_models(tmp_path):
    """Fails if someone changed models.py without adding a migration."""
    config = alembic_config(tmp_path / "test.db")
    command.upgrade(config, "head")
    command.check(config)


def test_migrations_downgrade_cleanly(tmp_path):
    config = alembic_config(tmp_path / "test.db")
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
