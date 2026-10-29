// T13: lobby roster + comms-card helpers, shared by every page and by
// index.html. The roster is pure lobby metadata (who's connected/ready) -
// it is identical for every viewer, so unlike stage.js/bombface.js this file
// has zero filtering concerns: nothing here is PRESENCE or PERCEPTION.

export const REQUIRED_ROLES = ["blind", "deaf", "mute"];

// T13.5: what players actually see on screen. Internal role ids (blind,
// deaf, mute, scope, dispatch) never change - they're the wire protocol,
// the URL ?role= param, and every server-side check. This is the ONE place
// that maps an id to the label a human reads, so every page stays in sync
// if the names ever change again.
export const DISPLAY_NAME = {
  blind: "BLIND", deaf: "DEAF", mute: "MUTE", scope: "SCOPE", dispatch: "DISPATCH",
};

// Reminder text for each role's own Discord settings and who they talk to -
// see AGENTS.md's role table. Voice is Discord-only in this game (no video
// call): other players' nods/shakes are the in-game head avatar driven by
// mouse-look (see stage.js/T11), so nothing here ever mentions a camera.
export const COMMS = {
  blind: "You are BLIND. Voice NORMAL in Discord. You're the only one who can touch the bomb \u2014 describe what you feel to MUTE and DEAF.",
  deaf: "You are DEAF. Deafen yourself in Discord \u2014 you must not hear anyone. Tell BLIND and MUTE what you see.",
  mute: "You are MUTE. Mute yourself in Discord \u2014 you cannot speak. Nod, shake your head, and flash cards to signal DEAF. You hear everyone.",
  scope: "You are SCOPE. Mute yourself in Discord \u2014 you cannot speak. (A drawing canvas to MUTE is coming in a later update \u2014 for now, just listen in.)",
  dispatch: "You are DISPATCH. Voice normal in Discord. Watch the big picture \u2014 timer, strikes, alarms \u2014 and call it out to BLIND.",
};

// Polish pass: a one-time "how do I actually play this" explainer per role,
// shown behind a collapsed toggle (see the .help-toggle/.help-panel wiring
// in blind/deaf/mute.html) so it doesn't clutter the page for repeat
// players, but a brand-new player doesn't need it explained over voice.
export const HELP = {
  blind: "LEFT/RIGHT arrows move your fingertip between cells (on a Gauge they turn the knob). Click a cell to jump to it. "
    + "Each touch tells you what you feel there - describe it out loud. To act, hold the key shown on a button "
    + "(or the button itself) until the bar fills: cut a wire, discharge a warm one first, press or skip a tile, purge a vent, "
    + "lock in a gauge, confirm a sync. Everyone sees that bar filling on the bomb, so MUTE can stop you. "
    + "Moving your fingertip mid-hold cancels it. TAB switches module.",
  deaf: "You see full detail on the bomb - colours, printed numbers, letters, the needle, which vent glows - but you cannot hear anyone. "
    + "Call out what you see so BLIND and MUTE can act on it. BLIND's blue fingertip shows where their hand is; a red bar means "
    + "they are committing to that cell right now. MUTE's flashcards appear full-screen. TAB switches module.",
  mute: "You hear everyone but cannot speak. Your manual (right) holds the answers. Signal DEAF with the flashcards - "
    + "SPACE flashes STOP, and every card shows its key - one card every 2 seconds. Move your mouse over the room to move your head: "
    + "quick side-to-side is a shake, up-and-down a nod, and looking down shows everyone you are reading. Click a module "
    + "to point at it for everyone to see. When BLIND starts holding, a red bar fills on that cell - that is your moment to slam STOP.",
  scope: "You see the bomb's internal wiring only - no colours or textures. You are muted; listen in and help MUTE "
    + "(a shared drawing canvas is planned for a later update).",
  dispatch: "You see the big picture only - timer, strikes, and alarms - never any module detail. Call out what you see to BLIND.",
};

// True once every required seat (blind/deaf/mute) shows connected:true.
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
    const opt = r.required ? "" : " roster-optional";
    const tip = !r.connected ? "not here yet" : (r.ready ? "ready" : "connected");
    return '<span class="roster-item roster-' + state + opt + '" title="' + tip + '">' +
      (DISPLAY_NAME[r.role] || r.role.toUpperCase()) + '</span>';
  }).join("");
}

// The same chips during a round, when the lobby roster is no longer
// rebroadcast: presence still carries `connected` for every seat (to every
// role, BLIND included - it's in the matrix's always-shared row).
export function rosterFromPresence(presence) {
  return ((presence && presence.players) || []).map(p => ({
    role: p.role, connected: !!p.connected, ready: false, required: REQUIRED_ROLES.includes(p.role),
  }));
}

// Text for the "PAUSED" banner (T13: disconnecting a required role mid-match
// pauses the timer). Reads presence rather than the roster, because presence
// is what's still updating live once a bomb exists - the lobby roster stops
// being rebroadcast the moment a round starts.
export function pauseText(presence) {
  const byRole = {};
  for (const p of (presence && presence.players) || []) byRole[p.role] = p;
  const missing = REQUIRED_ROLES.filter(r => !(byRole[r] && byRole[r].connected))
    .map(r => DISPLAY_NAME[r] || r.toUpperCase());
  return missing.length ? "PAUSED \u2014 waiting for " + missing.join(", ") : "PAUSED";
}
