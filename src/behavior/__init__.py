"""behavior —— 【行为树】层（抽象层）：通用框架 + 具体树实例。

- 框架（任务无关，只依赖 py_trees + config）：
  `blackboard.Blackboard`（便签本）、`runner.BehaviorRunner`（发动机）、
  `manager.RunnerManager`（多树管理员）、`idioms`（可复用积木）、`hitl.AskHuman`（通用向人提问/求助叶子）。
- 树实例（具体任务，可 import 工具/文案）：`trees/`（如 `trees.boardgame` 对弈树）。
"""
from .blackboard import Blackboard
from .hitl import AskHuman
from .manager import RunnerManager
from .runner import BehaviorRunner

__all__ = ["Blackboard", "BehaviorRunner", "RunnerManager", "AskHuman"]
