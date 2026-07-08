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

from anima.config import Settings


def test_defaults_match_pre_migration():
    s = Settings(_env_file=None)
    assert s.max_steps == 8
    assert s.context_token_budget == 6000
    assert s.dev_api is False
    assert s.world_timeout == 30
    assert s.world_liveness_timeout == 20
    assert s.world_invoke_hard_cap == 180
    assert s.service_mcp_timeout == 15
    assert s.max_tokens == 1024
    assert s.default_brain == "gpt-5.4"
    assert s.ollama_base_url == "http://localhost:11434/v1"


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
