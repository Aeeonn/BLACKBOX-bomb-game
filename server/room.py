
"""Room: sockets, role assignment, message handling, tick loop."""
import asyncio
import random
import time

from .bomb import Bomb
from .modules.base import Result
from .stage import Stage

ROLES = ["hands", "eyes", "book", "scope", "dispatch"]
CARDS = ["STOP", "GO", "YES", "NO", "WAIT", "AGAIN", "1", "2", "3", "4", "LEFT", "RIGHT"]
FLASH_COOLDOWN = 2.0

ROOMS: dict[str, "Room"] = {}


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
                                       "roles": sorted(self.sockets.keys())})
            return
        for role in list(self.sockets):
            await self.send(role, {"type": "state", "role": role,
                                   "payload": self.bomb.snapshot(role)})

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
                     probe_echo: bool = True) -> None:
        # Refuse to clobber a bomb that's still running - REARM (or a stray
        # extra ARM click) may only replace a bomb that hasn't been created
        # yet or has already ended in "won"/"lost".
        if self.bomb is not None and self.bomb.phase == "running":
            return
        self.bomb = Bomb(seed if seed is not None else random.randrange(2 ** 31),
                         module_count=modules, seconds=seconds,
                         roles=set(self.sockets.keys()))
        self.stage.probe_echo = probe_echo
        # A stale probe/charge from the previous round could momentarily
        # point at a slot that doesn't exist in the new bomb's modules.
        self.stage.avatars["hands"].probe = None
        self.stage.avatars["hands"].charge = None
        await self.log("Bomb armed. Seed %d." % self.bomb.seed)
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        last = time.monotonic()
        try:
            while self.bomb is not None and self.bomb.phase == "running":
                await asyncio.sleep(0.1)
                now = time.monotonic()
                self.bomb.tick(now - last)
                last = now
                await self.broadcast_state()
            await self.broadcast_state()
        except asyncio.CancelledError:
            pass

    async def handle(self, role: str, sock, msg: dict) -> None:
        kind = msg.get("type")

        if kind == "start":
            await self.start(seed=msg.get("seed"),
                             modules=int(msg.get("modules", 2)),
                             seconds=float(msg.get("seconds", 300)),
                             probe_echo=bool(msg.get("probe_echo", True)))

        elif kind == "act" and self.bomb is not None:
            idx = int(msg.get("module", 0))
            r = self.bomb.act(role, idx, msg.get("action", {}))
            if r is Result.STRIKE:
                await self.log("STRIKE  (%d/%d)" % (self.bomb.strikes, self.bomb.max_strikes))
            elif r is Result.SOLVED:
                await self.log("Module %d defused." % (idx + 1))
            await self.broadcast_state()

        elif kind == "probe" and self.bomb is not None:
            idx = int(msg.get("module", 0))
            cell = int(msg.get("cell", 0))
            # Only the indices go to Stage - never `data` (the inspect()
            # result below), which is what keeps the descriptor text unicast.
            self.stage.apply_probe(role, idx, cell)
            data = self.bomb.inspect(role, idx, {"cell": cell})
            await self.send(role, {"type": "probe_result", "module": idx, "data": data})

        elif kind == "flash" and role == "book":
            now = time.monotonic()
            card = msg.get("card")
            if card in CARDS and now - self.last_flash >= FLASH_COOLDOWN:
                self.last_flash = now
                await self.send("eyes", {"type": "flash", "card": card})
                await self.send("book", {"type": "flash_ok", "card": card})

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
            # exists to track where HANDS' hold currently is.
            if msg.get("action") == "start":
                self.stage.start_charge(role, msg.get("kind", ""),
                                        int(msg.get("module", 0)), int(msg.get("cell", 0)))
            else:
                self.stage.stop_charge(role)

        elif kind == "hello":
            await self.broadcast_state()
            await self.broadcast_presence()
