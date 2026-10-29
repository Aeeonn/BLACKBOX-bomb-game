// Game audio, BLIND and MUTE only. DEAF must never hear a game sound -
// AGENTS.md's three-channel model is about server payloads, but the same
// "wrong role gets information" mistake is just as real if a client-only
// effect leaks past its role. There is no server message to filter here, so
// the gate has to live in this module: every sound below is a silent no-op
// for every role but BLIND and MUTE, because the AudioContext is never even
// created for them. test_invariants.py cannot catch a mistake here (T3) -
// check by hand that deaf.html stays silent.
import { ROLE } from "/common/net.js";

export const ALLOWED = ROLE === "blind" || ROLE === "mute";
const KEY = "blackbox.sound";
let ctx = null, master = null;
let enabled = ALLOWED && localStorage.getItem(KEY) !== "off";

if (ALLOWED) {
  // Browsers refuse to start audio before a user gesture; the first key or
  // pointer press anywhere on the page unlocks it.
  const unlock = () => {
    if (!ctx) {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      master = ctx.createGain();
      master.gain.value = enabled ? 1 : 0;
      master.connect(ctx.destination);
    }
    if (ctx.state === "suspended") ctx.resume();
    removeEventListener("keydown", unlock);
    removeEventListener("pointerdown", unlock);
  };
  addEventListener("keydown", unlock);
  addEventListener("pointerdown", unlock);
}

export const soundOn = () => enabled;
export function setSound(on) {
  enabled = ALLOWED && on;
  localStorage.setItem(KEY, on ? "on" : "off");
  if (master) master.gain.value = enabled ? 1 : 0;
}

// One enveloped oscillator, optionally gliding from freq to `to`.
export function tone(freq, ms, { type = "sine", gain = 0.05, to = null, delay = 0 } = {}) {
  if (!ctx) return;
  const t0 = ctx.currentTime + delay / 1000, t1 = t0 + ms / 1000;
  const osc = ctx.createOscillator(), g = ctx.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  if (to) osc.frequency.exponentialRampToValueAtTime(to, t1);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(gain, t0 + 0.006);
  g.gain.exponentialRampToValueAtTime(0.0001, t1);
  osc.connect(g).connect(master);
  osc.start(t0);
  osc.stop(t1 + 0.02);
}

// A filtered, decaying noise burst: clicks, thumps, card slaps, the boom.
export function noise(ms, { gain = 0.05, freq = 1800, q = 0.8, type = "bandpass", delay = 0 } = {}) {
  if (!ctx) return;
  const len = Math.max(1, Math.floor((ctx.sampleRate * ms) / 1000));
  const buf = ctx.createBuffer(1, len, ctx.sampleRate), data = buf.getChannelData(0);
  for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / len) ** 2;
  const src = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain();
  src.buffer = buf;
  f.type = type; f.frequency.value = freq; f.Q.value = q;
  g.gain.value = gain;
  src.connect(f).connect(g).connect(master);
  src.start(ctx.currentTime + delay / 1000);
}

// A sustained tone whose pitch the caller keeps steering - the whine of a
// commit-hold charging up. Returns null when this role has no audio.
export function drone({ type = "triangle", gain = 0.03 } = {}) {
  if (!ctx) return null;
  const osc = ctx.createOscillator(), g = ctx.createGain();
  osc.type = type;
  g.gain.setValueAtTime(0.0001, ctx.currentTime);
  g.gain.exponentialRampToValueAtTime(gain, ctx.currentTime + 0.05);
  osc.connect(g).connect(master);
  osc.start();
  return {
    pitch(hz) { osc.frequency.setTargetAtTime(hz, ctx.currentTime, 0.03); },
    stop() { g.gain.setTargetAtTime(0.0001, ctx.currentTime, 0.025); osc.stop(ctx.currentTime + 0.25); },
  };
}

// Named cues. None of them depend on what BLIND felt - a probe sounds the
// same on every cell, so audio can never become a side channel for texture.
export const sfx = {
  probe() { noise(26, { freq: 2600, q: 1.3, gain: 0.06 }); tone(140, 50, { gain: 0.035 }); },
  commit() { tone(200, 170, { to: 55, gain: 0.1 }); noise(80, { type: "lowpass", freq: 900, gain: 0.07 }); },
  strike() { tone(160, 280, { type: "sawtooth", to: 70, gain: 0.05 }); noise(240, { type: "lowpass", freq: 600, gain: 0.08 }); },
  solved() { [660, 880, 1320].forEach((f, i) => tone(f, 170, { type: "triangle", gain: 0.05, delay: i * 85 })); },
  flash() { noise(55, { freq: 1300, q: 0.6, gain: 0.06 }); },
  tick(urgent) { tone(urgent ? 1500 : 880, 55, { type: "square", gain: 0.03 }); },
  defused() { [523, 659, 784, 1047].forEach((f, i) => tone(f, 460, { type: "triangle", gain: 0.05, delay: i * 110 })); },
  boom() { noise(1500, { type: "lowpass", freq: 360, q: 0.4, gain: 0.45 }); tone(95, 1000, { to: 28, gain: 0.22 }); },
};
