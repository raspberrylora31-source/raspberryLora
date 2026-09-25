"""Test environment: skip radio hardware, use a temp SQLite file."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ["GATEWAY_SKIP_RADIO"] = "true"
os.environ["MQTT_ENABLED"] = "false"
os.environ["COM_PORT"] = "COM5"
os.environ["HOST"] = "127.0.0.1"
os.environ["GATEWAY_NAME"] = "Test Gateway"
os.environ["GATEWAY_ID"] = "test-gateway"
os.environ.setdefault("MQTT_PASSWORD", "")

_TEST_DB = Path(tempfile.gettempdir()) / "meshtastic_gateway_pytest.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"

from app.config import settings  # noqa: E402

settings.reload()

from app.database import init_db, reset_engine  # noqa: E402

reset_engine(settings.database_url)
init_db()
