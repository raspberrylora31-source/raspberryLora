"""Gateway identity and radio reconnect."""

from __future__ import annotations

from fastapi import APIRouter

from app.services.meshtastic_service import radio_service

router = APIRouter(prefix="/api/gateway", tags=["gateway"])


@router.get("")
def api_gateway() -> dict:
    status = radio_service.status_payload()
    status["radio_info"] = radio_service.radio_info()
    return status


@router.post("/reconnect")
def api_reconnect() -> dict:
    radio_service.reconnect_now()
    return {"ok": True, "radio_status": radio_service.connection_status()}
