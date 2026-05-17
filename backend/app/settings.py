from functools import lru_cache
import os
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    app_db_path: Path = Path("backend/data/app_state.sqlite3")
    metrics_db_path: Path = Path("backend/data/metrics.sqlite3")
    demo_mode: bool = True
    jwt_secret: str = "dev-secret-change-me"
    jwt_issuer: str = "chartdex.local"
    jwt_audience: str = "chartdex.api"
    access_token_minutes: int = 8 * 60


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_db_path=Path(os.environ.get("CHARTDEX_APP_DB_PATH", "backend/data/app_state.sqlite3")),
        metrics_db_path=Path(
            os.environ.get("CHARTDEX_METRICS_DB_PATH", "backend/data/metrics.sqlite3")
        ),
        demo_mode=os.environ.get("CHARTDEX_DEMO_MODE", "true").lower() == "true",
        jwt_secret=os.environ.get("CHARTDEX_JWT_SECRET", "dev-secret-change-me"),
        jwt_issuer=os.environ.get("CHARTDEX_JWT_ISSUER", "chartdex.local"),
        jwt_audience=os.environ.get("CHARTDEX_JWT_AUDIENCE", "chartdex.api"),
        access_token_minutes=int(os.environ.get("CHARTDEX_ACCESS_TOKEN_MINUTES", str(8 * 60))),
    )
