// Shared bomb-face positioning. Reads ONLY the shared layout() geometry (see
// AGENTS.md hard rule 3: "one geometry, three skins") to place one element
// per slot. This file never decides what a slot looks like - the caller's
// paint(el, slot) callback does that, using that role's OWN views() data.
// That split is what makes it structurally impossible for this file to leak
// PERCEPTION: it never receives colour, texture or any module property.

// Builds (or reuses) one positioned box per slot inside `container`, then
// calls paint(el, slot, index) for each so the caller can fill in whatever
// that role is allowed to see. Safe to call every state update - it reuses
// existing elements by slot index rather than rebuilding the DOM each time.
export function renderBombFace(container, layout, paint) {
  const slots = (layout && layout.slots) || [];
  while (container.children.length > slots.length) {
    container.removeChild(container.lastChild);
  }
  while (container.children.length < slots.length) {
    const el = document.createElement("div");
    el.className = "slot";
    container.appendChild(el);
  }
  slots.forEach((slot, i) => {
    const el = container.children[i];
    el.style.left = (slot.x * 100) + "%";
    el.style.top = (slot.y * 100) + "%";
    paint(el, slot, i);
  });
}
