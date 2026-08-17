# 服务生命周期脚本实现计划（service-lifecycle-scripts）

状态：Completed
最后更新：2026-08-17

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本仓库提供 `scripts/qed_tracker_service.py`（start/stop/restart/status），承接根仓库 REQ-017①，8900 控制中心可黑盒调用。

**Architecture:** 单文件纯标准库脚本，子进程 = `sys.executable -m qed_tracker.cli serve`；PID 文件与子进程日志落 `logs/`（已 gitignore）；与 8900 的接入契约写入设计文档 `docs/design/service-lifecycle.md`。TDD：先写 `tests/test_service_scripts.py`（红）再实现（绿）。

**Tech Stack:** Python 3.12（QED_env）、pytest（TDD）、ruff、argparse 子命令。

**约束：** 用户 `release` 分支存在未提交的 0007 迁移 WIP，commit 只用显式路径 `git add`，绝不触碰用户 WIP；不写根仓库代码（service_manager 接入另排）。

---

## 任务 1：生命周期脚本与测试（TDD）

**Files:**
- Create: `scripts/qed_tracker_service.py`
- Create: `tests/test_service_scripts.py`

- [x] **Step 1: 写失败测试** — `tests/test_service_scripts.py`（19 用例：parser/退出码/默认端口/start 幂等与 PID 写入/`--wait` 健康与超时/stop 无 PID、stale 清理、优雅、强杀兜底、SystemError 兜底/restart 顺序/status 双路径/main 转发），`importlib.util` 加载模块，tmp 目录 + monkeypatch 隔离。
- [x] **Step 2: 运行确认失败** — `pytest tests/test_service_scripts.py -q` → FileNotFoundError（脚本不存在）。
- [x] **Step 3: 实现** — `scripts/qed_tracker_service.py`：子命令 start/stop/restart/status；`--port`（默认 `QED_TRACKER_PORT`→8901）与 `--wait [N]`（默认 30s）；PID 文件 `logs/qed-tracker.pid`；子进程 stdout/stderr → `logs/qed-tracker-serve.log`；stop 用 `CTRL_BREAK_EVENT` + 5s 宽限 + `taskkill /PID /T /F` 兜底；进程存在性用 `tasklist`（Windows `os.kill(pid,0)` 会直接 TerminateProcess）。
- [x] **Step 4: 验证通过** — `pytest tests/test_service_scripts.py -q` → 18 passed；`ruff check scripts tests/test_service_scripts.py` → All checks passed。
- [x] **Step 5: 提交** — `git add scripts/qed_tracker_service.py tests/test_service_scripts.py` → commit `feat(scripts): QED-Tracker 8901 服务生命周期脚本（start/stop/restart/status，承接 REQ-017①）`（40a1248）。

## 任务 2：设计文档、计划文档与指南/白名单同步

**Files:**
- Create: `docs/design/service-lifecycle.md`（接口契约 + 8900 接入契约 + 平台约束）
- Create: `docs/plans/2026-08-service-lifecycle-scripts.md`（本文件）
- Edit: `docs/design/index.md`（新增入口）
- Edit: `docs/guides/operations.md`（工作台服务节补脚本用法）
- Edit: `README.md`（快速使用补一行）
- Edit: `docs/guides/development.md`（门禁 ruff 命令补 `scripts`）
- Edit: `docs/trackers/todo.md`（登记 QED-032，引用 `../plans/2026-08-service-lifecycle-scripts.md`）
- Edit: `tests/test_documentation.py`（`REQUIRED_CURRENT_DOCS` += 设计文档 + 计划文档；`DESIGN_DOCS` += 设计文档）

- [x] **Step 1: 写设计文档** — `docs/design/service-lifecycle.md`（Accepted/Implemented，含脚本接口契约、运行事实、8900 接入契约、平台约束、验证）。
- [x] **Step 2: 同步索引与指南** — design/index、operations.md、README、development.md 门禁。
- [x] **Step 3: 登记 todo** — `docs/trackers/todo.md` 新增 QED-032（Plan，承接 REQ-017①）。
- [x] **Step 4: 同步白名单** — `tests/test_documentation.py` 两集合。
- [x] **Step 5: 全量门禁** — `pytest tests -q` + `ruff check src tests scripts` + `git diff --check` 全绿。
- [x] **Step 6: 提交** — 显式路径 commit（文档与治理同步，单一目的）。

## 收尾

- [x] 整理 REQ-017① 回执内容（提交号 + 测试输出）交付用户写入根仓库 REQ-017 行。
- [x] 用户未提交的 0007 迁移 WIP 全程未触碰。