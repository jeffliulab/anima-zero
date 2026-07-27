"""Which worlds the operator has reviewed and approved.

## The problem this solves

A world is a separate process reached over a URL, and ANIMA hands it an unusual amount of
authority: its `guidance` text is concatenated into the system prompt, its tool
descriptions go into the model's tool sheet, and its `kind` annotations used to decide
whether the safety gate even ran. All of that is written by whoever operates that URL.

While every world is one you wrote yourself on localhost, this is fine. The moment ANIMA
is installable and its README invites people to "add its address to `ANIMA_WORLDS` and the
brain will drive it unchanged", it stops being fine — a stranger's text becomes part of
your system prompt.

The MCP specification is explicit about where the responsibility sits: tool descriptions
are to be treated as **untrusted input**, and the host is the component that must enforce
guardrails. ANIMA is the host.

## The rule

**A world may describe itself; only the operator may authorise it.**

Approval is bound to the *content* of what was reviewed, not to a label. This is the same
idea as SSH pinning a host key or Docker pinning an image digest: swapping something new in
under an old name has to be detectable. Approving a world called "arm" must not silently
authorise whatever is called "arm" tomorrow.

Two attack shapes this is aimed at, both of which have names and real-world incidents:

  - **tool poisoning** — the description text a server controls enters the agent's context
    and is acted on as if it came from the operator
  - **rug pull** — a server behaves while it is being reviewed, then changes its
    descriptions once approved

The hash defeats the second outright and makes the first a decision the human takes with
the text in front of them, rather than one taken silently on their behalf.

## What this does NOT do

It does not solve prompt injection. Nothing here inspects the guidance for hostile intent,
and no such check would be reliable — that is an open problem for the whole field. Nor does
it help once a world is approved: an approved world can still send fabricated camera frames
or report a failed action as a success. **This layer decides whether to connect at all.**
Everything downstream of that decision rests on the human having actually read the manifest.

哪些世界是操作者审阅并批准过的。

## 它解决什么问题

「世界」是一个通过 URL 连上的独立进程，而 ANIMA 交给它的权限异乎寻常地大：它的 `guidance` 文本会被
拼进系统提示词、它的工具描述会进模型的工具单、它的 `kind` 标注过去甚至决定了安全闸要不要跑。
**这些全都由那个 URL 背后的人书写。**

在所有世界都是你自己写、跑在 localhost 上的时候，这没问题。但一旦 ANIMA 可以被安装、而它的 README
邀请别人「把地址加进 `ANIMA_WORLDS`，大脑一行不改就能驱动它」，问题就来了——**一个陌生人的文本成了
你系统提示词的一部分。**

MCP 规范对责任归属写得很清楚：工具描述应当被当作**不可信输入**，而**由 host 负责设防**。
ANIMA 正是 host。

## 规则

**世界可以自我描述，但只有操作者能授权。**

审批绑定在**被审阅的内容**上，不绑在标签上。这和 SSH 钉主机密钥、Docker 钉镜像摘要是同一个思路：
拿新东西顶着旧名字换进来，必须是能被发现的。批准了一个叫 "arm" 的世界，不等于默许明天那个叫 "arm"
的东西。

针对的是两类有名字、也有真实事故的攻击：

  - **tool poisoning（工具投毒）**——服务器控制的描述文本进入 agent 上下文，被当成操作者的话执行
  - **rug pull（先取信后变脸）**——被审阅时表现正常，批准之后再改描述

哈希把第二类彻底挡掉；第一类则从"悄悄替人做主"变成"人对着文本自己拿主意"。

## 它**不**做的事

它不解决提示词注入。这里没有任何代码去检查 guidance 有没有恶意，而且这种检查也不可能可靠——那是
全行业的未解问题。它对"批准之后"也帮不上忙：一个已批准的世界照样可以发假的相机画面、把失败的动作
报成成功。**这一层决定的只是"要不要连"。** 这个决定之下的一切，都建立在人**真的读过**那份清单上。
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .. import paths

# Development escape hatch. Named for what it does, not for what it is for, so that anyone
# who finds it in a shell history can tell it is dangerous.
# 开发逃生门。名字按"它干了什么"起，不按"它用来干嘛"起——好让任何在 shell 历史里看到它的人
# 一眼就知道这东西危险。
TRUST_ALL_ENV = "ANIMA_TRUST_ALL"

UNKNOWN = "unknown"      # never seen this URL / 这个地址没见过
CHANGED = "changed"      # seen and approved, but the manifest is not the one approved
TRUSTED = "trusted"      # approved, and unchanged since / 批准过，且此后没变


def trust_all_enabled() -> bool:
    """Is the development escape hatch on? / 开发逃生门开着吗？"""
    return os.environ.get(TRUST_ALL_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def manifest(url: str, tools, guidance: str) -> dict:
    """The reviewable description of a world, in a canonical shape.

    This is what a human is shown before approving, and what the hash is taken over. The
    two must be the same object: showing one thing and hashing another is how approval
    dialogs end up meaning nothing.

    ⛔ The world's *name* is deliberately absent. A name is a local label the operator
    chose — renaming a world should not invalidate a decision about its content, and a name
    must never be able to carry trust across to different content. The *URL* is present,
    because approval means "this manifest, served from this address": copying a popular
    world's manifest onto your own server is a different thing to approve.

    一个世界**可供审阅的描述**，形状是规范化的。

    这既是批准前给人看的东西，也是被取哈希的东西。两者必须是同一个对象：**给人看一样、拿去哈希另
    一样**，正是审批对话框最终变得毫无意义的方式。

    ⛔ 世界的**名字**是**有意**不在里面的。名字是操作者自己起的本地标签——改个名不该让一个关于内容的
    决定失效，而一个名字更不能把信任带到别的内容上去。**URL 在里面**，因为批准的含义是「这份清单、
    来自这个地址」：把一个热门世界的清单原样搬到自己的服务器上，是另一件需要重新批准的事。
    """
    return {
        "url": url,
        "guidance": guidance or "",
        "tools": sorted(
            ({
                "name": t.name,
                "kind": t.kind,
                "description": t.description,
                "parameters": t.parameters,
            } for t in (tools or [])),
            key=lambda d: d["name"],
        ),
    }


def manifest_hash(m: dict) -> str:
    """SHA-256 over the canonical JSON form. / 对规范化 JSON 取 SHA-256。"""
    blob = json.dumps(m, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def manifest_diff(old: dict, new: dict) -> list[str]:
    """Human-readable list of what changed between two manifests.

    Shown when a previously approved world comes back different. Saying only "this changed"
    would push the operator toward clicking approve without reading; saying *what* changed
    is the difference between a real decision and a rubber stamp.

    两份清单之间**改了什么**的人类可读列表。

    在一个批准过的世界回来时长得不一样了的时候展示。只说"它变了"会把操作者推向"不看就点批准"；
    说清**变了什么**，才是"真的做了个决定"和"盖个橡皮图章"的区别。
    """
    lines: list[str] = []
    if old.get("url") != new.get("url"):
        lines.append(f"URL: {old.get('url')!r} → {new.get('url')!r}")
    if (old.get("guidance") or "") != (new.get("guidance") or ""):
        lo, ln = len(old.get("guidance") or ""), len(new.get("guidance") or "")
        lines.append(f"guidance 说明书变了（{lo} 字 → {ln} 字）")

    old_tools = {t["name"]: t for t in old.get("tools", [])}
    new_tools = {t["name"]: t for t in new.get("tools", [])}
    for name in sorted(set(new_tools) - set(old_tools)):
        lines.append(f"新增工具 {name}（kind={new_tools[name].get('kind')}）")
    for name in sorted(set(old_tools) - set(new_tools)):
        lines.append(f"移除工具 {name}")
    for name in sorted(set(old_tools) & set(new_tools)):
        o, n = old_tools[name], new_tools[name]
        if o.get("kind") != n.get("kind"):
            # Called out on its own line: `kind` is what the safety gate reads, so a change
            # here is a change in how the action is policed.
            # 单列一行：`kind` 是安全闸要读的东西，它变了就意味着这个动作被管束的方式变了。
            lines.append(f"⚠ 工具 {name} 的 kind 变了：{o.get('kind')} → {n.get('kind')}")
        if o.get("description") != n.get("description"):
            lines.append(f"工具 {name} 的描述变了")
        if o.get("parameters") != n.get("parameters"):
            lines.append(f"工具 {name} 的参数 schema 变了")
    return lines or ["（内容有变化但未能定位到具体字段）"]


# ===================================================================================
# Quarantining world-provided text / 把世界给的文本隔离起来
# ===================================================================================

FENCE_OPEN = "<<<BEGIN_WORLD_TEXT"
FENCE_CLOSE = ">>>END_WORLD_TEXT"


def fence(text: str, max_chars: int) -> str:
    """Wrap text written by a world in a boundary it cannot break out of, and cap its size.

    Two jobs, both small and neither sufficient on its own:

    1. **The world must not be able to close the fence early.** If the guidance itself
       contained the closing marker, everything after it would read as if it were ANIMA's
       own instructions again. So any occurrence of either marker is stripped from the
       text before it is wrapped. This is the same reason a database driver escapes quotes
       rather than trusting the caller not to type one.
    2. **Length cap.** A 500 KB guidance needs no cleverness at all to blow the context
       budget and make every turn expensive. Over the cap the text is truncated **and the
       truncation is stated inside the fence** — silently dropping it would leave the model
       believing it had read the whole thing.

    ⚠️ A fence is a speed bump, not a wall. It gives the model a clear signal about where
    the untrusted text begins and ends; it does not make the text safe. Prompt injection
    is an open problem for the entire field and nothing in this function solves it. The
    protection that actually matters is the human approval in `TrustStore`.

    把世界写的文本包进一个**它自己突破不了**的边界里，并限制大小。

    两件小事，单拿出来哪件都不够：

    1. **世界不能提前把围栏关掉。** 如果说明书正文里就含有结束标记，那么它之后的内容会重新被读成
       "ANIMA 自己的指令"。所以包装之前，文本里任何一处标记都会被剥掉。这和数据库驱动要转义引号、
       而不是相信调用方不会打引号，是同一个道理。
    2. **长度上限。** 一份 500KB 的说明书不需要任何巧思就能把上下文预算撑爆、让每一轮都变贵。
       超出部分会被截断，**并且截断这件事写在围栏里面**——静默丢掉会让模型以为自己读到的是全文。

    ⚠️ 围栏是减速带，不是墙。它给模型一个清楚的信号"不可信文本从这里开始、到这里结束"；
    它并不能让文本变安全。提示词注入是全行业的未解问题，本函数里没有任何东西解决了它。
    真正管用的保护是 `TrustStore` 那道人类审批。
    """
    clean = (text or "").replace(FENCE_OPEN, "").replace(FENCE_CLOSE, "")
    if len(clean) > max_chars:
        clean = clean[:max_chars] + (
            f"\n…（这份说明书超过 {max_chars} 字，已截断。你读到的不是全文。）")
    return f"{FENCE_OPEN}\n{clean}\n{FENCE_CLOSE}"


def clip(text: str, max_chars: int) -> str:
    """Cap a short piece of world-provided text, saying so when it happens.

    Used for tool descriptions, which cannot be fenced — they travel inside the
    function-calling schema, where extra framing would be read as part of the description.
    A length cap is the only thing available there.

    给世界提供的**短**文本做长度上限，并在截断时说出来。

    用在工具描述上——它没法加围栏，因为它是在 function-calling 的 schema 里传的，多加的框会被当成
    描述的一部分读进去。那里能做的只有限长。
    """
    text = text or ""
    return text if len(text) <= max_chars else text[:max_chars] + "…（描述过长，已截断）"


@dataclass
class TrustDecision:
    """The answer to "may this world's content reach the brain?"
    / 对「这个世界的内容能不能进大脑」这个问题的回答。"""

    state: str                       # UNKNOWN / CHANGED / TRUSTED
    manifest: dict                   # what was just fetched / 刚取回来的这份
    approved_manifest: dict | None = None    # what was approved before / 之前批准的那份
    reason: str = ""
    changes: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.state == TRUSTED


class TrustStore:
    """The record of what the operator has approved, kept outside any repository.

    操作者批准过什么的记录，存在任何仓库之外。"""

    def __init__(self, path: str | None = None):
        # `ANIMA_HOME` is re-read here rather than taken from the import-time constant, so
        # that setting it in a `.env` (or a test) actually takes effect. A trust store that
        # silently ignored the variable would be worse than not having it.
        # 这里**重新读** `ANIMA_HOME` 而不是用 import 时算好的常量，好让在 `.env`（或测试）里设它
        # 真的生效。一个静默无视这个变量的信任存储，比没有这个变量更糟。
        home = os.environ.get("ANIMA_HOME") or os.path.dirname(paths.TRUST_FILE)
        self.path = path or os.path.join(home, os.path.basename(paths.TRUST_FILE))
        self._data = self._load()

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"version": 1, "worlds": {}}
        data.setdefault("worlds", {})
        return data

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)      # 原子替换，别让中断留下半个文件

    # ------------------------------------------------------------------ queries ---

    def check(self, url: str, tools, guidance: str) -> TrustDecision:
        """Decide whether this world's content may reach the brain.
        / 判断这个世界的内容能不能进大脑。"""
        m = manifest(url, tools, guidance)

        if trust_all_enabled():
            # Announced in the decision rather than silently allowed, so that anything
            # printing the reason says out loud why it let this through.
            # 在决定里写明而不是悄悄放行——这样任何打印原因的地方都会把"为什么放它进来"说出口。
            return TrustDecision(TRUSTED, m, reason=f"{TRUST_ALL_ENV} 已开启（仅限开发）")

        record = self._data["worlds"].get(url)
        if record is None:
            return TrustDecision(UNKNOWN, m, reason="这个世界还没有被审批过")

        if record.get("hash") == manifest_hash(m):
            return TrustDecision(TRUSTED, m, approved_manifest=record.get("manifest"))

        old = record.get("manifest") or {}
        return TrustDecision(
            CHANGED, m, approved_manifest=old,
            reason="这个世界的能力清单和你上次批准时不一样了",
            changes=manifest_diff(old, m),
        )

    def approved_record(self, url: str) -> dict | None:
        return self._data["worlds"].get(url)

    def list_approved(self) -> dict:
        return dict(self._data["worlds"])

    # ------------------------------------------------------------------ mutations ---

    def approve(self, url: str, tools, guidance: str, label: str = "") -> str:
        """Record the operator's approval of exactly this manifest. Returns the hash.
        / 记下操作者对**这一份**清单的批准。返回哈希。"""
        m = manifest(url, tools, guidance)
        h = manifest_hash(m)
        self._data["worlds"][url] = {
            "hash": h,
            "label": label,
            "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "manifest": m,
        }
        self._save()
        return h

    def revoke(self, url: str) -> bool:
        """Forget an approval. / 撤销一次批准。"""
        if self._data["worlds"].pop(url, None) is None:
            return False
        self._save()
        return True
