<!--
English first, then Chinese — that is the convention for commits and PRs in this repo.
英文在前、中文在后——本仓的 commit 与 PR 都是这个约定。
-->

## What this changes / 改了什么

<!-- One or two sentences. / 一两句话说清。 -->

## Why / 为什么

<!-- The problem this solves. If it fixes an issue, link it. / 它解决的问题；修 issue 请附链接。 -->

---

## Checklist / 自查

- [ ] **One thing per PR.** / **一个 PR 只做一件事。**
- [ ] `pytest -q` passes. / 测试通过。
- [ ] `ruff check .` passes. / 代码风格通过。
- [ ] `python scripts/selfcheck.py` passes. / 项目自检通过。
- [ ] If behaviour changed, every CHANGELOG (English + `docs/i18n/*/`) and the relevant README are updated.
      / 行为有变则更新了每一份 CHANGELOG 和相应 README。

### If you touched the orchestrator / 如果你动了主循环

- [ ] No task-specific logic went into `src/core/orchestrator.py`. The loop must not know
      what game or task it is driving — that lives in the world.
      / 没有把任务专属逻辑放进主循环。主循环不许知道它在驱动什么任务，那属于世界。

### If you added a world, a tool or a config value / 如果你加了世界、工具或配置项

- [ ] **Appended, not replaced.** `ANIMA_WORLDS`, `.env.example`, default lists and README
      tables are *whole sets* — adding a new entry must never drop an existing one.
      / **是追加不是替换。** 这些是「全集」，加新的绝不能弄丢旧的。
- [ ] Any tunable number went into `src/config.py` with a description, not inline.
      / 可调数字进了中央配置并带说明，没有内联魔法数字。
- [ ] Any placeholder or hardcoded stand-in is called out explicitly in this PR description.
      / 任何占位或临时写死，都在上面的说明里点出来了。
