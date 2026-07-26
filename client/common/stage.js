// The shared-room diorama: a table with the bomb at its centre and the other
// players seated across from you. This file only ever reads WORLD data
// (module count, bomb phase) and PRESENCE data (pose/connection/movement) -
// never a module's views() - so it cannot leak PERCEPTION no matter how the
// drawing code grows later. Kept behind a small interface
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

const ROLE_ORDER = ["hands", "eyes", "book", "scope", "dispatch"];

// Avatar legend colours only. Deliberately NOT the same hues M1 uses for wire
// colours (red/blue/yellow/white/black/green), so a bust on the stage can
// never be mistaken for a piece of module PERCEPTION.
const ROLE_COLOUR = {
  hands: "#7d8fce",
  eyes: "#cd8b62",
  book: "#a678b0",
  scope: "#5fae96",
  dispatch: "#b8637e",
};

const BG = "#111318";
const FG = "#e8e4d8";
const DIM = "#4a4a4a";
const HOT = "#c8402f";
const OK = "#4c9a5a";

const TABLE = { cx: 0.5, cy: 0.66, rx: 0.40, ry: 0.15 };
const SEAT_ARC = [205, 335]; // degrees: the far rim of the table, across from the camera

// T11 tuning. Expect these to move once real people try it - see the design
// doc's own "expect to change T9-T12 based on what happens" note.
const YAW_RANGE = 0.6;             // radians of head yaw at full mouse deflection
const PITCH_RANGE = 0.4;           // radians of head pitch at full mouse deflection
const MANUAL_GAZE_PITCH = 0.22;    // pitch past this (looking down) => gaze:"manual"
const POSE_SEND_HZ_MS = 100;       // ~10Hz outgoing pose - well under presence's 20Hz
const GESTURE_WINDOW_MS = 500;     // how far back the shake/nod detector looks
const GESTURE_THRESHOLD = 0.9;     // oscillation "energy" needed to fire
const GESTURE_MARGIN = 1.3;        // how much bigger one axis must be than the other
const GESTURE_COOLDOWN_MS = 700;   // minimum gap between two emitted gestures

export function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

// Frame-rate-independent exponential easing: closes `rate`'s share of the
// remaining distance to `target` per second, regardless of dt. Used for both
// the local mouse parallax and other players' head interpolation, so nothing
// ever snaps between presence frames.
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
// by eyes.html/book.html/scope.html for both HANDS' probe echo (T9) and
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
let seats = [];   // [{role, connected, moving, hasDetail, yaw, pitch, displayYaw, displayPitch, gesture}]
let bomb = { phase: "running", moduleCount: 0 };
let parallax = { x: 0, y: 0, targetX: 0, targetY: 0 };
let lastTs = null;
let looping = false;
let sendFn = () => {};
let gestureDetector = null;
let lastPoseSentAt = -Infinity;

// Third argument is the same `send` exported by common/net.js - passed in
// rather than imported directly so this file still has zero import of
// net.js, keeping it swappable/testable independent of the transport layer.
// Omit it (e.g. in tests) and pose/gesture detection simply has nowhere to
// send - everything else (parallax, rendering) still works.
export function init(canvasEl, role, send) {
  canvas = canvasEl;
  ctx = canvas.getContext("2d");
  sendFn = typeof send === "function" ? send : () => {};
  gestureDetector = makeGestureDetector();
  seats = seatOrder(role).map(r => ({
    role: r, connected: false, moving: false, hasDetail: false,
    yaw: 0, pitch: 0, displayYaw: 0, displayPitch: 0, gesture: null,
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

// PRESENCE in. Only ever stores role/connected/moving, and - only when the
// server actually included them (never for HANDS viewing other players; see
// server/stage.py) - yaw/pitch/gesture. Never stores pointer: that's T12's
// job, not smuggled in early unused.
export function setPresence(payload) {
  const byRole = {};
  for (const p of (payload.players || [])) byRole[p.role] = p;
  for (const seat of seats) {
    const p = byRole[seat.role];
    if (!p) continue;
    seat.connected = !!p.connected;
    seat.moving = !!p.moving;
    seat.hasDetail = "yaw" in p;
    if (seat.hasDetail) {
      seat.yaw = p.yaw || 0;
      seat.pitch = p.pitch || 0;
      seat.gesture = p.gesture || null;
    } else {
      seat.gesture = null;
    }
  }
}

// WORLD in. Only ever reads `phase` (shared game state, already identical
// for every role) and the module count from `layouts` (shared geometry, see
// T4). Immediately discards everything else in the snapshot - this file
// physically cannot grow a dependency on any role's views() later by
// accident, because it never keeps a reference to the full object.
export function setBomb(snapshot) {
  bomb = {
    phase: snapshot.phase || "running",
    moduleCount: (snapshot.layouts || []).length,
  };
}

function tick(ts) {
  const dt = lastTs == null ? 0 : Math.min(0.1, (ts - lastTs) / 1000);
  lastTs = ts;

  parallax.x = smoothTowards(parallax.x, parallax.targetX, dt, 6);
  parallax.y = smoothTowards(parallax.y, parallax.targetY, dt, 6);
  for (const seat of seats) {
    seat.displayYaw = smoothTowards(seat.displayYaw, seat.yaw, dt, 8);
    seat.displayPitch = smoothTowards(seat.displayPitch, seat.pitch, dt, 8);
  }

  if (ts - lastPoseSentAt > POSE_SEND_HZ_MS) {
    lastPoseSentAt = ts;
    const yaw = parallax.x * YAW_RANGE;
    const pitch = parallax.y * PITCH_RANGE;
    // "manual" stands in for looking down at BOOK's lectern until T12 gives
    // BOOK an actual in-world manual object to look at; "bomb" is the
    // sensible default since that's what's in front of the camera otherwise.
    const gaze = pitch > MANUAL_GAZE_PITCH ? "manual" : "bomb";
    sendFn({ type: "pose", yaw, pitch, gaze });
  }

  render(ts);
  requestAnimationFrame(tick);
}

export function render(ts) {
  if (!ctx) return;
  if (ts === undefined) ts = performance.now();
  const w = canvas.width, h = canvas.height;
  ctx.fillStyle = BG;
  ctx.fillRect(0, 0, w, h);

  // Local head parallax - the camera itself pans opposite the mouse. The
  // yaw/pitch actually sent to the server (in tick(), above) comes from the
  // same underlying parallax state, so what other players see matches what
  // moved this camera.
  const px = -parallax.x * 14, py = -parallax.y * 8;
  ctx.save();
  ctx.translate(px, py);

  drawTable(w, h);
  drawBomb(w, h, ts);
  for (let i = 0; i < seats.length; i++) {
    drawSeat(seats[i], i, seats.length, w, h, ts);
  }

  ctx.restore();
}

function drawTable(w, h) {
  ctx.strokeStyle = "#333";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.ellipse(w * TABLE.cx, h * TABLE.cy, w * TABLE.rx, h * TABLE.ry, 0, 0, Math.PI * 2);
  ctx.stroke();
}

function drawBomb(w, h, ts) {
  const cx = w * TABLE.cx, cy = h * TABLE.cy;
  const colour = bomb.phase === "won" ? OK : bomb.phase === "lost" ? HOT : FG;
  const pulse = bomb.phase === "running" ? 0.85 + 0.15 * Math.sin(ts / 400) : 1;
  const boxW = 90, boxH = 46;

  ctx.save();
  ctx.globalAlpha = pulse;
  ctx.strokeStyle = colour;
  ctx.lineWidth = 2;
  ctx.strokeRect(cx - boxW / 2, cy - boxH / 2, boxW, boxH);

  // One tick per module - a placeholder only. T8 replaces this box with real
  // per-role skins painted from this same shared layout() geometry.
  const n = Math.max(1, bomb.moduleCount);
  ctx.fillStyle = colour;
  for (let i = 0; i < bomb.moduleCount; i++) {
    const fx = cx - boxW / 2 + ((i + 0.5) / n) * boxW;
    ctx.fillRect(fx - 2, cy - 4, 4, 8);
  }
  ctx.restore();
}

function drawSeat(seat, index, total, w, h, ts) {
  const angle = seatAngleDeg(index, total);
  const p = ellipsePoint(w * TABLE.cx, h * TABLE.cy, w * TABLE.rx, h * TABLE.ry, angle);

  const base = seat.connected ? 1 : 0.28;
  let alpha = base;
  if (seat.connected && !seat.hasDetail && seat.moving) {
    // HANDS' "sonar" view of others: a pulse on movement instead of a
    // rotating head, because HANDS never receives yaw/pitch/gesture for
    // other players - AGENTS.md hard rule 5.
    alpha = base * (0.55 + 0.45 * Math.sin(ts / 150));
  }
  const yaw = seat.hasDetail ? seat.displayYaw : 0;

  // Gesture animation: a brief bob (nod) or wag (shake) on the head only -
  // gated on hasDetail, same as yaw/pitch, so HANDS never animates other
  // seats this way either (hard rule 5 holds structurally, not by role-check).
  let bobY = 0, wagX = 0;
  if (seat.hasDetail && seat.gesture === "nod") bobY = Math.sin(ts / 90) * 5;
  if (seat.hasDetail && seat.gesture === "shake") wagX = Math.sin(ts / 70) * 6;

  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.translate(p.x, p.y);
  ctx.rotate(clamp(yaw, -0.6, 0.6) * 0.3); // a subtle head tilt, not a spin

  ctx.fillStyle = seat.connected ? ROLE_COLOUR[seat.role] : "#2a2a2a";
  ctx.strokeStyle = seat.connected ? FG : DIM;
  ctx.lineWidth = 1.5;

  ctx.beginPath(); // shoulders (gestures move the head, not the shoulders)
  ctx.ellipse(0, 16, 20, 12, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  ctx.beginPath(); // head
  ctx.arc(wagX, -6 + bobY, 12, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  ctx.restore();

  ctx.save();
  ctx.globalAlpha = Math.max(alpha, 0.5);
  ctx.fillStyle = seat.connected ? FG : DIM;
  ctx.font = "11px monospace";
  ctx.textAlign = "center";
  ctx.fillText(seat.role.toUpperCase(), p.x, p.y + 40);
  ctx.restore();
}
