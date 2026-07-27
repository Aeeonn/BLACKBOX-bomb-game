// Full-screen win/lose overlay, shared by every role page. It is its own
// module (not baked into any one page) so every role can show the same
// DEFUSED/DETONATED screen without merging the separate HTML files.
let el = null;

function ensure() {
  if (el) return el;
  el = document.createElement("div");
  el.id = "overlay";
  document.body.appendChild(el);
  return el;
}

// Call this from your existing "state" handler with the bomb's phase. Pass
// onRearm (a function) only on the page that should offer a REARM button -
// today that's MUTE. Every other page omits it and gets no button.
//
// Polish pass: paused/pauseLabel are optional extra args - pass the round's
// "paused" flag and roster.js's pauseText(presence) to also show a full,
// unmissable dim screen while a required role is disconnected (previously
// this was only a small line of amber HUD text, easy to miss if you'd
// alt-tabbed). Omitting them (as scope.html/dispatch.html currently do)
// simply means this page keeps its old behaviour - win/lose only, no pause
// overlay - so those pages needed zero changes to keep working exactly as
// before.
export function updateOverlay(phase, onRearm, paused, pauseLabel) {
  const node = ensure();
  if (paused) {
    node.className = "overlay show paused";
    node.innerHTML = "<div class='overlay-label paused-label'>" + (pauseLabel || "PAUSED") + "</div>";
    return;
  }
  if (phase !== "won" && phase !== "lost") {
    node.className = "overlay";
    node.innerHTML = "";
    return;
  }
  node.className = "overlay show " + phase;
  const label = phase === "won" ? "DEFUSED" : "DETONATED";
  node.innerHTML = "<div class='overlay-label'>" + label + "</div>" +
    (onRearm ? "<button class='rearm'>REARM</button>" : "");
  if (onRearm) {
    node.querySelector(".rearm").onclick = onRearm;
  }
}
