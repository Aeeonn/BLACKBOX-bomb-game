// Minimal websocket wrapper. No framework, no build step, on purpose.
export const params = new URLSearchParams(location.search);
export const ROOM = (params.get("room") || "").toUpperCase();
export const ROLE = params.get("role") || "blind";

let sock = null;
const handlers = {};

export function on(type, fn) { handlers[type] = fn; }
export function send(msg) { if (sock && sock.readyState === 1) sock.send(JSON.stringify(msg)); }

export function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  sock = new WebSocket(proto + "://" + location.host + "/ws?room=" + ROOM + "&role=" + ROLE);
  sock.onopen = () => { setStatus("connected"); send({ type: "hello" }); };
  sock.onclose = () => { setStatus("disconnected - retrying"); setTimeout(connect, 1500); };
  sock.onmessage = (e) => { const m = JSON.parse(e.data); if (handlers[m.type]) handlers[m.type](m); };
}

function setStatus(t) {
  const el = document.getElementById("status");
  if (el) el.textContent = ROOM + " / " + ROLE + " - " + t;
}

export function logLine(text) {
  const el = document.getElementById("log");
  if (!el) return;
  const d = document.createElement("div");
  d.textContent = text;
  el.prepend(d);
}

export function fmtTime(s) {
  const m = Math.floor(s / 60), r = Math.floor(s % 60);
  return m + ":" + String(r).padStart(2, "0");
}
