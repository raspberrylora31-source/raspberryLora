"""Node upsert and online/stale/offline classification.

GPS coordinates are stored only when Meshtastic provides them. Missing
latitude/longitude stay NULL — they are never invented.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.logging_setup import get_logger
from app.models import Node, utcnow

logger = get_logger()

ONLINE_AFTER = timedelta(minutes=15)
STALE_AFTER = timedelta(minutes=60)


def has_valid_gps(lat: Any, lon: Any) -> bool:
    if lat is None or lon is None:
        return False
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return False
    return -90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0


def marker_state(node: Node, now: Optional[datetime] = None) -> str:
    now = now or utcnow()
    last = node.last_seen
    if last is None:
        return "offline"
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age = now - last
    if age <= ONLINE_AFTER:
        return "online"
    if age <= STALE_AFTER:
        return "stale"
    return "offline"


def node_to_dict(node: Node) -> dict[str, Any]:
    state = marker_state(node)
    gps = has_valid_gps(node.latitude, node.longitude)
    return {
        "id": node.id,
        "node_id": node.node_id,
        "node_number": node.node_number,
        "long_name": node.long_name,
        "short_name": node.short_name,
        "latitude": node.latitude if gps else None,
        "longitude": node.longitude if gps else None,
        "altitude": node.altitude if gps else None,
        "battery_level": node.battery_level,
        "ground_speed": node.ground_speed if gps else None,
        "ground_track": node.ground_track if gps else None,
        "hardware_model": node.hardware_model,
        "firmware_version": node.firmware_version,
        "last_seen": node.last_seen.isoformat() if node.last_seen else None,
        "first_seen": node.first_seen.isoformat() if node.first_seen else None,
        "gateway_id": node.gateway_id,
        "is_online": state == "online",
        "location_available": gps,
        "marker_state": state,
        "location_label": None if gps else "Location unavailable",
    }


def _get_by_node_id(db: Session, node_id: str) -> Node | None:
    return db.scalar(select(Node).where(Node.node_id == node_id))


def upsert_node(db: Session, fields: dict[str, Any], *, seen: bool = True) -> Node:
    node_id = fields["node_id"]
    node = _get_by_node_id(db, node_id)
    now = utcnow()
    if node is None:
        node = Node(
            node_id=node_id,
            first_seen=now,
            gateway_id=fields.get("gateway_id") or settings.gateway_id,
        )
        db.add(node)
        logger.info("New mesh node %s (%s)", node_id, fields.get("long_name") or fields.get("short_name") or "")
    for key, value in fields.items():
        if key == "node_id":
            continue
        if value is None:
            continue
        setattr(node, key, value)
    if seen:
        node.last_seen = now
        node.is_online = True
    if not node.gateway_id:
        node.gateway_id = settings.gateway_id
    db.flush()
    return node


def list_nodes(db: Session, query: str | None = None) -> list[Node]:
    stmt = select(Node).order_by(Node.last_seen.is_(None), Node.last_seen.desc())
    rows = list(db.scalars(stmt).all())
    if query:
        q = query.lower()
        rows = [
            n
            for n in rows
            if q in (n.node_id or "").lower()
            or q in (n.long_name or "").lower()
            or q in (n.short_name or "").lower()
            or q in str(n.node_number or "")
        ]
    return rows


def get_node(db: Session, node_id: str) -> Node | None:
    return _get_by_node_id(db, node_id)


def count_nodes(db: Session) -> dict[str, int]:
    rows = list(db.scalars(select(Node)).all())
    now = utcnow()
    online = stale = offline = 0
    gps = 0
    for node in rows:
        state = marker_state(node, now)
        if state == "online":
            online += 1
        elif state == "stale":
            stale += 1
        else:
            offline += 1
        if has_valid_gps(node.latitude, node.longitude):
            gps += 1
    return {
        "total": len(rows),
        "online": online,
        "stale": stale,
        "offline": offline,
        "with_gps": gps,
    }


def mark_stale_nodes(db: Session) -> None:
    now = utcnow()
    cutoff = now - ONLINE_AFTER
    rows = list(db.scalars(select(Node).where(Node.is_online.is_(True))).all())
    for node in rows:
        last = node.last_seen
        if last is None:
            node.is_online = False
            continue
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last < cutoff:
            node.is_online = False


def refresh_online_flags() -> None:
    db = SessionLocal()
    try:
        mark_stale_nodes(db)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to refresh node online flags")
    finally:
        db.close()


def node_count() -> int:
    db = SessionLocal()
    try:
        return int(db.scalar(select(func.count()).select_from(Node)) or 0)
    finally:
        db.close()
