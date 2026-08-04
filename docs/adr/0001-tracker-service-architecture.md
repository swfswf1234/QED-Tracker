# ADR 0001：服务化与统一配置接入

状态：Accepted
日期：2026-08-04
最后更新：2026-08-04
领域：API 与任务
决策阶段：v0.6
取代：—
被取代：—

## 背景

QED-Tracker 是纯 CLI（不运行常驻服务、不维护数据库），配置使用本地 TOML 与 `QED_TRACKER_*`
环境变量。QED-Engine 根仓库按 [ADR 0002](../../../docs/adr/0002-frontend-and-port-centralization.md)
规划了全局端口段（8900/8901/8902/8903）与统一配置：QED-Tracker 服务端口 8901、根 `.env` 的
`QED_*` 变量为唯一事实源。前端与统一 CLI 需要经 HTTP 调用本项目的下载、校验与登记能力，
纯 CLI 形态无法满足。

## 决定

1. **服务化**：新增常驻 HTTP 服务（端口 8901，前缀 `/api/v1`）：
   - 只读查询（搜索、资源列表、选择报告、目录）同步返回；
   - 写操作（下载、推荐、目录批处理、扫描、Axiom 推送）一律创建**后台任务**：
     `POST /tasks/...` 返回 `task_id`，`GET /tasks/{id}` 轮询状态与结果；
     状态机 `queued → running → succeeded / failed`；任务记录落盘 `meta/tasks/`；
   - 同 sha256 已登记时任务直接 `succeeded` 并复用既有记录（幂等）；
   - 并发上限 2，线程池执行现有同步下载器，不重写核心逻辑。
2. **CLI 转 HTTP 客户端**：`qed-tracker` 命令改为调用本地 8901 服务（默认等待完成，
   `--no-wait` 输出 task_id 供前端场景）；独立脚本入口保留至统一 CLI `qed` 承接后退役。
3. **配置统一**：直读根 `.env` 的 `QED_*` 变量（`QWEN_API_KEY`、`QED_MODEL`、
   `QED_AXIOM_URL` 等），本地 TOML 与 `QED_TRACKER_*` 退役；无配置时使用内置最小默认值并
   输出启动尾注提醒。
4. **数据布局**：数据根默认指向根仓库 `dataset/qed-tracker/`：
   - `raw/`（books/inbox、books/math-qe/<course>、exercises/inbox、papers/<year>）成品区；
   - `meta/`（resources/selections/transfers/tasks）JSON 状态，替代 `.qed-tracker/`；
   - `tmp/downloads/` 下载临时区，校验通过后原子落盘，任务结束清理；
   - 文件名规则 `<语义标识>_<sha256前8>.pdf`（教材/习题为标题 slug，论文为 arXiv ID）。
5. **存量数据不迁移**：已有数据根（如 `D:\coding\dataset\textbooks`）不动，仅新下载使用新布局。

## 后果

- 增加常驻服务与进程管理，部署面扩大；`qed-tracker-serve` 服务入口与 API/客户端测试加入门禁。
- 冒烟测试升级为基于真实 8901 服务的启动 → 建任务 → 轮询 → 文件落位链路。
- 文档契约测试需同步：FastAPI 重新进入当前技术栈（Legacy 禁令移除），文档入口集合变更。
- Axiom-Flow 地址默认 `http://127.0.0.1:8902`；`axiom_url` 旧默认 8000 失效。
- 后台任务让长下载/推荐不再阻塞 HTTP 调用，前端可按任务展示进度与结果路径。

## 关联

- 关联标准：[文档规范](../standards/documentation.md)、[ADR 治理](../standards/adr-governance.md)
- 关联设计：[服务接口设计](../design/tracker-service.md)（Draft，需求方 QED-Engine）、
  [下载与清单](../design/acquisition-and-inventory.md)
- 关联架构：[系统总览](../architecture/system-overview.md)（实现后更新实现状态）
- 关联 ADR（根仓库）：[ADR 0002](../../../docs/adr/0002-frontend-and-port-centralization.md)
