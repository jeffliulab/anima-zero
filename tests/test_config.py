"""中央配置 Settings 的校验网（v0.8 迁 pydantic-settings 时立）。

守四条契约：
1. 默认值与迁移前逐一相同（消费方 `config.MAX_STEPS` 等 re-export 由此背书）；
2. env 覆盖生效且优先于默认（env 名 = 历史名，如 ANIMA_MAX_STEPS）；
3. 非法值 fail-fast：`ge=1` 拒 0/负数（回合制步数上限没有 0 的语义）；
4. 类型错误报可读校验错（`abc` 不再是 int() 的丑堆栈，而是 pydantic 指名道姓的 ValidationError）。

测试直接实例化 Settings 并禁用 .env（_env_file=None）——不受本机 .env 内容影响、
也不 reload config 模块（模块级 re-export 在 import 时定值，测类本身即可）。
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from anima import config
from anima.config import Settings


def test_defaults_match_pre_migration():
    """迁移前后默认值逐一相同——**除了 v0.9 有意改掉的两项**（见下面那条测试）。"""
    s = Settings(_env_file=None)
    assert s.context_token_budget == 6000
    assert s.dev_api is False
    assert s.world_timeout == 30
    assert s.world_liveness_timeout == 20
    assert s.world_invoke_hard_cap == 180
    assert s.service_mcp_timeout == 15
    assert s.max_tokens == 1024
    assert s.default_brain == "gpt-5.4"
    assert s.ollama_base_url == "http://localhost:11434/v1"


def test_v09_turn_budget_defaults():
    """v0.9 有意改掉的默认值——单独立一条，改动是**决定**不是漂移，改了这里就会红。

    背景：v0.8 定 max_steps=8 是回合制的节拍器（每手停下等用户）。v0.9 起口径变成
    「一个回合做一件事」，一轮什么时候收尾由 LLM 自己出文字决定，步数退化成安全带，
    另加墙钟闸兜住费用。下棋仍是一手 2-6 步自然收尾、碰不到 60。
    """
    s = Settings(_env_file=None)
    assert s.max_steps == 60, "v0.9：步数上限是安全带（长任务要跑得完），不是节拍器"
    assert s.turn_time_budget_s == 900, "v0.9：单轮墙钟上限 15 分钟——真正的费用闸"


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("ANIMA_MAX_STEPS", "12")
    monkeypatch.setenv("ANIMA_DEV_API", "1")
    s = Settings(_env_file=None)
    assert s.max_steps == 12
    assert s.dev_api is True


def test_max_steps_rejects_zero_and_negative(monkeypatch):
    monkeypatch.setenv("ANIMA_MAX_STEPS", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setenv("ANIMA_MAX_STEPS", "-3")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_non_numeric_gives_readable_error(monkeypatch):
    monkeypatch.setenv("ANIMA_MAX_STEPS", "abc")
    with pytest.raises(ValidationError) as ei:
        Settings(_env_file=None)
    # 报错必须指得出是哪个配置坏了（可读性），而不是匿名 int() 堆栈
    assert "max_steps" in str(ei.value) or "ANIMA_MAX_STEPS" in str(ei.value)


def test_timeout_rejects_nonpositive(monkeypatch):
    monkeypatch.setenv("ANIMA_WORLD_TIMEOUT", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# ------------------------------------------------- 可选世界（gazebo-chess）/ T0 不丢老能力 ----

def test_an_optional_world_comes_back_even_when_anima_worlds_is_set(monkeypatch):
    """⛔ v1.2 把 gazebo-chess 移出默认清单时承诺「设了 GAZEBO_CHESS_URL 它就回来」。

    起初这个补丁只加在默认清单那条分支上，而 `ANIMA_WORLDS` 一旦非空就提前 return 了——
    偏偏 `.env.example` 默认就把 `ANIMA_WORLDS` 写满，所以那句承诺对**照文档配好的人正好
    是假的**。这条测试盯的就是"人真的会走的那条路"。
    """
    monkeypatch.setenv("ANIMA_WORLDS", "sim-chess=http://localhost:8102")
    monkeypatch.setenv("GAZEBO_CHESS_URL", "http://localhost:8106")
    assert ("gazebo-chess", "http://localhost:8106") in config.worlds()


def test_an_optional_world_comes_back_without_anima_worlds(monkeypatch):
    monkeypatch.delenv("ANIMA_WORLDS", raising=False)
    monkeypatch.setenv("GAZEBO_CHESS_URL", "http://localhost:8106")
    assert ("gazebo-chess", "http://localhost:8106") in config.worlds()


def test_an_optional_world_is_not_listed_twice(monkeypatch):
    """在 ANIMA_WORLDS 里手写了它的人说了算——不重复追加，也不覆盖他写的地址。"""
    monkeypatch.setenv("ANIMA_WORLDS", "gazebo-chess=http://custom:9999")
    monkeypatch.setenv("GAZEBO_CHESS_URL", "http://localhost:8106")
    names = [n for n, _ in config.worlds()]
    assert names.count("gazebo-chess") == 1
    assert dict(config.worlds())["gazebo-chess"] == "http://custom:9999"


def test_no_optional_world_when_its_address_is_unset(monkeypatch):
    """没设地址就不该出现——默认清单里多一个永远 offline 的死条目，正是 v1.2 要清掉的。"""
    monkeypatch.delenv("ANIMA_WORLDS", raising=False)
    monkeypatch.delenv("GAZEBO_CHESS_URL", raising=False)
    assert "gazebo-chess" not in [n for n, _ in config.worlds()]
