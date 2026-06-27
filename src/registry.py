"""世界注册表:登记可连的世界(名字 + URL),同一时刻只绑定一个(给旧的单连接路径用)。

注:会话(session)那套「按世界单活」的模型在 src/session.py;这里的 bind / current 是给编排器
内置的 connect / disconnect 工具用的轻量单绑。注册世界时**不在启动时发 HTTP 握手**,避免硬依赖
「世界必须先起」——能力 / 感知都在运行时(世界已起)才真正去调。
"""
from __future__ import annotations

from .awi import World


class WorldRegistry:
    def __init__(self) -> None:
        self._worlds: dict[str, World] = {}
        self._bound: str | None = None

    def register_world(self, name: str, url: str) -> None:
        """注册一个远程世界(按给定名字;不在此握手)。"""
        from .world_client import RemoteWorld

        self._worlds[name] = RemoteWorld(name, url)

    def bind(self, name: str) -> None:
        if name not in self._worlds:
            raise KeyError(f"world 未注册:{name}")
        self._bound = name  # 只绑一个;这里不发 HTTP

    def unbind(self) -> None:
        self._bound = None

    def current_or_none(self) -> World | None:
        return self._worlds.get(self._bound) if self._bound else None

    def get(self, name: str) -> World | None:
        return self._worlds.get(name)

    def bound_name(self) -> str | None:
        return self._bound

    def list_worlds(self) -> list[str]:
        return list(self._worlds)
