// Per-role bomb skins - AGENTS.md hard rule 3, "one geometry, three skins".
// bombface.js positions one element per slot from the shared layout(); the
// painters here decide what goes INSIDE each element, and each one reads
// only the view its own role's page already received from the server. A
// painter handed BLIND's view has no colour to paint because BLIND's payload
// never contained one - this file changes how things look, never what any
// role knows.
import { paintCharge, renderBombFace } from "/common/bombface.js";

const SWATCH = {
  red: "#c8372d", blue: "#2f6fd0", yellow: "#e2c230", white: "#e8e6df",
  black: "#141414", green: "#2f9e4a", amber: "#d98a1c", teal: "#1f9a94",
};
export function swatch(name) { return SWATCH[name] || "#555"; }

export const esc = v => String(v ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// Rebuild a slot's inner DOM only when what it shows actually changed, so
// presence frames arriving at 20Hz don't restart a CSS animation or
// transition (a glowing vent, a swinging needle) every 50ms.
function setInner(el, key, html) {
  if (el._key === key) return false;
  el._key = key;
  el.innerHTML = html;
  return true;
}

// BLIND's hand and the commit ring (PRESENCE: indices and progress only,
// never what BLIND felt). Call after the skin painter, which may have
// replaced the slot's children.
export function markPresence(el, probed, chargeProgress) {
  el.classList.toggle("probed", !!probed);
  el.classList.toggle("charging", chargeProgress != null);
  paintCharge(el, chargeProgress);
}

// Decorative braille-style dots for Ledger tiles (AGENTS.md T14: client-side
// flavour, no real encoding). Derived from the slot index alone.
function dotArt(i) {
  const bits = [0b101100, 0b110010, 0b011001, 0b100110, 0b010101, 0b111000][i % 6];
  let html = '<div class="dots">';
  for (let b = 0; b < 6; b++) html += '<i class="' + ((bits >> b) & 1 ? "on" : "") + '"></i>';
  return html + "</div>";
}

function dialSVG(n) {
  let marks = "";
  for (let k = 1; k <= n; k++) {
    const a = (k / n) * 2 * Math.PI, sx = Math.sin(a), sy = -Math.cos(a);
    marks += '<line class="tick" x1="' + (sx * 78).toFixed(1) + '" y1="' + (sy * 78).toFixed(1) +
      '" x2="' + (sx * 87).toFixed(1) + '" y2="' + (sy * 87).toFixed(1) + '"/>' +
      '<text x="' + (sx * 63).toFixed(1) + '" y="' + (sy * 63).toFixed(1) + '">' + k + "</text>";
  }
  return '<svg class="dial" viewBox="-100 -100 200 200"><circle class="rim" r="97"/><circle class="face" r="89"/>' +
    marks + '<g class="needle"><path d="M-5 12 L0 -74 L5 12 Z"/><circle r="9"/></g></svg>';
}

// DEAF: full exterior detail for one slot of the current module.
export function paintDeaf(el, view, i) {
  let done = false, glowing = false, syncing = false;
  switch (view.kind) {
    case "ledger": {
      const t = (view.tiles || [])[i] || {};
      done = !!t.resolved;
      setInner(el, "l|" + t.value + "|" + i, '<div class="tile-face">' + dotArt(i) +
        '<span class="tile-num">' + esc(t.value) + '</span></div><div class="slot-cap">' + (i + 1) + "</div>");
      break;
    }
    case "gauge": {
      const n = view.count || 12;
      if (setInner(el, "g|" + n, dialSVG(n) + '<div class="slot-cap">NEEDLE AT <b class="needle-num"></b></div>')) el._angle = null;
      const pos = (view.position ?? 0) + 1;
      const target = pos * (360 / n);
      // The short way round, so 12 -> 1 sweeps one notch forward instead of
      // spinning all the way back.
      el._angle = el._angle == null ? target : el._angle + ((((target - el._angle) % 360) + 540) % 360) - 180;
      el.querySelector(".needle").style.transform = "rotate(" + el._angle + "deg)";
      el.querySelector(".needle-num").textContent = pos;
      break;
    }
    case "vent":
      glowing = view.glowing === i;
      setInner(el, "v|" + glowing + "|" + i, '<div class="vent-grille"></div><div class="slot-cap">VENT ' + (i + 1) +
        (glowing ? " \u00b7 <b>GLOWING</b>" : "") + "</div>");
      break;
    case "manifest": {
      const s = (view.stamps || [])[i] || {};
      done = !!s.pressed;
      setInner(el, "m|" + s.letter + "|" + i, '<div class="stamp">' + esc(s.letter) + '</div><div class="slot-cap">' + (i + 1) + "</div>");
      break;
    }
    case "static": {
      const t = (view.tiles || [])[i] || {};
      done = !!t.pressed;
      setInner(el, "s|" + t.colour + "|" + i, '<div class="swatch" style="--swatch:' + swatch(t.colour) + '"></div>' +
        '<div class="slot-cap">' + (i + 1) + " \u00b7 <b>" + esc(t.colour) + "</b></div>");
      break;
    }
    case "handshake":
      syncing = !!view.open;
      setInner(el, "h|" + syncing, '<div class="port"><i></i></div><span class="led' + (syncing ? " sync" : "") + '"></span>' +
        '<div class="slot-cap">' + (syncing ? "<b>SYNCING</b>" : "idle") + "</div>");
      break;
    default: {
      const w = (view.wires || [])[i] || {};
      const led = i === view.led_wire;
      done = !!w.cut;
      setInner(el, "w|" + w.colour + "|" + led + "|" + i, '<span class="led' + (led ? " on" : "") + '"' +
        (led ? ' title="This wire feeds the LED"' : "") + '></span><div class="wire" style="--wire:' + swatch(w.colour) +
        '"><span></span><span></span></div><div class="slot-cap">' + (i + 1) + " \u00b7 <b>" + esc(w.colour) + "</b></div>");
    }
  }
  el.classList.toggle("done", done);
  el.classList.toggle("glowing", glowing);
  el.classList.toggle("syncing", syncing);
}

// "cut" (wires), "resolved" (ledger) and "pressed" (manifest/static) all mean
// the same thing to BLIND: this cell can no longer be acted on.
export function doneList(view) {
  if (view.kind === "ledger") return view.resolved || [];
  if (view.kind === "manifest" || view.kind === "static") return view.pressed || [];
  return view.cut || [];
}

// BLIND: a featureless, tactile shell. Shape comes from the slot's WORLD
// kind (data-slot, set by bombface.js); state only from BLIND's own view.
export function paintTactile(el, view, i) {
  const discharged = view.kind === "wires" && (view.discharged || [])[i];
  let html;
  if (view.kind === "gauge") html = '<div class="knob"></div><div class="slot-cap">\u2190 TURN \u2192</div>';
  else if (view.kind === "handshake") html = '<div class="port"><i></i></div><div class="slot-cap">SYNC PORT</div>';
  else html = '<div class="bump"></div><div class="slot-cap">' + (i + 1) + (discharged ? " \u00b7 discharged" : "") + "</div>";
  setInner(el, view.kind + "|" + i + "|" + !!discharged, html);
  el.classList.toggle("done", !!doneList(view)[i]);
}

// MUTE/SCOPE: slot indices and nothing else.
export function paintShell(el, i) {
  setInner(el, "shell|" + i, '<b class="idx">' + (i + 1) + "</b>");
}

const findRow = (presence, role) => (presence && presence.players.find(p => p.role === role)) || null;

// MUTE's and SCOPE's view of every module at once: index-only shells (their
// own views carry no per-slot data), BLIND's fingertip and commit ring, and
// MUTE's module pointer - all PRESENCE. Pass onPoint to make modules
// clickable (MUTE); module names appear only if the viewer's own view has
// them.
export function renderShells(box, s, presence, { onPoint, pointLabel = "\u25C9 POINTING" } = {}) {
  if (box.querySelector(".chip")) box.innerHTML = "";
  const layouts = s.layouts || [];
  while (box.children.length > layouts.length) box.lastChild.remove();
  const blind = findRow(presence, "blind"), mute = findRow(presence, "mute");
  const probe = blind && blind.probe, charge = blind && blind.charge;
  const pointed = mute && mute.pointer ? mute.pointer.module : null;
  layouts.forEach((layout, i) => {
    let wrap = box.children[i];
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "shell-wrap" + (onPoint ? " pointable" : "");
      wrap.innerHTML = '<div class="shell-label"><span></span><span></span></div><div class="bombface shell"></div>';
      if (onPoint) wrap.onclick = () => onPoint(i);
      box.appendChild(wrap);
    }
    const mv = s.modules[i] || {};
    wrap.classList.toggle("pointed", i === pointed);
    wrap.classList.toggle("solved", !!mv.solved);
    const [name, tag] = wrap.querySelectorAll(".shell-label span");
    name.textContent = "MODULE " + (i + 1) + (mv.module ? " \u00b7 " + mv.module : "");
    tag.textContent = mv.solved ? "DEFUSED \u2713" : i === pointed ? pointLabel : "";
    const face = wrap.querySelector(".bombface");
    face.classList.toggle("pointed", i === pointed);
    renderBombFace(face, layout, (el, slot, idx) => {
      paintShell(el, idx);
      const here = ref => ref && ref.module === i && ref.cell === idx;
      markPresence(el, here(probe), here(charge) ? charge.progress : null);
    });
  });
}

// Module tabs for pages that show one module at a time (BLIND, DEAF).
export function renderTabs(container, modules, current, { pointed = null, onPick } = {}) {
  if (container.children.length !== modules.length) {
    container.innerHTML = "";
    modules.forEach((_, i) => {
      const b = document.createElement("button");
      b.className = "tab";
      b.textContent = "MODULE " + (i + 1);
      // Clicking must not steal keyboard focus - TAB and the arrow keys
      // drive these pages.
      b.addEventListener("mousedown", e => e.preventDefault());
      b.addEventListener("click", () => onPick && onPick(i));
      container.appendChild(b);
    });
  }
  modules.forEach((mv, i) => {
    const b = container.children[i];
    b.classList.toggle("current", i === current);
    b.classList.toggle("solved", !!mv.solved);
    b.classList.toggle("pointed", i === pointed);
  });
}
