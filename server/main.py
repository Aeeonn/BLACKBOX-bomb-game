
"""FastAPI entrypoint.  python -m uvicorn server.main:app --reload --port 8000"""
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .room import ROOMS, Room, new_code

CLIENT = Path(__file__).resolve().parent.parent / "client"
app = FastAPI(title="BLACKBOX")


@app.post("/api/room")
async def create_room():
    code = new_code()
    ROOMS[code] = Room(code)
    return {"room": code}


@app.get("/api/rooms")
async def list_rooms():
    return {c: sorted(r.sockets.keys()) for c, r in ROOMS.items()}


@app.get("/manual/{code}", response_class=HTMLResponse)
async def manual(code: str):
    room = ROOMS.get(code.upper())
    if room is None or room.bomb is None:
        return HTMLResponse("<p>No armed bomb in this room yet.</p>")
    css = (CLIENT / "common" / "manual.css").read_text(encoding="utf-8")
    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'><title>Manual %s</title><style>%s</style>"
        "<h1>Defusal Manual</h1><p class='seed'>Room %s / seed %d</p>%s"
        % (code.upper(), css, code.upper(), room.bomb.seed, room.bomb.manual_html()))


@app.websocket("/ws")
async def ws_endpoint(sock: WebSocket):
    await sock.accept()
    code = (sock.query_params.get("room") or "").upper()
    role = sock.query_params.get("role") or "hands"
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
            await room.handle(role, sock, await sock.receive_json())
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        room.detach(role, sock)


app.mount("/", StaticFiles(directory=str(CLIENT), html=True), name="client")
