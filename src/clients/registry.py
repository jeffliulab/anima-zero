"""世界注册表:登记可连的世界(名字 + URL),同一时刻只绑定一个(给旧的单连接路径用)。

注:会话(session)那套「按世界单活」的模型在 src/session.py;这里的 bind / current 是给编排器
内置的 connect / disconnect 工具用的轻量单绑。注册世界时**不在启动时发 HTTP 握手**,避免硬依赖
「世界必须先起」——能力 / 感知都在运行时(世界已起)才真正去调。
"""
from __future__ import annotations

from ..core.awi import World


class WorldRegistry:
    def __init__(self) -> None:
        self._worlds: dict[str, World] = {}
        self._bound: str | None = None
        self._services: dict[str, object] = {}   # url -> RemoteService（同一 URL 共用一个客户端）

    def register_world(self, name: str, url: str) -> None:
        """注册一个远程世界(按给定名字;不在此握手)。"""
        from .world_client import RemoteWorld

        self._worlds[name] = RemoteWorld(name, url)

    def bind(self, name: str) -> None:
        if name not in self._worlds:
            raise KeyError(f"world not registered: {name}")
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

    # ---------- 挂载服务（Host 组装：大脑按 config.services() 自行挂载；world 不声明服务）----------
    def mounted_services(self) -> list:
        """按 config.services() 返回（并缓存）service 客户端列表。

        标准 MCP 的「Host 组装」：连哪些 server 是大脑（Host）自己的配置决定，server 之间互不相识。
        惰性：建客户端不握手（同 register_world，能力在运行时才真正去问）；同一 URL 只建一个客户端。
        「棋世界要用引擎」这类配对不靠结构绑定——服务工具并进工具单后，模型看画面自选（不相关就不调）。"""
        from .. import config
        from .service_client import RemoteService

        out = []
        for name, url in config.services():
            url = (url or "").strip()
            if not url:
                continue
            svc = self._services.get(url)
            if svc is None:
                svc = RemoteService((name or url).strip(), url)
                self._services[url] = svc
            out.append(svc)
        return out

    def list_services(self) -> list:
        """已知的全部 service 客户端（/awi 仪表盘用；含全部被 mounted_services 建过的）。"""
        return list(self._services.values())
