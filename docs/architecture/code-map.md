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
| `src/qed_tracker/api/main.py` | FastAPI 服务入口（8901）：路由、后台任务注册、轻量状态迁移端点 | Current | `docs/design/tracker-service.md` | `tests/test_api.py`、`tests/test_resources_api.py`、`tests/test_catalog_evaluate.py` | register/backup/review_note 端点（QED-017/020/021）。 |
| `src/qed_tracker/api/tasks.py` | 后台任务管理器与任务落盘（queued→running→succeeded/failed，并发上限 2） | Current | `docs/design/tracker-service.md` | `tests/test_api.py` | 任务记录落 `meta/tasks/`。 |
| `src/qed_tracker/application/books.py` | 教材搜索编排、resolve 与目录运行（严格匹配 + 下载） | Current | `docs/design/acquisition-and-inventory.md` | `tests/test_services.py`、`tests/test_book_providers.py` | file_hint 选文件（QED-019/021）。 |
| `src/qed_tracker/application/papers.py` | 论文搜索/推荐编排与选择报告下载 | Current | `docs/design/paper-discovery.md` | `tests/test_paper_application.py` | 报告快照显式下载。 |
| `src/qed_tracker/application/resources.py` | 资源服务：候选下载与登记编排 | Current | `docs/design/acquisition-and-inventory.md` | `tests/test_download_inventory.py`、`tests/test_services.py` | 统一下载/校验/哈希入口。 |
| `src/qed_tracker/application/catalog_evaluate.py` | 目录评估任务：搜索 → LLM 评估 → 候选落库，同源去重 + file_hint 例外 | Current | `docs/design/review-round-dedup.md`、`docs/design/tracker-service.md` | `tests/test_catalog_evaluate.py` | 跳过 backup/approved/rejected 已评估目标。 |
| `src/qed_tracker/providers/books.py` | 教材来源适配器（internet_archive/open_library/google_books/libgen_li）与 `RETIRED_PROVIDERS` | Current | `docs/design/acquisition-and-inventory.md`、`docs/design/source-discovery.md` | `tests/test_book_providers.py` | libgen_li 发现专用（QED-021），CJK 查询策略（QED-018）。 |
| `src/qed_tracker/providers/arxiv.py` | arXiv 搜索适配器 | Current | `docs/design/acquisition-and-inventory.md` | `tests/test_arxiv_provider.py` | 关键词/分类/作者/ID 查询。 |
| `src/qed_tracker/providers/bailian.py` | 百炼论文顾问：检索计划与评分（不写资源事实） | Current | `docs/design/paper-discovery.md` | `tests/test_bailian_advisor.py` | 密钥直读根 `.env` `QWEN_API_KEY`。 |
| `src/qed_tracker/providers/book_advisor.py` | 百炼教材评估顾问：书目结构化补全与候选评分 | Current | `docs/design/tracker-service.md`（QED-013） | `tests/test_catalog_evaluate.py`（评估链路用假顾问） | 输出可审阅评估，不写事实。 |
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
| `src/qed_tracker/axiom.py` | Axiom-Flow HTTP 客户端（健康检查/上传/可选解析） | Current | `docs/design/axiom-handoff.md` | `tests/test_axiom.py` | 默认不解析，不自动重试。 |
| `src/qed_tracker/cli.py` | 唯一用户入口：命令树、机器输出、稳定退出码、serve | Current | `docs/design/tracker-service.md`、`docs/design/axiom-handoff.md` | `tests/test_cli_architecture.py` | 闭环命令属 QED-010 未实现（见 tracker-service.md）。 |
| `src/qed_tracker/database.py` | SQLAlchemy 引擎与会话工厂（按 `QED_DB_*`） | Current | `docs/design/tracker-service.md` | `tests/test_db_models.py` | 服务启动与冒烟复用。 |
| `src/qed_tracker/db/models.py` | qt_resources ORM 与状态枚举 | Current | `docs/design/tracker-service.md` | `tests/test_db_models.py` | 10 状态 + review_note 列。 |
| `src/qed_tracker/db/repository.py` | 状态机仓库与查询索引数据访问 | Current | `docs/design/tracker-service.md`、`docs/design/review-round-dedup.md` | `tests/test_resources_api.py`、`tests/test_db_registry.py` | confirm/backup/reject 带 note。 |
| `src/qed_tracker/db/registry.py` | 双写登记服务（JSON 事实源 → MySQL 索引） | Current | `docs/design/tracker-service.md` | `tests/test_db_registry.py` | 失败可重放、sha256 幂等。 |
| `src/qed_tracker/migrations/versions/0001_qt_resources.py` | Alembic 建表迁移 | Current | `docs/design/tracker-service.md` | `tests/test_db_mysql_smoke.py` | 纯 ASCII。 |
| `src/qed_tracker/migrations/versions/0002_review_note.py` | review_note 增列迁移（QED-020） | Current | `docs/design/review-round-dedup.md` | `tests/test_resources_api.py` | 纯 ASCII。 |

## 测试映射

| 测试路径 | 职责 | 设计关联 |
| --- | --- | --- |
| `tests/test_api.py` | API 路由、任务提交/轮询、幂等、CORS | `docs/design/tracker-service.md` |
| `tests/test_resources_api.py` | 资源端点与 review_note 契约 | `docs/design/tracker-service.md`、`docs/design/review-round-dedup.md` |
| `tests/test_catalog_evaluate.py` | 评估任务：落库/降级/跳过/同源去重 | `docs/design/review-round-dedup.md`、`docs/design/tracker-service.md` |
| `tests/test_services.py` | 应用层编排 | `docs/design/acquisition-and-inventory.md` |
| `tests/test_book_providers.py` | 来源解析/CJK/libgen_li 方案 | `docs/design/acquisition-and-inventory.md`、`docs/design/source-discovery.md` |
| `tests/test_arxiv_provider.py` | arXiv 适配器 | `docs/design/acquisition-and-inventory.md` |
| `tests/test_bailian_advisor.py` | 百炼顾问契约 | `docs/design/paper-discovery.md` |
| `tests/test_paper_application.py` | 论文应用层与报告重放 | `docs/design/paper-discovery.md` |
| `tests/test_paper_selection_cli.py` | 选择报告 CLI | `docs/design/paper-discovery.md` |
| `tests/test_profiles_and_selections.py` | 档案与选择存储 | `docs/design/paper-discovery.md` |
| `tests/test_download_inventory.py` | 下载器/清单/scan/verify | `docs/design/acquisition-and-inventory.md` |
| `tests/test_config_catalog_matching.py` | 配置/目录/匹配边界 | `docs/design/tracker-service.md`、`docs/design/acquisition-and-inventory.md` |
| `tests/test_cli_architecture.py` | CLI 命令树与退出码 | `docs/design/tracker-service.md`、`docs/design/axiom-handoff.md` |
| `tests/test_axiom.py` | Axiom 客户端 | `docs/design/axiom-handoff.md` |
| `tests/test_db_models.py` | ORM 模型与状态枚举 | `docs/design/tracker-service.md` |
| `tests/test_db_registry.py` | 双写登记与重放 | `docs/design/tracker-service.md` |
| `tests/test_db_mysql_smoke.py` | 真实 MySQL 冒烟（QED_DB_SMOKE=1） | `docs/design/tracker-service.md` |
| `tests/test_data_layout.py` | 数据布局与路径解析 | `docs/design/tracker-service.md` |
| `tests/test_documentation.py` | 文档守护（入口/元数据/链接/CLI 一致性/tracker ID） | `docs/standards/documentation.md` |

变更规则：模块职责或 DesignRef 变化时同步本表、设计文档与关联测试；`__init__.py` 等豁免文件
不得承载业务规则。治理依据对齐根仓库 `code-document-traceability.md` 模式（守护测试增强属
QED-022 范围，见 `docs/design/governance-contract-alignment.md`）。
