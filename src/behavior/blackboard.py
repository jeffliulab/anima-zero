"""通用黑板基类（框架契约）—— 一棵行为树跨拍共享的"便签本"。

只放**框架（runner/manager/idioms）真正读写的、任务无关的字段**：世界句柄、事件流、
生命周期标志、失败分类计数、单写者令牌、暂停/HITL 状态。任何具体任务（下棋/整理桌面…）的专属字段
（belief 局面、执方 my_side、棋种适配器 adapter…）放各自的子类，不进这里。

⛔ 这个文件不许出现任何棋种语义或中文文案——保证它能被任意任务的树复用。
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .. import config


@dataclass
class Blackboard:
    world: Any                                  # 世界客户端（对弈用短超时 RemoteWorld）
    display_name: str = "Task"
    # 生命周期
    cancelled: bool = False
    finished: bool = False
    exit_reason: str = ""
    # 失败【分类】计数（别合并成一个匿名计数，否则掩盖根因）
    perceive_fail: int = 0                      # 世界异常：拿不到画面
    act_fail: int = 0                           # 命令被世界拒
    # 单写者令牌：manager 在 start 时写入 epoch + 注入 is_writer（详见 manager.py）
    epoch: int = 0
    is_writer: Callable[[], bool] = field(default=lambda: True)
    # 暂停 / HITL（通用、任务无关）：runner 据 paused 挂起 tick；AskHuman 叶子用 pending_question/answer
    # 实现"提问→等人答→带答恢复"(interrupt/checkpoint/resume)。这里不含任何任务语义。
    paused: bool = False
    pending_question: Optional[dict] = None     # 当前向人类提的问题 {id,text,options}；None=没在问
    answer: Optional[str] = None                # 人类对 pending_question 的回答；被 AskHuman 消费后清空
    # 事件流（给前端/日志看）
    events: deque = field(default_factory=lambda: deque(maxlen=config.GAME_EVENT_BUFFER))
    _seq: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def emit(self, channel: str, text: str = "", **extra) -> None:
        with self.lock:
            self._seq += 1
            self.events.append({"id": self._seq, "ts": time.strftime("%H:%M:%S"),
                                "channel": channel, "text": text, **extra})

    def events_since(self, last_id: int) -> list:
        with self.lock:
            return [e for e in self.events if e["id"] > last_id]

    def base_status(self) -> dict:
        """通用骨架状态（不含任何任务专属字段，如 turn/my_side）。子类 status() 在此基础上补充。"""
        return {
            "display_name": self.display_name,
            "finished": self.finished,
            "exit_reason": self.exit_reason,
            "paused": self.paused,
            "question": self.pending_question,       # 有值=正等人类回答（前端可据此显示问题/选项）
            "last": self.events[-1]["text"] if self.events else "",
        }

    def status(self) -> dict:
        return self.base_status()
