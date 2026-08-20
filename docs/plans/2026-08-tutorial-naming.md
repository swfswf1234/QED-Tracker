# 教程命名规范实现计划（tutorial-naming）

状态：Current
最后更新：2026-08-20

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `qt_knowledge` 教程行 `name` 统一为「教程{set_no}：书名（作者）」（en 套「教程en：…」），承接根仓库 REQ-041；`other_material` 归类名不加前缀。

**Architecture:** 设计见 `docs/design/tutorial-naming.md`（Proposed）。命名规则为纯函数 `tutorial_name(set_no, title, authors)`；书名/作者取自教材决定引用 `textbook_ref{title, version, authors}`（**方案 A**，2026-08-20 评审定案）；migrate 与 CLI 默认命名共用该函数。

**Tech Stack:** Python 3.12（QED_env）、pytest（TDD）、ruff。

**约束：** 存量 3 行（`kn_23d99d…`/`kn_b8e157…`/`kn_ad4d78…`）改名只动 `name`/`textbook_ref`（completed 态，不动状态机）；一次性数据修正脚本 + 证据归档 `docs/history/`；**本计划待人工审核后执行（2026-08-20 用户裁决）**。

---

## 任务 1：命名规则 + migrate 默认命名（TDD）

**Files:**
- Edit: `src/qed_tracker/application/migrate_knowledge.py`
- Edit: `src/qed_tracker/db/knowledge_repository.py`
- Edit: `tests/test_migrate_knowledge.py`

- [ ] **Step 1: 写失败测试** — `tests/test_migrate_knowledge.py` 新增/更新断言：migrate 生成的 tutorial 行 name 为规范格式（无作者时退化 `教程{set_no}：{书名}`）。
- [ ] **Step 2: 运行确认失败**。
- [ ] **Step 3: 实现** — 命名纯函数（set_no="en"→「教程en：…」；"1"~"4"→「教程{set_no}：…」；空→「教程：…」兜底）；`migrate_legacy_data` name 生成改规范格式（约 :223）；书行创建后回填 `textbook_ref{title, version, authors}`（confirmed 行 confirm 时传回填值，约 :227-228）。
- [ ] **Step 4: 幂等兼容** — `create_knowledge` 幂等键含 name（`knowledge_repository.py:105`），改名后旧库重放会生成新 id：migrate 改为按 `(course_id, kind, set_no)` 先查后建（存在则复用，不覆盖 name，存量改名由一次性脚本负责），新库正常生成规范 id。
- [ ] **Step 5: 验证通过** — `pytest tests/test_migrate_knowledge.py -q`。

## 任务 2：CLI 默认命名与决定引用（TDD）

**Files:**
- Edit: `src/qed_tracker/cli.py`
- Edit: `tests/test_cli_architecture.py`、`tests/test_main_line_cli.py`

- [ ] **Step 1: 写失败测试** — `mainline new` 带 `--set-no 1` 时 name=规范格式；不带时保持 title。`mainline review` 带 `--title/--author` 时 `textbook_ref={title, version, authors}`。
- [ ] **Step 2: 运行确认失败**。
- [ ] **Step 3: 实现** — `mainline new` 增加 `--set-no`（cli.py:136-139）；name 默认值：有 set_no 按规范生成，否则保持 title（:697）。`mainline review` 增加 `--title/--author` 可选参数（cli.py:140-143、:737-741）；缺省时从 name 剥离「教程{set_no}：」前缀与「（作者）」后缀回退原始书名。
- [ ] **Step 4: 验证通过**。

## 任务 3：database-schema.md 决定引用 + 存量 3 行修正 + 测试/白名单同步

**Files:**
- Edit: `docs/design/database-schema.md`、`docs/design/index.md`（tutorial-naming 状态更新）
- Create: `docs/history/qed-036-tutorial-naming/`（证据：before/after dump + API 冒烟）
- Edit: `tests/test_knowledge_api.py`

- [ ] **Step 1: 文档** — database-schema.md :116/:144 决定引用说明补 authors（`{title, version, authors}`）。
- [ ] **Step 2: 一次性脚本** — 存量 01 数学分析 3 行（`kn_23d99d…`/`kn_b8e157…`/`kn_ad4d78…`）name 改规范格式 + textbook_ref 回填 authors（取自既有书行：Rudin/菲赫金哥尔茨/陈纪修）；completed 态行仅改 name/textbook_ref，不动状态机；执行后 before/after 证据归档。
- [ ] **Step 3: 测试** — `tests/test_knowledge_api.py` 断言 API 返回 name 已规范。
- [ ] **Step 4: 全量门禁** — `pytest tests -q` + `ruff check src tests scripts` + `git diff --check` 全绿。
- [ ] **Step 5: 提交** — 显式路径 commit。

## 收尾

- [ ] 真实 MySQL 冒烟：8901 核验 3 行 name 分别为「教程1：数学分析（Rudin）」「教程2：微积分学教程（菲赫金哥尔茨）」「教程3：数学分析（陈纪修）」（以实际书行 authors/title 为准）。
- [ ] 整理 REQ-041 回执内容（提交号 + 测试输出）交付用户写入根仓库 REQ-041 行；根仓库前端教程叶子联调验收。
