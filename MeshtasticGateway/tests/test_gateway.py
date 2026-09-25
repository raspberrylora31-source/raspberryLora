"""Software tests that do not require a T-Beam."""

from __future__ import annotations

import compileall
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]


def test_python_syntax():
    ok = compileall.compile_dir(str(ROOT / "app"), quiet=1)
    assert ok
    ok = compileall.compile_file(str(ROOT / "tools" / "test_radio.py"), quiet=1)
    assert ok


def test_sqlite_init_and_insert():
    from app.database import SessionLocal, init_db
    from app.models import Message, Node
    from app.services.node_service import upsert_node
    from app.services.packet_service import store_message

    init_db()
    db = SessionLocal()
    try:
        node = upsert_node(
            db,
            {
                "node_id": "!abcdef01",
                "node_number": 123,
                "long_name": "Alpha1",
                "short_name": "A1",
                "hardware_model": "TBEAM",
                "firmware_version": "2.7.15.567b8ea",
                "gateway_id": "test-gateway",
            },
        )
        assert node.latitude is None
        assert node.longitude is None
        store_message(
            db,
            packet_id="1",
            source_node_id="!abcdef01",
            destination_node_id="^all",
            message_text="hello",
            message_type="text",
            direction="rx",
            raw_packet={"id": 1, "decoded": {"text": "hello"}},
        )
        db.commit()
        nodes = list(db.scalars(select(Node)).all())
        messages = list(db.scalars(select(Message)).all())
        assert any(n.node_id == "!abcdef01" for n in nodes)
        assert any(m.message_text == "hello" for m in messages)
    finally:
        db.close()


def test_gps_null_means_unavailable():
    from app.services.node_service import has_valid_gps, node_to_dict
    from app.models import Node

    node = Node(id=1, node_id="!n1", latitude=None, longitude=None, is_online=True)
    data = node_to_dict(node)
    assert data["location_available"] is False
    assert data["location_label"] == "Location unavailable"
    assert data["latitude"] is None
    assert has_valid_gps(None, None) is False
    assert has_valid_gps(37.5, -122.2) is True


def test_com_port_detection():
    from app.services.meshtastic_service import radio_service

    ports = radio_service.list_ports()
    assert isinstance(ports, list)
    devices = [p["device"] for p in ports]
    assert "COM5" in devices  # configured default, even if not attached


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_pages_load(client: TestClient):
    for path in ["/", "/map", "/messages", "/nodes", "/gateway", "/settings", "/logs"]:
        res = client.get(path)
        assert res.status_code == 200, path
        assert "Meshtastic" in res.text


def test_status_and_settings_api(client: TestClient):
    status = client.get("/api/status").json()
    assert status["radio_status"] in {"CONNECTED", "DISCONNECTED"}
    assert status["com_port"]
    assert status["gps_status"] == "LOCATION UNAVAILABLE"
    assert status["mqtt_enabled"] is False
    settings = client.get("/api/settings").json()
    assert "mqtt_password" not in settings
    assert settings["mqtt_password_set"] in {True, False}


def test_send_without_radio_returns_409(client: TestClient):
    res = client.post("/api/messages/send", json={"text": "hello", "destination": "^all"})
    assert res.status_code == 409


def test_rejects_invalid_destination(client: TestClient):
    res = client.post("/api/messages/send", json={"text": "hello", "destination": "not a node"})
    assert res.status_code == 422


def test_websocket(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        assert first["type"] in {"radio_status", "gateway_status", "mqtt_status"}
        assert "data" in first
        assert isinstance(first["data"], dict)


def test_logs_api_no_password_leak(client: TestClient, caplog):
    from app.logging_setup import get_logger

    log = get_logger()
    log.info("mqtt_password=super-secret-value connecting")
    res = client.get("/api/logs?lines=50")
    assert res.status_code == 200
    joined = "\n".join(res.json()["lines"])
    assert "super-secret-value" not in joined


def test_mock_disconnect_reconnect_and_send():
    from app.services.meshtastic_service import MeshtasticService

    class FakeIface:
        def __init__(self, destPath=None):
            self.devPath = destPath
            self.nodes = {}
            self.closed = False
            self.sent = []
            self.heartbeats = 0
            self.isConnected = threading.Event()
            self.isConnected.set()
            self.metadata = type("M", (), {"firmware_version": "2.7.15.567b8ea", "hw_model": 4})()
            self.myInfo = type("I", (), {"my_node_num": 1})()

        def getMyNodeInfo(self):
            return {
                "num": 1,
                "user": {"id": "!00000001", "longName": "Alpha1", "shortName": "A1", "hwModel": "TBEAM"},
                "position": {},
            }

        def getMyUser(self):
            return self.getMyNodeInfo()["user"]

        def getLongName(self):
            return "Alpha1"

        def getShortName(self):
            return "A1"

        def sendText(self, text, destinationId="^all", wantAck=False, channelIndex=0, **_k):
            pkt = {"id": 42, "decoded": {"text": text}}
            self.sent.append((text, destinationId, channelIndex, wantAck))
            return pkt

        def sendHeartbeat(self):
            if self.closed:
                raise RuntimeError("closed")
            self.heartbeats += 1

        def close(self):
            self.closed = True
            self.isConnected.clear()

    created = []

    def factory(port):
        iface = FakeIface(port)
        created.append(iface)
        return iface

    svc = MeshtasticService(interface_factory=factory)
    try:
        assert svc.connect("COM5") is True
        assert svc.connection_status() == "CONNECTED"
        info = svc.radio_info()
        assert info["long_name"] == "Alpha1"
        assert info["gps_status"] == "LOCATION UNAVAILABLE"
        assert info["latitude"] is None
        payload = svc.send_text("ping", destination="^all")
        assert payload["message_text"] == "ping"
        assert payload["direction"] == "tx"
        assert created[0].sent[0][0] == "ping"
        svc.disconnect()
        assert svc.connection_status() == "DISCONNECTED"
        assert created[0].closed is True
        assert svc.connect("COM5") is True
        assert svc.connection_status() == "CONNECTED"
        assert len(created) == 2
    finally:
        svc.stop()


def test_mqtt_disabled_and_dedup():
    from app.services.mqtt_service import PacketDeduper, mqtt_service
    from app.config import settings

    assert settings.mqtt_enabled is False
    assert mqtt_service.is_connected() is False
    d = PacketDeduper()
    key = PacketDeduper.make_key("1", "!a", "gw1", "t0")
    assert d.seen_or_add(key) is False
    assert d.seen_or_add(key) is True


def test_position_from_meshtastic_fields_only():
    from app.services.packet_service import extract_position

    empty = extract_position({})
    assert empty["latitude"] is None and empty["longitude"] is None
    scaled = extract_position({"latitudeI": 377749000, "longitudeI": -1224194000, "altitude": 12})
    assert abs(scaled["latitude"] - 37.7749) < 1e-5
    assert abs(scaled["longitude"] - (-122.4194)) < 1e-5
    assert scaled["altitude"] == 12


def test_meshtastic_api_symbols_exist():
    import inspect
    import meshtastic
    from meshtastic.serial_interface import SerialInterface
    from meshtastic.mesh_interface import MeshInterface
    import meshtastic.util

    assert meshtastic.BROADCAST_ADDR == "^all"
    assert "devPath" in str(inspect.signature(SerialInterface.__init__))
    assert "destinationId" in str(inspect.signature(MeshInterface.sendText))
    assert hasattr(MeshInterface, "sendHeartbeat")
    assert hasattr(meshtastic.util, "findPorts")
