<div align="center">

<a href="README.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="README_zh.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>

</div>

# sim-house-nav — a robot finding its way around a house by sight

A robot stands in a house — a **Go2 quadruped** or a **G1 humanoid**, switchable — with one
forward-facing camera on its head. ANIMA sees the world through that camera, works out for
itself which room it is in and where to go, and directs the robot with three primitives.

**What this world tests**: no map, no coordinates, nobody tells it the room names, and **the
guidance does not say what is in the house**. Rooms have to be recognised by looking.

```
ANIMA (brain) ──image + eight-way ranging──▶ "this looks like the living room,
                                              I should turn" ──primitive──▶ world
                                                                              │
                                                       translated to a velocity
                                                       command (vx, vy, wz)
                                                                              ▼
                                                       a learned gait policy
                                                       actually walks the legs
                                                                              │
                                       camera takes a new frame ◀────────────┘   (loop)
```

## The action list (everything the brain can call)

| Action | What it does | Parameter | Does position change? |
|---|---|---|---|
| `move_forward` | Walk forward a distance | `meters`, 0 – `MAX_MOVE_M` (3.0) | Yes |
| `turn_left` | Turn anticlockwise on the spot | `degrees`, 0 – `MAX_TURN_DEG` (180) | No — heading only |
| `turn_right` | Turn clockwise on the spot | As above | No — heading only |
| ~~`look_around`~~ | Turn full circle taking frames | — | **Off by default since v1.0** — see below |

⛔ **None of the three contains any navigation intelligence.** Where to go, which room this
is, whether it has been found — all of that is the brain's judgement.

**About `look_around`.** The code is still there (`HOUSENAV_LOOK_AROUND=1` enables it) but
since v1.0 it is **off by default for both bodies**. Two reasons. First, it has **never once
been measured** — through v0.9 it was hidden behind the brain's capability cache for seven
experiments and never reached the tool sheet, so leaving it listed would be claiming
something that was never verified. Second, **the humanoid cannot turn on the spot** (measured:
a turn command at 0.2 rad/s for 8 seconds produced 2.8°), so "turn full circle and take
frames" does not mean anything for it. Neither body gets it for now — the question is whether
a model can find rooms on turning and ranging alone.

⚠️ Changing the actions means changing **three places together**: this table, `capabilities()`
in `world.py`, and the guidance in `guidance.py`. The phrase in the guidance saying how many
actions there are is **generated from the tools actually registered**, and the brain repo has
a test pinning "as many as it says there are".

> ⛔ **After changing the action list, restart the brain backend (:8000) or nothing has
> changed.** `RemoteWorld` **caches a world's capabilities at the first handshake** and does
> not ask again. Restart the world, add the tool — the backend still holds the old list, and
> the new action never appears on the model's tool sheet. To diagnose:
> `curl -s localhost:8000/api/awi` and look at the tool names the brain **actually** has, not
> at what the world offers. (This cost seven experiments on 2026-07-25 after `look_around` was
> added: it was never used, which looked like the model not wanting it, when in fact it had
> never seen it.)

## How it really walks and turns

**Nothing teleports and no arrow is faked.** The robot runs a **velocity-conditioned** motion
policy trained in Isaac Lab and exported to ONNX. Its observation carries a command
`(vx, vy, wz)` — forward speed, lateral speed and **yaw rate**. During training that command
is randomised and the reward pushes the policy to track it. At deployment each control step
(50 Hz) feeds in the desired velocity and the policy emits twelve joint targets, so the legs
walk out that velocity with a real gait.

| Primitive | Velocity command the world sends |
|---|---|
| Forward | `vx = +WALK_SPEED`, `wz = 0` |
| Turn left | `wz = +TURN_RATE`, `vx ≈ 0` (in place) |
| Turn right | `wz = −TURN_RATE` |
| Stop | `(0, 0, 0)` — stand |

A real Go2 deployment uses the same interface: the on-board policy takes `(vx, vy, wz)` from a
gamepad or a high-level planner.

**The primitives execute closed loop.** A learned gait does not track a velocity command 1:1
(measured: about 83% in a straight line, about 62% turning), so dispatching open loop by time
systematically falls short and the navigation drifts. Instead the world measures as it goes,
**stops when the measured distance or angle is reached**, and reports honestly how far it
actually went and how many degrees it actually turned. Walking into a wall is reported as
stuck, and says so.

## What counts as "arrived" (decided 2026-07-25)

**Seeing it counts.** If ANIMA can clearly see the target room and name the landmarks it sees,
that is done — the body does not have to be all the way inside. Standing in the doorway,
looking into the kitchen and recognising the hob and the oven counts as finding the kitchen.

So when checking against `/status`, **do not compare `room_label` mechanically**: the dog can
be in the doorway with its body centre still outside (`room_label` shows the previous room),
and if it genuinely saw and recognised the kitchen it passes. The other way round too — if it
declares arrival on the strength of some indistinct cupboard doors, that fails. The criterion
is **recognising landmarks**.

> Background: this used to be "must actually walk in and look at the floor material", and in
> practice it got stuck agonising over a 13 cm threshold. The rule changed because for a
> navigation task the point is *knowing where the thing is*, and half a body length does not
> bear on that.

## What the brain can see (the AWI observation)

Only what a real robot would actually carry:

- **the camera image** (head, forward-facing, 640×480)
- `heading_deg` — IMU compass heading
- `clearance_m` — **laser ranging**: how far it could walk in each of eight directions (below)
- `front_cone_m` — how far away the nearest thing straight ahead is (what braking looks at)
- `fallen` — whether it has fallen over
- `last_action` — the result of the previous action

⛔ It contains **no** x/y coordinates, no room name, no map of the house. Those are the
world's god's-eye ground truth; they go out of band on `/status` for humans checking results,
and never onto AWI. Item 4 of `test_lidar.py` pins that line.

## How the ranging works (v1.0)

A ring of horizontal rays from the body measures how far it could travel in eight directions
(ahead, ahead-left, left, behind-left, behind, behind-right, right, ahead-right). ⚠️ This is
not an add-on: a real Go2 (Pro/Edu) carries an L1 lidar on its head.

**Why add it.** The camera only sees forward, so whether there is a way out behind is pure
guesswork. Ranging covers every direction — a large reading means that way is clear. ⛔ But it
gives **distance only**. What is over there and whether to go remains entirely the brain's
judgement from the picture.

**Implementation notes — read before changing it:**

1. **The robot must be filtered out of its own rays.** They start at the body origin, so the
   first thing any ray hits is the robot's own torso — measured at 0.127 m straight ahead.
2. **Filtering is done with geom group masks, not by "skip the hit and cast again".** That was
   tried: straight ahead the ray passed through six of the robot's own geoms (torso box, head
   cylinder, sphere, front legs, visual meshes) and still had not left, and a fixed retry count
   is not reliable. A group mask settles it in one pass. ⛔ **If the robot's groups collide
   with the house's, the world refuses to start** — without separation there is no way to tell
   whether a ray hit a wall or the robot's own arm, and readings from a broken setup are worse
   than no lidar at all. (The menagerie convention already separates them: visual group 2,
   collision group 3; the house uses 0 and 1.)
3. **`mj_ray` must be passed `flg_static = 1`.** Walls and furniture are static geometry; with
   0 the rays hit nothing (measured: all −1, producing the catastrophic reading that every
   direction is clear).
4. **What is reported to the brain and what braking uses are two different things**,
   deliberately not shared:
   - `clearance_m` is **one** ray per direction, so it means exactly "how far I could walk
     straight that way".
   - `front_cone_m` is a **fan** straight ahead (±20° by default, nearest of five rays), so it
     means "will a body this wide hit something going forward". A single centre line slips
     through a door gap and reports 8 m clear while the shoulders are about to hit — there is
     such a spot right beside the spawn point (8.00 m straight ahead against 0.46 m in the
     cone). Both numbers go to the brain, each with its meaning stated.

**Braking before a collision**: while walking forward it watches that cone, and closer than
the braking distance (the body's front length plus a margin, below) it stops and stands, and
reports honestly how far it went and how much room is left. ⛔ **It stops; it does not steer.**
It never sidesteps or goes around on its own — where to go after stopping is always the
brain's decision. Turning on the spot is exempt (it can turn while close to something).

## Where the scene and robots come from

Both live in a separate open-source asset library, **alice-house** (MIT,
`github.com/jeffliulab/alice-house`). This world only mounts it, and the path is configured
rather than assumed:

```
HOUSENAV_ASSETS_ROOT   where the asset library is (default: alice-house/ at the project root)

HOUSENAV_ROBOT         which robot to fit (default: DEFAULT_ROBOT from the manifest)
```

**alice-house** is a large flat: three bedrooms, two receptions, two bathrooms, twelve spaces,
with rooms distinguished by their furniture and floor materials — which is the whole point,
and why the scene is built in detail.

⚠️ Which rooms exist and what is in them **may be written here** — this document is for people
— but **must never appear in the world's guidance**, which goes to the brain. Writing it there
hands over the answer.

## Running it

```bash
cd anima-zero/world/sim-house-nav
./.venv/bin/uvicorn server:app --port 8112
```

| Address | What it is |
|---|---|
| `http://localhost:8112/` | Human page: watch what the robot sees, live |
| `/mcp` | **AWI** — the brain's line (tools / perception / guidance / config declaration) |
| `/stream` `/streams` | MJPEG live views (used by the sensor panel in ANIMA's web UI) |
| `/stream/third` | ⛔ Third-person chase camera: **humans only**, the brain never sees this |
| `/status` | ⚠️ God's-eye ground truth (which room the robot is in), **for checking results** |
| `/config` | Read/change the world's setup (swap bodies). ⚠️ Out of band: a **human** action, unreachable from the brain |
| `/reset` | Put the robot back at the spawn point |
| `/health` | Liveness |

⚠️ Every entry in `/streams` carries an `awi` field: `true` (or absent) means the brain really
sees this view, `false` means a spectator view for people. The web page splits the sensor
panel accordingly — putting the chase camera under the "what ANIMA sees" heading would be a
lie.

To connect from the brain, the world must be in the world list (`config.worlds()` already
includes it by default, or **append** to `ANIMA_WORLDS` in `.env` — ⛔ append, never replace,
or you drop the other worlds).

## Settings

All in `config.py`, each overridable by a `HOUSENAV_*` environment variable, with no bare
numbers left in the code. The ones you are likely to touch:

| Variable | Default | What it is |
|---|---|---|
| `HOUSENAV_WALK_SPEED` | 0.6 | The vx sent while walking (m/s) |
| `HOUSENAV_TURN_RATE` | 0.8 | The wz sent while turning (rad/s, about 46°/s) |
| `HOUSENAV_MAX_MOVE_M` | 3.0 | Furthest one call may walk (so the brain cannot ask for 50 m) |
| `HOUSENAV_MAX_TURN_DEG` | 180 | Furthest one call may turn |
| `HOUSENAV_LIDAR_RANGE_M` | 8.0 | Ranging limit (m); beyond it everything reports this number |
| `HOUSENAV_LIDAR_Z_OFFSET` | 0.05 | Ray height above the body origin (m), moving with the body |
| `HOUSENAV_BRAKE_MARGIN_M` | 0.20 | Braking margin (m) — see below |
| `HOUSENAV_BRAKE_CONE_DEG` | 40 | Width of the cone braking watches (degrees) |
| `HOUSENAV_ROBOT` | empty | Which robot to fit (`go2` / `g1`); empty = the manifest's default |
| `HOUSENAV_LOOK_AROUND` | 0 | Enable look-around (off by default since v1.0) |
| `HOUSENAV_THIRD_PERSON` | 1 | Enable the third-person chase view (humans only) |

⚠️ **The braking distance is computed, not filled in**: the body's front length (measured from
the model) plus `BRAKE_MARGIN_M`. How long the front of the robot is, is an objective fact
about the robot — something that can be computed should not be typed in, because a typed
number goes quietly stale when the model changes. The margin is the part that is a human
choice: how much room I want to leave.

## Swapping bodies (v1.0)

This world fits two robots: the **Go2 quadruped** and the **G1 humanoid**. Which one is chosen
on the AWI page in the web UI (the Config section of the world card), or by setting
`HOUSENAV_ROBOT=g1` before starting.

Every fact about *what this robot is* lives in the asset library's **`robots/manifest.py`** —
where the model is, how high it spawns, what the camera is called, how torque is sent. This
world just follows it, and hard-codes nothing for any particular robot.

⛔ **The two send torque in opposite ways** (`pd_mode` in the manifest; get it backwards and
the robot falls immediately). Go2 was trained with explicit PD — the deployer computes −kd·qd
itself and the model's damping is zeroed. G1 is implicit PD — kd goes into `dof_damping` for
MuJoCo to handle, and only the kp term is sent as torque.

⛔ Swapping bodies **rebuilds the entire simulation** (different model, different policy, back
to the spawn point), so it is configuration set **before a run**, not something to switch
mid-conversation. The brain has no tool for it — it is simply told what body it now has.

## The third-person chase view (v1.0, ⛔ humans only)

A view from above and behind that follows the robot, so you can watch it move through the
house as though it were televised.

- **The line**: this view **never enters `observe()`**. Handing the brain a god's-eye view
  gives away the ability this world exists to test, and it does so without any error or crash
  — it just inflates the result. The line is held in three places (`observe()` does not touch
  it, `/streams` marks `awi=false`, the web page shows two separate sections) and the brain
  repo's `tests/test_third_person.py` pins each one.
- Rendering switches off the ceiling geom group (the asset library groups the ceiling
  separately for exactly this kind of overhead view).
- ⚠️ **The azimuth is the body heading — do not add 180.** MuJoCo's free-camera `azimuth`
  describes *which way the camera looks*, not *where the camera is*. Add 180 and the camera
  swings round to shoot the robot in the face — and **the picture still looks perfectly
  plausible**: the robot is there, a background is there, and nothing about it looks wrong
  unless you stare. Do not reason about it, look at it: **the chase view's background should
  be the same scenery as the first-person view's**. That is how it was caught on 2026-07-26 —
  with the 180 the background was the cupboard behind the robot, without it, the two doorways
  the robot was facing.
- **It pulls in when furniture blocks it** — standard third-person camera behaviour in games.
  The house is tight and the camera position often lands right behind a cupboard. This reuses
  the lidar's rays: cast one from the robot towards the camera position, and if it hits, pull
  back to just in front of the hit.

## Traps already fallen into (read before changing this world)

1. **A MuJoCo free joint's `qvel[3:6]` is already body-frame angular velocity** — do not
   multiply by `R.T` again. The symptom is well hidden: at yaw = 0, `R = I` and the dog stands
   perfectly; turn it west (150°–210°) and it flips. Rule of thumb: **a fault that appears
   only at certain headings — suspect a frame conversion first.**
2. **MuJoCo actuator names differ from joint names** (joint `FL_hip_joint` versus actuator
   `FL_hip`). Looking up by name returns −1 for everything, and `data.ctrl[-1]` raises no
   error — it writes every torque into the last actuator, and the dog collapses on the spot.
   Look them up by **transmission target** (`actuator_trnid`) instead.
3. **The policy's observation order and scaling must match training term by term.** So
   `dump_contract.py` exports `contract.json` from a live Isaac environment (joint order,
   default pose, gains, observation order and scales) and the inference side assembles the
   observation from that rather than from a hand copy.
4. **The two robots send torque in opposite ways**, decided by `pd_mode` in the robot manifest;
   get it backwards and it falls immediately. Go2 is explicit PD (`dof_damping` and
   `dof_frictionloss` zeroed, torque computed as `kp*(q*−q) − kd*qd`); G1 is implicit PD (kd
   goes into `dof_damping` for MuJoCo's semi-implicit integrator, and only `kp*(q*−q)` is
   sent). Running G1 as explicit makes joint velocity ring at high frequency from the first
   step, the policy receives rubbish observations, and it falls in about a second.
5. **Whether the observation stacks history frames comes from the contract's
   `history_length`**, not from the robot. Go2 is 1, G1 is 5 — and G1 stacks **per-term
   blocks** (five frames of each term, concatenated), not whole-frame blocks. The two have
   identical dimensions and completely different values; get it wrong and there is no error,
   it just falls over after two steps.
6. **The lidar separates robot from house by geom group**, and the world refuses to start when
   the groups collide (see the ranging section).

## Files

```
server.py          The world service (AWI + human page)
world.py           The AWI world object: capabilities / observe / invoke, plus the guidance
sim.py             Physics and policy threads; the closed-loop primitives drive_distance /
                   drive_turn; laser ranging
config.py          Every setting (env-overridable)
scene_assets.py    Loads the asset library per configuration (layout / robot manifest / scene
                   MJCF) — one place, do not copy this around
export_policy.py   Training checkpoint → ONNX (with a torch/onnx consistency check that
                   refuses to deliver on a mismatch)
dump_contract.py   Exports the observation contract from a live Isaac environment
test_walk.py       Headless self-test: given a velocity command, does it really walk and turn
                   without falling
test_lidar.py      Headless self-test: rays miss the robot / follow its heading / brake before
                   a collision / the observation carries no god's-eye data
awi_mcp.py         The AWI-over-MCP adapter (byte-identical copy in each world, held by a test)
web/index.html     The human page
```

Both self-tests run directly, and each takes tens of seconds because it really starts MuJoCo:

```bash
./.venv/bin/python test_walk.py
./.venv/bin/python test_lidar.py
```
