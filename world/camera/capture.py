"""camera 世界的采集层 —— 枚举 / 按需打开 / 切换 / 抓帧编码。

职责边界（重要）：
- 只【被动读】真实摄像头，不让任何硬件动起来或带电，是只读传感。
- **枚举设备这一步不打开任何摄像头**（只读 /dev 节点 + sysfs 名字）；
  真正打开硬件只发生在 `Camera.select()`——也就是人在世界页下拉框里选定某个摄像头那一下。
- 拿不到画面（没插 / 被占用 / 还没选）就**如实**返回 None / "不在线"，
  **绝不**伪造一张黑图冒充真画面（造假是最严重的硬编码，禁止）。

可调项全部 env 可覆盖，默认值集中在本文件顶部——世界是独立进程，不 import 脑 config。
"""
from __future__ import annotations

import glob
import os
import re
import threading

import cv2

import v4l2_caps

# ---- 可调项（env 可覆盖；默认集中此处，禁止散落 inline 魔法数字）----
# 设备节点发现模式：Linux 下摄像头在 /dev/video*。是平台路径，走发现式 + env 覆盖，不写死单个设备。
DEVICE_GLOB = os.getenv("CAMERA_DEVICE_GLOB", "/dev/video*")
# 默认抓帧分辨率（向摄像头请求；选中摄像头后可在世界页改到该设备真支持的任一档）。
FRAME_WIDTH = int(os.getenv("CAMERA_WIDTH", "640"))
FRAME_HEIGHT = int(os.getenv("CAMERA_HEIGHT", "480"))
# 本世界能解码成 BGR 的采集格式（按偏好排序）：同分辨率多格式时，优先靠前的（同帧率下 YUYV 无损优先；
# 高分辨率下 MJPG 帧率更高会被自动选中）。设备报的其它格式（如 H264）本管线解不了，不放进可选项。
USABLE_FOURCCS = [s.strip() for s in os.getenv("CAMERA_USABLE_FOURCCS", "YUYV,MJPG").split(",") if s.strip()]
# JPEG 画质（给 /stream 用）：1..100，越大越清晰越占带宽。
JPEG_QUALITY = int(os.getenv("CAMERA_JPEG_QUALITY", "80"))
# 打开摄像头后先丢掉几帧：很多 USB 摄像头开机头几帧偏暗（自动曝光还没收敛）。
WARMUP_READS = int(os.getenv("CAMERA_WARMUP_READS", "3"))


def _sysfs_name(idx: int) -> str | None:
    """读 /sys 里这个 video 节点的人类可读名字（如 "HD Pro Webcam C920"）；读不到 → None。
    只读文件、不打开摄像头设备。"""
    try:
        with open(f"/sys/class/video4linux/video{idx}/name", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def list_cameras() -> list[dict]:
    """枚举电脑上的摄像头节点，**不打开任何一个**。

    返回 [{"id": 0, "device": "/dev/video0", "name": "HD Pro Webcam C920"}, ...]，按 id 升序。
    注：一个 USB 摄像头在 Linux 上常暴露多个 video 节点（如 video0=取流、video1=元数据），
    名字可能相同——这里如实全列，具体哪个能取流，等人选中、真正打开时才知道（打不开会如实报错）。"""
    cams: list[dict] = []
    for path in sorted(glob.glob(DEVICE_GLOB)):
        m = re.search(r"(\d+)$", path)
        if not m:
            continue
        idx = int(m.group(1))
        cams.append({"id": idx, "device": path, "name": _sysfs_name(idx) or f"video{idx}"})
    cams.sort(key=lambda c: c["id"])
    return cams


def encode(frame, fmt: str = "png") -> bytes | None:
    """把一帧 BGR numpy 编码成 PNG（给 perceive）或 JPEG（给 stream）字节；失败 → None。"""
    if fmt == "jpeg":
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    else:
        ok, buf = cv2.imencode(".png", frame)
    return buf.tobytes() if ok else None


def _device_for(cam_id: int) -> str | None:
    """由摄像头 id 找回它的设备节点路径（不靠拼 "/dev/video"+id，走枚举结果，尊重 DEVICE_GLOB）。"""
    for c in list_cameras():
        if c["id"] == cam_id:
            return c["device"]
    return None


def _usable_modes(modes: list[dict]) -> list[dict]:
    """从设备自报的全部分辨率里，只留【本世界能解码的格式】下可用的那些，并按偏好排序格式。"""
    out: list[dict] = []
    for m in modes:
        fmts = [f for f in m["formats"] if f["fourcc"] in USABLE_FOURCCS]
        if not fmts:
            continue  # 这个分辨率只有 H264 之类我们解不了的格式 → 不放进可选项
        # 排序：帧率高的在前；帧率相同时，按 USABLE_FOURCCS 的偏好顺序（YUYV 无损优先）。
        fmts.sort(key=lambda f: (-(f["max_fps"] or 0), USABLE_FOURCCS.index(f["fourcc"])))
        out.append({"width": m["width"], "height": m["height"], "formats": fmts})
    return out


def _pick_fourcc(modes: list[dict], width: int, height: int) -> str | None:
    """在给定分辨率下，从可用格式里挑首选的那个（_usable_modes 已按偏好排好序）；查不到 → None。"""
    for m in _usable_modes(modes):
        if m["width"] == width and m["height"] == height:
            return m["formats"][0]["fourcc"]
    return None


def _readback(cap: cv2.VideoCapture) -> dict:
    """打开/设置后，从设备读回【真正生效】的分辨率 / 帧率 / 格式（设备可能回退到最近的档，如实报）。"""
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps_raw = cap.get(cv2.CAP_PROP_FPS)
    fourcc = v4l2_caps.fourcc_to_str(int(cap.get(cv2.CAP_PROP_FOURCC)))
    return {
        "width": width or None,
        "height": height or None,
        "fps": round(fps_raw) if fps_raw and fps_raw > 0 else None,
        "fourcc": fourcc or None,
    }


class Camera:
    """当前选中的那一个摄像头。线程安全：select / 抓帧 / 释放都持同一把锁。

    没选 / 没开时不持有任何打开的设备——符合"不主动开启，由人选了才开"。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cap: cv2.VideoCapture | None = None
        self._selected: int | None = None
        self._error: str = ""
        # 当前选中设备真支持的分辨率档（选中时由 V4L2 枚举填充；前端只许从这里选）。
        self._modes: list[dict] = []
        # 向摄像头【请求】的分辨率（默认来自 env，可在线切换到真支持的某一档）。
        self._req_w, self._req_h = FRAME_WIDTH, FRAME_HEIGHT
        # 设备【真正生效】的参数（分辨率/帧率/格式），打开或切换后回读填入。
        self._actual: dict = {}

    # ---- 枚举（不打开设备）----
    def cameras(self) -> list[dict]:
        return list_cameras()

    def modes(self) -> dict:
        """当前选中摄像头真支持、且本世界能解码的分辨率档（给前端下拉框；没选 → 空）。"""
        with self._lock:
            return {"selected": self._selected, "modes": _usable_modes(self._modes)}

    # ---- 打开/应用某分辨率（持锁内部用；失败如实返回 message）----
    def _open_locked(self, cam_id: int, width: int, height: int) -> dict:
        cap = cv2.VideoCapture(cam_id)
        if not cap.isOpened():
            cap.release()
            self._error = f"打不开摄像头 {cam_id}（可能不是取流节点、或被别的程序占用）"
            return {"ok": False, "message": self._error}
        # 先设格式再设宽高：高分辨率下 C920 这类摄像头须走 MJPG 才能上高帧率，纯 YUYV 会很慢/打不开。
        fourcc = _pick_fourcc(self._modes, width, height)
        if fourcc:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        for _ in range(WARMUP_READS):
            cap.read()
        self._cap = cap
        self._selected = cam_id
        self._req_w, self._req_h = width, height
        self._actual = _readback(cap)
        self._error = ""
        return {"ok": True, "selected": cam_id, "actual": self._actual}

    # ---- 选定并打开（人在下拉框选定那一下；这里才真正碰硬件）----
    def select(self, cam_id: int) -> dict:
        with self._lock:
            self._release_locked()
            device = _device_for(cam_id)
            # 选中后先问内核：这台摄像头真支持哪些分辨率（前端据此只给真支持的档）。
            self._modes = v4l2_caps.list_supported_modes(device) if device else []
            # 打开用的分辨率：默认档若该设备不支持，回退到最接近（像素数最近）的支持档。
            width, height = self._resolve_initial(self._req_w, self._req_h)
            res = self._open_locked(cam_id, width, height)
            if res["ok"]:
                res["modes"] = _usable_modes(self._modes)
            return res

    def _resolve_initial(self, width: int, height: int) -> tuple[int, int]:
        """把请求分辨率落到该设备真支持的档：支持就用它，否则取像素数最接近的支持档；查不到能力 → 原样请求。"""
        usable = _usable_modes(self._modes)
        if not usable:
            return width, height
        for m in usable:
            if m["width"] == width and m["height"] == height:
                return width, height
        target = width * height
        nearest = min(usable, key=lambda m: abs(m["width"] * m["height"] - target))
        return nearest["width"], nearest["height"]

    # ---- 在线切换分辨率（人在世界页选了别的档；只接受该设备真支持的档）----
    def set_resolution(self, width: int, height: int) -> dict:
        with self._lock:
            if self._cap is None or self._selected is None:
                return {"ok": False, "message": "还没选摄像头，无法设置分辨率"}
            usable = _usable_modes(self._modes)
            if usable and not any(m["width"] == width and m["height"] == height for m in usable):
                return {"ok": False, "message": f"该摄像头不支持 {width}×{height}"}
            cam_id = self._selected
            modes = self._modes  # 同一设备重开，能力清单不变；_release_locked 不清它，这里仅留作说明
            # 换分辨率必须重开取流（live cap 上热改分辨率不可靠），重开并回读真值。
            self._release_locked()
            self._modes = modes
            return self._open_locked(cam_id, width, height)

    def _release_locked(self) -> None:
        if self._cap is not None:
            self._cap.release()
        self._cap = None
        self._selected = None
        self._actual = {}

    def release(self) -> dict:
        """松开当前摄像头（回到"未选择"）。"""
        with self._lock:
            self._release_locked()
            self._modes = []
            self._error = ""
            return {"ok": True}

    # ---- 抓一帧（拿不到就如实给 None，绝不造假）----
    def snapshot(self, fmt: str = "png") -> bytes | None:
        with self._lock:
            if self._cap is None:
                return None
            ok, frame = self._cap.read()
            if not ok or frame is None:
                return None
            return encode(frame, fmt)

    # ---- 状态（含【请求】与【真正生效】两套参数；真值供前端展示 + 存进 perceive 的 state）----
    def status(self) -> dict:
        with self._lock:
            online = self._cap is not None and self._cap.isOpened()
            a = self._actual
            return {
                "selected": self._selected,
                "online": online,
                # 请求分辨率（向摄像头要的）
                "width": self._req_w,
                "height": self._req_h,
                # 真正生效的核心参数（设备回读，可能与请求不同）
                "actual_width": a.get("width"),
                "actual_height": a.get("height"),
                "fps": a.get("fps"),
                "fourcc": a.get("fourcc"),
                "error": self._error,
            }


# 单文件自测：枚举一遍；可选地打开某个摄像头抓一帧存图（只在传了 index 时才真正开硬件）。
#   仅枚举（不碰硬件）：  python capture.py
#   抓一帧存图（开硬件）：python capture.py 0  out.png
if __name__ == "__main__":
    import sys

    print("枚举到的摄像头（未打开任何设备）：")
    for c in list_cameras():
        print(f"  id={c['id']:<3} {c['device']:<14} {c['name']}")

    if len(sys.argv) >= 2:
        idx = int(sys.argv[1])
        out = sys.argv[2] if len(sys.argv) >= 3 else "camera_test.png"
        cam = Camera()
        res = cam.select(idx)
        print(f"\nselect({idx}) → ok={res.get('ok')}  生效参数={res.get('actual')}")
        print("该摄像头真支持、本世界能解码的分辨率档：")
        for m in cam.modes()["modes"]:
            print(f"  {m['width']}×{m['height']:<5} 首选 {m['formats'][0]['fourcc']}"
                  f" @{m['formats'][0]['max_fps']}fps")
        if res.get("ok"):
            png = cam.snapshot("png")
            if png:
                with open(out, "wb") as f:
                    f.write(png)
                print(f"抓到一帧，{len(png)} 字节，已存 {out}（自己看一眼是不是真画面）")
            else:
                print("打开了但抓不到帧（如实报告，未伪造画面）")
            cam.release()
