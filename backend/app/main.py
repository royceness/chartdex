from contextlib import asynccontextmanager
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.auth import AuthContext, require_auth
from app.codex_service import codex_execution_provider, validate_codex_context
from app.database import (
    CodexThreadBusyError,
    append_codex_user_turn,
    create_codex_thread,
    database_paths_exist,
    get_codex_thread,
    get_dashboard_detail,
    initialize_databases,
    list_codex_threads,
    list_dashboards,
    list_metric_points,
    reset_demo_state,
)
from app.routes.auth import router as auth_router
from app.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    initialize_databases(settings.app_db_path, settings.metrics_db_path, settings.demo_mode)
    try:
        yield
    finally:
        await codex_execution_provider.close()


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

OPENAI_REALTIME_CALLS_URL = "https://api.openai.com/v1/realtime/calls"


class CodexThreadContextRequest(BaseModel):
    dashboard_id: str | None = None
    panel_id: str | None = None
    metric_key: str | None = None
    range_start: str | None = None
    range_end: str | None = None


class CreateCodexThreadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    utterance: str = Field(min_length=1, max_length=4000)
    context: CodexThreadContextRequest | None = None


class AppendCodexTurnRequest(BaseModel):
    utterance: str = Field(min_length=1, max_length=4000)


@app.get("/api/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "databases": dict(database_paths_exist(settings.app_db_path, settings.metrics_db_path)),
    }


@app.post("/api/demo/reset")
def reset_demo(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    settings = get_settings()
    return {
        "reset": reset_demo_state(
            settings.app_db_path,
            org_id=auth.org_id,
            user_id=auth.user_id,
        )
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
    settings = get_settings()
    return {
        "threads": list_codex_threads(
            settings.app_db_path,
            org_id=auth.org_id,
            user_id=auth.user_id,
        )
    }


@app.post("/api/realtime/session")
async def realtime_session(
    request: Request,
    auth: AuthContext = Depends(require_auth),
) -> Response:
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OpenAI API key is not configured",
        )

    content_type = request.headers.get("content-type")
    if not content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content-Type header is required",
        )

    upstream_request = UrlRequest(
        OPENAI_REALTIME_CALLS_URL,
        data=await request.body(),
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": content_type,
        },
    )
    try:
        with urlopen(upstream_request, timeout=30) as upstream_response:
            body = upstream_response.read()
            response_content_type = upstream_response.headers.get("content-type", "application/sdp")
            return Response(
                content=body,
                media_type=response_content_type,
                status_code=upstream_response.status,
            )
    except HTTPError as exc:
        body = exc.read()
        response_content_type = exc.headers.get("content-type", "text/plain")
        return Response(
            content=body,
            media_type=response_content_type,
            status_code=exc.code,
        )
    except URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to reach OpenAI Realtime API: {exc.reason}",
        ) from exc


@app.post("/api/codex/threads", status_code=status.HTTP_201_CREATED)
def create_codex_thread_route(
    request: CreateCodexThreadRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    settings = get_settings()
    context = validate_codex_context(
        settings.app_db_path,
        org_id=auth.org_id,
        user_id=auth.user_id,
        context=request.context.model_dump() if request.context else None,
    )
    title = require_non_empty(request.title, "title")
    utterance = require_non_empty(request.utterance, "utterance")
    thread = create_codex_thread(
        settings.app_db_path,
        org_id=auth.org_id,
        user_id=auth.user_id,
        title=title,
        utterance=utterance,
        context=context,
    )
    background_tasks.add_task(
        codex_execution_provider.execute_thread_turn,
        app_db_path=settings.app_db_path,
        thread_id=str(thread["id"]),
        org_id=auth.org_id,
        user_id=auth.user_id,
    )
    return {"thread": thread}


@app.get("/api/codex/threads/{thread_id}")
def codex_thread_detail(thread_id: str, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    settings = get_settings()
    thread = get_codex_thread(
        settings.app_db_path,
        thread_id=thread_id,
        org_id=auth.org_id,
        user_id=auth.user_id,
    )
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Codex thread not found")
    return {"thread": thread}


@app.post("/api/codex/threads/{thread_id}/turns")
def append_codex_thread_turn(
    thread_id: str,
    request: AppendCodexTurnRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    settings = get_settings()
    utterance = require_non_empty(request.utterance, "utterance")
    existing_thread = get_codex_thread(
        settings.app_db_path,
        thread_id=thread_id,
        org_id=auth.org_id,
        user_id=auth.user_id,
    )
    if existing_thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Codex thread not found")
    if existing_thread["status"] in {"queued", "running"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Codex thread is still running",
        )
    try:
        thread = append_codex_user_turn(
            settings.app_db_path,
            thread_id=thread_id,
            org_id=auth.org_id,
            user_id=auth.user_id,
            utterance=utterance,
        )
    except CodexThreadBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    background_tasks.add_task(
        codex_execution_provider.execute_thread_turn,
        app_db_path=settings.app_db_path,
        thread_id=thread_id,
        org_id=auth.org_id,
        user_id=auth.user_id,
    )
    return {"thread": thread}


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


def require_non_empty(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must not be blank",
        )
    return stripped
