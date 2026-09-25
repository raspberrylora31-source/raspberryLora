const GatewayWS = (() => {
  const handlers = {};
  let socket = null;

  function on(type, fn) {
    (handlers[type] ||= []).push(fn);
  }

  function emit(event) {
    (handlers[event.type] || []).forEach((fn) => {
      try { fn(event.data || {}, event); } catch (err) { console.error(err); }
    });
    (handlers["*"] || []).forEach((fn) => {
      try { fn(event); } catch (err) { console.error(err); }
    });
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${proto}://${location.host}/ws`);
    socket.onmessage = (ev) => {
      try { emit(JSON.parse(ev.data)); } catch (err) { console.error("Bad WS payload", err); }
    };
    socket.onclose = () => setTimeout(connect, 1500);
  }

  function formatUptime(seconds) {
    if (seconds == null) return "—";
    const s = Number(seconds) || 0;
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return `${h}h ${m}m ${sec}s`;
  }

  function applyChrome(data) {
    const radio = data.radio_status || (data.radio_connected ? "CONNECTED" : "DISCONNECTED");
    const gps = data.gps_status || "LOCATION UNAVAILABLE";
    const setText = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    setText("nav-radio", radio);
    setText("nav-gps", gps);
    setText("nav-port", data.com_port || "");
    setText("top-gateway-name", data.gateway_name || "");
    setText("top-uptime", "uptime " + formatUptime(data.uptime_seconds));
    const rd = document.getElementById("nav-radio-dot");
    const gd = document.getElementById("nav-gps-dot");
    if (rd) rd.className = "dot " + (radio === "CONNECTED" ? "ok" : "bad");
    if (gd) gd.className = "dot " + (gps === "FIX AVAILABLE" ? "ok" : "warn");
  }

  on("radio_status", applyChrome);
  on("gateway_status", applyChrome);
  connect();

  return { on, formatUptime, applyChrome };
})();
