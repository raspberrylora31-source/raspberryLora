"""Application settings loaded from environment / .env."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


class Settings:
    """Runtime settings. MQTT password is never logged or returned by APIs."""

    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        load_dotenv(ENV_PATH, override=False)
        self.host = os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1"
        self.port = _as_int(os.getenv("PORT"), 8000)
        self.gateway_name = os.getenv("GATEWAY_NAME", "Meshtastic PC Gateway").strip() or "Meshtastic PC Gateway"
        self.gateway_id = os.getenv("GATEWAY_ID", "pc-gateway-1").strip() or "pc-gateway-1"
        self.com_port = os.getenv("COM_PORT", "COM5").strip() or "COM5"
        self.skip_radio = _as_bool(os.getenv("GATEWAY_SKIP_RADIO"), False)
        self.database_url = os.getenv(
            "DATABASE_URL",
            f"sqlite:///{(BASE_DIR / 'database' / 'meshtastic.db').as_posix()}",
        )
        self.log_dir = BASE_DIR / "logs"
        self.log_file = self.log_dir / "gateway.log"

        self.mqtt_enabled = _as_bool(os.getenv("MQTT_ENABLED"), False)
        self.mqtt_broker = os.getenv("MQTT_BROKER", "localhost").strip() or "localhost"
        self.mqtt_port = _as_int(os.getenv("MQTT_PORT"), 1883)
        self.mqtt_user = os.getenv("MQTT_USER", "").strip()
        self.mqtt_password = os.getenv("MQTT_PASSWORD", "")
        self.mqtt_tls = _as_bool(os.getenv("MQTT_TLS"), False)
        self.mqtt_topic_prefix = os.getenv("MQTT_TOPIC_PREFIX", "meshradio").strip() or "meshradio"

    def public_dict(self) -> dict:
        """Settings safe to show in the UI / API (no password)."""
        return {
            "host": self.host,
            "port": self.port,
            "gateway_name": self.gateway_name,
            "gateway_id": self.gateway_id,
            "com_port": self.com_port,
            "mqtt_enabled": self.mqtt_enabled,
            "mqtt_broker": self.mqtt_broker,
            "mqtt_port": self.mqtt_port,
            "mqtt_user": self.mqtt_user,
            "mqtt_password_set": bool(self.mqtt_password),
            "mqtt_tls": self.mqtt_tls,
            "mqtt_topic_prefix": self.mqtt_topic_prefix,
        }

    def persist(self, updates: dict) -> None:
        """Write selected settings to .env without logging secrets."""
        current = {}
        if ENV_PATH.exists():
            for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                current[key.strip()] = value

        mapping = {
            "gateway_name": "GATEWAY_NAME",
            "gateway_id": "GATEWAY_ID",
            "com_port": "COM_PORT",
            "host": "HOST",
            "port": "PORT",
            "mqtt_enabled": "MQTT_ENABLED",
            "mqtt_broker": "MQTT_BROKER",
            "mqtt_port": "MQTT_PORT",
            "mqtt_user": "MQTT_USER",
            "mqtt_password": "MQTT_PASSWORD",
            "mqtt_tls": "MQTT_TLS",
            "mqtt_topic_prefix": "MQTT_TOPIC_PREFIX",
        }
        for field, env_key in mapping.items():
            if field not in updates or updates[field] is None:
                continue
            value = updates[field]
            if field == "mqtt_password" and value == "":
                continue
            if isinstance(value, bool):
                current[env_key] = "true" if value else "false"
            else:
                current[env_key] = str(value)
            os.environ[env_key] = current[env_key]

        ordered_keys = [
            "HOST",
            "PORT",
            "GATEWAY_NAME",
            "GATEWAY_ID",
            "COM_PORT",
            "GATEWAY_SKIP_RADIO",
            "MQTT_ENABLED",
            "MQTT_BROKER",
            "MQTT_PORT",
            "MQTT_USER",
            "MQTT_PASSWORD",
            "MQTT_TLS",
            "MQTT_TOPIC_PREFIX",
        ]
        lines = [
            "# Meshtastic PC Gateway configuration",
            "# This file may contain secrets. Do not share or commit it.",
            "",
        ]
        for key in ordered_keys:
            if key in current:
                lines.append(f"{key}={current[key]}")
                current.pop(key)
        for key, value in current.items():
            lines.append(f"{key}={value}")
        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.reload()


settings = Settings()
