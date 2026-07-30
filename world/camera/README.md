# camera

<a href="README.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="README_zh.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>

A standalone **world** (AWI) for ANIMA: it hands the live picture from a **real camera** to
the brain.

This is the first time ANIMA looks at the real physical world rather than at an image a
program drew. The scope is deliberately small: **it can look and it can talk. It cannot act.**

**Looking is all the brain gets.** Perception returns a frame and a minimal state, and the
`tools` list in `capabilities` is **empty** — in this world ANIMA has no executable action at
all. "It can only look" is guaranteed structurally, not asked for in a prompt.

**A person chooses and opens the camera.** Starting the service opens nothing; it only
enumerates what the machine has. Which one to open is picked from a dropdown on the world's
page, and with several plugged in you can switch at any time. Only once one is selected does
a picture appear and reach ANIMA.

**Resolution is changed live.** With a camera selected, the world asks the kernel through
Linux V4L2 **which resolutions the device actually supports** — no hard-coded table — and the
page offers only those. Switching picks the best capture format for that mode (at equal frame
rates lossless YUYV wins; at high resolutions MJPG gives more frames and is chosen
automatically). The page shows the camera's real parameters — the resolution, frame rate and
pixel format **actually in effect**, read back from the device — and those go into the
perception state that reaches ANIMA too.

```
cd world/camera && pip install -e . && uvicorn server:app --port 8104
```

Open `localhost:8104`, pick a camera from the dropdown, and a picture appears. Select the
`camera` world in the main UI and ANIMA can see it and talk about it.

## Interfaces

**AWI (brain ↔ world)** goes entirely through **`/mcp`** (MCP): `tools/list` (empty here),
`resources/read anima://observation` (perception), `prompts/get` (guidance), `tools/call`
(refused here — there are no actions). Plus out-of-band `GET /health` for liveness.

**Human page and controls** (world-local, never on AWI): `GET /stream`, `GET /cameras`,
`GET /modes` (the resolutions this camera really supports), `POST /select`,
`POST /resolution`, `POST /release`, `GET /status`, `GET /`.

## Settings (env, all with defaults)

| env | Default | Meaning |
|---|---|---|
| `CAMERA_DEVICE_GLOB` | `/dev/video*` | Glob for enumerating camera nodes (platform specific — discovered, not assumed) |
| `CAMERA_WIDTH` / `CAMERA_HEIGHT` | `640` / `480` | Default capture resolution (changeable on the page to any mode the device supports) |
| `CAMERA_USABLE_FOURCCS` | `YUYV,MJPG` | Capture formats this world can decode, in order of preference. Anything else the device reports (H264, say) is not offered |
| `CAMERA_JPEG_QUALITY` | `80` | JPEG quality for `/stream` (1–100) |
| `CAMERA_WARMUP_READS` | `3` | Frames discarded after opening, while auto-exposure settles |
| `CAMERA_STREAM_FPS` | `15` | Live stream frame rate |
| `CAMERA_WORLD_VERSION` | `0.3` | World version |

## Self-test

```
python capture.py            # enumerate cameras only; opens no device
python capture.py 0 out.png  # open camera 0 and save one frame (this really opens hardware)
```
