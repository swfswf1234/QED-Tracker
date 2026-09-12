# 探索契约对齐计划（exploration-contract-alignment）

状态：Historical
任务类型：B
最后更新：2026-09-11
需求方：QED-Engine（REQ-076 / REQ-077 / REQ-078，来源 PLAN-038 文档对齐轮）
目标项目：QED-Tracker
评审方：用户

> **Historical（2026-09-11 归档，[ADR 0009](../../adr/0009-closed-plan-archival.md)）**：
> 本计划已关闭，QED-063/064/065 完成并验收；结果见
> [完成台账](../../trackers/completed.md)。正文保留当时结论，文内相对链接按原 `docs/plans/`
> 位置书写，已失效，仅作追溯。

> 本计划承接 QED-Engine 根仓库 PLAN-038「下载管理全链路文档对齐轮」向 QED-Tracker 发出的
> 三项跨项目请求：课程探索状态机 6→5 态与 `explore_pending.kind` 归一（REQ-076）、
> `PATCH /courses/{id}` 支持 `exploration_stage`（REQ-077）、探索产物 JSON 入 `raw/` 的
> dataset 例外口径确认（REQ-078）。根侧文档已先行对齐，QED-Tracker 侧以本计划完成
> 代码 + 文档 + 测试对齐后回执。
> 唯一事实源：探索状态机与写主体以[数据库共享表设计](../architecture/database-shared-tables.md)
> 为准；探索产物落盘与 dataset 例外以[探索管线设计](../design/exploration-pipeline.md)、
> [知识录入设计](../design/knowledge-import.md)为准；端点契约以[架构 API](../architecture/api.md)为准。

## 目标与成功标准

用户 2026-09-11 裁决（D1~D5）：

1. 课程探索状态机 **5 态**（未开始 / 探索中 / 待确认 / 已完成 / 失败），**不与领域 6 态混用**，
   课程**无「已生成」**；领域保持 6 态（未开始 / 已生成 / 探索中 / 待确认 / 已完成 / 失败）。
2. `explore_pending.kind` 归一为 `review_results` / `name_confirmation` / `error`（删除
   `failed` 与 `import_courses` 双形态）。
3. `PATCH /courses/{course_id}` 支持 `exploration_stage`（同时暴露 `explore_pending`）；
   8900 课程阶段流转改经该端点，取消共享表直写依赖（D3=B）。
4. 课程 5 态加**运行时校验**：拒绝「已生成」与未知值（422 `INVALID_PARAMS`）；接受根仓库
   代码跟进完成前 8900 可能发「已生成」而被拒的依赖。
5. 探索产物 JSON 例外口径确认：`domains.json` + `tutorials.json` 作**知识正本 / 可重导入
   输入**，`courses.json` 为**中间态**（已完成反写 `domains.json` 并删除）；状态事实源仍在 DB。

成功标准：

1. QED-Tracker `database-shared-tables.md`、`exploration-pipeline.md`、`knowledge-import.md`、
   `api.md` 中课程状态机统一为 5 态、领域 6 态，零矛盾；`explore_pending.kind` 仅三形态。
2. `PATCH /courses/{id}` 透传 `exploration_stage` / `explore_pending`，5 态校验生效（非法值
   422）；8900 直写白名单中 `qed_course.exploration_stage`/`explore_pending` 改经 8901。
3. 探索产物 JSON 例外在 QED-Tracker 文档显式声明并与根 `dataset-conventions.md` 口径一致。
4. `pytest tests -q` 全绿（含新增/改写用例）、`ruff check src tests scripts` 通过、
   `git diff --check` 无错误、`tests/test_documentation.py` 全绿。

## 范围与非目标

- **范围**：`docs/architecture/{api,database-shared-tables}.md`、
  `docs/design/{exploration-pipeline,knowledge-import}.md`、`src/qed_tracker/api/main.py`
  （`patch_course` 透传 + 5 态校验）、`src/qed_tracker/db/knowledge_repository.py`（如需校验）、
  `tests/{test_exploration_stage,test_knowledge_api,test_db_models}.py`、`docs/trackers/{todo,completed}.md`、
  `docs/plans/index.md`。
- **非目标**：根仓库代码（8900 路由/客户端、前端 store）与根仓库文档同步（由根侧 PLAN-038
  代码跟进清单承接）；Axiom-Flow 解析链；`explore_pending` 载荷结构本身不变（只归一 kind）。
- 历史迁移说明（`database-private-tables.md` 0015 行）保持历史留痕，不改写。

## 前置条件

- 根仓库 PLAN-038 已完成文档对齐并登记 REQ-076/077/078（`docs/trackers/todo.md`）。
- 根 `dataset-conventions.md` 已起草例外段（标注 REQ-078 待确认）。
- QED-Tracker 现状核对完成：课程代码从不写「已生成」、`kind` 已归一；缺口在文档、测试与
  `PATCH /courses` 透传（详见工作项）。

## 工作项

### W1 REQ-076 课程 5 态 + kind 归一（文档 + 测试）

- `docs/architecture/database-shared-tables.md`：
  - `qed_course` DDL 注释与列说明由「6 态同 qed_domain」改为「5 态（无已生成）」；
  - 拆分 `qed_course` 状态机节为 5 态，删除「已生成」行；写主体表按 5 态重排；
  - 「在本项目中的作用」节与写权限例外段同步。
- `docs/design/exploration-pipeline.md`：状态机节由「领域与课程共用 6 态」改为「领域 6 态、
  课程 5 态，不混用」；课程流转改「未开始 → 探索中 → 待确认 → 已完成」；头部与关联文档措辞。
- 测试：`tests/test_exploration_stage.py` 课程流转用例改 5 态（删除「已生成」步骤）；
  `tests/test_db_models.py` 课程用例改用合法 5 态值。

### W2 REQ-077 PATCH /courses 支持 exploration_stage（代码 + 文档 + 测试）

- `src/qed_tracker/api/main.py`：`patch_course` 透传 `exploration_stage` 与 `explore_pending`；
  对 `exploration_stage` 做 5 态值域校验，非 `{未开始,探索中,待确认,已完成,失败}`（含「已生成」）
  返回 422 `INVALID_PARAMS`。
- `src/qed_tracker/db/knowledge_repository.py`：如校验落在仓储层，则 `update_course` 同步校验；
  否则仅端点层校验（实现时定，保持单一事实源）。
- `docs/architecture/api.md` ②组 `PATCH /courses/{id}`：字段表补 `exploration_stage`/
  `explore_pending`，重写「解释」（不再说「不经本端点维护」）；③组 dry-run 解释中「8900 直写」
  改指 8901 `PATCH /courses`。
- `docs/architecture/database-shared-tables.md` 写权限例外段：`qed_course` 的
  `exploration_stage`/`explore_pending` 从 8900 离线直写白名单移除，注明改经 8901
  `PATCH /courses`（D3=B，跨项目契约变更）。
- 测试：`tests/test_knowledge_api.py` 新增 `exploration_stage` 更新成功、`explore_pending`
  更新、非法值（含「已生成」）422 用例。

### W3 REQ-078 dataset JSON 例外（文档 + 回执）

- `docs/design/exploration-pipeline.md`「已完成落盘收口」：例外口径由「由跨项目 REQ 对齐」
  改为「已确认（REQ-078）」，引用根 `dataset-conventions.md`。
- `docs/design/knowledge-import.md`：补同一例外声明（`domains.json`/`tutorials.json` 知识正本、
  `courses.json` 中间态；状态事实源仍在 DB）。
- 完成后在 `docs/trackers/completed.md` 记录回执，供根仓库同步 `dataset-conventions.md` 并关闭
  REQ-078。

## 验证与验收

- `conda run -n qed_env python -m pytest tests -q` 全绿。
- `conda run -n qed_env python -m ruff check src tests scripts` 通过。
- `git diff --check` 无空白错误。
- `tests/test_documentation.py` 全绿（计划登记、链接、元数据）。
- 人工交叉核对 PLAN-038 验收清单第 4 项：8901 端点集（含 start/fail/verify/cancel，
  不含 decide/retry/complete/reject/supersede）与 QED-Tracker `api.md` 一致。
- 用户审阅确认。

## 执行记录（2026-09-11）

实现已完成，待用户审阅 + 根仓库回执：

- W1 文档：`database-shared-tables.md` 拆分领域 6 态 / 课程 5 态、`qed_course` DDL/列说明改 5 态、
  写主体表重排；`exploration-pipeline.md` 状态机节与关联措辞对齐。
- W2 文档 + 代码：`api.md` `PATCH /courses` 补 `exploration_stage`/`explore_pending` 与 422 说明；
  `patch_course` 透传两字段（缺省 no-op）；`update_course` 课程 5 态运行时校验（拒绝「已生成」
  与未知值）；`database-shared-tables.md` 写权限例外移除 `qed_course` 探索列（改经 8901）。
- W3 文档：`exploration-pipeline.md`/`knowledge-import.md` 显式声明 dataset JSON 例外并引用根
  `dataset-conventions.md`。
- 测试：`test_exploration_stage.py` 课程流转改 5 态 + 新增值域校验用例；`test_knowledge_api.py`
  新增 PATCH `exploration_stage`/`explore_pending`/422/no-op 用例；`test_db_models.py` 课程值改合法态。
- 门禁：`pytest tests -q` **482 passed + 1 skipped**；`ruff check` 通过；`git diff --check` 无错误；
  `tests/test_documentation.py` 全绿。

## 回滚

- 文档与测试变更由 Git 锚点恢复；代码变更（`patch_course` 透传 + 校验）可单点 revert。
- 若根仓库 8900 尚未停止写「已生成」导致 422，可临时放宽校验（回退校验分支）并保留透传。

## 关闭与归档

- 关闭条件：成功标准 1~4 达成 + 用户审阅通过 + 根仓库回执送达。
- 归档动作：设计事实并入 `design/` 与 `architecture/` 固定文档；本计划按 Delete 关闭
  （内容并入完成台账与设计文档），`todo.md` QED-063/064/065 行移除并在 `plans/index.md` 登记去处。

## 附：跨项目映射

| QED-Tracker 任务 | QED-Engine 请求 | 内容 | 目标文档 |
| --- | --- | --- | --- |
| QED-063 | REQ-076 | 课程探索 5 态 + `explore_pending.kind` 归一 | `database-shared-tables.md`、`exploration-pipeline.md` |
| QED-064 | REQ-077 | `PATCH /courses/{id}` 支持 `exploration_stage`/`explore_pending` | `api.md`、`database-shared-tables.md` |
| QED-065 | REQ-078 | dataset JSON 例外口径确认与回执 | `exploration-pipeline.md`、`knowledge-import.md` |
