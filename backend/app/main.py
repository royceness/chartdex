from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.auth import AuthContext, require_auth
from app.database import (
    database_paths_exist,
    get_dashboard_detail,
    initialize_databases,
    list_codex_threads,
    list_dashboards,
    list_metric_points,
)
from app.routes.auth import router as auth_router
from app.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    initialize_databases(settings.app_db_path, settings.metrics_db_path, settings.demo_mode)
    yield


app = FastAPI(title="ChartDex API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5175",
        "http://localhost:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.get("/api/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "databases": dict(database_paths_exist(settings.app_db_path, settings.metrics_db_path)),
    }


@app.get("/api/dashboards")
def dashboards(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    settings = get_settings()
    org_dashboards = list_dashboards(
        settings.app_db_path,
        org_id=auth.org_id,
        space="org",
    )
    personal_dashboards = list_dashboards(
        settings.app_db_path,
        org_id=auth.org_id,
        space="personal",
        owner_user_id=auth.user_id,
    )
    return {
        "dashboards": [*org_dashboards, *personal_dashboards]
    }


@app.get("/api/dashboards/{dashboard_id}")
def dashboard_detail(dashboard_id: str, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    settings = get_settings()
    dashboard = get_dashboard_detail(
        settings.app_db_path,
        dashboard_id=dashboard_id,
        org_id=auth.org_id,
        user_id=auth.user_id,
    )
    if dashboard is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")
    return {"dashboard": dashboard}


@app.get("/api/codex/threads")
def codex_threads(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    return {"threads": list_codex_threads()}


@app.get("/api/metrics/{metric}")
def metric_points(metric: str, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    settings = get_settings()
    return {
        "points": list_metric_points(
            settings.app_db_path,
            org_id=auth.org_id,
            metric=metric,
        )
    }
