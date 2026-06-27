"""会话(session)+ 本地记忆。

一个 session = 一个任务,绑定一个世界(world 名;也可为 None = 纯聊天)。规则:
- **每个世界同一时刻只允许一个活跃 session**;在某世界上新建 session,会把该世界上原来的活跃 session
  冻结成只读(安全红线)。不同世界的 session 互不影响。
- 会话之间互相独立、不共享记忆;一个 session 里可中途换大脑(记忆和大脑解耦)。
- 记忆全存在本地 JSON(单用户),每个 session 一个文件;图片落成 PNG 文件,记录里只放路径。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_HERE, "..", "memory", "sessions")  # anima-zero/memory/sessions
TITLE_MAX_LEN = 24  # 会话标题取用户首句的前几个字


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _gen_id() -> str:
    return f"s_{time.time_ns()}"


@dataclass
class Session:
    id: str
    world: str | None  # 连接的世界名(None = 纯聊天)
    brain: str
    status: str  # "active" | "frozen"
    created_at: str
    title: str
    messages: list = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "id": self.id, "world": self.world, "brain": self.brain,
            "status": self.status, "created_at": self.created_at, "title": self.title,
        }


class SessionStore:
    def __init__(self, root: str = _ROOT) -> None:
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _path(self, sid: str) -> str:
        return os.path.join(self.root, f"{sid}.json")

    def _imgs_dir(self, sid: str) -> str:
        d = os.path.join(self.root, sid, "imgs")
        os.makedirs(d, exist_ok=True)
        return d

    def save(self, s: Session) -> None:
        with open(self._path(s.id), "w", encoding="utf-8") as f:
            json.dump(asdict(s), f, ensure_ascii=False, indent=2)

    def load(self, sid: str) -> Session:
        with open(self._path(sid), encoding="utf-8") as f:
            data = json.load(f)
        if "object" in data and "world" not in data:  # 兼容旧字段(object → world)
            data["world"] = data.pop("object")
        return Session(**data)

    def exists(self, sid: str) -> bool:
        return os.path.exists(self._path(sid))

    def all(self) -> list[Session]:
        out = []
        for fn in os.listdir(self.root):
            if fn.endswith(".json"):
                try:
                    out.append(self.load(fn[:-5]))
                except Exception:
                    pass
        out.sort(key=lambda s: s.created_at, reverse=True)
        return out

    def new(self, world: str | None, brain: str) -> Session:
        if world:  # 同一个世界的活跃会话先冻结(安全)
            for s in self.all():
                if s.world == world and s.status == "active":
                    s.status = "frozen"
                    self.save(s)
        s = Session(
            id=_gen_id(), world=world, brain=brain, status="active",
            created_at=_now(), title="(新会话)", messages=[],
        )
        self.save(s)
        return s

    def get(self, sid: str) -> Session:
        return self.load(sid)

    def list(self) -> list[dict]:
        return [s.summary() for s in self.all()]

    def append(self, sid: str, entry: dict) -> None:
        s = self.load(sid)
        entry.setdefault("ts", _now())
        s.messages.append(entry)
        if s.title == "(新会话)" and entry.get("role") == "user":  # 用首条用户消息当标题
            s.title = entry["text"][:TITLE_MAX_LEN]
        self.save(s)

    def append_perception(self, sid: str, image_png: bytes | None, state: dict) -> None:
        s = self.load(sid)
        ref = None
        if image_png:
            n = sum(1 for m in s.messages if m.get("role") == "perception")
            with open(os.path.join(self._imgs_dir(sid), f"{n}.png"), "wb") as f:
                f.write(image_png)
            ref = f"{sid}/imgs/{n}.png"
        s.messages.append({"role": "perception", "image_ref": ref, "state": state, "ts": _now()})
        self.save(s)

    def set_brain(self, sid: str, brain: str) -> None:
        s = self.load(sid)
        s.brain = brain
        self.save(s)

    def is_active(self, sid: str) -> bool:
        return self.load(sid).status == "active"
