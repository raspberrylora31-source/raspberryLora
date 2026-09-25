"""Optional MQTT publisher. Disabled by default.

Topics: meshradio/<gateway_id>/rx|position|status

Dedup key: packet_id + source_node + origin_gateway + timestamp
Inbound MQTT is never retransmitted onto the radio (no A→B→A loops).
paho-mqtt is imported only when MQTT is enabled so a first run works
without the extra library.
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from typing import Any

from app.config import settings
from app.logging_setup import get_logger
from app.services.websocket_service import ws_manager

logger = get_logger()

_MAX_DEDUP = 2000


class PacketDeduper:
    def __init__(self, maxlen: int = _MAX_DEDUP) -> None:
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._maxlen = maxlen
        self._lock = threading.Lock()

    @staticmethod
    def make_key(packet_id: Any, source_node: Any, origin_gateway: Any, timestamp: Any) -> str:
        return f"{packet_id}|{source_node}|{origin_gateway}|{timestamp}"

    def seen_or_add(self, key: str) -> bool:
        with self._lock:
            if key in self._seen:
                return True
            self._seen[key] = None
            while len(self._seen) > self._maxlen:
                self._seen.popitem(last=False)
            return False


class MqttService:
    def __init__(self) -> None:
        self._client = None
        self._connected = threading.Event()
        self._lock = threading.Lock()
        self._deduper = PacketDeduper()
        self._started = False

    def is_connected(self) -> bool:
        return self._connected.is_set()

    def start(self) -> None:
        self._started = True
        if not settings.mqtt_enabled:
            logger.info("MQTT disabled (MQTT_ENABLED=false)")
            self._emit_status()
            return
        self._connect()

    def stop(self) -> None:
        with self._lock:
            client = self._client
            self._client = None
        self._connected.clear()
        if client is not None:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception as exc:
                logger.warning("MQTT disconnect error: %s", exc)
        self._emit_status()

    def restart(self) -> None:
        self.stop()
        if settings.mqtt_enabled:
            self._connect()
        else:
            logger.info("MQTT remains disabled")
            self._emit_status()

    def _connect(self) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.error(
                "MQTT is enabled but paho-mqtt is not installed. "
                "Install with: pip install paho-mqtt"
            )
            self._connected.clear()
            self._emit_status()
            return
        client_id = f"meshtastic-gateway-{settings.gateway_id}"
        client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        if settings.mqtt_user:
            # Password is passed to the library only; never logged.
            client.username_pw_set(settings.mqtt_user, settings.mqtt_password or None)
        if settings.mqtt_tls:
            client.tls_set()

        def on_connect(_client, _userdata, _flags, rc, *_args):
            if rc == 0:
                self._connected.set()
                logger.info(
                    "MQTT connected to %s:%s prefix=%s",
                    settings.mqtt_broker,
                    settings.mqtt_port,
                    settings.mqtt_topic_prefix,
                )
                topic = f"{settings.mqtt_topic_prefix}/+/rx"
                _client.subscribe(topic)
            else:
                self._connected.clear()
                logger.error("MQTT connect failed rc=%s", rc)
            self._emit_status()

        def on_disconnect(_client, _userdata, rc, *_args):
            self._connected.clear()
            logger.warning("MQTT disconnected rc=%s", rc)
            self._emit_status()

        def on_message(_client, _userdata, msg):
            # Observe foreign RX for dedup only. Never send onto the radio.
            try:
                payload = json.loads(msg.payload.decode("utf-8"))
            except Exception:
                logger.warning("MQTT message on %s was not JSON; ignored", msg.topic)
                return
            key = PacketDeduper.make_key(
                payload.get("packet_id"),
                payload.get("source_node_id") or payload.get("source_node"),
                payload.get("origin_gateway") or payload.get("gateway_id"),
                payload.get("timestamp"),
            )
            if self._deduper.seen_or_add(key):
                logger.info("MQTT duplicate dropped key=%s", key)
                return
            logger.info("MQTT rx observed (not retransmitted) topic=%s", msg.topic)

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message
        try:
            logger.info("Connecting MQTT broker %s:%s (TLS=%s)", settings.mqtt_broker, settings.mqtt_port, settings.mqtt_tls)
            client.connect_async(settings.mqtt_broker, settings.mqtt_port, keepalive=30)
            client.loop_start()
            with self._lock:
                self._client = client
        except Exception:
            logger.exception("MQTT connection failed")
            self._connected.clear()
            self._emit_status()

    def _topic(self, kind: str) -> str:
        return f"{settings.mqtt_topic_prefix}/{settings.gateway_id}/{kind}"

    def _publish(self, kind: str, payload: dict[str, Any]) -> None:
        if not settings.mqtt_enabled or not self._connected.is_set():
            return
        body = dict(payload)
        body["origin_gateway"] = settings.gateway_id
        key = PacketDeduper.make_key(
            body.get("packet_id"),
            body.get("source_node_id") or body.get("node_id"),
            body.get("origin_gateway"),
            body.get("timestamp") or body.get("last_seen"),
        )
        if kind != "status" and self._deduper.seen_or_add(key):
            logger.info("Skip MQTT publish of duplicate %s", key)
            return
        with self._lock:
            client = self._client
        if client is None:
            return
        try:
            client.publish(self._topic(kind), json.dumps(body, default=str), qos=0, retain=False)
        except Exception:
            logger.exception("MQTT publish failed for %s", kind)

    def publish_rx(self, payload: dict[str, Any]) -> None:
        self._publish("rx", payload)

    def publish_position(self, payload: dict[str, Any]) -> None:
        self._publish("position", payload)

    def publish_status(self, payload: dict[str, Any]) -> None:
        self._publish("status", payload)

    def _emit_status(self) -> None:
        ws_manager.emit(
            "mqtt_status",
            {
                "enabled": settings.mqtt_enabled,
                "connected": self.is_connected(),
                "broker": settings.mqtt_broker if settings.mqtt_enabled else None,
                "port": settings.mqtt_port if settings.mqtt_enabled else None,
            },
        )


mqtt_service = MqttService()
