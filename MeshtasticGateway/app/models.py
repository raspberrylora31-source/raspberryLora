"""SQLAlchemy tables for nodes, messages, and gateway status."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    node_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    long_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    short_name: Mapped[str | None] = mapped_column(String(16), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    ground_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    ground_track: Mapped[float | None] = mapped_column(Float, nullable=True)
    hardware_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    gateway_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    packet_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    source_node_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    destination_node_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gateway_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_type: Mapped[str] = mapped_column(String(32), default="text")
    direction: Mapped[str] = mapped_column(String(8), default="rx")
    raw_packet_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class GatewayStatus(Base):
    __tablename__ = "gateway_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gateway_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    radio_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    mqtt_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
