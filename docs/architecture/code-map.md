# 代码与设计映射表

设计状态：Accepted
实现状态：Implemented
最后更新：2026-08-12
维护位置：`docs/architecture/code-map.md`
关联代码：受管模块清单
关联测试：`tests/test_documentation.py`（入口与引用守护）
关联 ADR：—

本表是 QED-Tracker 代码与文档关系的唯一事实源。`__init__.py`、`__main__.py` 及无业务语义的
极短文件豁免；子项目代码不进入本表。新增、移动或删除模块时同步本表与关联设计文档。

## 受管代码映射

| 代码路径 | 层级/职责 | 状态 | 设计关联 | 关联测试 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `src/qed_tracker/api/main.py` | FastAPI 服务入口（8901）：路由、后台任务注册、五层端点组（QED-031） | Current | `docs/design/tracker-service.md`、`docs/design/database-schema.md` | `tests/test_api.py`、`tests/test_knowledge_api.py` | `/api/v1/domains|courses|knowledge|books|sources`（QED-031，`KnowledgeRepository` 注入，未配置 DB 时 409 降级）。 |
| `src/qed_tracker/api/tasks.py` | 后台任务管理器与任务落盘（queued→running→succeeded/failed，并发上限 2） | Current | `docs/design/tracker-service.md` | `tests/test_api.py` | 任务记录落 `meta/tasks/`。 |
| `src/qed_tracker/application/books.py` | 教材搜索编排、resolve 与目录运行（严格匹配 + 下载） | Current | `docs/design/acquisition-and-inventory.md` | `tests/test_services.py`、`tests/test_book_providers.py` | file_hint 选文件（QED-019/021）。 |
| `src/qed_tracker/application/papers.py` | 论文搜索/推荐编排与选择报告下载 | Current | `docs/design/paper-discovery.md` | `tests/test_paper_application.py` | 报告快照显式下载。 |
| `src/qed_tracker/application/resources.py` | 资源服务：候选下载与登记编排 | Current | `docs/design/acquisition-and-inventory.md` | `tests/test_download_inventory.py`、`tests/test_services.py` | 统一下载/校验/哈希入口。 |
| `src/qed_tracker/providers/books.py` | 教材来源适配器（internet_archive/open_library/google_books/libgen_li）与 `RETIRED_PROVIDERS` | Current | `docs/design/acquisition-and-inventory.md`、`docs/design/source-discovery.md` | `tests/test_book_providers.py` | libgen_li 发现专用（QED-021），CJK 查询策略（QED-018）。 |
| `src/qed_tracker/providers/arxiv.py` | arXiv 搜索适配器 | Current | `docs/design/acquisition-and-inventory.md` | `tests/test_arxiv_provider.py` | 关键词/分类/作者/ID 查询。 |
| `src/qed_tracker/providers/bailian.py` | 百炼论文顾问：检索计划与评分（不写资源事实） | Current | `docs/design/paper-discovery.md` | `tests/test_bailian_advisor.py` | 模型调用经 `llm_client.py` 兼容层（`API_KEY`，自身 `.env` → 根 `.env` 兜底；local 直连 / qed-engine 网关）。 |
| `src/qed_tracker/providers/book_advisor.py` | 百炼教材评估顾问：书目结构化补全与候选评分 | Current | `docs/design/tracker-service.md`（QED-013） | — | 输出可审阅评估，不写事实。 |
| `src/qed_tracker/config.py` | 统一配置：直读根 `.env` `QED_*`，默认值 + 降级尾注 | Current | `docs/design/tracker-service.md` | `tests/test_config_catalog_matching.py` | TOML 与旧 `QED_TRACKER_*` 退役。 |
| `src/qed_tracker/catalog.py` | 冻结目录读取（包内 JSON） | Current | `docs/design/acquisition-and-inventory.md` | `tests/test_config_catalog_matching.py` | `math-qe` 永久 frozen。 |
| `src/qed_tracker/catalogs/math-qe.json` | 冻结目录数据（13 门课程 54 目标） | Current | `docs/design/acquisition-and-inventory.md` | `tests/test_config_catalog_matching.py` | 01 数学分析套归属按 note 文本（QED-024 set_no 属 Plan，方案确定后再进设计）。 |
| `src/qed_tracker/matching.py` | 冻结目录严格匹配（标题/作者/语言/版次） | Current | `docs/design/acquisition-and-inventory.md` | `tests/test_config_catalog_matching.py` | 不确定候选不自动落盘。 |
| `src/qed_tracker/downloader.py` | 通用下载器：重试、PDF 校验、SHA-256、原子落盘 | Current | `docs/design/acquisition-and-inventory.md` | `tests/test_download_inventory.py` | `.part` 校验后原子替换。 |
| `src/qed_tracker/inventory.py` | 资源清单：单资源 JSON 事实源、登记/verify/scan/传输记录 | Current | `docs/design/acquisition-and-inventory.md` | `tests/test_download_inventory.py` | 路径限定数据根内。 |
| `src/qed_tracker/models.py` | 候选/目录目标/资源记录/下载方案模型 | Current | `docs/design/acquisition-and-inventory.md` | `tests/test_services.py` 等（被广泛引用） | `Candidate.links`（QED-021）。 |
| `src/qed_tracker/profiles.py` | 论文目标档案加载与校验 | Current | `docs/design/paper-discovery.md` | `tests/test_profiles_and_selections.py` | 内置 + 自定义 JSON。 |
| `src/qed_tracker/paper_profiles/`（llm-engineering.json、math-research.json） | 内置论文目标档案 | Current | `docs/design/paper-discovery.md` | `tests/test_profiles_and_selections.py` | 包数据。 |
| `src/qed_tracker/selection_store.py` | 论文选择报告原子存储（`meta/selections/`） | Current | `docs/design/paper-discovery.md` | `tests/test_profiles_and_selections.py`、`tests/test_paper_selection_cli.py` | sel- 前缀 ID 校验。 |
| `src/qed_tracker/axiom.py` | Axiom-Flow HTTP 客户端（健康检查/上传/可选解析） | Current | `docs/design/tracker-service.md`（外部接口：Axiom-Flow 消费面） | `tests/test_axiom.py` | 默认不解析，不自动重试。 |
| `src/qed_tracker/cli.py` | 唯一用户入口：命令树、机器输出、稳定退出码、serve | Current | `docs/design/tracker-service.md`、`docs/design/main-line-curriculum.md`（courses/mainline 命令组） | `tests/test_cli_architecture.py`、`tests/test_main_line_cli.py` | 闭环命令属 QED-010 未实现（见 tracker-service.md）。 |
| `src/qed_tracker/courses.py` | 学科课程体系加载（包内 JSON，数学范本 14 门，含先修关系 DAG） | Current | `docs/design/main-line-curriculum.md` | `tests/test_courses.py` | 主链路课程梳理；与 catalogs/ 同模式。 |
| `src/qed_tracker/migrations/data/math.json` | 课程体系种子数据（14 门课程，三大无前置基础课；qed_domain/qed_course 迁移与测试种子） | Current | `docs/design/main-line-curriculum.md`、`docs/design/database-schema.md` | `tests/test_courses.py`、`tests/test_migrate_knowledge.py` | related_targets 只关联已二次确认评估目标（当前全空）。 |
| `src/qed_tracker/main_line/advisor.py` | 主链路 LLM 预填（参照顶尖大学 + 防总评高校准，可审阅） | Current | `docs/design/main-line-curriculum.md` | `tests/test_main_line_advisor.py` | 模型不写资源事实。 |
| `src/qed_tracker/database.py` | SQLAlchemy 引擎与会话工厂（按 `QED_DB_*`） | Current | `docs/design/tracker-service.md` | `tests/test_db_models.py` | 服务启动与冒烟复用。 |
| `src/qed_tracker/db/models.py` | 五表 ORM（QedDomain/QedCourse/QtKnowledge/QtBook/QtSource）与状态枚举（KnowledgeStatus/BookStatus） | Current | `docs/design/database-schema.md` | `tests/test_db_models.py` | 五层 `_HIDDEN_*` 彻底隐藏语义（QED-031）；qt_resources 已退役（QED-030）。 |
| `src/qed_tracker/db/knowledge_repository.py` | 五层仓库（QED-031）：qt_knowledge/qt_books 状态机 + 彻底隐藏过滤 + 确定性幂等 ID + 教材下载登记入口 | Current | `docs/design/database-schema.md` | `tests/test_knowledge_repository.py`、`tests/test_knowledge_api.py` | backup⇄confirmed 可逆、candidate→downloaded 仅 register 直转（需 sha256+path）；`add_source` 记录渠道事实。 |
| `src/qed_tracker/migrations/versions/0001_qt_resources.py` | Alembic 建表迁移（qt_resources，链上保留，0005 已 drop） | Historical | `docs/design/tracker-service.md` | — | 纯 ASCII。 |
| `src/qed_tracker/migrations/versions/0002_review_note.py` | review_note 增列迁移（QED-020，链上保留，0005 已 drop） | Historical | `docs/design/review-round-dedup.md` | — | 纯 ASCII。 |
| `src/qed_tracker/migrations/versions/0003_three_table.py` | 三表建表迁移（QED-028） | Current | `docs/design/three-table-schema.md` | `tests/test_db_three_table_smoke.py` | 真实 MySQL 已 upgrade（alembic_version 将推进至 0005_drop_resources）。 |
| `src/qed_tracker/migrations/versions/0004_download_intro.py` | qt_downloads.intro 增列迁移 | Current | `docs/design/three-table-schema.md` | — | 12 条简介已落库。 |
| `src/qed_tracker/migrations/versions/0005_drop_resources.py` | qt_resources 退役 drop 迁移（QED-030，真实 MySQL 待执行） | Current | `docs/design/three-table-schema.md`、`docs/history/qed-030-retire-qt_resources/index.md` | — | 证据已归档；downgrade 不支持。 |
| `src/qed_tracker/migrations/versions/0006_knowledge_schema.py` | 五层建表迁移（QED-031：qed_domain/qed_course/qt_knowledge/qt_books；真实 MySQL 待执行） | Current | `docs/design/database-schema.md` | `tests/test_migrate_knowledge.py` | 纯 ASCII；qt_sources 由 migrate 命令按需创建。 |

## 测试映射

| 测试路径 | 职责 | 设计关联 |
| --- | --- | --- |
| `tests/test_api.py` | API 路由、任务提交/轮询、幂等、CORS | `docs/design/tracker-service.md` |
| `tests/test_services.py` | 应用层编排 | `docs/design/acquisition-and-inventory.md` |
| `tests/test_book_providers.py` | 来源解析/CJK/libgen_li 方案 | `docs/design/acquisition-and-inventory.md`、`docs/design/source-discovery.md` |
| `tests/test_arxiv_provider.py` | arXiv 适配器 | `docs/design/acquisition-and-inventory.md` |
| `tests/test_bailian_advisor.py` | 百炼顾问契约 | `docs/design/paper-discovery.md` |
| `tests/test_paper_application.py` | 论文应用层与报告重放 | `docs/design/paper-discovery.md` |
| `tests/test_paper_selection_cli.py` | 选择报告 CLI | `docs/design/paper-discovery.md` |
| `tests/test_profiles_and_selections.py` | 档案与选择存储 | `docs/design/paper-discovery.md` |
| `tests/test_download_inventory.py` | 下载器/清单/scan/verify | `docs/design/acquisition-and-inventory.md` |
| `tests/test_config_catalog_matching.py` | 配置/目录/匹配边界 | `docs/design/tracker-service.md`、`docs/design/acquisition-and-inventory.md` |
| `tests/test_cli_architecture.py` | CLI 命令树与退出码 | `docs/design/tracker-service.md` |
| `tests/test_axiom.py` | Axiom 客户端 | `docs/design/tracker-service.md`（外部接口：Axiom-Flow 消费面） |
| `tests/test_db_models.py` | ORM 模型与状态枚举 | `docs/design/tracker-service.md`、`docs/design/three-table-schema.md` |
| `tests/test_knowledge_repository.py` | 五层仓库状态机/隐藏/幂等 | `docs/design/database-schema.md` |
| `tests/test_knowledge_api.py` | 五层 API 契约与彻底隐藏 | `docs/design/database-schema.md`、`docs/design/tracker-service.md` |
| `tests/test_migrate_knowledge.py` | 一次性存量迁移（种子/三表→五表/幂等/可恢复） | `docs/design/database-schema.md` |
| `tests/test_db_three_table_smoke.py` | 真实 MySQL 三表契约冒烟（默认 skip） | `docs/design/three-table-schema.md` |
| `tests/test_data_layout.py` | 数据布局与路径解析 | `docs/design/tracker-service.md` |
| `tests/test_courses.py` | 课程体系加载（14 门/阶段/前置/别名） | `docs/design/main-line-curriculum.md` |
| `tests/test_main_line_advisor.py` | 主链路 LLM 预填契约（MockTransport） | `docs/design/main-line-curriculum.md` |
| `tests/test_main_line_cli.py` | courses/mainline CLI 命令与闭环 | `docs/design/main-line-curriculum.md` |
| `tests/test_encoding_regression.py` | 来源响应强制 UTF-8 解码回归 | `docs/design/main-line-curriculum.md` |
| `tests/test_documentation.py` | 文档守护（入口/元数据/链接/CLI 一致性/tracker ID） | `docs/standards/documentation.md` |

变更规则：模块职责或 DesignRef 变化时同步本表、设计文档与关联测试；`__init__.py` 等豁免文件
不得承载业务规则。治理依据对齐根仓库 `code-document-traceability.md` 模式（守护测试增强属
QED-022 范围，见 `docs/design/governance-contract-alignment.md`）。
