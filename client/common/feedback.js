// Polish pass: strike/solved feedback. A strike or a solved module was
// nearly silent before this - the counter just changed. This file adds a
// short audio cue (BLIND/MUTE only, reusing timer-audio.js's existing
// AudioContext + role gate - DEAF must never hear it, same reasoning as the
// timer tick) and a brief full-screen colour flash (every role - strikes and
// solved-count are already broadcast to everyone via the existing "state"
// message, so a flash reacting to them leaks nothing new).
import { ALLOWED, beep } from "/common/timer-audio.js";

// Hex values duplicated from ui.css's --hot/--ok custom properties (a CSS var
// isn't directly readable from a plain string here without extra DOM
// plumbing) - keep these two in sync if that palette ever changes.
const HOT = "#c8402f";
const OK = "#4c9a5a";

function playStrikeSound() {
  if (!ALLOWED) return;
  beep(160, 160);
  setTimeout(() => beep(120, 220), 90);
}

function playSolvedSound() {
  if (!ALLOWED) return;
  beep(660, 90);
  setTimeout(() => beep(990, 150), 90);
}

let flashEl = null;
function ensureFlashEl() {
  if (flashEl) return flashEl;
  flashEl = document.createElement("div");
  flashEl.id = "fx-flash";
  flashEl.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:80;opacity:0;";
  document.body.appendChild(flashEl);
  return flashEl;
}

function flash(colour) {
  const el = ensureFlashEl();
  el.style.transition = "none";
  el.style.background = colour;
  el.style.opacity = "0.55";
  // Forces the browser to apply the two lines above before the next one, so
  // the following transition actually animates FROM .55 back down to 0
  // instead of silently no-op'ing (the standard "force reflow" trick).
  void el.offsetHeight;
  el.style.transition = "opacity 380ms ease-out";
  el.style.opacity = "0";
}

let lastStrikes = null;
let lastSolvedCount = null;

// Call this once per "state" message with the round's current strike count,
// how many modules are currently solved, and the round's phase. Fires the
// cues on genuine increases only - never on the first tick after a page
// load or reconnect (lastStrikes/lastSolvedCount start null, so there is
// nothing to compare against yet) and never while a round isn't actually
// "running" (resets its baseline instead, so a fresh ARM doesn't replay old
// deltas). A disconnect-pause does NOT reset this - phase stays "running"
// while paused, only time_left freezes, so counts already earned before a
// pause are compared correctly against whatever comes after it.
export function updateFeedback(strikes, solvedCount, phase) {
  if (phase !== "running") {
    lastStrikes = null;
    lastSolvedCount = null;
    return;
  }
  if (lastStrikes !== null && strikes > lastStrikes) {
    playStrikeSound();
    flash(HOT);
  }
  if (lastSolvedCount !== null && solvedCount > lastSolvedCount) {
    playSolvedSound();
    flash(OK);
  }
  lastStrikes = strikes;
  lastSolvedCount = solvedCount;
}
