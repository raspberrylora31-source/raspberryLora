function paintDashboard(s) {
  const set = (id, v, cls) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = v ?? "—";
    if (cls) el.className = "value " + cls;
  };
  set("d-radio", s.radio_status, s.radio_connected ? "ok" : "bad");
  set("d-port", s.com_port);
  set("d-name", s.gateway_name, "small");
  set("d-node-id", s.gateway_node_id || "—", "small");
  set("d-fw", s.firmware_version || "—", "small");
  set("d-hw", s.hardware_model || "—", "small");
  set("d-gps", s.gps_status, s.gps_status === "FIX AVAILABLE" ? "ok" : "muted");
  set("d-online", s.nodes_online);
  set("d-total", s.node_count);
  set("d-messages", s.message_count);
  set("d-last", s.last_packet_at || "—", "small");
  set("d-uptime", GatewayWS.formatUptime(s.uptime_seconds), "small");
  const err = document.getElementById("d-error");
  if (err) err.textContent = s.last_error || "";
}

async function loadDashboard() {
  const s = await (await fetch("/api/status")).json();
  paintDashboard(s);
  GatewayWS.applyChrome(s);
}

GatewayWS.on("radio_status", paintDashboard);
GatewayWS.on("gateway_status", paintDashboard);
GatewayWS.on("message", () => loadDashboard());
GatewayWS.on("node_update", () => loadDashboard());
loadDashboard();
setInterval(loadDashboard, 5000);
