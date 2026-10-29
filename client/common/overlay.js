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
// alt-tabbed). Every page now passes them via client/common/chrome.js.
//
// Called on every 10Hz state tick, so the DOM is only rebuilt when what the
// overlay shows actually changes - rebuilding each tick would restart its
// entrance animation ten times a second.
let shown = null;
export function updateOverlay(phase, onRearm, paused, pauseLabel, summary) {
  const node = ensure();
  const key = paused ? "paused|" + pauseLabel : phase + "|" + !!onRearm + "|" + (summary || "");
  if (key === shown) return;
  shown = key;
  if (paused) {
    node.className = "overlay show paused";
    node.innerHTML = "<div class='overlay-label paused-label'></div>";
    node.firstChild.textContent = pauseLabel || "PAUSED";
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
    "<div class='overlay-summary'></div>" +
    (onRearm ? "<button class='rearm btn-primary'>REARM</button>"
      : "<div class='overlay-sub'>WAITING FOR MUTE TO REARM</div>");
  node.querySelector(".overlay-summary").textContent = summary || "";
  if (onRearm) {
    node.querySelector(".rearm").onclick = onRearm;
  }
}
