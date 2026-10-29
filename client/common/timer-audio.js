// Timer tick, BLIND and MUTE only - DEAF must never hear this cue. The role
// gate and the reasoning behind it live in client/common/audio.js, the one
// place that owns game audio; this file only decides when to tick.
import { ALLOWED, sfx } from "/common/audio.js";

let lastSlot = -1;

// Call from the page's "state" handler with (time_left, phase, paused).
// Ticks about once a second, faster under 30s, faster still under 10s;
// silent whenever the round isn't running or is paused.
export function updateTimerAudio(timeLeft, phase, paused) {
  if (!ALLOWED || phase !== "running" || paused) { lastSlot = -1; return; }
  const period = timeLeft < 10 ? 0.25 : timeLeft < 30 ? 0.45 : 1.0;
  const slot = Math.floor(timeLeft / period);
  if (slot === lastSlot) return;
  lastSlot = slot;
  sfx.tick(timeLeft < 30);
}
