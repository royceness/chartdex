from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import (
    database_paths_exist,
    initialize_databases,
    list_dashboards,
    list_metric_points,
)
from app.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    initialize_databases(settings.app_db_path, settings.metrics_db_path)
    yield


app = FastAPI(title="ChartDex API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "databases": dict(database_paths_exist(settings.app_db_path, settings.metrics_db_path)),
    }


@app.get("/api/dashboards")
def dashboards() -> dict[str, Any]:
    settings = get_settings()
    return {"dashboards": list_dashboards(settings.app_db_path)}


@app.get("/api/metrics/{metric}")
def metric_points(metric: str) -> dict[str, Any]:
    settings = get_settings()
    return {"points": list_metric_points(settings.metrics_db_path, metric)}
