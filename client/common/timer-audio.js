// Timer tick, BLIND and MUTE only. DEAF must never hear this cue - AGENTS.md's
// three-channel model is about server payloads, but the same "wrong role gets
// information" mistake is just as real if a client-only effect leaks past its
// role. There is no server message to filter here, so the gating has to live
// in this module instead: it silently does nothing for every role but BLIND
// and MUTE.
import { ROLE } from "/common/net.js";

// Exported (not just used internally) so client/common/feedback.js can reuse
// the SAME AudioContext + role gate for strike/solved cues, instead of every
// audio-playing file opening its own separate context.
export const ALLOWED = ROLE === "blind" || ROLE === "mute";

let ctx = null;
let lastSlot = -1;

if (ALLOWED) {
  // Browsers refuse to start audio before a user gesture. BLIND's arrow keys
  // and hold-buttons, and MUTE's flashcards/ARM button, all qualify - listen
  // for the first one anywhere on the page and use it to unlock the
  // AudioContext, then get out of the way.
  const unlock = () => {
    if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") ctx.resume();
    removeEventListener("keydown", unlock);
    removeEventListener("mousedown", unlock);
  };
  addEventListener("keydown", unlock);
  addEventListener("mousedown", unlock);
}

export function beep(freq, ms) {
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "square";
  osc.frequency.value = freq;
  const t0 = ctx.currentTime;
  gain.gain.setValueAtTime(0.06, t0);
  gain.gain.exponentialRampToValueAtTime(0.0001, t0 + ms / 1000);
  osc.connect(gain).connect(ctx.destination);
  osc.start(t0);
  osc.stop(t0 + ms / 1000 + 0.02);
}

// Call from the page's existing "state" handler with (time_left, phase).
// Ticks about once a second; faster once under 30s remain; silent whenever
// the round isn't "running". No-ops entirely for every role but BLIND/MUTE.
export function updateTimerAudio(timeLeft, phase) {
  if (!ALLOWED || phase !== "running") { lastSlot = -1; return; }
  const period = timeLeft < 30 ? 0.45 : 1.0;
  const slot = Math.floor(timeLeft / period);
  if (slot === lastSlot) return;
  lastSlot = slot;
  beep(timeLeft < 30 ? 1500 : 880, 70);
}
