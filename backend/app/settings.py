from functools import lru_cache
import os
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    app_db_path: Path = Path("backend/data/app_state.sqlite3")
    metrics_db_path: Path = Path("data/chartdex_demo.sqlite")
    demo_mode: bool = True
    jwt_secret: str = "dev-secret-change-me"
    jwt_issuer: str = "chartdex.local"
    jwt_audience: str = "chartdex.api"
    access_token_minutes: int = 8 * 60
    openai_api_key: str | None = None
    github_token: str | None = None
    github_repository: str = "royceness/acme-outdoor-demo-store"


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
        openai_api_key=load_openai_api_key(),
        github_token=os.environ.get("CHARTDEX_GITHUB_TOKEN") or None,
        github_repository=os.environ.get(
            "CHARTDEX_GITHUB_REPOSITORY",
            "royceness/acme-outdoor-demo-store",
        ),
    )


def load_openai_api_key() -> str | None:
    from_env = os.environ.get("CHARTDEX_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if from_env:
        return from_env

    env_path = Path.home() / ".env"
    if not env_path.exists():
        return None

    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() in {"CHARTDEX_OPENAI_API_KEY", "OPENAI_API_KEY"}:
            return value.strip().strip('"').strip("'")
    return None
