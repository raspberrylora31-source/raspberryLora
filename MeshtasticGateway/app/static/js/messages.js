function rowHtml(m) {
  return `<tr>
    <td>${m.timestamp || ""}</td>
    <td>${m.direction || ""}</td>
    <td>${m.source_node_id || ""}</td>
    <td>${m.destination_node_id || ""}</td>
    <td>${escapeHtml(m.message_text || "")}</td>
    <td>${m.packet_id || ""}</td>
    <td>${m.gateway_id || ""}</td>
  </tr>`;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function prependMessage(m) {
  const body = document.getElementById("msg-body");
  body.insertAdjacentHTML("afterbegin", rowHtml(m));
}

async function loadMessages() {
  const body = await (await fetch("/api/messages?limit=200")).json();
  const tbody = document.getElementById("msg-body");
  tbody.innerHTML = (body.messages || []).map(rowHtml).join("");
}

async function loadDestinations() {
  const body = await (await fetch("/api/nodes")).json();
  const select = document.getElementById("send-dest");
  const current = select.value;
  select.innerHTML = '<option value="^all">Broadcast (^all)</option>';
  (body.nodes || []).forEach((n) => {
    const opt = document.createElement("option");
    opt.value = n.node_id;
    opt.textContent = `${n.long_name || n.short_name || n.node_id} (${n.node_id})`;
    select.appendChild(opt);
  });
  select.value = current;
}

document.getElementById("send-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const status = document.getElementById("send-status");
  const text = document.getElementById("send-text").value.trim();
  const destination = document.getElementById("send-dest").value;
  const res = await fetch("/api/messages/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, destination }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    status.textContent = body.detail || "Send failed (radio disconnected?)";
    return;
  }
  status.textContent = "Queued on radio.";
  document.getElementById("send-text").value = "";
});

GatewayWS.on("message", prependMessage);
GatewayWS.on("node_update", loadDestinations);
loadMessages();
loadDestinations();
