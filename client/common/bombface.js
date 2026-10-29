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
//
// Also publishes the layout's grid size (--cols/--rows) for sizing, and each
// slot's WORLD kind as data-slot, so even a featureless shell can show a
// slot's shape (a wire groove, a tile, a vent) - shape is geometry, shared
// by every role; nothing here is a property.
export function renderBombFace(container, layout, paint) {
  const slots = (layout && layout.slots) || [];
  container.style.setProperty("--cols", (layout && layout.w) || 1);
  container.style.setProperty("--rows", (layout && layout.h) || 1);
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
    el.dataset.slot = slot.kind;
    paint(el, slot, i);
  });
}

// Shared commit-charge fill (AGENTS.md hard rule 12 / T10). Call this AFTER
// setting el.textContent/innerHTML in your paint callback - both of those
// replace all of el's children, which would otherwise wipe the fill div this
// creates. Pass progress=null (or omit the call) when this slot isn't the
// one currently charging, to remove any leftover fill from a previous paint.
export function paintCharge(el, progress) {
  let fill = el.querySelector(".charge-fill");
  if (progress == null) {
    if (fill) fill.remove();
    return;
  }
  if (!fill) {
    fill = document.createElement("div");
    fill.className = "charge-fill";
    el.appendChild(fill);
  }
  fill.style.height = (progress * 100) + "%";
}
