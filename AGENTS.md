# AGENTS.md — BLACKBOX build contract

Read this in full before writing any code. It is the contract for every change in this repo. Place it at the repo root so your coding agent picks it up automatically.

Design rationale lives in `bomb-game-design-doc.md`. This file is the *engineering* contract. Where they disagree, this file wins.

---

## What this project is

A 3–5 player asymmetric co-op bomb-defusal game. All players are **embodied in one shared room**, sitting around one table with one bomb on it. They can see each other's bodies, heads, hands and gestures in real time.

What they **cannot** see is what the other players *perceive*. The bomb renders differently to each role, from a single shared geometry.

Voice runs on **Discord** (players use Discord's own Mute / Deafen buttons). This app supplies the room, the bomb, the role-filtered perception, and a generated manual.

---

## THE CENTRAL CONCEPT: three data channels

Every byte the server sends belongs to exactly one of three channels. Almost every bug that could ruin this game is a byte in the wrong channel.

| Channel | Contains | Shared? |
|---|---|---|
| **WORLD** | Geometry and structure. Where the table is, that this module has six wire slots, where slot 3 sits in space. | **Identical for everyone.** |
| **PRESENCE** | Embodiment. Head pose, gaze target, hand position, gestures, pointer rays, commit-charge progress, who is connected. | **Shared, but detail-filtered per role** (see matrix below). |
| **PERCEPTION** | Properties. Colours, textures, labels, braille letters, needle readings, manual text. | **Never crosses roles. Ever.** |

The one-sentence version, and the thing to check every change against:

> **Structure and bodies are shared. Properties are not.**

Knowing that a wire *exists at slot 3* is WORLD. Knowing that BLIND's hand is *hovering over slot 3* is PRESENCE. Knowing that slot 3 is *green and braided* is PERCEPTION. The first two are broadcast. The third is filtered and, for textures, unicast.

---

## HARD RULES — never violate, never "improve"

1. **PERCEPTION never crosses roles.** BLIND's payload contains no colours, labels or readings. DEAF's payload contains no textures or braille dot patterns. MUTE's payload contains no bomb properties at all. Enforced by `tests/test_invariants.py`. If that test fails, **the change is wrong — never weaken the test.**

2. **PRESENCE must never smuggle PERCEPTION.** Broadcasting *where* BLIND's hand is, is required and correct. Broadcasting the descriptor text under that hand is a game-ending leak. Same for pointer rays: the target index is shareable, the target's properties are not. When you add any presence field, ask: *is this a position, or is this a property?*

3. **One geometry, three skins.** Every module produces exactly one spatial layout via `layout()`, shared by all roles. Roles differ only in how it is *painted*. Never build separate geometry per role — divergent layouts is how Mirror and coordinate mismatch break, and how leaks hide.

4. **Avatars always render, for everyone.** No role may be invisible or absent from the scene. The social layer is the game. A disconnected player's seat stays, greyed.

5. **BLIND receives low-detail presence only.** Other players appear to BLIND as positional silhouettes: seat location and gross body motion, and nothing else. No head pose, no gestures, no pointer rays, no flashcards. This is a **hard rule, not a cosmetic choice** — it is the only thing preventing MUTE from signalling BLIND directly and collapsing the comms ring.

6. **All rule logic lives on the server.** The client renders and sends intents. Never put a rule table, a solution, or a validity check in JavaScript.

7. **`Module.solution()` is for testbenches only.** Never in any payload, log line, or HTTP response other than the manual.

8. **No npm, no bundler, no build step.** Plain ES modules served as static files. *Exception:* one CDN-loaded ES-module rendering library may be added **with explicit human approval**, imported directly by URL. Nothing else.

9. **No new Python dependencies** beyond `fastapi`, `uvicorn`, `pytest` without asking the human first.

10. **No text chat and no screen sharing.** Do not add a chat box "for convenience." One typed sentence collapses the entire game.

11. **Adding a module requires zero engine changes** — one new file in `server/modules/`, one `@register` decorator. If you are editing `bomb.py` or `stage.py` to support a specific module, the abstraction is wrong. Stop and say so.

12. **The commit-hold stays, and it is broadcast.** BLIND's destructive actions require a 1s hold (2s discharge), and the charging progress is PRESENCE — every role sees the ring filling. It exists precisely so MUTE can see the mistake beginning and slam STOP. Do not optimise it away, and do not make it local-only.

---

## Roles

| Role | Discord | Sees the bomb as | Sees others as | Speaks to | Acts |
|---|---|---|---|---|---|
| **BLIND** | normal | featureless shell + own probe descriptor | silhouettes only (rule 5) | DEAF, MUTE | **yes — only role that may act** |
| **DEAF** | **Deafened** | full exterior detail | full detail | BLIND, MUTE | no |
| **MUTE** | **Muted** | featureless shell + slot indices | full detail | nobody (gestures + flashcards) | no |
| **SCOPE** | Muted | internal netlist only, no exterior | full detail | nobody (draws to MUTE) | no |
| **DISPATCH** | normal | timer, strikes, needy alarms, per-module solved/unsolved, ALL edge flags (tactile + visual) — zero module contents | full detail | BLIND | no |

**Comms ring:** `BLIND --voice--> MUTE --gesture/flashcard--> DEAF --voice--> BLIND`

MUTE hears everything and therefore knows the answer first. MUTE is also the only player who cannot speak. That asymmetry is the engine of the game — protect it.

**DISPATCH is an aggregator:** it receives every edge flag (both BLIND's tactile ones and DEAF's/SCOPE's visual ones), plus per-module solved/unsolved status, needy alarms, timer and strikes. It must receive zero module contents — no colours, textures, braille, rule tables, or layout-level detail beyond "module 2 is unsolved." Its whole value is holding the cross-cutting flags nobody else can see in full; guard that separation when wiring `Bomb.snapshot("dispatch")`.

---

## Presence filter matrix

Rows are presence fields; columns are the role **receiving** the broadcast. `own` means a player always receives their own field at full detail.

| Field | → DEAF | → MUTE | → BLIND | → SCOPE / DISPATCH |
|---|---|---|---|---|
| seat position, connected, ready | ✓ | ✓ | ✓ | ✓ |
| gross body motion (idle sway, lean) | ✓ | ✓ | ✓ | ✓ |
| head yaw / pitch | ✓ | ✓ | **✗** | ✓ |
| gaze target (bomb / manual / player) | ✓ | ✓ | **✗** | ✓ |
| gesture (nod, shake, shrug) | ✓ | ✓ | **✗** | ✓ |
| pointer ray + target index | ✓ | ✓ | **✗** | ✓ |
| MUTE's active flashcard | ✓ | own | **✗** | **✗** |
| BLIND's probe cell index | ✓ | ✓ | own | ✓ |
| BLIND's probe **descriptor text** | **✗** | **✗** | own (unicast) | **✗** |
| BLIND's commit-charge progress | ✓ | ✓ | own | ✓ |

Every `✗` in the BLIND column is load-bearing. Every `✓` in the DEAF and MUTE columns is a comedy generator. Do not "simplify" this table into "broadcast everything."

---

## Architecture

```
client (dumb renderer)  <--JSON over WebSocket-->  server (authoritative)
                                                     Room -> Bomb -> [Module]
                                                          -> Stage -> [Avatar]
```

- `Room` owns sockets, role assignment, both tick loops, and message dispatch.
- `Bomb` owns edge flags, module instances, timer, strikes, and `snapshot(role)`.
- `Stage` owns avatars, poses, gestures, pointers and `presence(role)`. **`Stage` never reads module properties** — that separation is what makes rule 2 easy to hold.
- `Module` is the unit of gameplay. See the ABC in `server/modules/base.py`.

Two tick rates:

- **game state — 10 Hz** (timer, strikes, module state)
- **presence — 20 Hz** (poses, batched; clients interpolate between frames)

### Wire protocol

Client → server:

```
{"type":"hello"}
{"type":"start",   "modules":2, "seconds":300, "seed":null}
{"type":"act",     "module":0, "action":{"cut":2}}         # BLIND only
{"type":"probe",   "module":0, "cell":2}                   # BLIND only, private reply
{"type":"pose",    "yaw":0.3, "pitch":-0.1, "gaze":"manual"}   # ~20Hz, any role
{"type":"gesture", "kind":"shake"}                         # any role
{"type":"point",   "target":{"module":1}}                  # any role except BLIND
{"type":"flash",   "card":"STOP"}                          # MUTE only, 2s cooldown
```

Server → client:

```
{"type":"state",    "role":"blind", "payload":{...}}            # 10Hz, PERCEPTION+WORLD
{"type":"presence", "players":[{...filtered per matrix...}]}    # 20Hz, PRESENCE
{"type":"probe_result", "module":0, "data":{"cell":2,"text":"ribbed, warm"}}  # UNICAST
{"type":"flash",    "card":"STOP"}                              # to DEAF only
{"type":"log",      "text":"STRIKE (1/3)"}
{"type":"error",    "text":"..."}
```

`probe_result` is **unicast and stays unicast.** Texture never enters broadcast state, so it cannot be recovered from DevTools by inspecting received messages. The *cell index* travels in `presence`; the *text* never does.

---

## Module ABC additions

Modules now declare geometry. `layout()` is WORLD — identical for every role.

```python
@dataclass
class Slot:
    idx: int
    kind: str          # "wire" | "button" | "dial" | "tile" | "vent"
    x: float           # 0..1 across the module's face
    y: float           # 0..1 down the module's face
@dataclass
class Layout:
    w: int             # face grid width
    h: int             # face grid height
    slots: list[Slot]
```

`layout()` must contain **no properties** — no colour, no texture, no label. If you find yourself wanting to put one there, it belongs in `views()`.

---

## Definition of done — every ticket

- [ ] `pytest tests` passes, including `test_invariants.py`
- [ ] New presence fields are added to the presence-filter test, not just the code
- [ ] A testbench exists for any new module (golden path over ≥200 seeds + fuzz)
- [ ] No new dependency
- [ ] Manually verified in 3 browser tabs via `python tools/devroom.py`
- [ ] No rule logic added to the client

---

## Ticket backlog

Work top to bottom. One ticket per commit. State your plan before coding and wait for the human's go-ahead.

**T1 — Run it.** ✅ *Done.*

**T2 — Win/lose overlay.** Full-screen DEFUSED / DETONATED on all roles. MUTE gets REARM, which must generate a genuinely fresh seed, not reset the current bomb. Share the overlay via a module in `client/common/`; do **not** merge the HTML pages.

**T3 — Timer audio, BLIND and MUTE only.** WebAudio tick, faster under 30s. **Must not play on `deaf.html`.** Gate client-side by `ROLE` with a comment explaining why. Note: `test_invariants.py` cannot catch a mistake here — flag it for manual check.

**T4 — Geometry in the Module ABC.** Add `Slot`, `Layout`, `Module.layout()`. Port M1 to declare its wire slots. `layout()` goes in the WORLD portion of every role's payload, identical for all. No visual change yet. Prove identity across roles with a test.

**T5 — Extract the module pool.** `Bomb` currently hardcodes `BraidHue`. Select from `modules.base.REGISTRY` by id, pool passed into the constructor. Then make it player-count aware: modules declare `requires_roles: set[str] = set()` and the pool excludes any module whose requirement is unmet. A `blind/deaf/mute` room must never generate a SCOPE-dependent module. Test both.

**T6 — Presence protocol.** `Stage` class, `pose`/`gesture` messages, 20 Hz batched `presence` broadcast, per-role filtering per the matrix above. No rendering yet — verify with a test asserting BLIND's presence payload contains no `yaw`, `pitch`, `gaze`, `gesture`, `pointer` or `card` keys for other players. **This test is as important as `test_invariants.py`.**

**T7 — The Stage renderer.** `client/common/stage.js`: fixed first-person camera at a round table, bomb in the centre, other players as seated bust avatars across from you. Mouse moves your head; others' heads interpolate between presence frames. Keep the renderer behind a small interface (`init`, `setPresence`, `setBomb`, `render`) so the backend can be swapped later without touching game code.

**T8 — Three bomb skins.** One `layout()`, three paints: DEAF full detail; BLIND featureless shell with only the probed cell highlighted; MUTE featureless shell with slot indices and nothing else. All three read the same geometry.

**T9 — Hand avatar and probe echo.** BLIND's probe cell renders as a hand on the bomb, visible to DEAF, MUTE and SCOPE. Descriptor stays unicast. Add match flag `probe_echo` (default `true`).

**T10 — Broadcast the commit ring.** When BLIND holds to cut, a charging ring renders on that slot **for every role**. This is the payoff for the whole presence layer — MUTE must be able to see the mistake starting.

**T11 — Gaze and gestures.** Mouse-look sets head pose. Rapid horizontal mouse motion emits `shake`; vertical emits `nod`. Looking down at MUTE's lectern sets `gaze:"manual"`, so DEAF can see MUTE is reading. Detection is client-side; the emitted gesture is authoritative.

**T12 — MUTE's console.** Flashcard board rendered in-world on MUTE's desk. Cards flash to DEAF only, 2s global cooldown, unchanged. Add MUTE's pointer: **module-level resolution by default** (`precise_pointing` flag, default `false`). Cell-level pointing makes MUTE too fluent; leave it off until the humans ask for it.

**T13 — Lobby roster and comms map.** Live roster of `{role, connected, ready}`; `blind/deaf/mute` required, `scope/dispatch` marked optional. Taken roles greyed on `index.html`. ARM disabled until the core three are present. Disconnect mid-match greys the seat and pauses the timer. Per-role comms card: *"You are DEAF. Deafen in Discord. Keep your camera on."* Roster is metadata — zero bomb state.

> ### ⏸ STOP HERE AND PLAY A REAL ROUND WITH THREE PEOPLE. Everything above is the game's skeleton. Everything below is content. Do not build content before finding out whether the room feels alive. Expect to change T9–T12 based on what happens.

**T14 — M2 "The Ledger."** Six tiles with decorative braille-style dot art (client-side flavour only, no real encoding). BLIND probes a tile and is told its own plain number outright (`reads 4`) - no dot-decoding step. DEAF sees a different, independently-generated number printed on each tile. MUTE's manual holds the (BLIND number, DEAF number) → PRESS/SKIP table. *(Simplified from the original alphabet-chart idea during playtesting - reading a number aloud plays far better than describing raised dots.)*

**T15 — Needy support + N1 "The Vent."** `Module.needy`, `tick(dt)` through `Bomb.tick`. Every ~45s a valve heats (BLIND probe only); DEAF sees which of three vents glows; MUTE has the purge sequence. Unpurged 15s = strike.

**T16 — M3 "Gauge & Detents."** BLIND turns a knob feeling detent clicks and one deeper notch. DEAF watches a needle on a labelled dial. MUTE knows the target zone. Continuous relay, no discrete answer.

**T17 — Manual print polish.** `/manual/{code}` prints cleanly to A4, one module per page, page numbers, seed in the footer.

**T18 — Mirror modifier.** BLIND's cell indices horizontally flipped relative to DEAF's. Mentioned only in a generated manual footnote. Implement in `Bomb`, not per-module, and **force `probe_echo` off when Mirror is active** — otherwise watching the hand reveals the flip instantly.

**T19 — SCOPE drawing canvas.** Strokes relayed and rendered **only on `mute.html`**. Never sent to BLIND or DEAF. Add an invariant test.

**T20 — M8 "Netlist."** The four-hop SCOPE module. `requires_roles = {"scope"}`. Requires T19.

**T21 — Post-round timeline.** Record `(t, role, event)` including poses and gestures. Replay after DEFUSED / DETONATED. Reveal full information only *after* the round ends.

**T22 — Ghost bot.** `tools/ghost.py` connects as DEAF with scripted answers so the human can test with two players.

---

## Style

- Python: stdlib plus FastAPI. Type hints on public methods. No clever metaprogramming.
- JS: ES modules, no dependencies. Each role page under ~120 lines; shared logic goes in `client/common/`.
- Roles are lowercase strings `blind|deaf|mute|scope|dispatch` everywhere — protocol, dicts, filenames, CSS classes.
- Commits: `T14: add M2 Ledger module + testbench`.

---

## Things an agent will be tempted to do — do not

- **Send everything and filter in CSS or JS.** The single worst thing you could do to this codebase. Filter in `views()` and `presence()`, on the server.
- **Give BLIND the other players' head poses** "so the scene looks better." This silently deletes the comms ring. See hard rule 5.
- **Put the probe descriptor into the presence broadcast** because the cell index is already there. This is the leak this architecture exists to prevent.
- **Let `Stage` read module properties** to render nicer avatars. `Stage` sees geometry and bodies only.
- **Build separate geometry per role.** One `layout()`, three skins.
- **Add a spectator or debug view** showing all roles at once. Behind `--dev` only, never linked from the lobby.
- **Replace the probe with a hover tooltip.** The slowness is the mechanic.
- **Add difficulty by shortening the timer.** Difficulty is module count and rule-table complexity.
- **Merge the role pages into one page with role switching.** Separate pages are what make leaks obvious on inspection.
- **Add a chat box, subtitles, or speech-to-text.** Especially not "just for DEAF."
