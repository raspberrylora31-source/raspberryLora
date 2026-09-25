"""Packet parsing and message persistence.

Uses real Meshtastic packet dictionaries produced by SerialInterface /
MeshInterface pubsub (decoded.text, decoded.position, decoded.user).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.logging_setup import get_logger
from app.models import Message, utcnow
from app.services.node_service import has_valid_gps, upsert_node

logger = get_logger()


def json_safe(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def packet_to_json(packet: dict[str, Any]) -> str:
    return json.dumps(json_safe(packet), default=str)


def _first(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def format_node_id(node_num: Any = None, node_id: Any = None) -> Optional[str]:
    if node_id:
        return str(node_id)
    if node_num in (None, ""):
        return None
    try:
        num = int(node_num)
    except (TypeError, ValueError):
        return str(node_num)
    if num in (0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
        return "^all"
    return f"!{num & 0xFFFFFFFF:08x}"


def extract_position(payload: dict[str, Any]) -> dict[str, Any]:
    """Pull real GPS fields only. Missing values stay None."""
    lat = _first(payload, "latitude", "lat")
    lon = _first(payload, "longitude", "lon", "lng")
    if lat is None and "latitudeI" in payload:
        try:
            lat = float(payload["latitudeI"]) * 1e-7
        except (TypeError, ValueError):
            lat = None
    if lon is None and "longitudeI" in payload:
        try:
            lon = float(payload["longitudeI"]) * 1e-7
        except (TypeError, ValueError):
            lon = None
    result = {
        "latitude": None,
        "longitude": None,
        "altitude": _first(payload, "altitude", "alt"),
        "ground_speed": _first(payload, "groundSpeed", "ground_speed"),
        "ground_track": _first(payload, "groundTrack", "ground_track"),
    }
    if has_valid_gps(lat, lon):
        result["latitude"] = float(lat)
        result["longitude"] = float(lon)
        if result["altitude"] is not None:
            try:
                result["altitude"] = float(result["altitude"])
            except (TypeError, ValueError):
                result["altitude"] = None
        for speed_key in ("ground_speed", "ground_track"):
            if result[speed_key] is not None:
                try:
                    result[speed_key] = float(result[speed_key])
                except (TypeError, ValueError):
                    result[speed_key] = None
    else:
        result["altitude"] = None
        result["ground_speed"] = None
        result["ground_track"] = None
    return result


def extract_user(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": _first(payload, "id", "userId", "node_id"),
        "long_name": _first(payload, "longName", "long_name"),
        "short_name": _first(payload, "shortName", "short_name"),
        "hardware_model": _stringify_hw(_first(payload, "hwModel", "hw_model", "hardware_model")),
    }


def _stringify_hw(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text.replace("HardwareModel.", "")


def extract_metrics(node_dict: dict[str, Any]) -> dict[str, Any]:
    metrics = node_dict.get("deviceMetrics") or node_dict.get("device_metrics") or {}
    battery = _first(metrics, "batteryLevel", "battery_level")
    if battery is None:
        battery = _first(node_dict, "batteryLevel", "battery_level")
    try:
        battery_f = float(battery) if battery is not None else None
    except (TypeError, ValueError):
        battery_f = None
    return {"battery_level": battery_f}


def node_fields_from_mesh(node_dict: dict[str, Any], gateway_id: str) -> Optional[dict[str, Any]]:
    user = node_dict.get("user") or {}
    position = node_dict.get("position") or {}
    node_num = _first(node_dict, "num", "node_number")
    node_id = _first(user, "id") or format_node_id(node_num)
    if not node_id:
        return None
    pos = extract_position(position) if position else {
        "latitude": None,
        "longitude": None,
        "altitude": None,
        "ground_speed": None,
        "ground_track": None,
    }
    metrics = extract_metrics(node_dict)
    last_heard = _first(node_dict, "lastHeard", "last_heard")
    last_seen = None
    if last_heard:
        try:
            last_seen = datetime.fromtimestamp(int(last_heard), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            last_seen = None
    fields: dict[str, Any] = {
        "node_id": str(node_id),
        "node_number": int(node_num) if node_num is not None else None,
        "long_name": _first(user, "longName", "long_name"),
        "short_name": _first(user, "shortName", "short_name"),
        "hardware_model": _stringify_hw(_first(user, "hwModel", "hw_model")),
        "gateway_id": gateway_id,
        **pos,
        **metrics,
    }
    if last_seen is not None:
        fields["last_seen"] = last_seen
    return fields


def store_message(
    db: Session,
    *,
    packet_id: str | None,
    source_node_id: str | None,
    destination_node_id: str | None,
    message_text: str | None,
    message_type: str,
    direction: str,
    raw_packet: dict[str, Any] | None = None,
) -> Message:
    row = Message(
        packet_id=str(packet_id) if packet_id is not None else None,
        timestamp=utcnow(),
        source_node_id=source_node_id,
        destination_node_id=destination_node_id,
        gateway_id=settings.gateway_id,
        message_text=message_text,
        message_type=message_type,
        direction=direction,
        raw_packet_json=packet_to_json(raw_packet) if raw_packet is not None else None,
    )
    db.add(row)
    db.flush()
    return row


def message_to_dict(row: Message) -> dict[str, Any]:
    return {
        "id": row.id,
        "packet_id": row.packet_id,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "source_node_id": row.source_node_id,
        "destination_node_id": row.destination_node_id,
        "gateway_id": row.gateway_id,
        "message_text": row.message_text,
        "message_type": row.message_type,
        "direction": row.direction,
    }


def list_messages(db: Session, limit: int = 200) -> list[Message]:
    stmt = select(Message).order_by(Message.timestamp.desc()).limit(max(1, min(limit, 1000)))
    return list(db.scalars(stmt).all())


def message_count() -> int:
    db = SessionLocal()
    try:
        return int(db.scalar(select(func.count()).select_from(Message)) or 0)
    finally:
        db.close()


def apply_text_packet(db: Session, packet: dict[str, Any]) -> Message:
    decoded = packet.get("decoded") or {}
    text = decoded.get("text")
    if text is None and isinstance(decoded.get("payload"), (bytes, bytearray)):
        try:
            text = bytes(decoded["payload"]).decode("utf-8")
        except UnicodeDecodeError:
            text = None
    source = format_node_id(packet.get("from"), packet.get("fromId"))
    dest = format_node_id(packet.get("to"), packet.get("toId")) or "^all"
    packet_id = packet.get("id")
    logger.info(
        "Text message rx packet_id=%s source=%s dest=%s text=%s",
        packet_id,
        source,
        dest,
        (text or "")[:120],
    )
    if source:
        upsert_node(db, {"node_id": source, "node_number": packet.get("from")})
    return store_message(
        db,
        packet_id=packet_id,
        source_node_id=source,
        destination_node_id=dest,
        message_text=text,
        message_type="text",
        direction="rx",
        raw_packet=packet,
    )


def apply_position_packet(db: Session, packet: dict[str, Any]) -> dict[str, Any] | None:
    decoded = packet.get("decoded") or {}
    position = decoded.get("position") or {}
    source = format_node_id(packet.get("from"), packet.get("fromId"))
    if not source:
        return None
    pos = extract_position(position)
    fields = {
        "node_id": source,
        "node_number": packet.get("from"),
        **pos,
    }
    if has_valid_gps(pos["latitude"], pos["longitude"]):
        logger.info(
            "GPS position from %s lat=%s lon=%s alt=%s",
            source,
            pos["latitude"],
            pos["longitude"],
            pos["altitude"],
        )
    else:
        logger.info("Position packet from %s without a GPS fix (location unavailable)", source)
    node = upsert_node(db, fields)
    return node


def apply_user_packet(db: Session, packet: dict[str, Any]) -> Any:
    decoded = packet.get("decoded") or {}
    user = decoded.get("user") or {}
    extracted = extract_user(user)
    node_id = extracted.get("node_id") or format_node_id(packet.get("from"), packet.get("fromId"))
    if not node_id:
        return None
    logger.info(
        "User/node update %s long=%s short=%s hw=%s",
        node_id,
        extracted.get("long_name"),
        extracted.get("short_name"),
        extracted.get("hardware_model"),
    )
    return upsert_node(
        db,
        {
            "node_id": str(node_id),
            "node_number": packet.get("from"),
            "long_name": extracted.get("long_name"),
            "short_name": extracted.get("short_name"),
            "hardware_model": extracted.get("hardware_model"),
        },
    )
