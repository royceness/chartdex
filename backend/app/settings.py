from functools import lru_cache
import os
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    app_db_path: Path = Path("backend/data/app_state.sqlite3")
    metrics_db_path: Path = Path("backend/data/metrics.sqlite3")


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_db_path=Path(os.environ.get("CHARTDEX_APP_DB_PATH", "backend/data/app_state.sqlite3")),
        metrics_db_path=Path(
            os.environ.get("CHARTDEX_METRICS_DB_PATH", "backend/data/metrics.sqlite3")
        ),
    )
