
"""Room: sockets, role assignment, message handling, tick loop."""
import asyncio
import math
import random
import time

from .bomb import Bomb
from .modules.base import Result
from .stage import Stage

ROLES = ["blind", "deaf", "mute", "scope", "dispatch"]
REQUIRED_ROLES = {"blind", "deaf", "mute"}
CARDS = ["STOP", "GO", "YES", "NO", "WAIT", "AGAIN", "1", "2", "3", "4", "LEFT", "RIGHT"]
FLASH_COOLDOWN = 2.0
# Bounds for a client's ARM request. Difficulty is module count (AGENTS.md),
# so the count is the real knob; the bounds only stop a stray or hostile
# message from building a thousand-module bomb.
MODULE_RANGE = (1, 8)
SECONDS_RANGE = (30.0, 3600.0)

ROOMS: dict[str, "Room"] = {}


def _int(value, default: int | None = None) -> int | None:
    """Lenient int parse for a client-supplied field: `default` instead of an
    exception for null, junk strings, bools or non-finite numbers. Every
    message field is untrusted - one malformed value must cost the sender
    that one message, never their seat."""
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def new_code() -> str:
    while True:
        c = "".join(random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(4))
        if c not in ROOMS:
            return c


class Room:
    def __init__(self, code: str):
        self.code = code
        self.sockets: dict[str, object] = {}
        self.bomb: Bomb | None = None
        self.stage = Stage()
        self.last_flash = 0.0
        self.task = None
        self.presence_task = None
        # T13: lobby roster metadata only - never read by anything that also
        # touches Bomb state. "connected" is derived from self.sockets rather
        # than stored separately, so it can never drift out of sync with it.
        self.ready: dict[str, bool] = {}

    def attach(self, role: str, sock) -> bool:
        if role not in ROLES or role in self.sockets:
            return False
        self.sockets[role] = sock
        self.stage.attach(role)
        self._ensure_presence_loop()
        return True

    def detach(self, role: str, sock) -> None:
        if self.sockets.get(role) is sock:
            del self.sockets[role]
            self.stage.detach(role)
            # A reconnecting player has to say they're ready again - a stale
            # "ready" from before a disconnect isn't information anyone
            # should still trust.
            self.ready.pop(role, None)

    def roster(self) -> list[dict]:
        """T13: `[{role, connected, ready, required}]` - identical for every
        viewer, unlike Stage.presence(). Never reads self.bomb, so it can be
        broadcast freely without becoming a second, unfiltered channel for
        bomb state."""
        return [{"role": r, "connected": r in self.sockets,
                 "ready": self.ready.get(r, False), "required": r in REQUIRED_ROLES}
                for r in ROLES]

    def is_paused(self) -> bool:
        """T13: true only while a round is running AND at least one of the
        three required roles has disconnected. Deliberately NOT tracked as
        separate state - always recomputed from self.sockets, so it can never
        desync from what's actually connected."""
        if self.bomb is None or self.bomb.phase != "running":
            return False
        return not REQUIRED_ROLES.issubset(self.sockets.keys())

    def _ensure_presence_loop(self) -> None:
        # Presence runs independently of the bomb's 10Hz tick loop, at 20Hz,
        # and even before ARM - players should see each other in the lobby.
        # Started lazily on first attach(); guarded because some callers
        # (unit tests) invoke attach() outside a running event loop. Checking
        # for a running loop *before* constructing the coroutine (rather than
        # catching the RuntimeError from create_task) avoids leaving a bare
        # never-awaited coroutine behind.
        if self.presence_task is not None and not self.presence_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self.presence_task = loop.create_task(self._presence_loop())

    async def send(self, role: str, msg: dict) -> None:
        sock = self.sockets.get(role)
        if sock is None:
            return
        try:
            await sock.send_json(msg)
        except Exception:
            self.sockets.pop(role, None)

    async def broadcast_state(self) -> None:
        if self.bomb is None:
            for role in list(self.sockets):
                await self.send(role, {"type": "lobby", "room": self.code,
                                       "roster": self.roster()})
            return
        # "paused" is a Room-level annotation, not a Bomb one - added after
        # snapshot() rather than inside it, the same way T4 kept "layouts" a
        # sibling key instead of touching Bomb's own role-filtered output.
        paused = self.is_paused()
        for role in list(self.sockets):
            payload = self.bomb.snapshot(role)
            payload["paused"] = paused
            await self.send(role, {"type": "state", "role": role, "payload": payload})

    async def broadcast_presence(self) -> None:
        for role in list(self.sockets):
            await self.send(role, {"type": "presence", "payload": self.stage.presence(role)})

    async def _presence_loop(self) -> None:
        # Independent of the bomb tick loop and of ARM state - presence (who's
        # here, moving, gesturing) exists in the lobby too. Exits once nobody
        # is connected; _ensure_presence_loop() restarts it on the next attach.
        try:
            while self.sockets:
                await self.broadcast_presence()
                await asyncio.sleep(0.05)  # 20 Hz
        except asyncio.CancelledError:
            pass

    async def log(self, text: str) -> None:
        for role in list(self.sockets):
            await self.send(role, {"type": "log", "text": text})

    async def start(self, seed=None, modules: int = 2, seconds: float = 300.0,
                     probe_echo: bool = True, precise_pointing: bool = False,
                     mirror: bool = False) -> None:
        # Refuse to clobber a bomb that's still running - REARM (or a stray
        # extra ARM click) may only replace a bomb that hasn't been created
        # yet or has already ended in "won"/"lost".
        if self.bomb is not None and self.bomb.phase == "running":
            return
        self.bomb = Bomb(seed if seed is not None else random.randrange(2 ** 31),
                         module_count=modules, seconds=seconds,
                         roles=set(self.sockets.keys()), mirror=mirror)
        # T18: Mirror forces probe_echo off, overriding even an explicit
        # request - watching BLIND's probe-echo ring at its shared-layout
        # position while DEAF describes a different position entirely would
        # reveal the flip instantly (see AGENTS.md T18).
        self.stage.probe_echo = False if mirror else probe_echo
        self.stage.precise_pointing = precise_pointing
        # A stale probe/charge/pointer from the previous round could
        # momentarily point at a slot that doesn't exist in the new bomb's
        # modules.
        self.stage.avatars["blind"].probe = None
        self.stage.avatars["blind"].charge = None
        for a in self.stage.avatars.values():
            a.pointer = None
        await self.log("Bomb armed. Seed %d." % self.bomb.seed)
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._loop())

    async def _tick_once(self, dt: float) -> None:
        """One tick's worth of bomb-clock advancement - or none at all while
        is_paused() is true. Split out from _loop() so a test can drive a
        single deterministic tick without waiting on the real 0.1s sleep."""
        if not self.is_paused():
            self.bomb.tick(dt)
        await self.broadcast_state()

    async def _loop(self) -> None:
        last = time.monotonic()
        try:
            while self.bomb is not None and self.bomb.phase == "running":
                await asyncio.sleep(0.1)
                now = time.monotonic()
                dt = now - last
                # Always advance `last`, paused or not - otherwise the dt on
                # the tick right after a reconnect would cover the entire
                # paused span in one jump and skip that much game time.
                last = now
                await self._tick_once(dt)
            await self.broadcast_state()
        except asyncio.CancelledError:
            pass

    async def handle(self, role: str, sock, msg: dict) -> None:
        kind = msg.get("type")

        if kind == "start":
            try:
                seconds = float(msg.get("seconds", 300))
            except (TypeError, ValueError):
                seconds = 300.0
            if not math.isfinite(seconds):
                seconds = 300.0
            await self.start(seed=_int(msg.get("seed")),
                             modules=_clamp(_int(msg.get("modules"), 2), *MODULE_RANGE),
                             seconds=_clamp(seconds, *SECONDS_RANGE),
                             probe_echo=bool(msg.get("probe_echo", True)),
                             precise_pointing=bool(msg.get("precise_pointing", False)),
                             mirror=bool(msg.get("mirror", False)))

        elif kind == "act" and self.bomb is not None:
            idx, action = _int(msg.get("module")), msg.get("action")
            # Paused means paused: the clock and needy modules already stop
            # while a required player is missing, so BLIND's hands do too -
            # otherwise a cut could land while DEAF or MUTE can't see it.
            if idx is None or not isinstance(action, dict) or self.is_paused():
                return
            r = self.bomb.act(role, idx, action)
            if r is Result.STRIKE:
                await self.log("STRIKE  (%d/%d)" % (self.bomb.strikes, self.bomb.max_strikes))
            elif r is Result.SOLVED:
                await self.log("Module %d defused." % (idx + 1))
            await self.broadcast_state()

        elif kind == "probe" and self.bomb is not None:
            idx, cell = _int(msg.get("module")), _int(msg.get("cell"))
            if idx is None or cell is None:
                return
            # Only the indices go to Stage - never `data` (the inspect()
            # result below), which is what keeps the descriptor text unicast.
            self.stage.apply_probe(role, idx, cell)
            data = self.bomb.inspect(role, idx, {"cell": cell})
            await self.send(role, {"type": "probe_result", "module": idx, "data": data})

        elif kind == "flash" and role == "mute":
            now = time.monotonic()
            card = msg.get("card")
            if card in CARDS and now - self.last_flash >= FLASH_COOLDOWN:
                self.last_flash = now
                await self.send("deaf", {"type": "flash", "card": card})
                await self.send("mute", {"type": "flash_ok", "card": card})

        elif kind == "pose":
            self.stage.apply_pose(role, msg.get("yaw", 0.0), msg.get("pitch", 0.0),
                                  msg.get("gaze"))
            # No immediate broadcast - poses are batched by _presence_loop at
            # 20Hz rather than fanned out on every single message.

        elif kind == "gesture":
            self.stage.apply_gesture(role, msg.get("kind", ""))

        elif kind == "point":
            self.stage.apply_point(role, msg.get("target"))

        elif kind == "charge":
            # Presence-layer, like pose/gesture/point above - not gated on
            # self.bomb, since Stage never needs to know whether a bomb
            # exists to track where BLIND's hold currently is.
            if msg.get("action") == "start":
                module, cell = _int(msg.get("module")), _int(msg.get("cell"))
                # No ring for a commit that a paused round would refuse anyway.
                if module is not None and cell is not None and not self.is_paused():
                    self.stage.start_charge(role, msg.get("kind", ""), module, cell)
            else:
                self.stage.stop_charge(role)

        elif kind == "ready":
            # Lobby metadata only - never touches self.bomb. Rebroadcasting
            # immediately (rather than waiting for the next unrelated
            # message) is what makes the roster feel live on index.html and
            # on the other players' pages.
            self.ready[role] = bool(msg.get("value", True))
            await self.broadcast_state()

        elif kind == "hello":
            await self.broadcast_state()
            await self.broadcast_presence()
