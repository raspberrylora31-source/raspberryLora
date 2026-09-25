"""Meshtastic serial radio service.

Uses the installed meshtastic 2.x Python API (verified against 2.7.11):

- meshtastic.serial_interface.SerialInterface(devPath=...)
- interface.sendText(text, destinationId=..., wantAck=..., channelIndex=...)
- interface.sendHeartbeat()
- interface.close()
- interface.getMyNodeInfo() / getMyUser() / getLongName() / getShortName()
- interface.nodes / nodesByNum / myInfo / metadata
- meshtastic.util.findPorts()
- pubsub: meshtastic.connection.established / lost,
  meshtastic.receive, meshtastic.receive.text / position / user,
  meshtastic.node.updated

SerialInterface() without destPath calls sys.exit when multiple ports exist,
so this service always passes an explicit destPath. Disconnects never crash
the FastAPI process.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from serial.tools import list_ports

from app.config import settings
from app.database import SessionLocal
from app.logging_setup import get_logger
from app.models import GatewayStatus, utcnow
from app.services import node_service, packet_service
from app.services.mqtt_service import mqtt_service
from app.services.node_service import has_valid_gps, node_to_dict
from app.services.websocket_service import ws_manager

logger = get_logger()

KEEPALIVE_SECONDS = 30
RECONNECT_SECONDS = 5
STALE_SWEEP_SECONDS = 30
CONNECT_TIMEOUT_SECONDS = 45


def _default_interface_factory(port: str):
    from meshtastic.serial_interface import SerialInterface

    return SerialInterface(devPath=port)


class MeshtasticService:
    def __init__(self, interface_factory: Optional[Callable[[str], Any]] = None) -> None:
        self._interface_factory = interface_factory or _default_interface_factory
        self._iface = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._port = settings.com_port
        self._started_at = utcnow()
        self._last_packet_at: datetime | None = None
        self._last_error: str | None = None
        self._radio_info: dict[str, Any] = {}
        self._nodes_memory: dict[str, dict[str, Any]] = {}
        self._threads: list[threading.Thread] = []
        self._subscribed = False
        self._connect_generation = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        self._started_at = utcnow()
        self._subscribe()
        if settings.skip_radio:
            logger.info("GATEWAY_SKIP_RADIO=true — not opening a serial port")
        else:
            self._spawn(self._reconnect_loop, "radio-reconnect")
        self._spawn(self._keepalive_loop, "radio-keepalive")
        self._spawn(self._stale_loop, "node-stale")
        logger.info("Meshtastic service started (configured port %s)", self._port)

    def stop(self) -> None:
        logger.info("Meshtastic service shutting down")
        self._stop.set()
        self.disconnect()
        for thread in self._threads:
            thread.join(timeout=2)
        self._threads.clear()

    def _spawn(self, target, name: str) -> None:
        thread = threading.Thread(target=target, name=name, daemon=True)
        thread.start()
        self._threads.append(thread)

    def _subscribe(self) -> None:
        if self._subscribed:
            return
        from pubsub import pub

        pub.subscribe(self._on_connection_established, "meshtastic.connection.established")
        pub.subscribe(self._on_connection_lost, "meshtastic.connection.lost")
        pub.subscribe(self._on_receive, "meshtastic.receive")
        pub.subscribe(self._on_receive_text, "meshtastic.receive.text")
        pub.subscribe(self._on_receive_position, "meshtastic.receive.position")
        pub.subscribe(self._on_receive_user, "meshtastic.receive.user")
        pub.subscribe(self._on_node_updated, "meshtastic.node.updated")
        self._subscribed = True
        logger.info("Subscribed to Meshtastic pubsub events")

    # ------------------------------------------------------------------
    # Ports
    # ------------------------------------------------------------------
    def list_ports(self) -> list[dict[str, Any]]:
        likely: set[str] = set()
        try:
            import meshtastic.util

            likely = set(meshtastic.util.findPorts(True))
        except Exception as exc:
            logger.warning("meshtastic.util.findPorts failed: %s", exc)
        ports = []
        for info in list_ports.comports():
            ports.append(
                {
                    "device": info.device,
                    "description": info.description,
                    "hwid": info.hwid,
                    "vid": info.vid,
                    "pid": info.pid,
                    "likely_meshtastic": info.device in likely,
                }
            )
        if self._port and not any(p["device"] == self._port for p in ports):
            ports.append(
                {
                    "device": self._port,
                    "description": "Configured port (not currently detected)",
                    "hwid": None,
                    "vid": None,
                    "pid": None,
                    "likely_meshtastic": False,
                }
            )
        return ports

    def select_port(self, port: str) -> None:
        previous = self._port
        self._port = port
        settings.com_port = port
        logger.info("COM port changed from %s to %s", previous, port)
        if not settings.skip_radio:
            self.reconnect_now()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def connect(self, port: Optional[str] = None) -> bool:
        port = port or self._port or settings.com_port
        if not port:
            self._last_error = "No COM port configured"
            logger.warning(self._last_error)
            return False
        self._port = port
        with self._lock:
            self.disconnect(emit=False)
            self._connect_generation += 1
            generation = self._connect_generation
            logger.info("Connecting to Meshtastic radio on %s", port)
            try:
                iface = self._interface_factory(port)
            except SystemExit as exc:
                self._last_error = f"SerialInterface exited: {exc}"
                logger.error(self._last_error)
                self._set_disconnected()
                return False
            except Exception as exc:
                self._last_error = f"Failed to open {port}: {exc}"
                logger.error(self._last_error)
                self._set_disconnected()
                return False
            if iface is None:
                self._last_error = f"No radio on {port}"
                logger.error(self._last_error)
                self._set_disconnected()
                return False
            self._iface = iface
        # Connection.established is published after node DB download.
        # Wait a bounded time; if the factory is a mock it may already be connected.
        deadline = time.time() + CONNECT_TIMEOUT_SECONDS
        while time.time() < deadline and not self._stop.is_set():
            if generation != self._connect_generation:
                return False
            if self._is_iface_connected(iface):
                if not self._connected.is_set():
                    self._on_connected(iface)
                return True
            time.sleep(0.1)
        if self._iface is iface:
            # Some mocks / noProto paths never fire pubsub; still expose the handle.
            logger.warning("Timed out waiting for connection.established on %s", port)
            if self._is_iface_connected(iface):
                if not self._connected.is_set():
                    self._on_connected(iface)
                return True
            self._last_error = f"Radio on {port} did not complete handshake"
            logger.error(self._last_error)
            self.disconnect()
        return False

    def disconnect(self, emit: bool = True) -> None:
        with self._lock:
            iface = self._iface
            self._iface = None
            self._connected.clear()
            if iface is not None:
                logger.info("Disconnecting Meshtastic radio")
                try:
                    iface.close()
                except Exception as exc:
                    logger.warning("Error closing radio: %s", exc)
        if emit:
            self._set_disconnected()

    def reconnect_now(self) -> None:
        logger.info("Manual radio reconnect requested")
        self.disconnect(emit=False)
        if settings.skip_radio:
            return
        threading.Thread(target=self._try_connect_once, name="radio-reconnect-now", daemon=True).start()

    def _try_connect_once(self) -> None:
        try:
            self.connect(self._port)
        except Exception:
            logger.exception("Reconnect attempt failed")

    def _reconnect_loop(self) -> None:
        while not self._stop.is_set():
            if not self._connected.is_set() and not settings.skip_radio:
                try:
                    self.connect(self._port)
                except Exception:
                    logger.exception("Auto-reconnect failed")
            self._stop.wait(RECONNECT_SECONDS)

    def _keepalive_loop(self) -> None:
        while not self._stop.wait(KEEPALIVE_SECONDS):
            iface = self._iface
            if iface is None or not self._connected.is_set():
                continue
            try:
                if hasattr(iface, "sendHeartbeat"):
                    iface.sendHeartbeat()
                    logger.debug("Radio keep-alive heartbeat sent")
            except Exception as exc:
                logger.warning("Keep-alive failed (%s) — will reconnect", exc)
                self.disconnect()

    def _stale_loop(self) -> None:
        while not self._stop.wait(STALE_SWEEP_SECONDS):
            try:
                node_service.refresh_online_flags()
            except Exception:
                logger.exception("Stale-node sweep failed")

    def _is_iface_connected(self, iface: Any) -> bool:
        flag = getattr(iface, "isConnected", None)
        if flag is None:
            return iface is not None
        if hasattr(flag, "is_set"):
            return bool(flag.is_set())
        return bool(flag)

    def _on_connected(self, iface: Any) -> None:
        self._connected.set()
        self._last_error = None
        self._refresh_radio_info(iface)
        self._ingest_nodedb(iface)
        logger.info(
            "Radio CONNECTED on %s node_id=%s firmware=%s hardware=%s",
            self._port,
            self._radio_info.get("node_id"),
            self._radio_info.get("firmware_version"),
            self._radio_info.get("hardware_model"),
        )
        self._emit_radio_status()
        self._snapshot_gateway_status(radio_connected=True)

    def _set_disconnected(self) -> None:
        self._connected.clear()
        self._emit_radio_status()
        self._snapshot_gateway_status(radio_connected=False)

    def _ours(self, interface: Any) -> bool:
        return interface is not None and interface is self._iface

    # ------------------------------------------------------------------
    # Pubsub handlers
    # ------------------------------------------------------------------
    def _on_connection_established(self, interface=None, **_kwargs) -> None:
        if not self._ours(interface):
            return
        try:
            self._on_connected(interface)
        except Exception:
            logger.exception("Error handling connection.established")

    def _on_connection_lost(self, interface=None, **_kwargs) -> None:
        if interface is not None and self._iface is not None and interface is not self._iface:
            return
        logger.warning("Radio connection lost")
        with self._lock:
            if self._iface is interface:
                self._iface = None
        self._set_disconnected()

    def _on_receive(self, packet=None, interface=None, **_kwargs) -> None:
        if not self._ours(interface) or not packet:
            return
        try:
            self._last_packet_at = utcnow()
            decoded = packet.get("decoded") or {}
            portnum = decoded.get("portnum")
            logger.info(
                "Packet rx id=%s from=%s to=%s portnum=%s",
                packet.get("id"),
                packet.get("fromId") or packet.get("from"),
                packet.get("toId") or packet.get("to"),
                portnum,
            )
        except Exception:
            logger.exception("Failed to log received packet")

    def _on_receive_text(self, packet=None, interface=None, **_kwargs) -> None:
        if not self._ours(interface) or not packet:
            return
        db = SessionLocal()
        try:
            row = packet_service.apply_text_packet(db, packet)
            db.commit()
            payload = packet_service.message_to_dict(row)
            ws_manager.emit("message", payload)
            mqtt_service.publish_rx(payload)
        except Exception:
            db.rollback()
            logger.exception("Failed to persist text packet")
        finally:
            db.close()

    def _on_receive_position(self, packet=None, interface=None, **_kwargs) -> None:
        if not self._ours(interface) or not packet:
            return
        db = SessionLocal()
        try:
            node = packet_service.apply_position_packet(db, packet)
            db.commit()
            if node is not None:
                data = node_to_dict(node)
                self._nodes_memory[data["node_id"]] = data
                ws_manager.emit("position_update", data)
                ws_manager.emit("node_update", data)
                mqtt_service.publish_position(data)
        except Exception:
            db.rollback()
            logger.exception("Failed to persist position packet")
        finally:
            db.close()

    def _on_receive_user(self, packet=None, interface=None, **_kwargs) -> None:
        if not self._ours(interface) or not packet:
            return
        db = SessionLocal()
        try:
            node = packet_service.apply_user_packet(db, packet)
            db.commit()
            if node is not None:
                data = node_to_dict(node)
                self._nodes_memory[data["node_id"]] = data
                ws_manager.emit("node_update", data)
        except Exception:
            db.rollback()
            logger.exception("Failed to persist user packet")
        finally:
            db.close()

    def _on_node_updated(self, node=None, interface=None, **_kwargs) -> None:
        if not self._ours(interface) or not node:
            return
        fields = packet_service.node_fields_from_mesh(node, settings.gateway_id)
        if not fields:
            return
        db = SessionLocal()
        try:
            stored = node_service.upsert_node(db, fields, seen=bool(fields.get("last_seen")))
            if fields.get("last_seen"):
                stored.last_seen = fields["last_seen"]
                age = utcnow() - fields["last_seen"]
                stored.is_online = age <= node_service.ONLINE_AFTER
            db.commit()
            data = node_to_dict(stored)
            self._nodes_memory[data["node_id"]] = data
            ws_manager.emit("node_update", data)
            if data.get("location_available"):
                ws_manager.emit("position_update", data)
        except Exception:
            db.rollback()
            logger.exception("Failed to persist node.updated")
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Radio info / send
    # ------------------------------------------------------------------
    def _refresh_radio_info(self, iface: Any) -> None:
        info: dict[str, Any] = {
            "com_port": self._port,
            "connected": True,
            "node_id": None,
            "node_number": None,
            "long_name": None,
            "short_name": None,
            "firmware_version": None,
            "hardware_model": None,
            "latitude": None,
            "longitude": None,
            "altitude": None,
            "battery_level": None,
            "ground_speed": None,
            "ground_track": None,
            "gps_status": "LOCATION UNAVAILABLE",
        }
        try:
            if hasattr(iface, "getLongName"):
                info["long_name"] = iface.getLongName()
            if hasattr(iface, "getShortName"):
                info["short_name"] = iface.getShortName()
        except Exception:
            logger.exception("Failed reading long/short name")
        try:
            metadata = getattr(iface, "metadata", None)
            if metadata is not None:
                info["firmware_version"] = getattr(metadata, "firmware_version", None)
                hw = getattr(metadata, "hw_model", None)
                info["hardware_model"] = _hw_name(hw)
        except Exception:
            logger.exception("Failed reading radio metadata")
        try:
            my = iface.getMyNodeInfo() if hasattr(iface, "getMyNodeInfo") else None
            if my:
                user = my.get("user") or {}
                info["node_id"] = user.get("id")
                info["node_number"] = my.get("num")
                info["long_name"] = info["long_name"] or user.get("longName")
                info["short_name"] = info["short_name"] or user.get("shortName")
                if not info["hardware_model"]:
                    info["hardware_model"] = str(user.get("hwModel") or "") or None
                pos = packet_service.extract_position(my.get("position") or {})
                info.update(pos)
                metrics = packet_service.extract_metrics(my)
                info["battery_level"] = metrics.get("battery_level")
                if has_valid_gps(info.get("latitude"), info.get("longitude")):
                    info["gps_status"] = "FIX AVAILABLE"
                    logger.info(
                        "Gateway GPS fix lat=%s lon=%s alt=%s",
                        info["latitude"],
                        info["longitude"],
                        info["altitude"],
                    )
                else:
                    info["gps_status"] = "LOCATION UNAVAILABLE"
                    logger.info("Gateway GPS has no fix (location unavailable)")
                # Persist the gateway node itself, GPS only if present.
                gw_db = SessionLocal()
                try:
                    node_service.upsert_node(
                        gw_db,
                        {
                            "node_id": info["node_id"] or f"gateway:{settings.gateway_id}",
                            "node_number": info["node_number"],
                            "long_name": info["long_name"],
                            "short_name": info["short_name"],
                            "hardware_model": info["hardware_model"],
                            "firmware_version": info["firmware_version"],
                            "gateway_id": settings.gateway_id,
                            **{k: pos[k] for k in pos},
                            "battery_level": info["battery_level"],
                        },
                    )
                    gw_db.commit()
                except Exception:
                    gw_db.rollback()
                    logger.exception("Failed to persist gateway node")
                finally:
                    gw_db.close()
        except Exception:
            logger.exception("Failed reading getMyNodeInfo")
        myinfo = getattr(iface, "myInfo", None)
        if myinfo is not None and not info["node_number"]:
            info["node_number"] = getattr(myinfo, "my_node_num", None)
        self._radio_info = info

    def _ingest_nodedb(self, iface: Any) -> None:
        nodes = getattr(iface, "nodes", None) or {}
        db = SessionLocal()
        try:
            for _key, node in nodes.items():
                fields = packet_service.node_fields_from_mesh(node, settings.gateway_id)
                if not fields:
                    continue
                stored = node_service.upsert_node(db, fields, seen=False)
                if fields.get("last_seen"):
                    stored.last_seen = fields["last_seen"]
                data = node_to_dict(stored)
                self._nodes_memory[data["node_id"]] = data
            db.commit()
            logger.info("Ingested %s nodes from radio node DB", len(self._nodes_memory))
        except Exception:
            db.rollback()
            logger.exception("Failed ingesting node DB")
        finally:
            db.close()

    def send_text(self, text: str, destination: str = "^all", channel_index: int = 0, want_ack: bool = True) -> dict[str, Any]:
        iface = self._iface
        if iface is None or not self._connected.is_set():
            raise RuntimeError("Radio is not connected")
        import meshtastic

        dest: Any = destination
        if destination in ("^all", "broadcast", ""):
            dest = meshtastic.BROADCAST_ADDR
        logger.info("Sending text via sendText dest=%s channel=%s", dest, channel_index)
        sent = iface.sendText(
            text,
            destinationId=dest,
            wantAck=want_ack,
            channelIndex=channel_index,
        )
        packet_id = None
        raw = None
        if sent is not None:
            packet_id = getattr(sent, "id", None)
            if packet_id is None and isinstance(sent, dict):
                packet_id = sent.get("id")
            try:
                raw = packet_service.json_safe(
                    sent if isinstance(sent, dict) else {"id": packet_id, "repr": str(sent)}
                )
            except Exception:
                raw = {"id": packet_id}
        source = (self._radio_info or {}).get("node_id") or settings.gateway_id
        db = SessionLocal()
        try:
            row = packet_service.store_message(
                db,
                packet_id=packet_id,
                source_node_id=source,
                destination_node_id="^all" if dest == meshtastic.BROADCAST_ADDR else str(destination),
                message_text=text,
                message_type="text",
                direction="tx",
                raw_packet=raw if isinstance(raw, dict) else None,
            )
            db.commit()
            payload = packet_service.message_to_dict(row)
        except Exception:
            db.rollback()
            logger.exception("Failed to store outbound message")
            payload = {
                "packet_id": packet_id,
                "source_node_id": source,
                "destination_node_id": str(destination),
                "message_text": text,
                "message_type": "text",
                "direction": "tx",
                "timestamp": utcnow().isoformat(),
                "gateway_id": settings.gateway_id,
            }
        finally:
            db.close()
        ws_manager.emit("message", payload)
        mqtt_service.publish_rx(payload)
        return payload

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def uptime_seconds(self) -> int:
        return max(0, int((utcnow() - self._started_at).total_seconds()))

    def connection_status(self) -> str:
        return "CONNECTED" if self._connected.is_set() else "DISCONNECTED"

    def memory_nodes(self) -> dict[str, dict[str, Any]]:
        return dict(self._nodes_memory)

    def status_payload(self) -> dict[str, Any]:
        counts = {}
        db = SessionLocal()
        try:
            counts = node_service.count_nodes(db)
        except Exception:
            logger.exception("Failed counting nodes")
        finally:
            db.close()
        gps_status = (self._radio_info or {}).get("gps_status") or "LOCATION UNAVAILABLE"
        if not self._connected.is_set():
            gps_status = "LOCATION UNAVAILABLE"
        return {
            "radio_status": self.connection_status(),
            "radio_connected": self._connected.is_set(),
            "com_port": self._port,
            "gateway_name": settings.gateway_name,
            "gateway_id": settings.gateway_id,
            "gateway_node_id": (self._radio_info or {}).get("node_id"),
            "firmware_version": (self._radio_info or {}).get("firmware_version"),
            "hardware_model": (self._radio_info or {}).get("hardware_model"),
            "long_name": (self._radio_info or {}).get("long_name"),
            "short_name": (self._radio_info or {}).get("short_name"),
            "gps_status": gps_status,
            "latitude": (self._radio_info or {}).get("latitude") if self._connected.is_set() else None,
            "longitude": (self._radio_info or {}).get("longitude") if self._connected.is_set() else None,
            "altitude": (self._radio_info or {}).get("altitude") if self._connected.is_set() else None,
            "battery_level": (self._radio_info or {}).get("battery_level"),
            "node_count": counts.get("total", 0),
            "nodes_online": counts.get("online", 0),
            "nodes_stale": counts.get("stale", 0),
            "nodes_offline": counts.get("offline", 0),
            "nodes_with_gps": counts.get("with_gps", 0),
            "message_count": packet_service.message_count(),
            "last_packet_at": self._last_packet_at.isoformat() if self._last_packet_at else None,
            "uptime_seconds": self.uptime_seconds(),
            "ip_address": settings.host,
            "last_error": self._last_error,
            "mqtt_enabled": settings.mqtt_enabled,
            "mqtt_connected": mqtt_service.is_connected(),
            "skip_radio": settings.skip_radio,
        }

    def radio_info(self) -> dict[str, Any]:
        return dict(self._radio_info)

    def _emit_radio_status(self) -> None:
        payload = self.status_payload()
        ws_manager.emit("radio_status", payload)
        ws_manager.emit("gateway_status", payload)
        mqtt_service.publish_status(payload)

    def _snapshot_gateway_status(self, radio_connected: bool) -> None:
        db = SessionLocal()
        try:
            row = GatewayStatus(
                gateway_id=settings.gateway_id,
                timestamp=utcnow(),
                radio_connected=radio_connected,
                mqtt_connected=mqtt_service.is_connected(),
                ip_address=settings.host,
                node_count=node_service.node_count(),
                message_count=packet_service.message_count(),
            )
            db.add(row)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to write gateway_status snapshot")
        finally:
            db.close()


def _hw_name(hw: Any) -> Optional[str]:
    if hw is None:
        return None
    try:
        from meshtastic.protobuf import mesh_pb2

        if isinstance(hw, int):
            return mesh_pb2.HardwareModel.Name(hw)
    except Exception:
        pass
    text = str(hw).replace("HardwareModel.", "")
    return text or None


radio_service = MeshtasticService()
