\# BLACKBOX â€” Design \& Build Document



\_v2 â€” the shared-room revision\_



A 3â€“5 player asymmetric co-op defusal game. Three people sit around one table with one

bomb. They can see each other. They cannot see what each other perceives.



Voice runs on Discord; the game supplies the room, the bomb, the role-filtered

perception, and a procedurally generated manual.



\---



\## 0. What changed in v2, and why



v1 was four separate dashboards. It worked, but it was three people reading three

spreadsheets at each other. The comedy lived entirely in Discord video, incidentally,

outside the game.



v2 puts all players in \*\*one room, at one table, around one bomb\*\*, embodied, in first

person. You watch the blind player's hand crawl across the casing. You watch the mute

player's head snap up from the manual and start shaking. You watch a cut begin to charge

and you have one second to stop it.



The information asymmetry is unchanged and just as strict. What's new is that the

\*social\* layer moved inside the game, where it can be mechanised.



This forced one architectural idea, which is now the spine of the whole project.



\---



\## 1. Design Laws



1\. \*\*The Ring.\*\* Information flows in a loop no two players can shortcut.

2\. \*\*Three-key rule.\*\* Every module's solution requires tactile Ã— visual Ã— a manual

&#x20;  rule. If two players can solve it alone, the module is broken. Delete it.

3\. \*\*Structure and bodies are shared. Properties are not.\*\* The whole architecture in

&#x20;  one line. See Â§2.

4\. \*\*Server-authoritative fiction.\*\* BLIND never \*receives\* colours. DEAF never

&#x20;  \*receives\* audio events. Not hidden â€” not sent.

5\. \*\*Output-limited roles are fun. Input-limited roles are boring.\*\* Any new role is a

&#x20;  rich information \*source\* with a \*crippled output channel\*.

6\. \*\*No text chat, no screen sharing.\*\* One typed sentence collapses the game.

7\. \*\*Presence is not perception.\*\* Seeing \*where\* someone's hand is, is the point.

&#x20;  Seeing \*what they feel there\* is the leak.



\---



\## 2. The three channels



| Channel | Contains | Shared? |

|---|---|---|

| \*\*WORLD\*\* | Geometry. The table, the bomb's shape, that this module has six wire slots and slot 3 is here. | Identical for everyone. |

| \*\*PRESENCE\*\* | Bodies. Head pose, gaze, hand position, gestures, pointers, commit charge. | Shared, detail-filtered per role. |

| \*\*PERCEPTION\*\* | Properties. Colour, texture, label, braille letter, needle reading, manual text. | Never crosses roles. |



Knowing a wire exists at slot 3 is WORLD. Knowing BLIND is touching slot 3 is PRESENCE.

Knowing slot 3 is green and braided is PERCEPTION.



\*\*One geometry, three skins.\*\* Every module emits one spatial `layout()` shared by all

roles. Roles differ only in how it's painted:



\- \*\*DEAF\*\* â€” full detail: colours, labels, LEDs, etched numbers, needle positions

\- \*\*BLIND\*\* â€” featureless grey shell; only the currently probed cell is highlighted,

&#x20; with a text descriptor delivered privately

\- \*\*MUTE\*\* â€” featureless grey shell with slot indices only; no properties at all



Same object, same positions, three different amounts of truth.



\---



\## 3. Roles



\### The core three



| | \*\*BLIND\*\* (blind) | \*\*DEAF\*\* (deaf) | \*\*MUTE\*\* (mute) |

|---|---|---|---|

| Discord | normal | \*\*Deafened\*\* | \*\*Muted\*\* |

| Bomb | shell + own probe | full detail | shell + slot indices |

| Other players | silhouettes only | full detail | full detail |

| Speaks to | DEAF, MUTE | BLIND, MUTE | nobody |

| Acts | \*\*yes â€” the only one who can\*\* | no | no |



\*\*Ring:\*\* `BLIND --voice--> MUTE --gesture/flashcard--> DEAF --voice--> BLIND`



MUTE hears both other players, so MUTE works out the answer first â€” and MUTE is the only

one who cannot say it. That asymmetry is the engine of the entire game.



\### Why BLIND sees only silhouettes



This is the one rule people want to break, so here's the reasoning. If BLIND could read

MUTE's head shake, MUTE would have a direct channel to the only player who can act, and

DEAF would become decorative. The ring would collapse in about ninety seconds of play.



So BLIND sees other players as positional ghosts â€” seat, presence, gross motion, nothing

more. Render it as sonar: pale outlines that pulse when someone moves. BLIND knows the

room is occupied. BLIND cannot read a face.



\### Optional fourth â€” SCOPE (X-ray)



Sees the internal netlist: topology, component shapes, pad connections. No colours, no

exterior labels, no textures. Meaningless without DEAF's colours and BLIND's textures.

Hears everyone, is \*\*muted\*\*, and communicates only by drawing on a canvas that renders

\*\*only on MUTE's screen\*\*.



Chain: `SCOPE --drawing--> MUTE --flashcard--> DEAF --voice--> BLIND`. Four hops from the

person who knows to the person who can do anything about it.



\### Optional fifth â€” GRIP or DISPATCH



\- \*\*GRIP\*\* â€” a second blind player owning the \*\*rear face\*\*, in a separate Discord

&#x20; channel, able to hear only DEAF. Enables genuine simultaneity modules. Pick this if

&#x20; your group likes fiddling.

\- \*\*DISPATCH\*\* â€” sees only the global layer: timer, strikes, edge flags, needy alarms.

&#x20; No module contents. Speaks only to BLIND. Pick this if your group likes talking.



\### Scaling



| Players | Roles |

|---|---|

| 3 | BLIND, DEAF, MUTE |

| 4 | + SCOPE |

| 5 | + GRIP \*or\* DISPATCH |



Extra roles are \*\*purely additive\*\*: no module may ever \*require\* SCOPE or DISPATCH,

except modules explicitly gated by `requires\_roles` and excluded from 3-player pools.

With 4+ players, always enable needy modules â€” extra roles create dead air otherwise.



\---



\## 4. The Stage



A fixed first-person camera, seated at a round table. The bomb sits in the centre. Other

players are bust avatars across from you. Your mouse moves your head, and everyone

(except BLIND) sees it move.



\*\*What the presence layer buys you, concretely:\*\*



\- \*\*The crawling hand.\*\* DEAF watches BLIND's hand drift across the casing and can say

&#x20; "left â€” left â€” no, back one â€” \*that\* one." This alone removes most of the

&#x20; coordinate-negotiation tedium that made v1 feel like data entry.

\- \*\*The charging ring.\*\* When BLIND holds to cut, a ring fills on that slot \*\*for

&#x20; everyone\*\*. MUTE sees the mistake begin and has one second to slam STOP. This is the

&#x20; single best interaction in the game and it only exists because of shared presence.

\- \*\*Reading posture.\*\* MUTE looking down at the lectern broadcasts `gaze:"manual"`. DEAF

&#x20; can see MUTE is mid-lookup and wait instead of repeating themselves.

\- \*\*Emergent emotes.\*\* Shake the mouse horizontally, your head shakes. Nod it, your head

&#x20; nods. No emote wheel, no menu â€” the head \*is\* the emote, and it's readable at a glance.



\*\*Pointing\*\* is deliberately coarse. MUTE's pointer resolves to a \*\*module\*\*, not a cell,

by default. Cell-level pointing plus a `CUT` card would let MUTE issue complete

instructions without the voice relay, and the ring would go slack. There's a

`precise\_pointing` flag if your group finds the default too fiddly â€” but try it strict

first.



\### The MUTE console



MUTE cannot speak. The game gives a constrained vocabulary on top of Discord video:



\- 8â€“12 large hand-drawn cards, rendered on MUTE's desk, flashing \*\*on DEAF's screen only\*\*

\- `STOP` `GO` `YES` `NO` `WAIT` `AGAIN` `1` `2` `3` `4` `LEFT` `RIGHT`

\- 2-second global cooldown â€” the constraint \*is\* the design; it prevents sentence-building



\*\*Commit delay:\*\* every destructive action requires a 1.0s hold (2.0s discharge), with

the charge visible to all. Fifteen lines of code. Best feature in the game.



\---



\## 5. Rendering "touch"



BLIND is a sighted person at a monitor. The tactile fiction comes from making

information \*\*slow and ambiguous\*\*, not from hiding it.



\*\*v1 â€” Probe grid.\*\* Arrow keys move a probe cell to cell. The current cell shows a short

descriptor only: `braided, warm`. One cell at a time, everything else blank. The cost of

scanning is the mechanic.



\*\*v2 â€” Audio textures.\*\* Each texture is a distinct short loop (scrape, click, buzz,

thrum) played on probe entry. BLIND wears headphones and must now \*describe a sound\* â€”

gloriously imprecise, and the source of most of the comedy. Freesound.org, free.



\*\*v3 â€” Gamepad rumble.\*\* Texture as rumble pattern, braille dots as pulse trains.

Optional, delightful.



\*\*Braille rule.\*\* BLIND sees raw dot positions (`dots 1,3,4`) or a pulse pattern, and is

\*\*never told the letter\*\*. Only MUTE's manual has the alphabet chart. Braille is

therefore always a two-player operation by construction.



\---



\## 6. Edge flags



Global per-match properties referenced by module rules. Cheap to implement, and they

force a full-ring pre-flight briefing before anyone touches anything.



\- \*\*BLIND-only:\*\* casing `rough|smooth|greasy`; corner screw `present|missing`; casing

&#x20; `cool|warm`; a raised braille mark underneath

\- \*\*DEAF-only:\*\* 6-char serial; badge colour; lit indicator LEDs (0â€“3); sticker

&#x20; `ACME|KOWALSKI|VOSS`

\- \*\*SCOPE-only:\*\* board revision; jumper count; whether a capacitor is bulging



Rules then read: \*"If the casing is rough AND the badge is green, invert the entire

table."\*



\---



\## 7. Module catalogue



\*\*M1 Braid \& Hue\*\* (wires) â€” BLIND feels texture and warmth; DEAF sees colour and metal

bands; MUTE holds the texture Ã— colour grid. Frayed cut last; the warm wire strikes

unless discharged.



\*\*M2 The Ledger\*\* (braille) â€” six tiles. BLIND reads dot patterns; DEAF sees etched

numbers \*\*in a shuffled order\*\*; MUTE maps letter+number to press or skip.



\*\*M3 Gauge \& Detents\*\* (dial) â€” BLIND turns a knob hunting one deeper notch; DEAF watches

a needle on a labelled dial; MUTE knows the target zone. Continuous live relay â€” the most

tense twenty seconds in the game.



\*\*M4 Silent Alarm\*\* (audio) â€” a beep pattern only BLIND and MUTE hear; a lamp flashing a

\*different\* pattern only DEAF sees. The manual intersects them.



\*\*M5 Balance Tray\*\* â€” BLIND places and removes a cube, sphere and star; DEAF watches a

scale tip toward a line; only MUTE knows the masses. Excellent with presence: everyone

watches the hand hover, undecided.



\*\*M6 The Labyrinth\*\* â€” BLIND nudges a marble, feeling bumps; DEAF sees the walls but

\*\*not the marble\*\*; MUTE knows the variant and the exit.



\*\*M7 Chord Lock\*\* â€” DEAF sees scrambled glyphs; MUTE translates glyph â†’ letter; BLIND

enters each letter as a six-dot braille chord.



\*\*M8 Netlist\*\* (SCOPE, 4+) â€” SCOPE sees unlabelled internal nets; DEAF sees numbered

exterior pads; BLIND feels which pads are raised. The full four-hop chain.



\*\*M9 The Handshake\*\* (climax) â€” all roles act inside a 3-second window. DEAF presses on

green, BLIND holds a lever until the click, MUTE hits a pedal. Nothing else in the game

demands simultaneity, so it lands hard.



\### Needy modules



\*\*N1 The Vent\*\* â€” every \~45s a valve heats (BLIND only); DEAF spots which of three vents

glows; MUTE has the purge sequence.



\*\*N2 The Chatterbox\*\* â€” a confident-sounding \*fake\* instruction only BLIND and MUTE hear.

Relaying it is a strike.



\*\*N3 Drift\*\* â€” a slider slowly slides. Everyone can see it drifting except the person who

can move it.



\### Modifiers



\*\*Mirror\*\* â€” BLIND's layout is horizontally flipped relative to DEAF's. Manual footnote

only. \*\*Disables probe echo\*\*, or watching the hand gives it away instantly.



\*\*Coordinate mismatch\*\* â€” BLIND's cells numbered 1â€“4 left to right; DEAF's labels Aâ€“D top

to bottom; the manual uses compass directions. The team must invent a convention

mid-panic.



\---



\## 8. Worked example â€” M1 "Braid \& Hue"



\*\*Generation (seeded):\*\* 3â€“6 wires; textures `braided ribbed smooth frayed sticky

glassy`; colours `red blue yellow white black green`; exactly one wire `warm`; a

`CUT`/`LEAVE`/`LAST` verdict for every (texture, colour) pair present.



\*\*Generated table, seed 7731:\*\*



| | red | blue | yellow | white | black | green |

|---|---|---|---|---|---|---|

| \*\*braided\*\* | CUT | LEAVE | CUT | LAST | LEAVE | CUT |

| \*\*ribbed\*\* | LEAVE | CUT | LAST | CUT | CUT | LEAVE |

| \*\*smooth\*\* | LAST | CUT | LEAVE | LEAVE | CUT | CUT |

| \*\*frayed\*\* | LEAVE | LAST | CUT | CUT | LEAVE | LAST |

| \*\*sticky\*\* | CUT | LEAVE | LEAVE | LAST | CUT | LEAVE |

| \*\*glassy\*\* | CUT | CUT | LAST | LEAVE | LAST | LEAVE |



\*\*Generated footnotes:\*\*

\- If the casing is \*\*greasy\*\*, swap all CUT and LEAVE entries.

\- The \*\*warm\*\* wire must be discharged (hold 2s) before cutting, whatever the table says.

\- If the serial contains a \*\*vowel\*\*, resolve LAST entries in reverse order.



\*\*Channels:\*\*

\- \*\*WORLD (all):\*\* six wire slots at fixed positions

\- \*\*BLIND:\*\* shell; probe cell 2 â†’ `ribbed, warm` (unicast)

\- \*\*DEAF:\*\* `red / blue / blue / white`, LED wired to wire 3

\- \*\*MUTE:\*\* the table above, plus a shell with indices 1â€“6

\- \*\*PRESENCE (all but BLIND in detail):\*\* hand on slot 2, charge ring at 0%



\---



\## 9. Tech stack



| Layer | Choice | Rationale |

|---|---|---|

| Server | Python 3.11 + FastAPI + WebSockets | You know Python. One process. |

| Client | Plain HTML/CSS/ES modules, no build step | Framework overhead exceeds the app |

| Renderer | \*\*2D canvas diorama\*\* (`client/common/stage.js`) | First person without 3D risk |

| Transport | JSON over WebSocket, two tick rates | state 10 Hz, presence 20 Hz interpolated |

| State | In-memory Room objects | No database |

| Art | Hand-drawn â†’ phone scan â†’ PNG | Manual glyphs, flashcards, avatars |

| Manual | Server-rendered HTML + print stylesheet | MUTE can print it |

| Voice | Discord | Free, has Mute and Deafen |

| Hosting | Your PC + Cloudflare Tunnel | $0, one command, public HTTPS |



\*\*On 3D:\*\* real 3D (Three.js via CDN ESM, no build step) is a legitimate later upgrade,

but the hard part of v2 is the \*\*presence protocol\*\*, which is renderer-agnostic. Build

the protocol against a 2D diorama, playtest it, and swap renderers later if the room

feels flat. `stage.js` exposes `init / setPresence / setBomb / render` precisely so that

swap costs one file.



\*\*Verilog note:\*\* a game module is an HDL module. `generate(seed)` is elaboration,

`views()` are output ports fanned per role, `layout()` is the pinout, `act()` is a

clocked input, needy modules have a `tick()`. Write a pytest testbench per module that

drives random action sequences and asserts no crash and no unwinnable state.



\---



\## 10. Repo structure



```

blackbox/

&#x20; server/

&#x20;   main.py            # FastAPI app, static mount, /ws

&#x20;   room.py            # Room: players, roles, phase, seed, dispatch

&#x20;   bomb.py            # Bomb: flags, modules, timer, strikes, snapshot(role)

&#x20;   stage.py           # Stage: avatars, poses, gestures, presence(role)

&#x20;   protocol.py        # message dataclasses

&#x20;   modules/

&#x20;     base.py          # Module ABC + Slot/Layout + registry

&#x20;     m01\_braid\_hue.py

&#x20;     ...

&#x20;   manual/render.py

&#x20; client/

&#x20;   index.html         # lobby, roster, role picker

&#x20;   blind.html  deaf.html  mute.html  scope.html

&#x20;   common/net.js      # websocket wrapper, reconnect

&#x20;   common/stage.js    # the diorama renderer

&#x20;   common/overlay.js  # win/lose

&#x20;   assets/

&#x20; tests/

&#x20;   test\_invariants.py # PERCEPTION leak test

&#x20;   test\_presence.py   # PRESENCE filter test

&#x20;   test\_m01.py

&#x20; tools/

&#x20;   devroom.py  ghost.py

```



\---



\## 11. Build phases



| Phase | Tickets | Output |

|---|---|---|

| \*\*0 â€” Paper prototype\*\* | â€” | Blindfold, headphones, spreadsheet. Validates the ring. |

| \*\*1 â€” Spike\*\* | T1 âœ… | Four tabs receiving different JSON |

| \*\*2 â€” Round loop\*\* | T2â€“T3 | Win/lose, timer audio |

| \*\*3 â€” Foundations\*\* | T4â€“T5 | Geometry in the ABC, module pool, role-aware pool |

| \*\*4 â€” The room\*\* | T6â€“T13 | Presence protocol, stage, skins, hand avatar, charge ring, gestures, MUTE console, lobby |

| \*\*â¸ PLAYTEST\*\* | | \*\*Three humans. Before any more content.\*\* |

| \*\*5 â€” Content\*\* | T14â€“T18 | M2, needy N1, M3, manual polish, Mirror |

| \*\*6 â€” Extra roles\*\* | T19â€“T20 | SCOPE canvas, M8 Netlist |

| \*\*7 â€” Juice\*\* | T21â€“T22 | Timeline replay, ghost bot, new module every couple of weeks |



\---



\## 12. Cost



$0. Hosting on your own PC via Cloudflare Tunnel, Discord for voice, freesound.org for

audio, paper and a phone camera for art. Optional domain \~$12/yr.



Time, solo with an agent, evenings and weekends: the room alive in \~2â€“3 weeks, genuinely

replayable in \~6 weeks.



\---



\## 13. Risks



1\. \*\*Presence leaks perception.\*\* The new top risk, and the reason `test\_presence.py`

&#x20;  exists alongside `test\_invariants.py`. Every new presence field needs a test entry.

2\. \*\*BLIND's silhouette rule gets softened\*\* because the scene looks nicer with full

&#x20;  avatars. This deletes the comms ring. Guard it.

3\. \*\*Playtesting needs 3â€“5 humans.\*\* Your real bottleneck. Mitigate with `devroom.py`

&#x20;  and `ghost.py`.

4\. \*\*Scope creep into 3D.\*\* The diorama is enough. Ugly and tense beats pretty and calm.

5\. \*\*Puzzle design > coding.\*\* Expect to cut half the module ideas after one playtest.

6\. \*\*Roles that only listen.\*\* If a role isn't talking, it's broken.



