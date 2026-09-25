"""Dashboard / radio status API."""

from __future__ import annotations

from fastapi import APIRouter

from app.services.meshtastic_service import radio_service

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status")
def get_status() -> dict:
    return radio_service.status_payload()


@router.get("/ports")
def get_ports() -> dict:
    return {"ports": radio_service.list_ports()}
