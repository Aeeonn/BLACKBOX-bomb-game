
"""Room: sockets, role assignment, message handling, tick loop."""
import asyncio
import random
import time

from .bomb import Bomb
from .modules.base import Result

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
        self.last_flash = 0.0
        self.task = None

    def attach(self, role: str, sock) -> bool:
        if role not in ROLES or role in self.sockets:
            return False
        self.sockets[role] = sock
        return True

    def detach(self, role: str, sock) -> None:
        if self.sockets.get(role) is sock:
            del self.sockets[role]

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

    async def log(self, text: str) -> None:
        for role in list(self.sockets):
            await self.send(role, {"type": "log", "text": text})

    async def start(self, seed=None, modules: int = 2, seconds: float = 300.0) -> None:
        self.bomb = Bomb(seed if seed is not None else random.randrange(10000),
                         module_count=modules, seconds=seconds)
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
                             seconds=float(msg.get("seconds", 300)))

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
            data = self.bomb.inspect(role, idx, {"cell": msg.get("cell", 0)})
            await self.send(role, {"type": "probe_result", "module": idx, "data": data})

        elif kind == "flash" and role == "book":
            now = time.monotonic()
            card = msg.get("card")
            if card in CARDS and now - self.last_flash >= FLASH_COOLDOWN:
                self.last_flash = now
                await self.send("eyes", {"type": "flash", "card": card})
                await self.send("book", {"type": "flash_ok", "card": card})

        elif kind == "hello":
            await self.broadcast_state()
