"""v4l2_caps —— 用 Linux V4L2 ioctl 问内核：某个摄像头【真正支持】哪些 (像素格式 × 分辨率 × 帧率)。

为什么不写死一张分辨率表：每台摄像头能力都不同，写死=硬编码且会骗人（界面给的档位设备根本不支持）。
这里直接走内核 V4L2 接口（和 `v4l2-ctl --list-formats-ext` 同一来源），如实拿设备自报的能力清单。

- 纯标准库（ctypes / fcntl / os），不引第三方依赖。
- 只读查询：打开设备节点发 ENUM 系列 ioctl，**不启动取流、不让硬件动**，是被动读能力。
- 非 Linux / 查询失败（设备拔了、被占用、没权限）→ 返回空清单，由上层如实降级，绝不编造档位。
"""
from __future__ import annotations

import ctypes
import fcntl
import os

# ---- V4L2 ioctl 号的拼装（对应内核 <linux/videodev2.h> 的 _IOWR('V', ...)）----
# ioctl 号 = 方向(2bit) | 大小(14bit) | 类型(8bit) | 序号(8bit)，下面是内核 _IOC 宏的等价实现。
_IOC_NRBITS, _IOC_TYPEBITS, _IOC_SIZEBITS = 8, 8, 14
_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS          # 8
_IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS      # 16
_IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS       # 30
_IOC_READ, _IOC_WRITE = 2, 1
_V4L2_IOC_TYPE = ord("V")

# V4L2 枚举类型常量（内核定义，是域常量不是魔法数字）。
_V4L2_BUF_TYPE_VIDEO_CAPTURE = 1
_V4L2_FRMSIZE_TYPE_DISCRETE = 1
_V4L2_FRMIVAL_TYPE_DISCRETE = 1


def _iowr(nr: int, struct_type) -> int:
    """组一个 _IOWR('V', nr, struct) 的 ioctl 号，并折成有符号 32 位。

    折有符号：V4L2 的 ioctl 号最高位（方向位）置 1 后 > 2^31，Python 的 fcntl.ioctl
    对超过 INT_MAX 的请求号会抛 OverflowError，按 C 的 int 语义折回负数即可正常下发。"""
    size = ctypes.sizeof(struct_type)
    op = ((_IOC_READ | _IOC_WRITE) << _IOC_DIRSHIFT) | (_V4L2_IOC_TYPE << _IOC_TYPESHIFT) \
        | (nr << _IOC_NRSHIFT) | (size << _IOC_SIZESHIFT)
    return op - 0x100000000 if op >= 0x80000000 else op


# ---- V4L2 结构体（字段布局严格对齐内核 ABI，顺序/类型不能改）----
class _Fmtdesc(ctypes.Structure):
    _fields_ = [
        ("index", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("description", ctypes.c_char * 32),
        ("pixelformat", ctypes.c_uint32),
        ("mbus_code", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32 * 3),
    ]


class _FrmsizeDiscrete(ctypes.Structure):
    _fields_ = [("width", ctypes.c_uint32), ("height", ctypes.c_uint32)]


class _FrmsizeStepwise(ctypes.Structure):
    _fields_ = [("min_width", ctypes.c_uint32), ("max_width", ctypes.c_uint32),
                ("step_width", ctypes.c_uint32), ("min_height", ctypes.c_uint32),
                ("max_height", ctypes.c_uint32), ("step_height", ctypes.c_uint32)]


class _FrmsizeUnion(ctypes.Union):
    _fields_ = [("discrete", _FrmsizeDiscrete), ("stepwise", _FrmsizeStepwise)]


class _Frmsizeenum(ctypes.Structure):
    _fields_ = [
        ("index", ctypes.c_uint32),
        ("pixel_format", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("u", _FrmsizeUnion),
        ("reserved", ctypes.c_uint32 * 2),
    ]


class _Fract(ctypes.Structure):
    _fields_ = [("numerator", ctypes.c_uint32), ("denominator", ctypes.c_uint32)]


class _FrmivalStepwise(ctypes.Structure):
    _fields_ = [("min", _Fract), ("max", _Fract), ("step", _Fract)]


class _FrmivalUnion(ctypes.Union):
    _fields_ = [("discrete", _Fract), ("stepwise", _FrmivalStepwise)]


class _Frmivalenum(ctypes.Structure):
    _fields_ = [
        ("index", ctypes.c_uint32),
        ("pixel_format", ctypes.c_uint32),
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("u", _FrmivalUnion),
        ("reserved", ctypes.c_uint32 * 2),
    ]


_VIDIOC_ENUM_FMT = _iowr(2, _Fmtdesc)
_VIDIOC_ENUM_FRAMESIZES = _iowr(74, _Frmsizeenum)
_VIDIOC_ENUM_FRAMEINTERVALS = _iowr(75, _Frmivalenum)


def fourcc_to_str(pixfmt: int) -> str:
    """把 V4L2 的 4 字节 pixelformat（小端打包的 4 个字符）还原成 'MJPG'/'YUYV' 这样的字符串。"""
    return "".join(chr((pixfmt >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00").strip()


def _max_fps(fd: int, pixfmt: int, width: int, height: int) -> int | None:
    """枚举某 (格式,分辨率) 下的所有离散帧率，返回最高的整数 fps；问不到 → None。"""
    best = 0.0
    index = 0
    while True:
        fival = _Frmivalenum(index=index, pixel_format=pixfmt, width=width, height=height)
        try:
            fcntl.ioctl(fd, _VIDIOC_ENUM_FRAMEINTERVALS, fival)
        except OSError:
            break
        if fival.type != _V4L2_FRMIVAL_TYPE_DISCRETE:
            break  # 连续/步进型帧率：本世界只用离散档，跳过
        num, den = fival.u.discrete.numerator, fival.u.discrete.denominator
        if num > 0:  # 帧率 = 分母/分子（间隔的倒数）
            best = max(best, den / num)
        index += 1
    return round(best) if best > 0 else None


def list_supported_modes(device: str) -> list[dict]:
    """问内核：这个设备节点支持哪些分辨率，每个分辨率下有哪些格式、各自最高多少 fps。

    返回按像素数升序的列表，每项形如：
      {"width":1280,"height":720,"formats":[{"fourcc":"MJPG","max_fps":30},{"fourcc":"YUYV","max_fps":10}]}
    查询失败（非 Linux/拔了/被占/没权限）→ 返回 []，绝不编造。"""
    try:
        fd = os.open(device, os.O_RDWR | os.O_NONBLOCK)
    except OSError:
        return []
    # (w,h) -> {fourcc: max_fps}，同一分辨率在不同格式下会合并到一项。
    merged: dict[tuple[int, int], dict[str, int | None]] = {}
    try:
        fmt_index = 0
        while True:
            fmtdesc = _Fmtdesc(index=fmt_index, type=_V4L2_BUF_TYPE_VIDEO_CAPTURE)
            try:
                fcntl.ioctl(fd, _VIDIOC_ENUM_FMT, fmtdesc)
            except OSError:
                break  # 格式枚举到头
            pixfmt = fmtdesc.pixelformat
            fourcc = fourcc_to_str(pixfmt)
            sz_index = 0
            while True:
                frmsize = _Frmsizeenum(index=sz_index, pixel_format=pixfmt)
                try:
                    fcntl.ioctl(fd, _VIDIOC_ENUM_FRAMESIZES, frmsize)
                except OSError:
                    break  # 该格式的分辨率枚举到头
                if frmsize.type != _V4L2_FRMSIZE_TYPE_DISCRETE:
                    break  # 步进/连续型分辨率：本世界只用离散档，跳过
                w, h = frmsize.u.discrete.width, frmsize.u.discrete.height
                merged.setdefault((w, h), {})[fourcc] = _max_fps(fd, pixfmt, w, h)
                sz_index += 1
            fmt_index += 1
    finally:
        os.close(fd)

    out: list[dict] = []
    for (w, h) in sorted(merged, key=lambda wh: (wh[0] * wh[1], wh[0])):
        formats = [{"fourcc": fc, "max_fps": fps} for fc, fps in merged[(w, h)].items()]
        out.append({"width": w, "height": h, "formats": formats})
    return out
