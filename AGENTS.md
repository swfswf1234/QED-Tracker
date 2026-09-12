# QED-Tracker Agent 执行入口

## 项目目标

QED-Tracker 是 QED 的前置 PDF 获取组件。它负责发现、下载、校验和登记教材、习题集与 arXiv 论文；解析、审阅和知识发布属于 Axiom-Flow。

## 阅读顺序

1. 从 [README](README.md) 确认产品边界和最短使用路径。
2. 阅读 [待办列表](docs/trackers/todo.md)，再从 [文档索引](docs/index.md) 进入对应架构、设计、计划或指南。
3. 工程治理规则以 `docs/standards/` 为唯一事实源，入口[规范索引](docs/standards/index.md)；跨项目协作与测试门禁规则分别见[跨项目协作规范](docs/standards/cross-project-collaboration.md)与[测试架构与门禁](docs/standards/testing.md)。
4. 按下方「标准映射」定位本任务需要的标准与文档；用 `rg` 搜索真实实现和测试，不根据历史文件名推断行为。
5. 只有追溯旧系统或 Math-QE 人工盘点时才阅读 `docs/history/`。
6. 跨项目契约（服务端口 8901/8902、根 `.env` 变量、dataset 布局）以 QED-Engine 根仓库 `docs/` 为准，本仓库文档只链接不复制。

**文档优先级**：agent 与项目开发优先读取**已确认文档**（当前：`standards/` 全部五份标准——文档治理、ADR 治理、测试门禁、跨项目协作、本地开发环境，均已确认）；`architecture/`、`design/` 文档的确认状态登记列入 QED-039 版本末期轮，登记前按暂定对待（可读可执行但待评审）。确认状态、冲突优先级与转正规则见[文档治理规范](docs/standards/doc-governance.md)「确认状态」节。

事实冲突时依次采用：运行代码和测试、当前设计、当前架构、当前指南、路线图、历史资料。历史资料不能覆盖当前实现。

## 标准映射（概念 → 本仓库文件）

全局 agent 工具层与技能只引用「概念」，实际文件以本表为准。

| 概念 | 本仓库文件 |
| --- | --- |
| 项目状态快照 | [docs/trackers/project-status.md](docs/trackers/project-status.md) |
| 文档治理 | [docs/standards/doc-governance.md](docs/standards/doc-governance.md) |
| ADR 治理 | [docs/standards/adr-governance.md](docs/standards/adr-governance.md) |
| 任务生命周期 | 内联于本文件「变更分级与边界」（本仓库暂无独立标准） |
| 测试门禁 | [docs/standards/testing.md](docs/standards/testing.md) |
| 跨项目协作 | [docs/standards/cross-project-collaboration.md](docs/standards/cross-project-collaboration.md) |
| 本地环境 | [docs/standards/local-dev.md](docs/standards/local-dev.md) |
| 模块映射 | [docs/architecture/code-map.md](docs/architecture/code-map.md) |
| 开发/联调门禁 | [docs/guides/development.md](docs/guides/development.md) |
| 全部入口汇总 | [docs/index.md](docs/index.md) |

## 任务路由

| 任务 | 首查实现 | 当前文档 | 定向测试 |
| --- | --- | --- | --- |
| 代码-设计-测试映射、模块定位 | `src/qed_tracker/`（全模块，映射唯一事实源见 `docs/architecture/code-map.md`） | `docs/architecture/code-map.md` | — |
| 项目当前状态与主线 | —（状态快照） | `docs/trackers/project-status.md` | — |
| 教材来源、候选归一化 | `src/qed_tracker/providers/books.py` | `docs/design/download-pipeline.md` | `tests/test_book_providers.py` |
| arXiv 搜索与下载 | `src/qed_tracker/providers/arxiv.py` | `docs/design/download-pipeline.md` | `tests/test_arxiv_provider.py` |
| arXiv 智能发现与评分 | `src/qed_tracker/application/papers.py`、`src/qed_tracker/providers/bailian.py` | `docs/design/paper-discovery.md` | `tests/test_paper_application.py`、`tests/test_bailian_advisor.py` |
| 下载、PDF 校验、清单 | `src/qed_tracker/downloader.py`、`src/qed_tracker/inventory.py`、`src/qed_tracker/application/resources.py` | `docs/design/download-pipeline.md` | `tests/test_download_inventory.py`、`tests/test_services.py` |
| 服务与 API（8901、后台任务、MySQL 登记索引、共享表契约） | `src/qed_tracker/api/main.py`、`src/qed_tracker/db/`（models/engine/schema/knowledge_repository/selection_repository/tasks_repository） | `docs/architecture/api.md`、`docs/design/service-management.md`、`docs/architecture/database-private-tables.md`、`docs/architecture/database-shared-tables.md`、`docs/adr/0001-tracker-service-architecture.md`、`docs/adr/0006-database-model-as-schema-rebuild.md` | `tests/test_api.py`、`tests/test_knowledge_api.py`、`tests/test_book_api.py`、`tests/test_db_models.py`、`tests/test_cli_architecture.py`、`tests/test_schema.py` |
| 主链路（课程梳理/教材条目/取书登记） | `src/qed_tracker/courses.py`、`src/qed_tracker/main_line/`（advisor）、`src/qed_tracker/application/book_fetch.py` | `docs/design/main-line-curriculum.md`、`docs/design/download-pipeline.md` | `tests/test_courses.py`、`tests/test_main_line_advisor.py`、`tests/test_main_line_cli.py`、`tests/test_book_fetch.py` |
| 配置、目录和 CLI | `src/qed_tracker/config.py`、`src/qed_tracker/catalog.py`、`src/qed_tracker/cli.py` | `docs/architecture/system-overview.md` | `tests/test_config_catalog_matching.py`、`tests/test_cli_architecture.py` |
| Axiom-Flow 交付 | `src/qed_tracker/axiom.py`、`src/qed_tracker/cli.py` | `docs/architecture/api.md`（外部接口：Axiom-Flow 消费面） | `tests/test_axiom.py` |
| 文档与仓库结构 | `README.md`、`docs/` | `docs/index.md` | `tests/test_documentation.py` |

## 强制约束

- 不得隐式扫描、移动或删除用户数据根内的 PDF。
- 来源适配器只搜索和解析下载地址；文件写入、重试、校验、哈希和去重必须经过通用服务。
- 默认测试不得访问公网。来源协议变化使用固定 fixture 覆盖，真实连通性由人工检查。
- TLS 校验默认开启，只能由用户显式配置关闭。
- 冻结目录自动下载必须保持严格匹配；不确定候选不得自动落盘。
- Axiom 上传默认不解析，只有显式 `--parse` 才能创建可能产生费用的任务。
- 百炼只生成检索计划（论文检索计划、书籍检索词变体）与可审阅评估（论文评分、书籍匹配确认）；模型不得直接下载，也不得把判断写入资源事实（判断只落 qt_sources 留痕与 qed_llm_calls 审计），下载与登记只能由确定性服务执行。
- 修改公开 CLI、配置、目录 schema、资源 schema 或 Axiom 契约时，必须同步更新当前设计、指南和测试。
- 当检测到本地机器UUID与[本地开发环境](docs/standards/local-dev.md)匹配时，必须遵循该文档的本地配置约定。
- 修改文档或执行todo任务时，必须遵守[文档治理规范](docs/standards/doc-governance.md)中的规定，包括文档生命周期、确认状态和归档规则。

## 变更分级与边界（AI 开发守则）

本项目以**文档控制代码**：先文档后实现，实现完成后文档与代码同步收口。任何改动先按下表
定级，再按[开发指南](docs/guides/development.md)六步模式执行；**未定级不实施**，无法判定时
询问用户。

| 变更对象 | 定级 | 前置动作 |
| --- | --- | --- |
| `docs/architecture/`（固定架构：API、数据库、code-map、system-overview 等） | 大修改 | 先建 todo 任务 + `plans/` 计划，评审后才动文档与代码 |
| `docs/` 目录结构（新建/删除/移动目录或治理类目） | **阻止项** | 默认阻止；仅用户明确同意且建 todo + `plans/` 计划后执行 |
| `docs/design/` 大变更（新增/重写设计契约） | 大修改 | todo + `plans/` 计划，评审确认后晋升 |
| `docs/design/` 小修/bug | 小修改 | 登记对应长期台账（无则新建）并补设计文档，不单独立项 |
| 一般小改（措辞、链接、错别字、无行为修正） | 豁免 | 差异 + 验证记录承接，不入 todo |
| `standards/` 实质规则变更 | 先立 ADR | 按[文档治理规范·变更与取代](docs/standards/doc-governance.md)新增 ADR |

任务分类（Plan / Defect / Validation / Candidate）与状态枚举见[待办列表](docs/trackers/todo.md)「规则」节；本仓库暂无独立任务生命周期标准。

## 分支与完成门禁

日常开发直接在 `develop`，较大改动从它派生 `feat/*` 并合回。发布候选由 `develop` 合入 `main`；`main` 上的修复发布后必须同步回 `develop`。提交保持单一目的，不维护逐日 worklog。

完成前运行 [开发指南](docs/guides/development.md) 中的完整门禁，保留用户已有改动，并确认没有读取或修改真实数据根。

### 完成检查

1. 公开 CLI / 配置 / 目录 schema / 资源 schema / Axiom 契约变更已同步设计、指南与测试。
2. 文档变更已运行 `tests/test_documentation.py` 且全绿。
3. 未读取或修改真实数据根，未产生越界代码改动。
4. 声称完成前已运行验证命令并展示输出。
5. 未获得明确要求不提交 git。
