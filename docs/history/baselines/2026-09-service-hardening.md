# 服务稳定性优化清单（service-hardening）

状态：Historical
任务类型：A
最后更新：2026-09-14
需求方：QED-Engine（根仓库 REQ-017「QED-Tracker 服务化遗留三缺口」②③、REQ-019 版本核对）
目标项目：QED-Tracker
评审方：用户

> **关闭归档（2026-09-14，QED-066）**：本计划随 QED-066 关闭，按 [ADR 0009](../../adr/0009-closed-plan-archival.md)
> 归档至 `history/baselines/`。实现结果见[完成台账](../../trackers/completed.md)。

## 项目目标

REQ-017 子项 ①（正式启动入口）已由 QED-032 完成。本文档承接 ②③ 两项服务稳定性
优化 + REQ-019 下载内容校验——确保后台任务在服务重启后不造成状态残留，进度信息可被
前端消费，且下载的 PDF 与登记书目内容一致。

## 清单

### ③ 服务重启后 running 任务恢复（核心，QED-Tracker 全权）✅ 已完成

**问题**：8901 异常退出或正常重启时，`qt_tasks` 中 `running`/`queued` 记录永久残留。
重启后无法重新提交同参数任务（dedup 返回 409），用户只能手动删 DB 行。

**改动**：
- `src/qed_tracker/api/tasks.py`：`TaskManager.__init__` 末尾调用 `recover_stale_tasks()`
- 查询 `status IN ('queued', 'running')` → 转 `failed`（message: "服务重启，任务中断/取消"，error: "ORPHANED"）
- 不做自动重试（保持「无隐式重试」策略）
- 4 个新测试：running→failed、queued→failed、terminal 不触碰、dedup 解除

**成功标准**：✅ 全部达成。

### ④ 下载后内容校验（REQ-019，QED-066 扩充）✅ 已完成

**问题**：当前下载验收只做结构校验（magic number/可解析/页数/大小/SHA-256），
无内容级校验。可注册"数学分析（第4版）"却下载"高等代数（第2版）"而不被发现。

**改动点**：

1. **`src/qed_tracker/downloader.py` — 新增 `verify_content()` 函数** ✅
   - 输入：PDF 路径、期望标题列表（`qt_books.title` + `original_title`）
   - 提取 PDF 第一页文本（pypdf `extract_text()`，取前 500 字符）
   - 用 `matching._similarity()` 对比期望标题
   - 阈值 < 0.5 时标记 `title_mismatch`（软信号，不硬拒）
   - 返回 `ContentVerificationResult(score, message, passed)`

2. **`src/qed_tracker/application/book_fetch.py` — 自动下载路径集成** ✅
   - 在 `_download_with_budget()` 中，`accept_pdf()` 通过后、`promote_staged()` 前调用
   - 结果写入 `qt_sources.note`（成功行 `note=resource_id + ；内容校验 score/警告`）

3. **`src/qed_tracker/api/main.py` — 手动导入路径** ✅
   - `book_import`：`_inspect_local_pdf()` 后调用 `verify_content()`，不匹配时警告追加进 `qt_sources.note`
   - `book_verify`：不增强（保持 downloaded→verified 纯状态迁移）

4. **测试** ✅
   - `tests/test_downloader.py`：匹配 → passed；不匹配 → failed（score < 0.5）；扫描版/无文本层/损坏/空标题不误拒
   - `tests/test_book_fetch.py`：自动下载成功 note 含内容校验（匹配/不匹配两用例）

**成功标准**：✅ 全部达成。

### ② 评估任务进度上报（评估，QED-Tracker 后端已就绪）✅ 已完成（仅评估）

**现状**：后端进度上报基础设施已完备——`qt_tasks.progress`/`message` 字段、handler
回调、`GET /tasks/{id}` 端点、8900 代理均已实现。**缺口在前端**：无轮询代码、无
进度 UI 组件。

**本轮动作**：**仅评估，不做代码改动**。结论登记供前端（QED-Engine 8903）后续承接。
如需改动，单独立项。

## 关联文档

- 根仓库 REQ-017：`QED-Engine/docs/trackers/todo.md`
- 根仓库 REQ-019：`QED-Engine/docs/trackers/todo.md`
- 服务管理中心设计：`docs/design/service-management.md`
- 后台任务调度器：`src/qed_tracker/api/tasks.py`
- 任务持久层：`src/qed_tracker/db/tasks_repository.py`
- API 端点：`docs/architecture/api.md`
- 代码映射：`docs/architecture/code-map.md`
- 下载管线设计：`docs/design/download-pipeline.md`
- 相似度匹配：`src/qed_tracker/matching.py`

## 验证

- `pytest tests/test_task_handlers.py -v`：恢复测试 + 原有测试全绿
- `pytest tests/test_downloader.py -v`：内容校验测试全绿
- `pytest tests/test_book_fetch.py -v`：note 落痕测试全绿
- `pytest tests -q`：全量回归无退化
- `ruff check src tests scripts`：无新 lint 错误
- `tests/test_documentation.py`：文档白名单通过
