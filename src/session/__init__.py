"""anima.session —— 会话+记忆+统一日志+上下文装配。

模块下沉后仍暴露 Session/SessionStore，保 `from anima.session import SessionStore` 不变。
"""
from .session import Session, SessionStore

__all__ = ["Session", "SessionStore"]
