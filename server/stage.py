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
        a.gaze = a.gesture = a.pointer = None

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

    def presence(self, role: str) -> dict:
        """Per-role filtered presence payload. See AGENTS.md's presence filter
        matrix: HANDS never receives yaw/pitch/gaze/gesture/pointer keys for
        OTHER players - those keys are omitted entirely, not just nulled out.
        A player always receives their own fields at full detail, regardless
        of which role they are.
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
            players.append(entry)
        return {"players": players}
