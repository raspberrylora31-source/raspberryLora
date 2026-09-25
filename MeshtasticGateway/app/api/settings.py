"""Gateway settings. MQTT password is write-only and never returned."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.logging_setup import get_logger
from app.schemas import SettingsResponse, SettingsUpdate
from app.services.meshtastic_service import radio_service
from app.services.mqtt_service import mqtt_service

router = APIRouter(prefix="/api/settings", tags=["settings"])
logger = get_logger()


@router.get("", response_model=SettingsResponse)
def api_get_settings() -> SettingsResponse:
    return SettingsResponse(**settings.public_dict())


@router.put("", response_model=SettingsResponse)
def api_put_settings(body: SettingsUpdate) -> SettingsResponse:
    updates = body.model_dump(exclude_unset=True)
    if "mqtt_password" in updates:
        # Keep existing password when the field is omitted or blank.
        if not updates["mqtt_password"]:
            updates.pop("mqtt_password")
    previous_port = settings.com_port
    mqtt_changed = any(key.startswith("mqtt_") for key in updates)
    try:
        settings.persist(updates)
    except Exception as exc:
        logger.exception("Failed to persist settings")
        raise HTTPException(status_code=500, detail="Could not save settings") from exc

    if "com_port" in updates and updates["com_port"] != previous_port:
        logger.info("COM port setting updated")
        radio_service.select_port(settings.com_port)
    if mqtt_changed:
        mqtt_service.restart()
    return SettingsResponse(**settings.public_dict())
