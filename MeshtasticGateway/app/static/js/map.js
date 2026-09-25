const markers = new Map();
const map = L.map("map", { worldCopyJump: true }).setView([20, 0], 2);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap",
}).addTo(map);

const colors = { online: "#3ecf8e", stale: "#e6b450", offline: "#6b7788" };

function iconFor(state) {
  const color = colors[state] || colors.offline;
  return L.divIcon({
    className: "",
    html: `<div style="width:16px;height:16px;border-radius:50%;background:${color};border:2px solid #0c1117"></div>`,
    iconSize: [16, 16],
  });
}

function popupHtml(n) {
  const gps = n.location_available
    ? `${n.latitude}, ${n.longitude}`
    : "Location unavailable";
  return `<strong>${n.long_name || n.short_name || n.node_id}</strong><br>
    ID: ${n.node_id}<br>
    Lat/Lon: ${gps}<br>
    Alt: ${n.altitude ?? "—"}<br>
    Battery: ${n.battery_level ?? "—"}<br>
    Last seen: ${n.last_seen || "—"}<br>
    Hardware: ${n.hardware_model || "—"}<br>
    Gateway: ${n.gateway_id || "—"}`;
}

function upsertMarker(n) {
  if (!n.location_available || n.latitude == null || n.longitude == null) {
    const existing = markers.get(n.node_id);
    if (existing) {
      map.removeLayer(existing);
      markers.delete(n.node_id);
    }
    return;
  }
  let marker = markers.get(n.node_id);
  if (!marker) {
    marker = L.marker([n.latitude, n.longitude], { icon: iconFor(n.marker_state) }).addTo(map);
    markers.set(n.node_id, marker);
  } else {
    marker.setLatLng([n.latitude, n.longitude]);
    marker.setIcon(iconFor(n.marker_state));
  }
  marker.bindPopup(popupHtml(n));
}

function fitIfNeeded() {
  const layers = [...markers.values()];
  if (layers.length === 1) {
    map.setView(layers[0].getLatLng(), 13);
  } else if (layers.length > 1) {
    const group = L.featureGroup(layers);
    map.fitBounds(group.getBounds().pad(0.25));
  }
}

async function loadNodes() {
  const body = await (await fetch("/api/nodes")).json();
  (body.nodes || []).forEach(upsertMarker);
  if (markers.size) fitIfNeeded();
}

GatewayWS.on("position_update", upsertMarker);
GatewayWS.on("node_update", upsertMarker);
loadNodes();
