// Hold-to-commit (AGENTS.md hard rule 12): every destructive BLIND action is
// a timed hold whose progress the server broadcasts as the charge ring, so
// MUTE can watch a mistake begin and slam STOP. Do not remove or shorten it.
//
// One controller owns the hold for both the keyboard and the on-screen
// buttons, so they can never run two overlapping holds. The target (module +
// cell) is captured when the hold STARTS - that is exactly what the ring
// shows everyone - and anything that would change the target (moving the
// probe, switching module) must cancel() first. Previously the action was
// sent to wherever the probe happened to be at release time, which could be
// a different slot from the one the ring was drawn on.
export function makeHold({ onStart, onCancel, onCommit }) {
  let active = null;

  function fire() {
    const h = active;
    active = null;
    onCommit(h);
  }

  return {
    get active() { return active; },

    // cfg: {action, chargeKind, ms, ...}; target: {module, cell}.
    start(cfg, target) {
      if (active) return false;
      active = { cfg, target, t0: performance.now(), timer: setTimeout(fire, cfg.ms) };
      onStart(active);
      return true;
    },

    cancel() {
      if (!active) return;
      clearTimeout(active.timer);
      active = null;
      onCancel();
    },

    // 0..1 for the local fill; the server's ring is computed from its own
    // clock, this only drives this page's button/slot animation.
    progress() {
      return active ? Math.min(1, (performance.now() - active.t0) / active.cfg.ms) : 0;
    },
  };
}
