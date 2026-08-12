# 2026-08 QED-Tracker 服务化与教材下载计划（service-and-book-download）

状态：Accepted
任务类型：B
最后更新：2026-08-05
关联 ADR：[ADR 0001 服务化架构](../adr/0001-tracker-service-architecture.md)；跨仓库决策见
QED-Engine [ADR 0002](../../../docs/adr/0002-frontend-and-port-centralization.md)
关联设计：[服务与外部接口设计](../design/tracker-service.md)、[下载与清单](../design/acquisition-and-inventory.md)、
[arXiv 论文智能发现](../design/paper-discovery.md)；跨项目契约见
QED-Engine [service-contracts.md](../../../docs/design/service-contracts.md)、
[dataset-conventions.md](../../../docs/design/dataset-conventions.md)、
[configuration-and-secrets.md](../../../docs/design/configuration-and-secrets.md)
关联 Tracker：`docs/trackers/todo.md`（QED-008~016；需求方 QED-Engine REQ-004/REQ-011/REQ-013/REQ-014）
归档判定：全部门禁与冒烟通过、联调回执完成后 Completed，Retain 归档至 `docs/history/`

## 目标与成功标准

承接 QED-Engine 教材下载轮（根仓库 ARCH-002）的 QED-Tracker 侧工作：服务化、配置与数据布局
迁移、MySQL 资源登记与状态机、书单与 LLM 筛选评估、人工确认下载、下载后验收闭环。

1. 服务化：8901 API（`/api/v1`）——只读查询同步返回，写操作一律后台任务 + 轮询；并发上限 2；
   同 sha256 幂等复用；任务落盘 `meta/tasks/`。
2. 配置统一：直读根 `.env` 的 `QED_*` 变量（`QWEN_API_KEY`、`QED_MODEL`、`QED_AXIOM_URL`、
   `QED_TRACKER_PORT`、`QED_DB_*`）；本地 TOML 与 `QED_TRACKER_*` 退役；无 `.env` 时最小默认
   值 + 尾注提醒。
3. 数据布局：数据根默认 `dataset/qed-tracker/`（raw/meta/tmp）；文件名规则
   `<slug>_<sha256前8>.pdf`；存量数据不迁移。
4. MySQL 登记与状态机：qed 库 `qt_resources` 表（来源/时间/书名/中英文/作者/路径/sha256/状态/
   llm_evaluation/catalog_ref/留痕）；状态机 candidate→confirmed→downloading→downloaded→
   approved/rejected（+failed 可重试、pending_manual/not_found 辅助状态）；`meta/resources/`
   JSON 保留文件状态事实，双写一致、失败可重放。
5. 书单与 LLM 筛选评估：`math-qe-v2` 覆盖 13 门课程，每课程教材组 + 习题集组（优先中文版经典
   教材中译本，英文原版补充）；qwen 辅助书目结构化与判断，宁缺勿滥；**按课程批量评估任务**
   （搜索源 → LLM 评估 → 候选落库）；中文书不可得时登记 `pending_manual`。
6. 人工确认与验收闭环（2026-08-05 用户裁决，人机协同）：前端/CLI 确认后才下载；下载后预览
   验收，通过转 approved，不通过删除（文件硬删 + DB 记录保留 reject_reason 留痕）；候选级
   拒绝同规则留痕。
7. CLI 转 HTTP 客户端（含闭环命令）；真实 8901 冒烟 + 重复下载幂等验证 + 联调回执。

成功标准：`qed-tracker catalog evaluate`（经 8901，按课程）→ 候选落库 → 确认 → 下载 → 验收
（approve/reject 留痕）全链路完成；PDF 落位、JSON 与 MySQL 记录一致；`qed` CLI 与 QED-Engine
前端（8903）可查询展示。

## 范围与非目标

范围内：上述 1-6 项，含 ORM 框架旧禁令移除（`tests/test_documentation.py` LEGACY_PATTERNS
与 `tests/test_cli_architecture.py` 禁导入清单）及其治理测试同步。

非目标：
- 不新增下载源（IA/OL/GB 之外的中文书源评估另立任务）。
- 不迁移存量数据根（`D:\coding\dataset\textbooks` 等保持不动）。
- 不解析 PDF（属于 Axiom-Flow）；不执行 Axiom 推送解析。
- 论文发现、来源可靠性评测、目录扩展等路线图项不进入本计划。

## 前置条件

- 根 `.env` 存在且 `QWEN_API_KEY` 已配置；`QED_DB_*` 已填写且本机 MySQL 8 实例可连接（qed 库
  由实现轮初始化）。
- 用户裁决（2026-08-04）：统一 qed 库；书单按"课程规划 + 现有索引"双轨、每课程两组、宁缺勿滥；
  资源登记 JSON + MySQL 双写。2026-08-05 复核裁决：统一 qed 库直写确认；pending_manual 补书
  扫描后转 `confirmed`（不引入 `registered` 状态）；独立性铁律修订依赖根仓库 ADR 0003
  （登记中，QED-Tracker 侧不写死链接）。
- QED-Tracker ADR 0001 已 Accepted；tracker-service.md 已转 Accepted（2026-08-05）。

## 工作项

1. **服务化 8901**（QED-008）：实现 API 层与任务层（状态机 queued→running→succeeded/failed、
   进度 0-100、并发上限 2、sha256 幂等）；任务落盘 `meta/tasks/`；TestClient 单元测试 +
   MockTransport 客户端测试。
2. **配置与数据布局迁移**（QED-009）：`config.py` 直读根 `.env` `QED_*` 变量；数据根默认
   `dataset/qed-tracker/`，raw/meta/tmp 布局与文件名规则；TOML 与 `QED_TRACKER_*` 退役；无
   `.env` 降级与尾注；相关配置/目录测试更新。
3. **MySQL 资源登记与状态机**（QED-012）：qed 库建库与迁移（Alembic，qt_* 表）；`qt_resources`
   登记服务与状态机（candidate→confirmed→downloading→downloaded→approved/rejected，+failed
   可重试；pending_manual/not_found 辅助状态）；llm_evaluation/catalog_ref/留痕字段；双写一致
   性与重放测试；旧禁令移除与治理测试同步。
4. **书单与 LLM 筛选评估**（QED-013）：整理 `catalogs/math-qe-v2.json`（13 门课程、每课程两组）；
   `POST /tasks/catalog/evaluate {course_id?}` 按课程批量评估任务（搜索源 → qwen 结构化补全 +
   评分报告，宁缺勿滥，不写资源事实 → 候选落库 candidate 状态）；书单/评估测试。
5. **下载任务与预览端点**（QED-015）：`POST /tasks/books/download {resource_id}` 仅 confirmed
   可触发（否则 409），下载后回填 sha256/relative_path/page_count；`GET /resources/{id}/file`
   PDF 预览流（downloaded/approved 可访问）。
6. **验收闭环与 CLI**（QED-016）：`confirm`（candidate→confirmed）、`approve`（downloaded→
   approved）、`reject {reason}`（candidate 或 downloaded→rejected，reason 必填，后者硬删文件
   + DB 留痕；同源已拒候选不再推荐）；CLI 闭环命令（catalog evaluate / resources
   list|show|confirm|reject|approve / books download）。
7. **CLI 转 HTTP 客户端**（QED-010）：默认等待、`--no-wait` 输出 task_id；客户端测试。
8. **验证与联调**（QED-011/QED-014）：真实 8901 冒烟（评估→确认→下载→验收/删除→登记→
   双写一致）；重复下载幂等验证；联调回执至 QED-Engine todo。

## 验证与验收

- 全量门禁：`pytest tests -q` 全绿、`ruff check src tests` 无错误、`tests/test_documentation.py`
  通过（含新计划登记）。
- 8901 冒烟：真实服务启动，`catalog evaluate`（按课程）→ 候选落库 → 确认 → 下载 → 验收/删除
  全链路，PDF 落位 `dataset/qed-tracker/raw/books/math-qe/<course-id>/`，JSON 与
  `qt_resources` 字段一致。
- 状态机：非法迁移（如未确认即下载、已拒再验收）返回 409；reject 缺 reason 返回 422；已拒
  资源 DB 记录保留且同源候选不再推荐。
- 补书路径：中文书不可得登记 `pending_manual`；人工放书后 `scan` 转 `confirmed` 并回填文件
  信息，回归确认/下载链路。
- 幂等：同一资源二次下载返回既有记录，不产生重复文件（QED-011）。
- 降级：无根 `.env` / 无 `QED_DB_PASSWORD` 时服务与 CLI 正常启动并输出提醒。
- 外部依赖（下载源、qwen）失败以证据记录，恢复条件与责任位置写入 todo。

## 回滚

- 代码与配置变更在本仓库提交，回滚 = git revert + 恢复旧默认值。
- `qed` 库为新建库（表可重建），回滚不触存量数据；`meta/tasks/` 任务记录保留可追溯。
- 数据布局迁移不自动执行（存量不迁移），新布局回滚仅影响新下载文件。

## 关闭与归档

- 工作项全部完成且门禁通过后转 Completed（关闭结果 Achieved）；QED-008~014 从 todo 原子移除
  并写 completed 台账。
- 按文档规范判定 Retain/Delete：本计划 Retain 归档至 `docs/history/` 作为跨仓库联调审计证据。
