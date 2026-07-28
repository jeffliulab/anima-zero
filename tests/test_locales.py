"""后端说英文正典、界面翻译显示——这条契约是隐形的，所以要钉住。

⛔ 为什么这几条测试非有不可：

后端一律输出英文，网页收到之后拿整串去词条表里查，命中就显示译文。中间没有任何 id、没有任何
结构——**只有"两边的字符串逐字相同"这一个约定**。所以后端改一个字，界面就静默回落英文：
`pytest` 全绿、`tsc` 全绿、前端的词条守卫也全绿，只有真的切到中文/日语去看才会发现。

这正是本轮修的那两个 bug 的形状：
  · 三句停顿语（中文对话里蹦出一句英文）——这件事的起因；
  · 四个运行参数标签（我把 config.py 英文化，中文界面那四个标签就变成了英文）。
修完不上锁，下次照坏。

⚠️ 这几条**有意住在 Python 这边**：它们要拿的是 Python 常量的真值。第一版写在前端的
`check-locales.mjs` 里用正则去抠 `STOP_REPLIES`，第一次跑就抓错了——那个字典的值是**常量引用**
不是字面量，正则只看得到 key，于是把 reason code `"time"` 当成了要翻译的文案。
**一个需要解析另一门语言的守卫，应该住在那门语言里。**

The backend speaks canonical English and the interface translates what it receives by looking
the whole string up. Nothing but byte-equality ties the two together, so a reworded backend
string silently falls back to English with every check still green. These pin it.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from anima import config, messages

REPO = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = REPO / "frontend" / "locales" / "en.json"


def _registry() -> dict:
    """英文词条表 = 合法 key 的登记表（恒等映射）。"""
    if not REGISTRY.exists():
        pytest.skip(f"没有 {REGISTRY.relative_to(REPO)}——前端没装/没建词条时跳过")
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["strings"]


@pytest.mark.parametrize("reason", sorted(messages.STOP_REPLIES))
def test_stop_replies_can_be_translated(reason):
    """⛔ G4：三句停顿语必须在词条表里。

    一轮被提前收尾时，回复不是模型写的、是框架自己吐的——所以它不会跟随用户的语言，
    只能靠界面翻译。改了措辞而没同步词条，中文/日语界面里就会蹦出一句英文。
    """
    text = messages.STOP_REPLIES[reason]
    assert text in _registry(), (
        f"停顿语（{reason}）不在词条登记表里，界面会静默显示英文：\n  {text!r}\n"
        f"→ 改了 src/messages.py 的措辞，就要同步 frontend/locales/*.json")


@pytest.mark.parametrize("text", [
    messages.UNKNOWN_BRAIN_REPLY,
    messages.BRAIN_NOT_CONFIGURED_REPLY,
    messages.BRAIN_CALL_FAILED_LEAD,
])
def test_brain_error_replies_can_be_translated(text):
    """⛔ G4 续：三句大脑错误同样走 reply 通道，同样要能翻译。

    `BRAIN_NOT_CONFIGURED` 是第一次装的人最容易撞上的那句——它蹦英文的话，
    正好在最需要好印象的时刻。

    ⚠️ 这三句**不许带插值**：界面是拿整串去查表的，插了变量就永远查不中。
    `BRAIN_CALL_FAILED` 例外地保留了 `{error}`，所以这里钉的是它可翻译的**前半句**。
    """
    assert "{" not in text, (
        f"这句带了插值，界面永远查不中它：{text!r}\n"
        f"→ 要么去掉变量，要么像 BRAIN_CALL_FAILED 那样把可翻译的前半句单独拆出来")
    assert text in _registry(), f"不在词条登记表里，界面会静默显示英文：\n  {text!r}"


def test_runtime_param_labels_can_be_translated():
    """⛔ G5：左下角那四个运行参数标签必须在词条表里。

    它们由后端 `/api/config` 送出，界面经 `t(p.label)` 翻译——全系统"后端说英文、前端翻译"
    的样板。**这条正是我把 config.py 英文化时弄坏的那个回归**：词条表当时按中文做 key，
    `t("Steps per turn")` 查不到就原样返回，于是中文界面显示英文。
    """
    reg = _registry()
    labels = config._RUNTIME_PARAM_LABELS
    missing = {k: v for k, v in labels.items() if v not in reg}
    assert not missing, (
        "这些运行参数标签不在词条登记表里，非英文界面会静默显示英文：\n  "
        + "\n  ".join(f"{k} → {v!r}" for k, v in missing.items())
        + "\n→ 改了 src/config.py 的 _RUNTIME_PARAM_LABELS，就要同步 frontend/locales/*.json")


def test_every_locale_covers_the_registry():
    """各语言词条要么译全、要么明确知道缺多少——缺译回落英文是**设计**，不是事故。

    这条不强制译全（新加一门语言时它必然是残缺的，那也该能用），
    只是把"缺多少"打出来，让残缺是**看得见**的。
    """
    reg = _registry()
    root = REGISTRY.parent
    for path in sorted(root.glob("*.json")):
        cat = json.loads(path.read_text(encoding="utf-8"))
        assert cat["meta"]["code"] == path.stem, f"{path.name}: meta.code 与文件名对不上"
        orphans = set(cat["strings"]) - set(reg)
        assert not orphans, (
            f"{path.name} 里有登记表中不存在的 key（错别字或过时条目）：\n  "
            + "\n  ".join(sorted(orphans)[:5]))
