"""Stage: avatars, poses, gestures, pointers, and presence(role).

Stage never reads module properties - it has no import of Bomb or any Module,
and never will. That separation is what keeps hard rule 2 (PRESENCE must never
smuggle PERCEPTION) easy to hold: nothing in this file has access to a wire's
colour or texture, so it cannot leak one by accident, no matter how the avatar
rendering evolves later.
"""
import time
from dataclasses import dataclass

ROLES = ("hands", "eyes", "book", "scope", "dispatch")
GESTURE_TTL = 1.2   # seconds a gesture stays visible before clearing itself
MOVING_TTL = 0.5    # seconds after a pose update before "moving" clears

# Canonical hold durations for the commit-charge ring (AGENTS.md hard rule 12:
# "1s hold (2s discharge)"). The server owns these so the ring's fill rate is
# identical for every viewer regardless of the charging client's own frame
# timing or network latency, and so a client can't lie about how fast it
# should fill. hands.html's own local action-firing timers use the same
# values for a different purpose (deciding when to actually send the `act`
# message) - see the comment there if either number ever changes.
HOLD_DURATIONS_S = {"cut": 1.0, "discharge": 2.0}


@dataclass
class Avatar:
    """Server-side body state for one seat. Deliberately NOT sent to clients
    via a blanket asdict() - presence() below hand-picks fields per viewer.
    Sending this whole dataclass verbatim to every role is exactly the
    "send everything and filter in JS" mistake AGENTS.md warns against.
    """
    role: str
    connected: bool = False
    yaw: float = 0.0
    pitch: float = 0.0
    gaze: str | None = None
    gesture: str | None = None
    gesture_at: float = 0.0
    pointer: dict | None = None
    probe: dict | None = None
    charge: dict | None = None
    last_pose_at: float = 0.0

    @property
    def moving(self) -> bool:
        return (time.monotonic() - self.last_pose_at) < MOVING_TTL

    def live_gesture(self) -> str | None:
        if self.gesture is not None and time.monotonic() - self.gesture_at > GESTURE_TTL:
            return None
        return self.gesture


class Stage:
    def __init__(self) -> None:
        # All five canonical seats exist from the start, connected=False,
        # so every role's avatar always renders (greyed) even before anyone
        # has ever taken that seat. See AGENTS.md hard rule 4.
        self.avatars: dict[str, Avatar] = {role: Avatar(role) for role in ROLES}
        # Match flag, default on (see AGENTS.md T9/T18). Gates whether HANDS'
        # probed cell is echoed to anyone at all. T18 (Mirror) will turn this
        # off, because watching the echoed hand would give the flip away
        # instantly.
        self.probe_echo: bool = True
        # Match flag, default off (see AGENTS.md T12). BOOK's pointer resolves
        # to a module by default; cell-level pointing would let BOOK issue
        # complete instructions without the voice relay, so it stays off
        # until the humans explicitly ask for it.
        self.precise_pointing: bool = False

    def attach(self, role: str) -> None:
        a = self.avatars.get(role)
        if a is not None:
            a.connected = True

    def detach(self, role: str) -> None:
        # A disconnected player's seat stays, greyed - it is not removed.
        a = self.avatars.get(role)
        if a is None:
            return
        a.connected = False
        a.yaw = a.pitch = 0.0
        a.gaze = a.gesture = a.pointer = a.probe = a.charge = None

    def apply_pose(self, role: str, yaw: float, pitch: float, gaze: str | None) -> None:
        a = self.avatars.get(role)
        if a is None:
            return
        a.yaw = float(yaw)
        a.pitch = float(pitch)
        a.gaze = gaze
        a.last_pose_at = time.monotonic()

    def apply_gesture(self, role: str, kind: str) -> None:
        a = self.avatars.get(role)
        if a is None:
            return
        a.gesture = kind
        a.gesture_at = time.monotonic()

    def apply_point(self, role: str, target: dict | None) -> None:
        # HANDS cannot point - HANDS is the only pair of hands that can act,
        # and giving HANDS a pointer too would let it skip the voice relay.
        if role == "hands":
            return
        a = self.avatars.get(role)
        if a is None:
            return
        if target is None or "module" not in target:
            a.pointer = None
            return
        # Module-level resolution by default, regardless of what a client
        # sends: a client cannot elevate its own precision by including a
        # "cell" the server doesn't allow. Precision is a match-wide flag,
        # not a per-message client choice.
        module = target["module"]
        if self.precise_pointing and "cell" in target:
            a.pointer = {"module": module, "cell": target["cell"]}
        else:
            a.pointer = {"module": module}

    def apply_probe(self, role: str, module: int, cell: int) -> None:
        """Record where HANDS' hand currently is on the bomb - module+cell
        indices ONLY. The descriptor text never reaches this class at all
        (callers must pass the raw incoming message args, never the result of
        Bomb.inspect()), which is what makes it safe for presence() to
        broadcast this to every role. See AGENTS.md T9.
        """
        if role != "hands":
            return
        a = self.avatars.get(role)
        if a is None:
            return
        a.probe = {"module": module, "cell": cell}

    def start_charge(self, role: str, kind: str, module: int, cell: int) -> None:
        """HANDS begins holding to cut/discharge. Only module+cell indices and
        a start timestamp are stored - presence() computes the live fill
        fraction from the server's own clock every tick (same self-correcting
        pattern as Avatar.moving), so the ring can never end up stuck at the
        wrong fraction for everyone just because a `stop` message was dropped
        or delayed, and a client can't lie about how fast it fills. See
        AGENTS.md hard rule 12 and T10.
        """
        if role != "hands" or kind not in HOLD_DURATIONS_S:
            return
        a = self.avatars.get(role)
        if a is None:
            return
        a.charge = {"kind": kind, "module": module, "cell": cell, "started_at": time.monotonic()}

    def stop_charge(self, role: str) -> None:
        a = self.avatars.get(role)
        if a is not None:
            a.charge = None

    def _charge_view(self, a: Avatar) -> dict | None:
        if a.charge is None:
            return None
        duration = HOLD_DURATIONS_S[a.charge["kind"]]
        elapsed = time.monotonic() - a.charge["started_at"]
        progress = max(0.0, min(1.0, elapsed / duration))
        return {"kind": a.charge["kind"], "module": a.charge["module"],
                "cell": a.charge["cell"], "progress": progress}

    def presence(self, role: str) -> dict:
        """Per-role filtered presence payload. See AGENTS.md's presence filter
        matrix: HANDS never receives yaw/pitch/gaze/gesture/pointer keys for
        OTHER players - those keys are omitted entirely, not just nulled out.
        A player always receives their own fields at full detail, regardless
        of which role they are. HANDS' probe cell (module+cell indices, never
        the descriptor text) is the one exception to the "hidden from HANDS'
        view of others" rule: it is visible to every role, including HANDS'
        own entry, per the matrix - gated only by probe_echo. The commit-charge
        ring is visible to every role unconditionally (no flag): hard rule 12
        says it must never be optimised away or made local-only.
        """
        players = []
        for other_role, a in self.avatars.items():
            entry = {"role": other_role, "connected": a.connected, "moving": a.moving}
            if other_role == role or role != "hands":
                entry["yaw"] = a.yaw
                entry["pitch"] = a.pitch
                entry["gaze"] = a.gaze
                entry["gesture"] = a.live_gesture()
                entry["pointer"] = a.pointer
            if other_role == "hands" and self.probe_echo:
                entry["probe"] = a.probe
            if other_role == "hands":
                entry["charge"] = self._charge_view(a)
            players.append(entry)
        return {"players": players}
