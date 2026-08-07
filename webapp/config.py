"""Configuration for the local BTA Rugby Dash application."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import URL


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_local_env(path: Path | None = None) -> None:
    """Load a simple local .env file without adding a runtime dependency."""
    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool_from_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    sql_server: str
    sql_database: str
    sql_driver: str
    trusted_connection: str
    app_host: str
    app_port: int
    app_debug: bool
    cache_ttl_seconds: int
    data_update_season: int = 2026
    data_update_timeout_seconds: int = 900
    data_update_run_scraper: bool = False
    data_update_run_predictions: bool = True
    sql_connection_string: str | None = None

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_local_env()
        return cls(
            sql_server=os.getenv("BTA_SQL_SERVER", "BIGTEDS"),
            sql_database=os.getenv("BTA_SQL_DATABASE", "RugbyAnalytics"),
            sql_driver=os.getenv("BTA_SQL_DRIVER", "ODBC Driver 17 for SQL Server"),
            trusted_connection=os.getenv("BTA_SQL_TRUSTED_CONNECTION", "yes"),
            app_host=os.getenv("BTA_APP_HOST", "127.0.0.1"),
            app_port=int(os.getenv("BTA_APP_PORT", "8050")),
            app_debug=_bool_from_env("BTA_APP_DEBUG", False),
            cache_ttl_seconds=int(os.getenv("BTA_CACHE_TTL_SECONDS", "300")),
            data_update_season=int(os.getenv("BTA_DATA_UPDATE_SEASON", "2026")),
            data_update_timeout_seconds=int(os.getenv("BTA_DATA_UPDATE_TIMEOUT_SECONDS", "900")),
            data_update_run_scraper=_bool_from_env("BTA_UPDATE_RUN_SCRAPER", False),
            data_update_run_predictions=_bool_from_env("BTA_UPDATE_RUN_PREDICTIONS", True),
            sql_connection_string=os.getenv("BTA_SQL_CONNECTION_STRING"),
        )

    def sqlalchemy_url(self) -> URL:
        if self.sql_connection_string:
            return URL.create("mssql+pyodbc", query={"odbc_connect": self.sql_connection_string})
        return URL.create(
            "mssql+pyodbc",
            host=self.sql_server,
            database=self.sql_database,
            query={
                "driver": self.sql_driver,
                "Trusted_Connection": self.trusted_connection,
                "Encrypt": "no",
                "TrustServerCertificate": "yes",
            },
        )
