"""Meshtastic PC Gateway FastAPI application."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import gateway as gateway_api
from app.api import messages as messages_api
from app.api import nodes as nodes_api
from app.api import settings as settings_api
from app.api import status as status_api
from app.config import settings
from app.database import init_db
from app.logging_setup import get_logger, setup_logging, tail_log
from app.services.meshtastic_service import radio_service
from app.services.mqtt_service import mqtt_service
from app.services.websocket_service import ws_manager

logger = get_logger()
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    init_db()
    if settings.host not in {"127.0.0.1", "localhost"}:
        logger.warning(
            "HOST is %s — the default is 127.0.0.1. Binding beyond localhost exposes the gateway.",
            settings.host,
        )
    logger.info(
        "Starting Meshtastic PC Gateway name=%s id=%s bind=%s:%s com=%s",
        settings.gateway_name,
        settings.gateway_id,
        settings.host,
        settings.port,
        settings.com_port,
    )
    ws_manager.set_loop(asyncio.get_running_loop())
    radio_service.start()
    mqtt_service.start()
    yield
    logger.info("Shutting down Meshtastic PC Gateway")
    mqtt_service.stop()
    radio_service.stop()


app = FastAPI(
    title="Meshtastic PC Gateway",
    description="Local Windows gateway: T-Beam USB serial → SQLite + FastAPI + WebSocket.",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(status_api.router)
app.include_router(nodes_api.router)
app.include_router(messages_api.router)
app.include_router(gateway_api.router)
app.include_router(settings_api.router)


def _page(request: Request, name: str, extra: dict | None = None) -> HTMLResponse:
    context = {
        "request": request,
        "gateway_name": settings.gateway_name,
        "active": name,
    }
    if extra:
        context.update(extra)
    return templates.TemplateResponse(f"{name}.html", context)


@app.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return _page(request, "dashboard")


@app.get("/map", response_class=HTMLResponse)
def map_page(request: Request):
    return _page(request, "map")


@app.get("/messages", response_class=HTMLResponse)
def messages_page(request: Request):
    return _page(request, "messages")


@app.get("/nodes", response_class=HTMLResponse)
def nodes_page(request: Request):
    return _page(request, "nodes")


@app.get("/gateway", response_class=HTMLResponse)
def gateway_page(request: Request):
    return _page(request, "gateway")


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return _page(request, "settings")


@app.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request):
    return _page(request, "logs")


@app.get("/api/logs")
def api_logs(lines: int = 200) -> dict:
    return {"lines": tail_log(lines)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        await websocket.send_json({"type": "radio_status", "data": radio_service.status_payload()})
        await websocket.send_json(
            {
                "type": "mqtt_status",
                "data": {
                    "enabled": settings.mqtt_enabled,
                    "connected": mqtt_service.is_connected(),
                },
            }
        )
        await websocket.send_json({"type": "gateway_status", "data": radio_service.status_payload()})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception:
        await ws_manager.disconnect(websocket)


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
