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

// Hold-to-commit: gives MUTE one second to slam STOP. Do not remove.
// onStart/onEnd are optional hooks so callers (blind.html) can report the
// hold's start/stop to the server for the broadcast commit-charge ring
// (AGENTS.md hard rule 12 / T10) without this generic UI helper needing to
// know anything about networking. onEnd fires exactly once per hold attempt,
// whether it ended by completing or by early release - callers that need to
// tell the two apart can check their own state instead of branching here.
export function holdButton(el, ms, onComplete, onStart, onEnd) {
  let t0 = null, raf = null;
  const bar = el.querySelector(".fill");
  function frame() {
    const p = Math.min(1, (performance.now() - t0) / ms);
    if (bar) bar.style.width = (p * 100) + "%";
    if (p >= 1) { stop(); onComplete(); } else { raf = requestAnimationFrame(frame); }
  }
  function start() { if (t0 !== null) return; t0 = performance.now(); if (onStart) onStart(); frame(); }
  function stop() {
    const wasActive = t0 !== null;
    t0 = null; if (raf) cancelAnimationFrame(raf); if (bar) bar.style.width = "0%";
    if (wasActive && onEnd) onEnd();
  }
  el.addEventListener("mousedown", start);
  el.addEventListener("mouseup", stop);
  el.addEventListener("mouseleave", stop);
  return { start, stop };
}
