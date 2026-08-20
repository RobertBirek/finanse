from pathlib import Path

from alembic.config import Config


def test_percent_encoded_database_url_is_escaped_for_alembic_config():
    database_url = "postgresql+asyncpg://user@127.0.0.1/db?passfile=%2Ftmp%2Fpgpass"
    config = Config()
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    assert config.get_main_option("sqlalchemy.url") == database_url
    env_source = (Path(__file__).parents[1] / "migrations" / "env.py").read_text()
    assert 'settings.DATABASE_URL.replace("%", "%%")' in env_source
