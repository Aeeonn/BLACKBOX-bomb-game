// Shared page furniture for every role page: header, HUD, briefing card,
// ready button, and the wiring each page used to copy-paste (stage, win/lose
// overlay, timer audio, strike/solve feedback, event log). Each page still
// declares its own HTML and its own console, so a role page stays the one
// place to inspect what that role is shown. This file reads only the global
// part of a snapshot - phase, timer, strikes, paused, solved count - which
// every role already receives identically.
import { on, send, logLine, ROOM, ROLE } from "/common/net.js";
import { updateOverlay } from "/common/overlay.js";
import { updateTimerAudio } from "/common/timer-audio.js";
import { ALLOWED as AUDIO, soundOn, setSound } from "/common/audio.js";
import { updateFeedback } from "/common/feedback.js";
import { init as initStage, setPresence, setBomb } from "/common/stage.js";
import { COMMS, HELP, DISPLAY_NAME, REQUIRED_ROLES, renderRoster, rosterFromPresence, pauseText } from "/common/roster.js";

let presence = null;
let phase = "lobby";
export function getPresence() { return presence; }

const $ = id => document.getElementById(id);

export function mmss(s) {
  const t = Math.max(0, Math.ceil(s || 0));
  return String(Math.floor(t / 60)).padStart(2, "0") + ":" + String(t % 60).padStart(2, "0");
}

export function initChrome({ onRearm } = {}) {
  document.body.dataset.role = ROLE;
  document.body.dataset.phase = "lobby";
  document.title = DISPLAY_NAME[ROLE] + " \u00b7 BLACKBOX";

  $("topbar").innerHTML =
    '<a class="brand" href="/" target="_blank" rel="noopener">BLACKBOX</a>' +
    '<span class="role-badge">' + DISPLAY_NAME[ROLE] + "</span>" +
    '<span class="room-code">ROOM <b>' + (ROOM || "????") + "</b></span>" +
    '<div class="roster" id="roster"></div>' +
    (AUDIO ? '<button class="btn-quiet sound-toggle" id="sound"></button>' : "") +
    '<span class="status" id="status" data-state="off">connecting\u2026</span>';
  if (AUDIO) {
    const paint = () => { $("sound").textContent = soundOn() ? "\u266A SOUND ON" : "SOUND OFF"; };
    $("sound").onclick = () => { setSound(!soundOn()); paint(); };
    paint();
  }

  $("hud").innerHTML =
    '<div class="timer idle" id="timer"><span class="ghost">88:88</span><span id="time">--:--</span></div>' +
    '<div class="strikes" id="strikes"></div>' +
    '<div class="phase" id="phase">LOBBY</div>';
  paintStrikes(0, 3);

  $("brief").innerHTML =
    '<p class="comms" id="comms"></p>' +
    '<div class="brief-actions"><button class="readybtn" id="ready">I\'M READY</button>' +
    '<button class="btn-quiet" id="helpToggle">HOW TO PLAY</button>' +
    '<span class="lobby-line" id="lobbyline"></span></div>' +
    '<div class="help" id="helpPanel" hidden></div>';
  $("comms").textContent = COMMS[ROLE];
  $("helpPanel").textContent = HELP[ROLE];
  $("helpToggle").onclick = () => { $("helpPanel").hidden = !$("helpPanel").hidden; };

  let isReady = false;
  const readyBtn = $("ready");
  const showReady = v => {
    isReady = v;
    readyBtn.classList.toggle("is-ready", v);
    readyBtn.textContent = v ? "\u2713 READY" : "I'M READY";
  };
  readyBtn.onclick = () => { showReady(!isReady); send({ type: "ready", value: isReady }); };

  const canvas = $("stage");
  initStage(canvas, ROLE, send);
  const hint = document.createElement("div");
  hint.className = "stage-hint";
  hint.textContent = "MOUSE OVER THE ROOM TO LOOK \u00b7 SHAKE OR NOD TO GESTURE";
  canvas.parentElement.appendChild(hint);

  on("lobby", m => {
    setPhase("lobby");
    renderRoster($("roster"), m.roster);
    const mine = m.roster.find(r => r.role === ROLE);
    if (mine) showReady(!!mine.ready);   // the server forgets "ready" on reconnect
    $("lobbyline").textContent = lobbyLine(m.roster);
    $("phase").textContent = "LOBBY";
    $("phase").className = "phase";
  });
  on("presence", m => {
    presence = m.payload;
    setPresence(m.payload);
    if (phase !== "lobby") renderRoster($("roster"), rosterFromPresence(presence));
  });
  on("state", m => {
    const s = m.payload;
    setPhase(s.phase);
    updateHud(s);
    document.body.classList.toggle("crit", s.phase === "running" && !s.paused && s.time_left < 30);
    updateOverlay(s.phase, onRearm, s.paused, pauseText(presence), summary(s));
    updateTimerAudio(s.time_left, s.phase, s.paused);
    updateFeedback(s.strikes, s.modules.filter(mv => mv.solved).length, s.phase);
    setBomb(s);
  });
  on("log", m => logLine(m.text));
  on("error", m => logLine("ERROR " + m.text));
}

// One line for the DEFUSED / DETONATED screen, from the global state every
// role already has.
function summary(s) {
  const strikes = s.strikes === 0 ? "NO STRIKES" : s.strikes + " STRIKE" + (s.strikes === 1 ? "" : "S");
  if (s.phase === "won") return mmss(s.time_left) + " TO SPARE \u00b7 " + strikes;
  if (s.phase === "lost") return s.time_left <= 0 ? "THE CLOCK RAN OUT" : "THREE STRIKES \u00b7 " + mmss(s.time_left) + " WAS LEFT";
  return "";
}

function setPhase(p) {
  phase = p;
  document.body.dataset.phase = p;
}

function lobbyLine(roster) {
  const here = new Set(roster.filter(r => r.connected).map(r => r.role));
  const missing = REQUIRED_ROLES.filter(r => !here.has(r)).map(r => DISPLAY_NAME[r]);
  if (missing.length) return "Waiting for " + missing.join(", ") + " to join.";
  return ROLE === "mute" ? "Everyone's here - arm the bomb when you're ready."
    : "Everyone's here - waiting for " + DISPLAY_NAME.mute + " to arm the bomb.";
}

function paintStrikes(strikes, max) {
  const el = $("strikes");
  if (el.children.length !== max + 1) {
    el.innerHTML = '<span class="strikes-label">STRIKES</span>' + '<i class="lamp"></i>'.repeat(max);
  }
  [...el.querySelectorAll(".lamp")].forEach((lamp, i) => lamp.classList.toggle("lit", i < strikes));
}

function updateHud(s) {
  $("time").textContent = mmss(s.time_left);
  let cls = "timer";
  if (s.phase !== "running") cls += " " + s.phase;
  else if (s.paused) cls += " paused";
  else if (s.time_left < 30) cls += " crit";
  else if (s.time_left < 60) cls += " warn";
  $("timer").className = cls;
  paintStrikes(s.strikes, s.max_strikes);
  const ph = $("phase");
  if (s.paused) { ph.textContent = pauseText(presence); ph.className = "phase paused"; }
  else if (s.phase === "won") { ph.textContent = "DEFUSED"; ph.className = "phase won"; }
  else if (s.phase === "lost") { ph.textContent = "DETONATED"; ph.className = "phase lost"; }
  else { ph.textContent = s.modules.length + " MODULE" + (s.modules.length === 1 ? "" : "S") + " ARMED"; ph.className = "phase"; }
}
