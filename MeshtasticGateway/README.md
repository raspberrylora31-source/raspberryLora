# Meshtastic PC Gateway

Local Windows web gateway for a LILYGO T-Beam running **existing, working Meshtastic firmware**. The radio is not flashed, erased, factory-reset, or reconfigured. The PC talks to it over USB serial (`SerialInterface`) and serves a browser UI on loopback.

```
LILYGO T-Beam --USB/COM5--> Python Meshtastic Gateway -- SQLite + FastAPI + WebSocket --> browser
```

Dashboard: **http://127.0.0.1:8000** (bound to `127.0.0.1` only by default, never `0.0.0.0` unless you change `HOST`).

This directory is a standalone app. The Raspberry Pi YOLO/LoRa project at the repository root is unrelated and is left unchanged.

## Hardware (do not change)

- LILYGO T-Beam, PCB T-Beam AXP2101 V1.2, ESP32, 433/470 MHz LoRa
- Onboard GPS/GNSS and OLED
- Windows **COM5**: USB-Enhanced-SERIAL CH9102
- Meshtastic CLI 2.7.11, firmware 2.7.15.567b8ea, model TBEAM
- Node name **Alpha1**, short name **A1**

GPS is stored only when the radio reports real position fields. If there is no fix, latitude/longitude stay `NULL` and the UI shows **Location unavailable**. Coordinates are never invented.

---

## 1. Install commands

On Windows (from this folder):

```bat
cd MeshtasticGateway
setup.bat
```

`setup.bat` creates `.venv`, upgrades pip, installs `requirements.txt`, copies `.env.example` → `.env` if needed, and initializes `database/meshtastic.db`.

Manual equivalent:

```bat
cd MeshtasticGateway
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
python -c "from app.database import init_db; init_db()"
```

Linux / this cloud VM:

```bash
cd MeshtasticGateway
python3 -m virtualenv .venv   # or python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp -n .env.example .env
python -c "from app.database import init_db; init_db()"
```

## 2. venv activate

```bat
cd MeshtasticGateway
.venv\Scripts\activate
```

Linux:

```bash
cd MeshtasticGateway
source .venv/bin/activate
```

## 3. start gateway

```bat
start_gateway.bat
```

which runs:

```bat
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Linux:

```bash
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 4. dashboard URL

Open **http://127.0.0.1:8000**

Other pages: `/map`, `/messages`, `/nodes`, `/gateway`, `/settings`, `/logs`.

## 5. test COM5 command

With the T-Beam plugged in on Windows:

```bat
.venv\Scripts\activate
python tools\test_radio.py --list
python tools\test_radio.py --port COM5
python tools\test_radio.py --port COM5 --listen 30
```

`--list` prints serial ports. The connect command opens `SerialInterface(devPath="COM5")`, prints radio info and the node DB, then disconnects cleanly. It does not write firmware or radio config.

## 6. how to test GPS

1. Place the T-Beam where it can see the sky (or confirm the OLED already has a GNSS fix).
2. Start the gateway and open Dashboard and Live Map.
3. **FIX AVAILABLE** plus lat/lon means the radio sent real position fields (`latitude` / `longitude` or `latitudeI` / `longitudeI`).
4. **LOCATION UNAVAILABLE** means those fields were absent — the map will not place a marker. The gateway never fills in a default city or simulated coordinates.

`tools/test_radio.py --port COM5 --listen 30` also prints `POSITION lat=… lon=…` when a position packet arrives, or omits them when there is no fix.

## 7. how to test receiving a message

1. Gateway running, radio **CONNECTED**.
2. From another Meshtastic node or the Meshtastic phone app, send a text to the mesh (or to Alpha1 / A1).
3. Watch **Messages** (`http://127.0.0.1:8000/messages`) — rows appear live over WebSocket (`type: message`).
4. Confirm `logs/gateway.log` has a text-message line (no credentials).

## 8. how to test sending a message

1. Open **Messages**.
2. Destination **Broadcast (^all)** or a specific node.
3. Type text and click **Send**.
4. The gateway calls the real API: `interface.sendText(text, destinationId=..., wantAck=True, channelIndex=0)`.
5. The OLED on the T-Beam should show the text for broadcasts; other nodes should receive it. The console stores the outbound row as `direction=tx`.

CLI equivalent after connecting in Python: `iface.sendText("hello mesh")` with `destinationId=meshtastic.BROADCAST_ADDR` (`"^all"`).

## 9. how to enable MQTT later

MQTT is **off** (`MQTT_ENABLED=false`) so the first run does not need an MQTT library.

```bat
pip install paho-mqtt
```

In `.env` or **Settings**:

```
MQTT_ENABLED=true
MQTT_BROKER=localhost
MQTT_PORT=1883
MQTT_USER=
MQTT_PASSWORD=
MQTT_TLS=false
MQTT_TOPIC_PREFIX=meshradio
```

Restart the gateway. Topics:

- `meshradio/<gateway_id>/rx`
- `meshradio/<gateway_id>/position`
- `meshradio/<gateway_id>/status`

Duplicates are dropped using `packet_id + source_node + origin_gateway + timestamp`. Inbound MQTT is **never** retransmitted onto the radio (no A→B→A loops). Passwords are never returned by the API or written to logs.

## 10. how to connect a second PC later

Default bind is loopback only. To let another computer on your LAN open the UI:

1. Set `HOST` in `.env` to the Windows PC’s LAN IP **or** (with a firewall rule you accept) `0.0.0.0`.
2. Restart: `uvicorn app.main:app --host 0.0.0.0 --port 8000` — only if you intentionally expose it.
3. On the second PC browse `http://<windows-lan-ip>:8000`.
4. Keep MQTT dedup enabled if both PCs might publish; never bridge RX blindly.

Prefer keeping `127.0.0.1` unless you need LAN access. There is no authentication layer in this first version.

---

## Pages and live events

| Path | Purpose |
|------|---------|
| `/` | Radio status, COM port, gateway identity, firmware, hardware, GPS, counts, last packet, uptime |
| `/map` | Leaflet markers **only** for valid GPS; Online / Stale / Offline |
| `/messages` | Live console + send form |
| `/nodes` | Searchable table; click a row for details |
| `/gateway` | Identity, COM, radio, GPS, **Reconnect Radio** |
| `/settings` | Gateway name, COM port, gateway ID, MQTT |
| `/logs` | Tail of `logs/gateway.log` (rotating files) |

WebSocket `/ws` payload shape: `{"type":"...","data":{...}}`  
Types: `message`, `node_update`, `position_update`, `radio_status`, `gateway_status`, `mqtt_status`.

## Configuration

See `.env.example`. Default COM port is `COM5` (change in Settings). SQLite path: `database/meshtastic.db`. No passwords are stored in the database.

## Tests

```bash
cd MeshtasticGateway
source .venv/bin/activate   # or .venv\Scripts\activate
pytest -q
```

Software tests cover syntax, SQLite, HTTP pages, WebSocket, COM listing, DB inserts, and mock disconnect/reconnect. They do **not** prove COM5 / T-Beam / GPS / RF send-receive unless that hardware is attached.

## Meshtastic Python API (installed 2.7.11)

Verified against the package, not guessed:

- `meshtastic.serial_interface.SerialInterface(devPath=...)`
- `interface.sendText(text, destinationId=..., wantAck=..., channelIndex=...)`
- `interface.sendHeartbeat()`, `interface.close()`
- `interface.getMyNodeInfo()`, `getMyUser()`, `getLongName()`, `getShortName()`
- `interface.nodes`, `nodesByNum`, `myInfo`, `metadata`
- `meshtastic.util.findPorts()`
- PubSub: `meshtastic.connection.established`, `meshtastic.connection.lost`, `meshtastic.receive`, `.text`, `.position`, `.user`, `meshtastic.node.updated`
- Broadcast destination: `meshtastic.BROADCAST_ADDR` (`"^all"`)

`SerialInterface()` without `devPath` calls `sys.exit` when multiple serial ports exist, so the gateway always passes an explicit port.
