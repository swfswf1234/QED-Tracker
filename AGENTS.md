# QED-Tracker Agent 执行入口

## 项目目标

QED-Tracker 是 QED 的前置 PDF 获取组件。它负责发现、下载、校验和登记教材、习题集与 arXiv 论文；解析、审阅和知识发布属于 Axiom-Flow。

## 阅读顺序

1. 从 [README](README.md) 确认产品边界和最短使用路径。
2. 阅读 [待办列表](docs/trackers/todo.md)，再从 [文档索引](docs/index.md) 进入对应架构、设计、计划或指南。
3. 用 `rg` 搜索真实实现和测试，不根据历史文件名推断行为。
4. 只有追溯旧系统或 Math-QE 人工盘点时才阅读 `docs/history/`。
5. 跨项目契约（服务端口 8901/8902、根 `.env` 变量、dataset 布局）以 QED-Engine 根仓库 `docs/` 为准，本仓库文档只链接不复制。

事实冲突时依次采用：运行代码和测试、当前设计、当前架构、当前指南、路线图、历史资料。历史资料不能覆盖当前实现。

## 任务路由

| 任务 | 首查实现 | 当前文档 | 定向测试 |
| --- | --- | --- | --- |
| 代码-设计-测试映射、模块定位 | `src/qed_tracker/`（全模块，映射唯一事实源见 `docs/architecture/code-map.md`） | `docs/architecture/code-map.md` | — |
| 项目当前状态与主线 | —（状态快照） | `docs/architecture/project-status.md` | — |
| 教材来源、候选归一化 | `src/qed_tracker/providers/books.py` | `docs/design/acquisition-and-inventory.md` | `tests/test_book_providers.py` |
| arXiv 搜索与下载 | `src/qed_tracker/providers/arxiv.py` | `docs/design/acquisition-and-inventory.md` | `tests/test_arxiv_provider.py` |
| arXiv 智能发现与评分 | `src/qed_tracker/application/papers.py`、`src/qed_tracker/providers/bailian.py` | `docs/design/paper-discovery.md` | `tests/test_paper_application.py`、`tests/test_bailian_advisor.py` |
| 下载、PDF 校验、清单 | `src/qed_tracker/downloader.py`、`src/qed_tracker/inventory.py`、`src/qed_tracker/application/resources.py` | `docs/design/acquisition-and-inventory.md` | `tests/test_download_inventory.py`、`tests/test_services.py` |
| 服务与 API（8901、后台任务、MySQL 登记索引、存量迁移） | `src/qed_tracker/api/main.py`、`src/qed_tracker/db/`（models/knowledge_repository/migrations）、`src/qed_tracker/application/migrate_knowledge.py` | `docs/design/tracker-service.md`、`docs/design/database-schema.md`、`docs/adr/0001-tracker-service-architecture.md` | `tests/test_api.py`、`tests/test_knowledge_api.py`、`tests/test_db_models.py`、`tests/test_cli_architecture.py`、`tests/test_migrate_knowledge.py` |
| 主链路（课程梳理/教材条目/验收移交） | `src/qed_tracker/courses.py`、`src/qed_tracker/main_line/`（advisor） | `docs/design/main-line-curriculum.md` | `tests/test_courses.py`、`tests/test_main_line_advisor.py`、`tests/test_main_line_cli.py` |
| 配置、目录和 CLI | `src/qed_tracker/config.py`、`src/qed_tracker/catalog.py`、`src/qed_tracker/cli.py` | `docs/architecture/system-overview.md` | `tests/test_config_catalog_matching.py`、`tests/test_cli_architecture.py` |
| Axiom-Flow 交付 | `src/qed_tracker/axiom.py`、`src/qed_tracker/cli.py` | `docs/design/tracker-service.md`（外部接口：Axiom-Flow 消费面） | `tests/test_axiom.py` |
| 文档与仓库结构 | `README.md`、`docs/` | `docs/index.md` | `tests/test_documentation.py` |

## 强制约束

- 不得隐式扫描、移动或删除用户数据根内的 PDF。
- 来源适配器只搜索和解析下载地址；文件写入、重试、校验、哈希和去重必须经过通用服务。
- 默认测试不得访问公网。来源协议变化使用固定 fixture 覆盖，真实连通性由人工检查。
- TLS 校验默认开启，只能由用户显式配置关闭。
- 冻结目录自动下载必须保持严格匹配；不确定候选不得自动落盘。
- Axiom 上传默认不解析，只有显式 `--parse` 才能创建可能产生费用的任务。
- 百炼只生成论文检索计划和可审阅评分；模型不得直接下载，也不得把判断写入资源事实。
- 修改公开 CLI、配置、目录 schema、资源 schema 或 Axiom 契约时，必须同步更新当前设计、指南和测试。

## 分支与完成门禁

日常开发直接在 `release`，较大改动从它派生 `feat/*` 并合回。发布候选由 `release` 合入 `main`；`main` 上的修复发布后必须同步回 `release`。提交保持单一目的，不维护逐日 worklog。

完成前运行 [开发指南](docs/guides/development.md) 中的完整门禁，保留用户已有改动，并确认没有读取或修改真实数据根。
