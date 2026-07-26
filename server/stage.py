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
        a.gaze = a.gesture = a.pointer = a.probe = None

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
        a.pointer = target

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

    def presence(self, role: str) -> dict:
        """Per-role filtered presence payload. See AGENTS.md's presence filter
        matrix: HANDS never receives yaw/pitch/gaze/gesture/pointer keys for
        OTHER players - those keys are omitted entirely, not just nulled out.
        A player always receives their own fields at full detail, regardless
        of which role they are. HANDS' probe cell (module+cell indices, never
        the descriptor text) is the one exception to the "hidden from HANDS'
        view of others" rule: it is visible to every role, including HANDS'
        own entry, per the matrix - gated only by probe_echo.
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
            players.append(entry)
        return {"players": players}
