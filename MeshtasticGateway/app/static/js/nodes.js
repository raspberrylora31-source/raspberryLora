function stateClass(state) {
  if (state === "online") return "ok";
  if (state === "stale") return "muted";
  return "bad";
}

function renderNodes(nodes) {
  const body = document.getElementById("nodes-body");
  body.innerHTML = nodes.map((n) => `
    <tr class="clickable" data-id="${n.node_id}">
      <td>${n.long_name || "—"}</td>
      <td>${n.node_id}</td>
      <td>${n.short_name || "—"}</td>
      <td class="${stateClass(n.marker_state)}">${(n.marker_state || "").toUpperCase()}</td>
      <td>${n.location_available ? `${n.latitude}, ${n.longitude}` : "Location unavailable"}</td>
      <td>${n.battery_level ?? "—"}</td>
      <td>${n.last_seen || "—"}</td>
      <td>${n.hardware_model || "—"}</td>
    </tr>
  `).join("");
  body.querySelectorAll("tr").forEach((row) => {
    row.addEventListener("click", () => openDetails(row.dataset.id));
  });
}

async function loadNodes(q = "") {
  const url = q ? `/api/nodes?q=${encodeURIComponent(q)}` : "/api/nodes";
  const body = await (await fetch(url)).json();
  renderNodes(body.nodes || []);
}

async function openDetails(nodeId) {
  const n = await (await fetch(`/api/nodes/${encodeURIComponent(nodeId)}`)).json();
  document.getElementById("dlg-title").textContent = n.long_name || n.node_id;
  document.getElementById("dlg-body").textContent = JSON.stringify(n, null, 2);
  document.getElementById("node-dialog").showModal();
}

document.getElementById("dlg-close").addEventListener("click", () => {
  document.getElementById("node-dialog").close();
});
document.getElementById("node-search").addEventListener("input", (ev) => {
  loadNodes(ev.target.value.trim());
});
GatewayWS.on("node_update", () => loadNodes(document.getElementById("node-search").value.trim()));
GatewayWS.on("position_update", () => loadNodes(document.getElementById("node-search").value.trim()));
loadNodes();
