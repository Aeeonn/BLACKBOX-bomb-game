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

// Call this from your existing "state" handler with the bomb's phase.
// Pass onRearm (a function) only on the page that should offer a REARM
// button - today that's BOOK. Every other page omits it and gets no button.
export function updateOverlay(phase, onRearm) {
  const node = ensure();
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
