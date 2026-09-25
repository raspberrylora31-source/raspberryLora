"""Pydantic request/response schemas with input validation."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

COM_PORT_RE = re.compile(r"^(COM\d+|com\d+|/dev/tty[A-Za-z0-9._-]+|/dev/cu\.[A-Za-z0-9._-]+)$")
NODE_DEST_RE = re.compile(r"^(\^all|\^local|![0-9a-fA-F]+|0x[0-9a-fA-F]+|\d{1,10})$")
GATEWAY_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=200)
    destination: str = Field(default="^all", max_length=32)
    channel_index: int = Field(default=0, ge=0, le=7)
    want_ack: bool = True

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message text cannot be empty")
        return cleaned

    @field_validator("destination")
    @classmethod
    def valid_destination(cls, value: str) -> str:
        dest = value.strip() or "^all"
        if not NODE_DEST_RE.match(dest):
            raise ValueError("Destination must be ^all, a node id like !aabbccdd, or a node number")
        return dest


class SettingsUpdate(BaseModel):
    gateway_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    com_port: Optional[str] = Field(default=None, min_length=1, max_length=64)
    gateway_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    mqtt_enabled: Optional[bool] = None
    mqtt_broker: Optional[str] = Field(default=None, max_length=255)
    mqtt_port: Optional[int] = Field(default=None, ge=1, le=65535)
    mqtt_user: Optional[str] = Field(default=None, max_length=128)
    mqtt_password: Optional[str] = Field(default=None, max_length=256)
    mqtt_tls: Optional[bool] = None
    mqtt_topic_prefix: Optional[str] = Field(default=None, max_length=64)

    @field_validator("com_port")
    @classmethod
    def valid_com_port(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        port = value.strip()
        if not COM_PORT_RE.match(port):
            raise ValueError("COM port must look like COM5 or /dev/ttyUSB0")
        return port

    @field_validator("gateway_id")
    @classmethod
    def valid_gateway_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        gid = value.strip()
        if not GATEWAY_ID_RE.match(gid):
            raise ValueError("Gateway ID may contain letters, digits, dot, underscore, colon, or hyphen")
        return gid

    @field_validator("mqtt_topic_prefix")
    @classmethod
    def valid_prefix(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        prefix = value.strip().strip("/")
        if not prefix or "/" in prefix or any(ch in prefix for ch in "#+"):
            raise ValueError("Topic prefix must be a single MQTT path segment")
        return prefix


class SettingsResponse(BaseModel):
    host: str
    port: int
    gateway_name: str
    gateway_id: str
    com_port: str
    mqtt_enabled: bool
    mqtt_broker: str
    mqtt_port: int
    mqtt_user: str
    mqtt_password_set: bool
    mqtt_tls: bool
    mqtt_topic_prefix: str


class NodeOut(BaseModel):
    id: int
    node_id: str
    node_number: Optional[int] = None
    long_name: Optional[str] = None
    short_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    battery_level: Optional[float] = None
    ground_speed: Optional[float] = None
    ground_track: Optional[float] = None
    hardware_model: Optional[str] = None
    firmware_version: Optional[str] = None
    last_seen: Optional[datetime] = None
    first_seen: Optional[datetime] = None
    gateway_id: Optional[str] = None
    is_online: bool = False
    location_available: bool = False
    marker_state: str = "offline"

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: int
    packet_id: Optional[str] = None
    timestamp: datetime
    source_node_id: Optional[str] = None
    destination_node_id: Optional[str] = None
    gateway_id: Optional[str] = None
    message_text: Optional[str] = None
    message_type: str
    direction: str

    model_config = {"from_attributes": True}


class ComPortOut(BaseModel):
    device: str
    description: str | None = None
    hwid: str | None = None
    likely_meshtastic: bool = False


class WsEvent(BaseModel):
    type: str
    data: dict[str, Any]
