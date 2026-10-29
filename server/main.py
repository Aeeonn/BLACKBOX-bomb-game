
"""FastAPI entrypoint.  python -m uvicorn server.main:app --reload --port 8000"""
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .room import ROOMS, Room, new_code

CLIENT = Path(__file__).resolve().parent.parent / "client"
app = FastAPI(title="BLACKBOX")
log = logging.getLogger("uvicorn.error")


@app.post("/api/room")
async def create_room():
    code = new_code()
    ROOMS[code] = Room(code)
    return {"room": code}


@app.get("/api/rooms")
async def list_rooms():
    return {c: sorted(r.sockets.keys()) for c, r in ROOMS.items()}


@app.get("/api/room/{code}")
async def room_info(code: str):
    # T13: lets index.html show a live "who's taken" roster via plain
    # polling, without opening a websocket just to watch the lobby fill up.
    room = ROOMS.get(code.upper())
    if room is None:
        return {"error": "no such room"}
    return {"code": code.upper(), "roster": room.roster(), "armed": room.bomb is not None}


@app.get("/manual/{code}", response_class=HTMLResponse)
async def manual(code: str):
    room = ROOMS.get(code.upper())
    if room is None or room.bomb is None:
        return HTMLResponse("<p>No armed bomb in this room yet.</p>")
    css = (CLIENT / "common" / "manual.css").read_text(encoding="utf-8")
    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'><title>Manual %s</title>"
        "<link rel='icon' href='/common/icon.svg'><style>%s</style>"
        "<h1>Defusal Manual</h1><p class='seed'>Room %s / seed %d</p>%s"
        "<div class='print-footer'>Room %s &middot; Seed %d</div>"
        % (code.upper(), css, code.upper(), room.bomb.seed, room.bomb.manual_html(),
           code.upper(), room.bomb.seed))


@app.websocket("/ws")
async def ws_endpoint(sock: WebSocket):
    await sock.accept()
    code = (sock.query_params.get("room") or "").upper()
    role = sock.query_params.get("role") or "blind"
    room = ROOMS.get(code)
    if room is None:
        await sock.send_json({"type": "error", "text": "no such room: " + code})
        await sock.close()
        return
    if not room.attach(role, sock):
        await sock.send_json({"type": "error", "text": "role taken or invalid: " + role})
        await sock.close()
        return
    try:
        await room.broadcast_state()
        while True:
            try:
                msg = await sock.receive_json()
            except (ValueError, TypeError, KeyError):
                continue  # not JSON at all - drop the frame, keep the player
            if not isinstance(msg, dict):
                continue
            # Failures are isolated per message. Before this, any exception
            # from one malformed message fell through to the outer handler
            # and detached the sender - pausing the round for everyone over
            # a single bad field.
            try:
                await room.handle(role, sock, msg)
            except Exception:
                log.exception("ignored bad %r message from %s in room %s",
                              msg.get("type"), role, code)
                await room.send(role, {"type": "error", "text": "ignored a malformed message"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        room.detach(role, sock)
        # T13: without this, the remaining players wouldn't see an updated
        # roster (or a newly-paused timer) until whatever unrelated message
        # happened to trigger the next broadcast - could be seconds late.
        await room.broadcast_state()


app.mount("/", StaticFiles(directory=str(CLIENT), html=True), name="client")
