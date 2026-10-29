// Strike / solve / round-end feedback. Sound comes from audio.js, which only
// ever plays for BLIND and MUTE (DEAF must never hear it - see the gate
// there). The visual half - a colour flash and a shake - plays for every
// role: strikes, solved counts and the round's outcome are already
// broadcast to everyone in the "state" message, so reacting to them leaks
// nothing new.
import { sfx } from "/common/audio.js";

// Duplicated from ui.css's --hot/--ok (a CSS var isn't readable from a plain
// string without extra DOM plumbing) - keep the two in sync.
const HOT = "#e0472f";
const OK = "#4fae68";

let flashEl = null;
function flash(colour, peak = 0.5) {
  if (!flashEl) {
    flashEl = document.createElement("div");
    flashEl.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:80;opacity:0;";
    document.body.appendChild(flashEl);
  }
  flashEl.style.transition = "none";
  flashEl.style.background = "radial-gradient(circle, transparent 30%, " + colour + ")";
  flashEl.style.opacity = String(peak);
  // Forces the two lines above to apply before the transition below, so it
  // animates FROM the peak back to 0 (the standard "force reflow" trick).
  void flashEl.offsetHeight;
  flashEl.style.transition = "opacity 450ms ease-out";
  flashEl.style.opacity = "0";
}

function shake(kind) {
  const b = document.body;
  b.classList.remove("shake", "quake");
  void b.offsetWidth;
  b.classList.add(kind);
  setTimeout(() => b.classList.remove(kind), kind === "quake" ? 900 : 400);
}

let lastStrikes = null;
let lastSolvedCount = null;
let lastPhase = null;

// Call once per "state" message. Fires on genuine changes only - never on
// the first state after a page load or reconnect (the baselines start
// null), and never replays old deltas after a REARM (they reset whenever
// the round isn't running). A disconnect-pause doesn't reset them: phase
// stays "running" while paused, so counts compare correctly across it.
export function updateFeedback(strikes, solvedCount, phase) {
  if (lastPhase === "running" && phase === "won") { sfx.defused(); flash(OK, 0.6); }
  if (lastPhase === "running" && phase === "lost") { sfx.boom(); flash("#ff5a2a", 0.85); shake("quake"); }
  lastPhase = phase;
  if (phase !== "running") {
    lastStrikes = null;
    lastSolvedCount = null;
    return;
  }
  if (lastStrikes !== null && strikes > lastStrikes) { sfx.strike(); flash(HOT); shake("shake"); }
  if (lastSolvedCount !== null && solvedCount > lastSolvedCount) { sfx.solved(); flash(OK); }
  lastStrikes = strikes;
  lastSolvedCount = solvedCount;
}
