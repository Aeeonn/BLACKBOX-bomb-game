// The shared-room diorama: a lamp-lit table with the bomb at its centre and
// the other players seated across from you. This file reads WORLD data (the
// shared module layouts), the round's global state that every role receives
// identically (phase, timer, strikes, paused), and PRESENCE data (seats,
// poses, gestures, gaze, pointers, BLIND's probe echo and commit ring) -
// never any module's views(), so it cannot leak PERCEPTION however the
// drawing grows. What a viewer may see is decided by the server: a BLIND
// viewer never receives other seats' yaw/gaze/gesture/pointer keys, and this
// file draws a silhouette whenever they're absent - hard rule 5 holds
// structurally, not by a role check here. Kept behind a small interface
// (init/setPresence/setBomb/render) so a future renderer (e.g. a real 3D
// engine) can replace this file without any server or game code changing -
// see AGENTS.md T7.
//
// T11: mouse movement now ALSO drives real pose/gesture messages sent to the
// server (via the `send` function passed into init()), not just the local
// parallax. This file still never imports net.js directly and still never
// touches module data - it only ever emits {yaw, pitch, gaze} and
// {gesture: kind}, exactly the PRESENCE shapes server/stage.py already
// expects and filters. Detection (mouse-look, shake/nod thresholds) is
// client-side; per AGENTS.md T11, the emitted gesture is authoritative once
// sent - the server does not re-validate *how* a gesture was produced.

const ROLE_ORDER = ["blind", "deaf", "mute", "scope", "dispatch"];

// Avatar legend colours only. Deliberately NOT the same hues M1 uses for wire
// colours (red/blue/yellow/white/black/green), so a bust on the stage can
// never be mistaken for a piece of module PERCEPTION.
const ROLE_COLOUR = {
  blind: "#7d8fce",
  deaf: "#cd8b62",
  mute: "#a678b0",
  scope: "#5fae96",
  dispatch: "#b8637e",
};

const FONT = '"Cascadia Mono", "JetBrains Mono", Consolas, monospace';
const HOT = "#e0472f";
const OK = "#4fae68";
const SEAT_ARC = [200, 340]; // degrees: the far rim of the table, across from the camera

// T11 tuning. Expect these to move once real people try it - see the design
// doc's own "expect to change T9-T12 based on what happens" note.
const YAW_RANGE = 0.6;             // radians of head yaw at full mouse deflection
const PITCH_RANGE = 0.4;           // radians of head pitch at full mouse deflection
const MANUAL_GAZE_PITCH = 0.22;    // pitch past this (looking down) => gaze:"manual"
const POSE_SEND_HZ_MS = 100;       // ~10Hz outgoing pose - well under presence's 20Hz
const POSE_EPSILON = 0.004;        // radians; smaller changes aren't worth a message
const GESTURE_WINDOW_MS = 500;     // how far back the shake/nod detector looks
const GESTURE_THRESHOLD = 0.9;     // oscillation "energy" needed to fire
const GESTURE_MARGIN = 1.3;        // how much bigger one axis must be than the other
const GESTURE_COOLDOWN_MS = 700;   // minimum gap between two emitted gestures

export function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

// Frame-rate-independent exponential easing: closes `rate`'s share of the
// remaining distance to `target` per second, regardless of dt. Used for the
// local mouse parallax, other players' head interpolation and BLIND's
// crawling hand, so nothing ever snaps between presence frames.
export function smoothTowards(current, target, dt, rate) {
  const t = 1 - Math.exp(-rate * dt);
  return current + (target - current) * t;
}

// The other (up to 4) seats, in a fixed canonical order that never changes
// with who's connected - AGENTS.md hard rule 4: every seat always renders,
// greyed if empty, never removed or reshuffled.
export function seatOrder(myRole) {
  return ROLE_ORDER.filter(r => r !== myRole);
}

export function seatAngleDeg(index, total) {
  if (total <= 1) return (SEAT_ARC[0] + SEAT_ARC[1]) / 2;
  return SEAT_ARC[0] + (index * (SEAT_ARC[1] - SEAT_ARC[0])) / (total - 1);
}

export function ellipsePoint(cx, cy, rx, ry, angleDeg) {
  const a = (angleDeg * Math.PI) / 180;
  return { x: cx + rx * Math.cos(a), y: cy + ry * Math.sin(a) };
}

// Small shared lookup for "find one role's row in a presence payload" - used
// by deaf.html/mute.html/scope.html for both BLIND's probe echo (T9) and
// commit-charge ring (T10), so this one tiny piece of bookkeeping doesn't
// have to be reinvented a third time by a future ticket.
export function findPlayer(presence, role) {
  return (presence && presence.players.find(p => p.role === role)) || null;
}

// Detects "shake" (rapid horizontal mouse motion) vs "nod" (vertical),
// distinguishing an oscillating wiggle from a smooth directed look-around:
// a genuine shake covers a lot of *path* (sum of |dx| between samples) while
// barely moving *net* distance (back-and-forth cancels out), whereas turning
// your head to look left is one smooth motion where path and net distance are
// close to equal. Exported as a factory (not a class) so each stage instance
// gets its own independent history/cooldown state, and so it's trivially
// unit-testable in isolation from the DOM/canvas.
export function makeGestureDetector(opts = {}) {
  const windowMs = opts.windowMs ?? GESTURE_WINDOW_MS;
  const threshold = opts.threshold ?? GESTURE_THRESHOLD;
  const margin = opts.margin ?? GESTURE_MARGIN;
  const cooldownMs = opts.cooldownMs ?? GESTURE_COOLDOWN_MS;
  let history = [];
  let lastFired = -Infinity;

  return {
    // t in ms (same clock as performance.now()/rAF timestamps); x, y in -1..1.
    // Returns "shake", "nod", or null.
    sample(t, x, y) {
      history.push({ t, x, y });
      while (history.length > 1 && t - history[0].t > windowMs) history.shift();
      if (history.length < 4 || t - lastFired < cooldownMs) return null;

      let pathH = 0, pathV = 0;
      for (let i = 1; i < history.length; i++) {
        pathH += Math.abs(history[i].x - history[i - 1].x);
        pathV += Math.abs(history[i].y - history[i - 1].y);
      }
      const netH = Math.abs(history[history.length - 1].x - history[0].x);
      const netV = Math.abs(history[history.length - 1].y - history[0].y);
      const oscH = pathH - netH;
      const oscV = pathV - netV;

      let kind = null;
      if (oscH > threshold && oscH > oscV * margin) kind = "shake";
      else if (oscV > threshold && oscV > oscH * margin) kind = "nod";

      if (kind) { lastFired = t; history = []; }
      return kind;
    },
  };
}

let canvas = null, ctx = null;
let viewW = 0, viewH = 0, dpr = 1;
let seats = [];   // [{role, connected, moving, hasDetail, yaw, pitch, displayYaw, displayPitch, gesture, gaze, pointer}]
let bomb = { phase: "lobby", layouts: [], timeLeft: null, strikes: 0, maxStrikes: 3, paused: false };
let blindBody = { probe: null, charge: null };   // BLIND's probe echo + commit ring (PRESENCE)
let ownPointer = null;
let hand = null;          // eased on-screen position of BLIND's hand
let chargeShown = 0;
let parallax = { x: 0, y: 0, targetX: 0, targetY: 0 };
let lastTs = null;
let frameDt = 1 / 60;
let looping = false;
let sendFn = () => {};
let gestureDetector = null;
let lastPoseSentAt = -Infinity;
let lastSentPose = null;   // {yaw, pitch, gaze} - null forces the next tick to send
let myRole = null;

// Third argument is the same `send` exported by common/net.js - passed in
// rather than imported directly so this file still has zero import of
// net.js, keeping it swappable/testable independent of the transport layer.
// Omit it (e.g. in tests) and pose/gesture detection simply has nowhere to
// send - everything else (parallax, rendering) still works.
export function init(canvasEl, role, send) {
  canvas = canvasEl;
  ctx = canvas.getContext("2d");
  myRole = role;
  sendFn = typeof send === "function" ? send : () => {};
  gestureDetector = makeGestureDetector();
  seats = seatOrder(role).map(r => ({
    role: r, connected: false, moving: false, hasDetail: false,
    yaw: 0, pitch: 0, displayYaw: 0, displayPitch: 0, gesture: null, gaze: null, pointer: null,
  }));

  canvas.addEventListener("mousemove", e => {
    const r = canvas.getBoundingClientRect();
    const x = clamp(((e.clientX - r.left) / r.width) * 2 - 1, -1, 1);
    const y = clamp(((e.clientY - r.top) / r.height) * 2 - 1, -1, 1);
    parallax.targetX = x;
    parallax.targetY = y;
    const kind = gestureDetector.sample(performance.now(), x, y);
    if (kind) sendFn({ type: "gesture", kind });
  });
  canvas.addEventListener("mouseleave", () => {
    parallax.targetX = 0; parallax.targetY = 0;
  });

  if (!looping) {
    looping = true;
    requestAnimationFrame(tick);
  }
}

// PRESENCE in. Detail fields (yaw/pitch/gesture/gaze/pointer) are stored only
// when the server actually included them - never for BLIND viewing other
// players (see server/stage.py). BLIND's probe echo and commit ring are read
// from BLIND's own row, which every viewer receives (probe gated by
// probe_echo on the server).
export function setPresence(payload) {
  const byRole = {};
  for (const p of (payload.players || [])) byRole[p.role] = p;
  // Poses are only sent on change, so if the server's copy of our own pose
  // ever disagrees with what we last sent (it resets to zero when a socket
  // reconnects), forget it and the next tick resends.
  const own = byRole[myRole];
  if (own && "yaw" in own && lastSentPose &&
      (Math.abs(own.yaw - lastSentPose.yaw) > POSE_EPSILON ||
       Math.abs(own.pitch - lastSentPose.pitch) > POSE_EPSILON ||
       own.gaze !== lastSentPose.gaze)) {
    lastSentPose = null;
  }
  for (const seat of seats) {
    const p = byRole[seat.role];
    if (!p) continue;
    seat.connected = !!p.connected;
    seat.moving = !!p.moving;
    seat.hasDetail = "yaw" in p;
    seat.yaw = seat.hasDetail ? p.yaw || 0 : 0;
    seat.pitch = seat.hasDetail ? p.pitch || 0 : 0;
    seat.gesture = seat.hasDetail ? p.gesture || null : null;
    seat.gaze = seat.hasDetail ? p.gaze || null : null;
    seat.pointer = p.pointer || null;
  }
  const b = byRole.blind || {};
  blindBody = { probe: b.probe || null, charge: b.charge || null };
  ownPointer = (own && own.pointer) || null;
}

// WORLD + shared round state in. Keeps only the module layouts (one shared
// geometry, identical for every role - T4) and the global fields every role
// receives identically. Everything else in the snapshot - every module's
// role-filtered view - is dropped here, so this file physically cannot grow
// a dependency on PERCEPTION later by accident.
export function setBomb(snapshot) {
  const prev = bomb;
  bomb = {
    phase: snapshot.phase || "running",
    layouts: snapshot.layouts || [],
    timeLeft: typeof snapshot.time_left === "number" ? snapshot.time_left : null,
    strikes: snapshot.strikes || 0,
    maxStrikes: snapshot.max_strikes || 3,
    paused: !!snapshot.paused,
  };
  // The room jolts on a strike and quakes on detonation. Only live
  // transitions count, so loading the page mid-round never shakes it.
  if (prev.phase === "running" && bomb.phase === "lost") kick(1300, 0.45);
  else if (prev.phase === "running" && bomb.phase === "running" && bomb.strikes > prev.strikes) kick(450, 0.16);
}

let shake = { until: 0, ms: 1, amp: 0 };
function kick(ms, amp) {
  shake = { until: performance.now() + ms, ms, amp };
}

function tick(ts) {
  const dt = lastTs == null ? 0 : Math.min(0.1, (ts - lastTs) / 1000);
  lastTs = ts;
  frameDt = dt;

  parallax.x = smoothTowards(parallax.x, parallax.targetX, dt, 6);
  parallax.y = smoothTowards(parallax.y, parallax.targetY, dt, 6);
  for (const seat of seats) {
    seat.displayYaw = smoothTowards(seat.displayYaw, seat.yaw, dt, 8);
    seat.displayPitch = smoothTowards(seat.displayPitch, seat.pitch, dt, 8);
  }

  if (ts - lastPoseSentAt > POSE_SEND_HZ_MS) {
    const yaw = parallax.x * YAW_RANGE;
    const pitch = parallax.y * PITCH_RANGE;
    // "manual" = looking down: at MUTE's lectern for MUTE, at your own desk
    // for everyone else. "bomb" is the default - it's what's in front of the
    // camera otherwise.
    const gaze = pitch > MANUAL_GAZE_PITCH ? "manual" : "bomb";
    // Only on change: the server marks a seat "moving" for half a second
    // after every pose, so sending unconditionally made every connected
    // player look permanently in motion - BLIND's sonar pulsed nonstop.
    if (!lastSentPose || gaze !== lastSentPose.gaze ||
        Math.abs(yaw - lastSentPose.yaw) > POSE_EPSILON ||
        Math.abs(pitch - lastSentPose.pitch) > POSE_EPSILON) {
      lastPoseSentAt = ts;
      lastSentPose = { yaw, pitch, gaze };
      sendFn({ type: "pose", yaw, pitch, gaze });
    }
  }

  render(ts);
  requestAnimationFrame(tick);
}

// ---------- drawing ----------

function rgbOf(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function rgba(hex, a) {
  const [r, g, b] = rgbOf(hex);
  return "rgba(" + r + "," + g + "," + b + "," + a + ")";
}
function mix(hex, t, to) {
  return "rgb(" + rgbOf(hex).map((v, i) => Math.round(v + (to[i] - v) * t)).join(",") + ")";
}
const lighten = (hex, t) => mix(hex, t, [255, 255, 255]);
const darken = (hex, t) => mix(hex, t, [0, 0, 0]);

function mmss(s) {
  const t = Math.max(0, Math.ceil(s));
  return String(Math.floor(t / 60)).padStart(2, "0") + ":" + String(t % 60).padStart(2, "0");
}

function poly(pts) {
  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].y);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
  ctx.closePath();
}

function roundRect(x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

// Keeps the backing store at the canvas's real on-screen size times the
// device pixel ratio, so the room is crisp at any window size or zoom.
function fit() {
  const r = canvas.getBoundingClientRect();
  const ratio = Math.min(2, window.devicePixelRatio || 1);
  const w = Math.max(1, Math.round(r.width)), h = Math.max(1, Math.round(r.height));
  if (w !== viewW || h !== viewH || ratio !== dpr) {
    viewW = w; viewH = h; dpr = ratio;
    canvas.width = Math.round(w * ratio);
    canvas.height = Math.round(h * ratio);
  }
}

// One frame's scene geometry. `u` is the scene unit (1/16 of a 16:9 frame),
// so everything scales together. The seats sit on a back parallax layer and
// the table/bomb on a front one, which is what gives mouse-look its depth.
function frame() {
  const w = viewW, h = viewH;
  const u = Math.min(w / 16, h / 9);
  const now = performance.now();
  const jolt = now < shake.until ? shake.amp * u * ((shake.until - now) / shake.ms) : 0;
  const jx = (Math.random() * 2 - 1) * jolt, jy = (Math.random() * 2 - 1) * jolt;
  const back = { x: -parallax.x * 0.16 * u + jx * 0.6, y: -parallax.y * 0.1 * u + jy * 0.6 };
  const front = { x: -parallax.x * 0.32 * u + jx, y: -parallax.y * 0.18 * u + jy };
  const cx = w * 0.5, cy = h * 0.69, rx = Math.min(w * 0.45, 7.6 * u), ry = 1.9 * u;
  const table = { cx: cx + front.x, cy: cy + front.y, rx, ry };
  const seatPos = seats.map((s, i) => {
    const a = seatAngleDeg(i, seats.length);
    const p = ellipsePoint(cx + back.x, cy + back.y, rx * 0.96, ry * 0.92, a);
    const depth = Math.max(0, -Math.sin((a * Math.PI) / 180));
    return { x: p.x, y: p.y, k: 1.1 - 0.28 * depth };
  });
  const n = bomb.layouts.length;
  const nearW = n ? clamp(n * 2.15 * u, 3.4 * u, 9.2 * u) : 3.2 * u;
  const depth = 1.3 * u;
  const B = { cx: table.cx, top: table.cy - depth * 0.78, nearW, farW: nearW * 0.86, depth, frontH: 0.66 * u, n };
  return { w, h, u, back, front, table, seatPos, B };
}

// A point on the bomb's top face: a across (0..1), b from far edge to near (0..1).
function onTop(B, a, b) {
  const edge = B.farW + (B.nearW - B.farW) * b;
  return { x: B.cx + (a - 0.5) * edge, y: B.top + b * B.depth, k: edge / B.nearW };
}

function panelSpan(B, i) {
  return [(i + 0.06) / B.n, (i + 0.94) / B.n];
}

// Where a module's slot sits on the stage bomb - straight from the shared
// layout(), the same numbers every role's bomb face is placed from.
function slotPoint(B, i, slot) {
  const [a0, a1] = panelSpan(B, i);
  return onTop(B, a0 + (a1 - a0) * (0.1 + 0.8 * slot.x), 0.14 + 0.72 * slot.y);
}

function slotOf(ref) {
  const L = ref && bomb.layouts[ref.module];
  return (L && L.slots[ref.cell]) || null;
}

export function render(ts) {
  if (!ctx) return;
  if (ts === undefined) ts = performance.now();
  fit();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const F = frame();
  drawRoom(F);
  drawLamp(F, ts);
  seats.forEach((seat, i) => drawSeat(seat, F.seatPos[i], F, ts));
  drawTable(F, ts);
  seats.forEach((seat, i) => { if (seat.role === "mute") drawLectern(seat, F.seatPos[i], F); });
  drawBomb(F, ts);
  drawPointers(F, ts);
  drawHand(F);
  drawCharge(F, ts);
  drawVignette(F);
}

function lampColour(ts) {
  if (bomb.phase === "lost") return [255, 70, 50];
  if (bomb.phase === "won") return [120, 235, 150];
  if (bomb.phase === "running" && !bomb.paused && bomb.timeLeft != null && bomb.timeLeft < 30) {
    const k = 0.5 + 0.5 * Math.sin(ts / 140);
    return [255, Math.round(214 - 140 * k), Math.round(150 - 110 * k)];
  }
  return [255, 214, 150];
}

function drawRoom(F) {
  const { w, h, u } = F;
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, "#16181e");
  g.addColorStop(0.5, "#0f1115");
  g.addColorStop(1, "#07080a");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);
  const step = 1.3 * u, off = ((F.back.x % step) + step) % step;
  ctx.strokeStyle = "rgba(255,255,255,0.03)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = off - step; x < w + step; x += step) { ctx.moveTo(x, 0); ctx.lineTo(x, h * 0.5 + F.back.y); }
  ctx.stroke();
  ctx.fillStyle = "rgba(255,255,255,0.035)";
  ctx.fillRect(0, h * 0.5 + F.back.y, w, 2);
}

function drawLamp(F, ts) {
  const { u, table: T } = F;
  const [r, g, b] = lampColour(ts);
  const lx = F.w / 2 + F.back.x * 0.6, shadeY = 1.1 * u, shadeH = 0.42 * u, shadeW = 0.62 * u;
  const cone = ctx.createLinearGradient(0, shadeY + shadeH, 0, T.cy + T.ry * 0.4);
  cone.addColorStop(0, "rgba(" + r + "," + g + "," + b + ",0.15)");
  cone.addColorStop(1, "rgba(" + r + "," + g + "," + b + ",0)");
  ctx.fillStyle = cone;
  poly([{ x: lx - shadeW * 0.8, y: shadeY + shadeH }, { x: lx + shadeW * 0.8, y: shadeY + shadeH },
        { x: T.cx + T.rx * 0.62, y: T.cy + T.ry * 0.4 }, { x: T.cx - T.rx * 0.62, y: T.cy + T.ry * 0.4 }]);
  ctx.fill();
  ctx.strokeStyle = "#2a2d33";
  ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(lx, 0); ctx.lineTo(lx, shadeY); ctx.stroke();
  const glow = ctx.createRadialGradient(lx, shadeY + shadeH, 0, lx, shadeY + shadeH, 1.3 * u);
  glow.addColorStop(0, "rgba(" + r + "," + g + "," + b + ",0.5)");
  glow.addColorStop(1, "rgba(" + r + "," + g + "," + b + ",0)");
  ctx.fillStyle = glow;
  ctx.fillRect(lx - 1.3 * u, shadeY + shadeH - 0.2 * u, 2.6 * u, 1.5 * u);
  const shade = ctx.createLinearGradient(0, shadeY, 0, shadeY + shadeH);
  shade.addColorStop(0, "#30343b");
  shade.addColorStop(1, "#1b1d22");
  ctx.fillStyle = shade;
  poly([{ x: lx - shadeW * 0.32, y: shadeY }, { x: lx + shadeW * 0.32, y: shadeY },
        { x: lx + shadeW, y: shadeY + shadeH }, { x: lx - shadeW, y: shadeY + shadeH }]);
  ctx.fill();
  ctx.fillStyle = "rgb(" + r + "," + g + "," + b + ")";
  ctx.fillRect(lx - shadeW, shadeY + shadeH - 1.5, shadeW * 2, 1.5);
}

function drawTable(F, ts) {
  const { u, table: T } = F;
  ctx.fillStyle = "#050607";
  ctx.beginPath(); ctx.ellipse(T.cx, T.cy + 0.24 * u, T.rx, T.ry, 0, 0, Math.PI * 2); ctx.fill();
  const felt = ctx.createRadialGradient(T.cx, T.cy - T.ry * 0.3, T.ry * 0.2, T.cx, T.cy, T.rx);
  felt.addColorStop(0, "#2c2f2b");
  felt.addColorStop(0.6, "#1d201e");
  felt.addColorStop(1, "#111312");
  ctx.fillStyle = felt;
  ctx.beginPath(); ctx.ellipse(T.cx, T.cy, T.rx, T.ry, 0, 0, Math.PI * 2); ctx.fill();
  ctx.save();
  ctx.clip();
  const [r, g, b] = lampColour(ts);
  const pool = ctx.createRadialGradient(T.cx, T.cy - 0.2 * u, 0, T.cx, T.cy - 0.2 * u, T.rx * 0.62);
  pool.addColorStop(0, "rgba(" + r + "," + g + "," + b + ",0.17)");
  pool.addColorStop(1, "rgba(" + r + "," + g + "," + b + ",0)");
  ctx.fillStyle = pool;
  ctx.fillRect(T.cx - T.rx, T.cy - T.ry, T.rx * 2, T.ry * 2);
  ctx.restore();
  ctx.lineWidth = 0.16 * u;
  ctx.strokeStyle = "#3a2c20";
  ctx.beginPath(); ctx.ellipse(T.cx, T.cy, T.rx, T.ry, 0, 0, Math.PI * 2); ctx.stroke();
  ctx.lineWidth = 0.05 * u;
  ctx.strokeStyle = "rgba(255,210,160,0.16)";
  ctx.beginPath(); ctx.ellipse(T.cx, T.cy, T.rx, T.ry, 0, Math.PI * 1.08, Math.PI * 1.92); ctx.stroke();
}

function drawSeat(seat, P, F, ts) {
  const s = F.u * P.k, x = P.x, y = P.y;
  const col = ROLE_COLOUR[seat.role] || "#888888";
  ctx.fillStyle = seat.connected ? "#1a1c21" : "#111216";
  roundRect(x - 0.8 * s, y - 2.2 * s, 1.6 * s, 2.5 * s, 0.32 * s);
  ctx.fill();
  ctx.strokeStyle = seat.connected ? "#2a2e36" : "#1b1d22";
  ctx.lineWidth = 1;
  ctx.stroke();
  if (seat.connected) {
    if (seat.hasDetail) drawBust(seat, x, y, s, col, ts);
    else drawSilhouette(seat, x, y, s, col, ts);
  }
  ctx.font = "600 " + Math.max(9, Math.round(0.22 * F.u)) + "px " + FONT;
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = seat.connected ? col : "#3d414a";
  ctx.fillText(seat.role.toUpperCase() + (seat.connected ? "" : " \u00b7 EMPTY"), x, y - 2.34 * s);
}

function torsoPath(x, y, s, lift) {
  const sy = y - 0.95 * s - lift;
  ctx.beginPath();
  ctx.moveTo(x - 0.98 * s, y + 0.35 * s);
  ctx.lineTo(x - 0.94 * s, sy + 0.4 * s);
  ctx.quadraticCurveTo(x - 0.9 * s, sy, x - 0.42 * s, sy);
  ctx.lineTo(x + 0.42 * s, sy);
  ctx.quadraticCurveTo(x + 0.9 * s, sy, x + 0.94 * s, sy + 0.4 * s);
  ctx.lineTo(x + 0.98 * s, y + 0.35 * s);
  ctx.closePath();
  return sy;
}

function drawBust(seat, x, y, s, col, ts) {
  const g = seat.gesture;
  const bob = g === "nod" ? Math.sin(ts / 85) * 0.1 * s : 0;
  const wag = g === "shake" ? Math.sin(ts / 65) * 0.12 * s : 0;
  const shrug = g === "shrug" ? (0.5 + 0.5 * Math.sin(ts / 160)) * 0.14 * s : 0;
  const yawN = clamp(seat.displayYaw / YAW_RANGE, -1, 1);
  const pitchN = clamp(seat.displayPitch / PITCH_RANGE, -1, 1);

  const torso = ctx.createLinearGradient(0, y - 1.1 * s, 0, y + 0.35 * s);
  torso.addColorStop(0, lighten(col, 0.08));
  torso.addColorStop(1, darken(col, 0.6));
  ctx.fillStyle = torso;
  const sy = torsoPath(x, y, s, shrug);
  ctx.fill();
  ctx.fillStyle = darken(col, 0.3);
  ctx.fillRect(x - 0.15 * s, sy - 0.22 * s, 0.3 * s, 0.26 * s);

  const hx = x + wag + yawN * 0.06 * s, hy = y - 1.5 * s + bob + pitchN * 0.05 * s, hr = 0.44 * s;
  const head = ctx.createRadialGradient(hx - hr * 0.3, hy - hr * 0.35, hr * 0.1, hx, hy, hr);
  head.addColorStop(0, lighten(col, 0.6));
  head.addColorStop(1, lighten(col, 0.16));
  ctx.fillStyle = head;
  ctx.beginPath(); ctx.arc(hx, hy, hr, 0, Math.PI * 2); ctx.fill();

  // The face turns with the head: eyes slide toward where this player is
  // looking, and squint down when they're reading.
  const ex = hx + yawN * 0.17 * s, ey = hy - 0.02 * s + pitchN * 0.14 * s;
  if (seat.role !== "blind") {
    ctx.fillStyle = "#14161a";
    for (const d of [-1, 1]) {
      ctx.beginPath();
      ctx.ellipse(ex + d * 0.15 * s, ey, 0.055 * s, seat.gaze === "manual" ? 0.022 * s : 0.06 * s, 0, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  drawFlair(seat.role, hx, hy, ex, ey, s);
  drawGestureMarks(g, hx, hy, hr, s, ts);
}

// Cosmetic role flair - static identity only, carries no game information.
function drawFlair(role, hx, hy, ex, ey, s) {
  ctx.save();
  if (role === "blind") {
    ctx.fillStyle = "#121318";
    roundRect(hx - 0.47 * s, ey - 0.1 * s, 0.94 * s, 0.2 * s, 0.07 * s);
    ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,0.08)";
    ctx.fillRect(hx - 0.4 * s, ey - 0.08 * s, 0.8 * s, 0.03 * s);
  } else if (role === "deaf") {
    ctx.strokeStyle = "#121318";
    ctx.lineWidth = 0.08 * s;
    ctx.beginPath(); ctx.arc(hx, hy, 0.52 * s, Math.PI * 1.1, Math.PI * 1.9); ctx.stroke();
    ctx.fillStyle = "#121318";
    for (const d of [-1, 1]) {
      ctx.beginPath(); ctx.ellipse(hx + d * 0.45 * s, hy + 0.04 * s, 0.13 * s, 0.18 * s, 0, 0, Math.PI * 2); ctx.fill();
    }
  } else if (role === "mute") {
    ctx.translate(ex, ey + 0.22 * s);
    ctx.rotate(-0.12);
    ctx.fillStyle = "#e6dcc2";
    ctx.fillRect(-0.2 * s, -0.055 * s, 0.4 * s, 0.11 * s);
    ctx.strokeStyle = "rgba(0,0,0,0.25)";
    ctx.lineWidth = 1;
    ctx.strokeRect(-0.2 * s, -0.055 * s, 0.4 * s, 0.11 * s);
  } else if (role === "scope") {
    ctx.strokeStyle = "#d4efe5";
    ctx.lineWidth = 0.05 * s;
    ctx.beginPath(); ctx.arc(ex + 0.15 * s, ey, 0.13 * s, 0, Math.PI * 2); ctx.stroke();
  } else if (role === "dispatch") {
    ctx.strokeStyle = "#121318";
    ctx.lineWidth = 0.07 * s;
    ctx.beginPath(); ctx.arc(hx, hy, 0.49 * s, Math.PI * 1.05, Math.PI * 1.95); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(hx + 0.45 * s, hy + 0.05 * s);
    ctx.quadraticCurveTo(hx + 0.42 * s, hy + 0.36 * s, ex + 0.05 * s, ey + 0.26 * s);
    ctx.stroke();
  }
  ctx.restore();
}

function drawGestureMarks(g, hx, hy, hr, s, ts) {
  if (!g) return;
  ctx.save();
  ctx.strokeStyle = "rgba(235,230,216,0.8)";
  ctx.lineWidth = Math.max(1.5, 0.05 * s);
  ctx.lineCap = "round";
  ctx.globalAlpha = 0.55 + 0.45 * Math.sin(ts / 90);
  if (g === "shake") {
    for (const d of [-1, 1]) {
      const c = d < 0 ? Math.PI : 0;
      ctx.beginPath(); ctx.arc(hx + d * (hr + 0.12 * s), hy, 0.22 * s, c - Math.PI / 4, c + Math.PI / 4); ctx.stroke();
    }
  } else if (g === "nod") {
    for (const d of [-1, 1]) {
      const c = d < 0 ? Math.PI * 1.5 : Math.PI * 0.5;
      ctx.beginPath(); ctx.arc(hx, hy + d * (hr + 0.1 * s), 0.22 * s, c - Math.PI / 4, c + Math.PI / 4); ctx.stroke();
    }
  } else if (g === "shrug") {
    for (const d of [-1, 1]) {
      ctx.beginPath(); ctx.moveTo(hx + d * 0.7 * s, hy + 0.2 * s); ctx.lineTo(hx + d * 0.85 * s, hy - 0.05 * s); ctx.stroke();
    }
  }
  ctx.restore();
}

// What BLIND gets instead of a person: a pale outline that pings when it
// moves. Position and gross motion only - hard rule 5.
function drawSilhouette(seat, x, y, s, col, ts) {
  ctx.save();
  ctx.strokeStyle = rgba(col, 0.5);
  ctx.fillStyle = rgba(col, 0.07);
  ctx.lineWidth = 1.5;
  torsoPath(x, y, s, 0);
  ctx.fill(); ctx.stroke();
  ctx.beginPath(); ctx.arc(x, y - 1.5 * s, 0.44 * s, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  if (seat.moving) {
    for (let k = 0; k < 2; k++) {
      const ph = (ts / 1100 + k * 0.5) % 1;
      ctx.strokeStyle = rgba(col, 0.55 * (1 - ph));
      ctx.beginPath(); ctx.arc(x, y - 1.2 * s, 0.5 * s + ph * 1.3 * s, 0, Math.PI * 2); ctx.stroke();
    }
  }
  ctx.restore();
}

// MUTE's lectern: a fixed WORLD prop. The book lights up only when MUTE's
// gaze is "manual" - a key BLIND never receives, so for BLIND it stays dark.
function drawLectern(seat, P, F) {
  const s = F.u * P.k;
  const x = P.x + (F.front.x - F.back.x), y = P.y + 0.1 * s + (F.front.y - F.back.y);
  const reading = seat.connected && seat.gaze === "manual";
  if (reading) {
    const glow = ctx.createRadialGradient(x, y, 0, x, y, 0.9 * s);
    glow.addColorStop(0, "rgba(255,226,168,0.35)");
    glow.addColorStop(1, "rgba(255,226,168,0)");
    ctx.fillStyle = glow;
    ctx.fillRect(x - 0.9 * s, y - 0.9 * s, 1.8 * s, 1.8 * s);
  }
  ctx.fillStyle = "#2b241d";
  poly([{ x: x - 0.5 * s, y: y + 0.18 * s }, { x: x + 0.5 * s, y: y + 0.18 * s },
        { x: x + 0.4 * s, y: y - 0.12 * s }, { x: x - 0.4 * s, y: y - 0.12 * s }]);
  ctx.fill();
  ctx.strokeStyle = "#433629";
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.fillStyle = reading ? "#f6e9c8" : "#9d9481";
  poly([{ x: x - 0.36 * s, y: y - 0.1 * s }, { x: x - 0.02 * s, y: y - 0.06 * s },
        { x: x - 0.02 * s, y: y + 0.12 * s }, { x: x - 0.42 * s, y: y + 0.14 * s }]);
  ctx.fill();
  poly([{ x: x + 0.36 * s, y: y - 0.1 * s }, { x: x + 0.02 * s, y: y - 0.06 * s },
        { x: x + 0.02 * s, y: y + 0.12 * s }, { x: x + 0.42 * s, y: y + 0.14 * s }]);
  ctx.fill();
}

function drawBomb(F, ts) {
  const { B, u } = F;
  const tl = onTop(B, 0, 0), tr = onTop(B, 1, 0), br = onTop(B, 1, 1), bl = onTop(B, 0, 1);
  const fy = bl.y + B.frontH;

  ctx.fillStyle = "rgba(0,0,0,0.5)";
  ctx.beginPath(); ctx.ellipse(B.cx, fy + 0.04 * u, B.nearW * 0.6, 0.3 * u, 0, 0, Math.PI * 2); ctx.fill();

  let g = ctx.createLinearGradient(0, bl.y, 0, fy);
  g.addColorStop(0, "#272b32");
  g.addColorStop(1, "#141619");
  ctx.fillStyle = g;
  poly([bl, br, { x: br.x, y: fy }, { x: bl.x, y: fy }]);
  ctx.fill();

  g = ctx.createLinearGradient(0, tl.y, 0, bl.y);
  g.addColorStop(0, "#2b2f37");
  g.addColorStop(1, "#383d47");
  ctx.fillStyle = g;
  poly([tl, tr, br, bl]);
  ctx.fill();
  ctx.strokeStyle = "#4b515d";
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.strokeStyle = "rgba(255,255,255,0.14)";
  ctx.beginPath(); ctx.moveTo(bl.x, bl.y); ctx.lineTo(br.x, br.y); ctx.stroke();

  if (bomb.phase === "won" || bomb.phase === "lost") {
    ctx.fillStyle = bomb.phase === "won" ? "rgba(79,174,104,0.2)" : "rgba(224,71,47,0.24)";
    poly([tl, tr, br, bl]);
    ctx.fill();
  }

  if (!B.n) {
    const c = onTop(B, 0.5, 0.5);
    ctx.save();
    ctx.translate(c.x, c.y);
    ctx.scale(1, 0.55);
    ctx.font = "700 " + Math.round(0.3 * u) + "px " + FONT;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "rgba(235,230,216,0.2)";
    ctx.fillText("BLACKBOX", 0, 0);
    ctx.restore();
  }
  for (let i = 0; i < B.n; i++) drawPanel(F, i);
  drawDisplay(F, bl, br, ts);

  if (bomb.phase === "lost") {
    for (let k = 0; k < 7; k++) {
      const ph = (ts / 2400 + k / 7) % 1;
      const sx = B.cx + Math.sin(k * 2.1 + ts / 900) * 0.45 * u * (0.5 + ph);
      ctx.fillStyle = "rgba(70,70,74," + (0.32 * (1 - ph)).toFixed(3) + ")";
      ctx.beginPath(); ctx.arc(sx, B.top - ph * 2.6 * u, (0.25 + ph * 0.7) * u, 0, Math.PI * 2); ctx.fill();
    }
  }
}

function drawPanel(F, i) {
  const { B, u } = F;
  const [a0, a1] = panelSpan(B, i);
  ctx.fillStyle = "#1a1d22";
  poly([onTop(B, a0, 0.08), onTop(B, a1, 0.08), onTop(B, a1, 0.92), onTop(B, a0, 0.92)]);
  ctx.fill();
  ctx.strokeStyle = "#424854";
  ctx.lineWidth = 1;
  ctx.stroke();
  const L = bomb.layouts[i];
  for (const slot of L.slots) {
    const q = slotPoint(B, i, slot);
    drawSlotGlyph(slot.kind, q, 0.105 * u * q.k, L.h || 1);
  }
}

// A slot's shape from its WORLD kind - grey and identical for every viewer.
function drawSlotGlyph(kind, p, s, rows) {
  ctx.save();
  ctx.lineWidth = Math.max(1, s * 0.22);
  ctx.strokeStyle = "#8d939e";
  ctx.fillStyle = "#2c3038";
  if (kind === "wire") {
    const half = s * (rows > 1 ? 1.1 : 3.0);
    ctx.lineCap = "round";
    ctx.strokeStyle = "#a9a294";
    ctx.lineWidth = Math.max(1.2, s * 0.45);
    ctx.beginPath(); ctx.moveTo(p.x, p.y - half); ctx.lineTo(p.x, p.y + half); ctx.stroke();
    ctx.fillStyle = "#6b6f78";
    ctx.fillRect(p.x - s * 0.5, p.y - half - s * 0.3, s, s * 0.5);
    ctx.fillRect(p.x - s * 0.5, p.y + half - s * 0.2, s, s * 0.5);
  } else if (kind === "tile") {
    ctx.fillStyle = "#8f8a7e";
    roundRect(p.x - s * 1.2, p.y - s * 0.8, s * 2.4, s * 1.6, s * 0.3);
    ctx.fill();
  } else if (kind === "dial") {
    ctx.beginPath(); ctx.arc(p.x, p.y, s * 2.4, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.arc(p.x, p.y, s * 0.7, 0, Math.PI * 2); ctx.stroke();
  } else if (kind === "vent") {
    roundRect(p.x - s * 1.3, p.y - s * 0.9, s * 2.6, s * 1.8, s * 0.3);
    ctx.fill(); ctx.stroke();
    ctx.beginPath();
    for (let k = -1; k <= 1; k++) { ctx.moveTo(p.x - s * 0.9, p.y + k * s * 0.45); ctx.lineTo(p.x + s * 0.9, p.y + k * s * 0.45); }
    ctx.stroke();
  } else if (kind === "button") {
    ctx.beginPath(); ctx.arc(p.x, p.y, s * 1.6, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.arc(p.x, p.y, s * 0.8, 0, Math.PI * 2); ctx.stroke();
  } else {
    ctx.beginPath(); ctx.arc(p.x, p.y, s * 0.6, 0, Math.PI * 2); ctx.fill();
  }
  ctx.restore();
}

// The bomb's own little timer display and strike LEDs, on its front face.
function drawDisplay(F, bl, br, ts) {
  const { B, u } = F;
  const h = B.frontH * 0.6, w = Math.min((br.x - bl.x) * 0.48, 2.1 * u);
  const ledsW = bomb.maxStrikes * h * 0.55;
  const x = B.cx - (w + 0.2 * u + ledsW) / 2, y = bl.y + (B.frontH - h) / 2;
  ctx.fillStyle = "#0a0605";
  roundRect(x, y, w, h, 3);
  ctx.fill();
  ctx.strokeStyle = "#2e1d18";
  ctx.lineWidth = 1;
  ctx.stroke();
  let col = "#ff5a3c";
  if (bomb.phase === "won") col = OK;
  else if (bomb.timeLeft == null) col = "#5a3a33";
  ctx.font = "700 " + Math.round(h * 0.78) + "px " + FONT;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "rgba(255,90,60,0.08)";
  ctx.fillText("88:88", x + w / 2, y + h / 2 + 1);
  if (!(bomb.paused && Math.floor(ts / 500) % 2)) {
    ctx.shadowColor = col;
    ctx.shadowBlur = 8;
    ctx.fillStyle = col;
    ctx.fillText(bomb.timeLeft == null ? "--:--" : mmss(bomb.timeLeft), x + w / 2, y + h / 2 + 1);
    ctx.shadowBlur = 0;
  }
  for (let i = 0; i < bomb.maxStrikes; i++) {
    const lit = i < bomb.strikes;
    ctx.beginPath();
    ctx.arc(x + w + 0.2 * u + h * 0.275 + i * h * 0.55, y + h / 2, h * 0.2, 0, Math.PI * 2);
    ctx.fillStyle = lit ? HOT : "#2a1714";
    if (lit) { ctx.shadowColor = HOT; ctx.shadowBlur = 10; }
    ctx.fill();
    ctx.shadowBlur = 0;
  }
}

function seatHandPoint(F, i) {
  const P = F.seatPos[i], s = F.u * P.k;
  return { x: P.x + (F.table.cx >= P.x ? 1 : -1) * 0.6 * s, y: P.y - 0.55 * s };
}

// Pointer beams: from each seat that has a pointer (keys BLIND never gets
// for others) and from our own, to the pointed module - or slot, when the
// match allows precise pointing.
function drawPointers(F, ts) {
  const { B, u } = F;
  const list = [];
  seats.forEach((seat, i) => {
    if (seat.connected && seat.pointer) list.push({ role: seat.role, pointer: seat.pointer, from: seatHandPoint(F, i) });
  });
  if (ownPointer) list.push({ role: myRole, pointer: ownPointer, from: { x: F.w * 0.36 + F.front.x, y: F.h + 0.2 * u } });
  for (const { role, pointer, from } of list) {
    const m = pointer.module;
    if (!(m >= 0 && m < B.n)) continue;
    const col = ROLE_COLOUR[role] || "#cccccc";
    const [a0, a1] = panelSpan(B, m);
    const slot = pointer.cell != null ? slotOf(pointer) : null;
    const to = slot ? slotPoint(B, m, slot) : onTop(B, (a0 + a1) / 2, 0.5);
    ctx.save();
    ctx.strokeStyle = col;
    ctx.shadowColor = col;
    ctx.shadowBlur = 14;
    ctx.lineWidth = Math.max(2, 0.05 * u);
    poly([onTop(B, a0, 0.03), onTop(B, a1, 0.03), onTop(B, a1, 0.97), onTop(B, a0, 0.97)]);
    ctx.stroke();
    ctx.shadowBlur = 6;
    ctx.setLineDash([0.16 * u, 0.12 * u]);
    ctx.lineDashOffset = -ts / 30;
    ctx.strokeStyle = rgba(col, 0.85);
    ctx.lineWidth = Math.max(1.5, 0.045 * u);
    ctx.beginPath(); ctx.moveTo(from.x, from.y); ctx.lineTo(to.x, to.y); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = col;
    ctx.beginPath(); ctx.arc(to.x, to.y, 0.07 * u, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }
}

// BLIND's hand (T9 probe echo): an arm from BLIND's seat - or from the bottom
// of the screen when you ARE blind - that crawls between slots instead of
// jumping, so everyone can watch it search.
function drawHand(F) {
  const pr = blindBody.probe;
  const slot = slotOf(pr);
  if (!slot) { hand = null; return; }
  const { u } = F;
  const t = slotPoint(F.B, pr.module, slot);
  if (!hand) hand = { x: t.x, y: t.y };
  hand.x = smoothTowards(hand.x, t.x, frameDt, 12);
  hand.y = smoothTowards(hand.y, t.y, frameDt, 12);
  let from;
  if (myRole === "blind") from = { x: F.w * 0.78 + F.front.x, y: F.h + 0.5 * u };
  else {
    const i = seats.findIndex(s => s.role === "blind");
    if (i < 0 || !seats[i].connected) return;
    from = seatHandPoint(F, i);
  }
  const col = ROLE_COLOUR.blind;
  const glow = ctx.createRadialGradient(t.x, t.y, 0, t.x, t.y, 0.5 * u);
  glow.addColorStop(0, rgba(col, 0.45));
  glow.addColorStop(1, rgba(col, 0));
  ctx.fillStyle = glow;
  ctx.fillRect(t.x - 0.5 * u, t.y - 0.5 * u, u, u);
  ctx.save();
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.quadraticCurveTo((from.x + hand.x) / 2, Math.min(from.y, hand.y) - 0.5 * u, hand.x, hand.y - 0.12 * u);
  ctx.strokeStyle = darken(col, 0.4);
  ctx.lineWidth = 0.26 * u;
  ctx.stroke();
  ctx.strokeStyle = col;
  ctx.lineWidth = 0.17 * u;
  ctx.stroke();
  ctx.fillStyle = lighten(col, 0.45);
  ctx.beginPath(); ctx.ellipse(hand.x, hand.y - 0.12 * u, 0.17 * u, 0.13 * u, 0, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = lighten(col, 0.7);
  ctx.beginPath(); ctx.arc(hand.x, hand.y, 0.07 * u, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}

// The commit ring (hard rule 12 / T10), on the bomb itself, for everyone.
function drawCharge(F, ts) {
  const c = blindBody.charge;
  const slot = slotOf(c);
  if (!slot) { chargeShown = 0; return; }
  if (c.progress < chargeShown - 0.25) chargeShown = c.progress;   // a fresh hold began
  chargeShown = smoothTowards(chargeShown, c.progress, frameDt, 16);
  const { u } = F;
  const p = slotPoint(F.B, c.module, slot);
  const r = 0.34 * u;
  ctx.save();
  const pulse = 0.6 + 0.4 * Math.sin(ts / 70);
  const halo = ctx.createRadialGradient(p.x, p.y, r * 0.3, p.x, p.y, r * 2.2);
  halo.addColorStop(0, "rgba(224,71,47," + (0.42 * pulse).toFixed(3) + ")");
  halo.addColorStop(1, "rgba(224,71,47,0)");
  ctx.fillStyle = halo;
  ctx.fillRect(p.x - r * 2.2, p.y - r * 2.2, r * 4.4, r * 4.4);
  ctx.lineWidth = 0.09 * u;
  ctx.lineCap = "round";
  ctx.strokeStyle = "rgba(224,71,47,0.25)";
  ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.stroke();
  ctx.strokeStyle = "#ff6a4d";
  ctx.shadowColor = HOT;
  ctx.shadowBlur = 14;
  ctx.beginPath();
  ctx.arc(p.x, p.y, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.max(0.001, chargeShown));
  ctx.stroke();
  ctx.shadowBlur = 0;
  ctx.font = "700 " + Math.round(0.2 * u) + "px " + FONT;
  ctx.textAlign = "center";
  ctx.textBaseline = "bottom";
  ctx.fillStyle = "#ff8a70";
  ctx.fillText(c.kind === "discharge" ? "DISCHARGING" : "COMMITTING", p.x, p.y - r - 0.08 * u);
  ctx.restore();
}

function drawVignette(F) {
  const g = ctx.createRadialGradient(F.w / 2, F.h * 0.55, Math.min(F.w, F.h) * 0.35, F.w / 2, F.h * 0.55, Math.max(F.w, F.h) * 0.75);
  g.addColorStop(0, "rgba(0,0,0,0)");
  g.addColorStop(1, "rgba(0,0,0,0.6)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, F.w, F.h);
}
