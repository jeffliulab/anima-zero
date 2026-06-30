"""RunnerManager —— 多棵活跃行为树的"管理员"。

py_trees 只管单棵树；"同时可能有多棵树、要能按 key 启停、开新前停旧、防泄漏"这层框架不提供，
自造在这里。职责：①按 session.id 路由到对应 runner；②**开新局前先把旧局干净停掉**（修现状真 bug：
旧 GameSession 线程被覆盖后没人 cancel、还在后台空跑甚至继续 invoke）；③**单写者令牌(epoch)**——
开新局 epoch++ 作废旧令牌，让旧 runner 即便没退透也不再向同一世界写命令；④对局结束自动清理；⑤加锁。

单写者残留窗口（诚实标注）：`is_writer()` 与世界 `invoke` 之间非原子，旧 runner 恰好已过检查、
正卡在 invoke 网络往返(≤短超时)里，仍可能多发一次命令；软件层不声称数学零双写，真机侧须靠
世界端命令幂等/序号去重兜底。
"""
from __future__ import annotations

import threading
from typing import Optional

from .. import config
from .runner import BehaviorRunner


class RunnerManager:
    def __init__(self) -> None:
        self._runners: dict[str, BehaviorRunner] = {}
        self._lock = threading.Lock()
        self._epoch = 0

    def active(self, key: str) -> bool:
        r = self._runners.get(key)
        return bool(r and not r.finished)

    def get(self, key: str) -> Optional[BehaviorRunner]:
        return self._runners.get(key)

    def epoch(self) -> int:
        return self._epoch

    def stop(self, key: str) -> None:
        """取消 + 限时 join + 移除。限时是为了不让'开新局/新建会话'的请求线程被旧局拖死。"""
        with self._lock:
            r = self._runners.pop(key, None)
        if r is not None:
            r.cancel()
            r.join(config.GAME_CANCEL_JOIN_S)            # 超时也不强杀（Python 杀不了线程）；epoch 已作废=旧 runner 禁写

    def start(self, key: str, runner: BehaviorRunner) -> None:
        self.stop(key)                                   # 开新前先停旧
        with self._lock:
            self._epoch += 1
            ep = self._epoch
            runner.bb.epoch = ep
            runner.bb.is_writer = (lambda e=ep: e == self._epoch)   # 当前 epoch 才是当前写者
            self._runners[key] = runner
        runner.start()

    def reap(self) -> None:
        """清掉已结束的 runner（防字典/线程越积越多）。"""
        with self._lock:
            for k in [k for k, r in self._runners.items() if r.finished]:
                self._runners.pop(k, None)
