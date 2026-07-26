// The shared-room diorama: a table with the bomb at its centre and the other
// players seated across from you. This file only ever reads WORLD data
// (module count, bomb phase) and PRESENCE data (pose/connection/movement) -
// never a module's views() - so it cannot leak PERCEPTION no matter how the
// drawing code grows later. Kept behind a small interface
// (init/setPresence/setBomb/render) so a future renderer (e.g. a real 3D
// engine) can replace this file without any server or game code changing -
// see AGENTS.md T7.
//
// Deliberately NOT wired to the network here: mouse movement only pans the
// local view (a parallax effect standing in for "moving your head"). Turning
// that into a real `pose` message sent to the server is T11's job. Likewise,
// gestures, pointer rays and the commit-hold ring are not drawn yet - those
// are T9/T10/T11/T12, once the interactions themselves exist to design UX for.

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

let canvas = null, ctx = null;
let seats = [];   // [{role, connected, moving, hasDetail, yaw, pitch, displayYaw, displayPitch}]
let bomb = { phase: "running", moduleCount: 0 };
let parallax = { x: 0, y: 0, targetX: 0, targetY: 0 };
let lastTs = null;
let looping = false;

export function init(canvasEl, role) {
  canvas = canvasEl;
  ctx = canvas.getContext("2d");
  seats = seatOrder(role).map(r => ({
    role: r, connected: false, moving: false, hasDetail: false,
    yaw: 0, pitch: 0, displayYaw: 0, displayPitch: 0,
  }));

  canvas.addEventListener("mousemove", e => {
    const r = canvas.getBoundingClientRect();
    parallax.targetX = clamp(((e.clientX - r.left) / r.width) * 2 - 1, -1, 1);
    parallax.targetY = clamp(((e.clientY - r.top) / r.height) * 2 - 1, -1, 1);
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
// server/stage.py) - yaw/pitch. Never stores gesture/pointer/gaze: those are
// added deliberately in T9/T11/T12, not smuggled in early unused.
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

  render(ts);
  requestAnimationFrame(tick);
}

export function render(ts) {
  if (!ctx) return;
  if (ts === undefined) ts = performance.now();
  const w = canvas.width, h = canvas.height;
  ctx.fillStyle = BG;
  ctx.fillRect(0, 0, w, h);

  // Local-only head parallax - stands in for "mouse moves your head" until
  // T11 also sends it to the server as a real pose message.
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

  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.translate(p.x, p.y);
  ctx.rotate(clamp(yaw, -0.6, 0.6) * 0.3); // a subtle head tilt, not a spin

  ctx.fillStyle = seat.connected ? ROLE_COLOUR[seat.role] : "#2a2a2a";
  ctx.strokeStyle = seat.connected ? FG : DIM;
  ctx.lineWidth = 1.5;

  ctx.beginPath(); // shoulders
  ctx.ellipse(0, 16, 20, 12, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  ctx.beginPath(); // head
  ctx.arc(0, -6, 12, 0, Math.PI * 2);
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
