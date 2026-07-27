// T13: lobby roster + comms-card helpers, shared by every page and by
// index.html. The roster is pure lobby metadata (who's connected/ready) -
// it is identical for every viewer, so unlike stage.js/bombface.js this file
// has zero filtering concerns: nothing here is PRESENCE or PERCEPTION.

export const REQUIRED_ROLES = ["hands", "eyes", "book"];

// Reminder text for each role's own Discord settings and who they talk to -
// see AGENTS.md's role table. Voice is Discord-only in this game (no video
// call): other players' nods/shakes are the in-game head avatar driven by
// mouse-look (see stage.js/T11), so nothing here ever mentions a camera.
export const COMMS = {
  hands: "You are HANDS. Voice NORMAL in Discord. You're the only one who can touch the bomb \u2014 describe what you feel to BOOK and EYES.",
  eyes: "You are EYES. DEAFEN yourself in Discord \u2014 you must not hear anyone. Tell HANDS and BOOK what you see.",
  book: "You are BOOK. MUTE yourself in Discord \u2014 you cannot speak. Nod, shake your head, and flash cards to signal EYES. You hear everyone.",
  scope: "You are SCOPE. MUTE yourself in Discord \u2014 you cannot speak. (A drawing canvas to BOOK is coming in a later update \u2014 for now, just listen in.)",
  dispatch: "You are DISPATCH. Voice normal in Discord. Watch the big picture \u2014 timer, strikes, alarms \u2014 and call it out to HANDS.",
};

// True once every required seat (hands/eyes/book) shows connected:true.
// Deliberately ignores "ready" - see the T13 plan note: ARM only checks who
// is actually present, not whether they've clicked the READY button.
export function coreConnected(roster) {
  if (!roster) return false;
  const byRole = {};
  for (const r of roster) byRole[r.role] = r;
  return REQUIRED_ROLES.every(r => byRole[r] && byRole[r].connected);
}

// Renders the roster as a row of small role tags into `el`. Shared by every
// role page and by index.html, so the "who's here" reading is identical
// everywhere rather than five slightly-different reimplementations of the
// same three-state (missing / connected / ready) badge.
export function renderRoster(el, roster) {
  if (!el || !roster) return;
  el.innerHTML = roster.map(r => {
    const state = !r.connected ? "off" : (r.ready ? "ready" : "on");
    const mark = !r.connected ? "\u2013" : (r.ready ? "\u2713" : "\u25CB");
    return '<span class="roster-item roster-' + state + '">' + mark + ' ' + r.role.toUpperCase() + '</span>';
  }).join(" ");
}

// Text for the "PAUSED" banner (T13: disconnecting a required role mid-match
// pauses the timer). Reads presence rather than the roster, because presence
// is what's still updating live once a bomb exists - the lobby roster stops
// being rebroadcast the moment a round starts.
export function pauseText(presence) {
  const byRole = {};
  for (const p of (presence && presence.players) || []) byRole[p.role] = p;
  const missing = REQUIRED_ROLES.filter(r => !(byRole[r] && byRole[r].connected)).map(r => r.toUpperCase());
  return missing.length ? "PAUSED \u2014 waiting for " + missing.join(", ") : "PAUSED";
}
