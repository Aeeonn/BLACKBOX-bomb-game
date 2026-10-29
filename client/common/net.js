// Minimal websocket wrapper. No framework, no build step, on purpose.
export const params = new URLSearchParams(location.search);
export const ROOM = (params.get("room") || "").toUpperCase();
export const ROLE = params.get("role") || "blind";

let sock = null;
let refusal = null;   // why the server last closed us, if it said
const handlers = {};

// Several listeners per message type, so the shared page chrome and the
// role page's own code can both react to "state" without either one having
// to know about the other.
export function on(type, fn) { (handlers[type] = handlers[type] || []).push(fn); }
export function send(msg) { if (sock && sock.readyState === 1) sock.send(JSON.stringify(msg)); }

export function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  sock = new WebSocket(proto + "://" + location.host + "/ws?room=" + ROOM + "&role=" + ROLE);
  sock.onopen = () => { refusal = null; setStatus("connected", "on"); send({ type: "hello" }); };
  sock.onclose = () => {
    setStatus(refusal || "reconnecting\u2026", "off");
    setTimeout(connect, refusal ? 3000 : 1500);
  };
  sock.onmessage = (e) => {
    const m = JSON.parse(e.data);
    // The server explains a refused seat in one "error" message and then
    // closes; keep that reason on screen instead of a bare "reconnecting".
    if (m.type === "error" && /role taken|no such room/.test(m.text || "")) {
      refusal = /no such room/.test(m.text) ? "no room " + ROOM : "seat already taken";
    }
    for (const fn of handlers[m.type] || []) fn(m);
  };
}

function setStatus(text, state) {
  const el = document.getElementById("status");
  if (!el) return;
  el.textContent = text;
  el.dataset.state = state;
}

export function logLine(text) {
  const el = document.getElementById("log");
  if (!el) return;
  const d = document.createElement("div");
  d.textContent = text;
  if (/STRIKE/.test(text)) d.className = "log-hot";
  else if (/defused|armed/i.test(text)) d.className = "log-ok";
  el.prepend(d);
  while (el.children.length > 40) el.lastChild.remove();
}

export function fmtTime(s) {
  const m = Math.floor(s / 60), r = Math.floor(s % 60);
  return m + ":" + String(r).padStart(2, "0");
}
