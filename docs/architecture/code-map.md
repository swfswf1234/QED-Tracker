# 代码与设计映射表

设计状态：Accepted
实现状态：Implemented
最后更新：2026-09-11
维护位置：`docs/architecture/code-map.md`
关联代码：受管模块清单
关联测试：`tests/test_documentation.py`（入口与引用守护）
关联 ADR：—

本表是 QED-Tracker 代码与文档关系的唯一事实源。`__init__.py`、`__main__.py`
及无业务语义的极短文件豁免；子项目代码不进入本表。新增、移动或删除模块时同步本表与关联设计文档。

主流程按模块分块（① 服务与接口 → ② 探索线 → ③ 下载与登记线 → ④ 主链路与课程 →
⑤ 配置与数据库 → ⑥ 导入与迁移 → ⑦ 运维脚本）；测试映射分**代码测试**（行为与契约）
与**守护测试**（文档/契约/正本不变量）两块。

## 受管代码映射（主流程）

### ① 服务与接口

| 代码路径 | 层级/职责 | 状态 | 设计关联 | 关联测试 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `src/qed_tracker/api/main.py` | FastAPI 服务入口（8901）：路由、后台任务注册、五层端点组（QED-031） | Current | `docs/architecture/api.md`、`docs/design/service-management.md`、`docs/architecture/database-private-tables.md` | `tests/test_api.py`、`tests/test_knowledge_api.py`、`tests/test_book_api.py` | 路由分组契约见 [API 设计文档](api.md)（`KnowledgeRepository` 注入，未配置 DB 时 409 降级）；QED-060 新增书籍下载生命周期端点 start/fail/verify/cancel；REQ-077 `PATCH /courses` 透传 exploration_stage/explore_pending + 课程 5 态校验（422）。 |
| `src/qed_tracker/api/tasks.py` | 后台任务管理器与落盘（queued→running→succeeded/failed，并发上限 2，dedup 查重防同任务并发） | Current | `docs/design/service-management.md`、`docs/design/download-pipeline.md`、`docs/design/exploration-pipeline.md` | `tests/test_api.py`、`tests/test_book_api.py`、`tests/test_task_handlers.py` | 任务记录落 `qt_tasks` 表；注册类型 `book_download`/`tutorial_fetch`/`domain_explore`/`course_explore`/`domain_explore_courses`（`all_handlers` 注册点在 `api/main.py`）。 |
| `src/qed_tracker/cli.py` | 唯一用户入口：命令树、机器输出、稳定退出码、serve | Current | `docs/design/service-management.md`、`docs/design/main-line-curriculum.md`（courses/mainline 命令组）、`docs/design/exploration-pipeline.md`（domains explore） | `tests/test_cli_architecture.py`、`tests/test_main_line_cli.py`、`tests/test_cli_domains_explore.py` | 主链路命令已转 HTTP 客户端并经真实 8901 全链路冒烟验收（QED-010 已关闭，2026-09-09，见 `docs/trackers/completed.md`）。 |
| `src/qed_tracker/axiom.py` | Axiom-Flow HTTP 客户端（健康检查/上传/可选解析） | Current | `docs/architecture/api.md`（外部接口：Axiom-Flow 消费面） | `tests/test_axiom.py` | 默认不解析，不自动重试。 |
| `src/qed_tracker/profiles.py` | 论文目标档案加载与校验 | Current | `docs/design/paper-discovery.md` | `tests/test_profiles_and_selections.py` | 内置 + 自定义 JSON。 |
| `src/qed_tracker/paper_profiles/`（llm-engineering.json、math-research.json） | 内置论文目标档案 | Current | `docs/design/paper-discovery.md` | `tests/test_profiles_and_selections.py` | 包数据。 |


### ② 探索线（prompt_lab）

| 代码路径 | 层级/职责 | 状态 | 设计关联 | 关联测试 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `src/qed_tracker/llm_client.py` | 模型调用兼容层（QED-037）：`local` 直连 / `qed-engine` 经 8900 网关（不接触密钥） | Current | `docs/design/service-management.md`、`docs/architecture/database-shared-tables.md`（qed_llm_calls 写入路径） | `tests/test_llm_client.py`、`tests/test_prompt_template_ids.py` | 调用记录写 `qed_llm_calls`，失败静默降级。 |
| `src/qed_tracker/prompt_lab/pipeline.py` | 探索管线：DomainPipeline（领域→课程两步，courses@v8 输出含 stage/prerequisites，交叉校验 track⊆classic_tracks）/ CoursePipeline（tutorials 单步，proposal_id 前缀） | Current | `docs/design/exploration-pipeline.md` | `tests/test_prompt_lab.py`、`tests/test_prompt_lab_course.py`、`tests/test_prompt_lab_api.py`、`tests/test_task_handlers.py` | dry-run 模式不写任何表（engine 置 None）。 |
| `src/qed_tracker/prompt_lab/templates.py` | 模板注册表（唯一事实源）：domain-explore domain@v4/courses@v8（path@v5 已并入）+ course-explore tutorials@v2、教程契约校验 `_validate_tutorials_v2` | Current | `docs/design/exploration-pipeline.md` | `tests/test_prompt_template_ids.py`、`tests/test_prompt_lab.py`（学科中立守护）、`tests/test_prompt_lab_course.py` | 编号格式 `{task}/{step}@v{n}`，落 `qed_llm_calls.prompt_template`。 |
| `src/qed_tracker/prompt_lab/priors.py` | 领域先验注入（DOMAIN_PRIORS：精确域名匹配，未命中不影响其它领域） | Current | `docs/design/exploration-pipeline.md` | `tests/test_prompt_lab.py`、`tests/test_prompt_lab_course.py` | 领域专属知识一律走本模块，模板保持学科中立。 |
| `src/qed_tracker/providers/explore_advisor.py` | 探索 LLM advisor 基类（ExploreAdvisorBase：严格 JSON 校验 + 一次修复重试 + 预算控制）与参考输入归一化（direct/text/doc） | Current | `docs/design/exploration-pipeline.md` | `tests/test_prompt_lab.py`、`tests/test_prompt_lab_course.py`（经管线假 advisor 驱动） | 模型调用经 `llm_client.py`；参考文本按不可信数据处理（防注入）。 |

### ③ 下载与登记线

| 代码路径 | 层级/职责 | 状态 | 设计关联 | 关联测试 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `src/qed_tracker/application/books.py` | 教材搜索编排、resolve 与目录运行（严格匹配 + 下载） | Current | `docs/design/download-pipeline.md` | `tests/test_services.py`、`tests/test_book_providers.py` | file_hint 选文件（QED-019/021）。 |
| `src/qed_tracker/application/papers.py` | 论文搜索/推荐编排与选择报告下载 | Current | `docs/design/paper-discovery.md` | `tests/test_paper_application.py` | 报告快照显式下载。 |
| `src/qed_tracker/application/resources.py` | 资源服务：候选下载与登记编排（`stage_download` staging 落盘 + `promote_staged` 内容指纹确定性入 raw/，QED-050-D） | Current | `docs/design/download-pipeline.md` | `tests/test_download_inventory.py`、`tests/test_services.py`、`tests/test_book_fetch.py` | 统一下载/校验/哈希入口。 |
| `src/qed_tracker/application/book_fetch.py` | 五阶段取书编排（QED-050-D）：检索→确认（预筛→enrich→LLM）→候选级预算下载→staging 机器验收→mark_owned 登记（status=downloaded）；书级 fetch 与教程级 fetch_tutorial（refs 聚合、排除 owned、顺序逐书、部分失败不中断），全部失败转人工指引；落盘取真实 `domain_id`（QED-060） | Current | `docs/design/download-pipeline.md` | `tests/test_book_fetch.py` | handler（`book_download`/`tutorial_fetch`）注册于 api/main.py；候选预算 `QED_BOOK_CANDIDATE_BUDGET`。 |
| `src/qed_tracker/providers/books.py` | 教材来源适配器（internet_archive/open_library/google_books/libgen_li）与 `RETIRED_PROVIDERS` | Current | `docs/design/download-pipeline.md`、`docs/plans/2026-09-source-discovery.md` | `tests/test_book_providers.py` | libgen_li 发现专用（QED-021），CJK 查询策略（QED-018）。 |
| `src/qed_tracker/providers/arxiv.py` | arXiv 搜索适配器 | Current | `docs/design/download-pipeline.md` | `tests/test_arxiv_provider.py` | 关键词/分类/作者/ID 查询。 |
| `src/qed_tracker/providers/bailian.py` | 百炼论文顾问：检索计划与评分（不写资源事实） | Current | `docs/design/paper-discovery.md` | `tests/test_bailian_advisor.py` | 模型调用经 `llm_client.py` 兼容层（`API_KEY`，自身 `.env` → 根 `.env` 兜底；local 直连 / qed-engine 网关）。 |
| `src/qed_tracker/providers/book_advisor.py` | 百炼书籍顾问（QED-050-D）：检索词变体 `book-query/variants@v1`（≤N 条，坏 JSON 一次修复）+ 候选确认 `book-confirm/assess@v1`（两值 verdict，覆盖完整性校验），书级共享 LLM 预算 | Current | `docs/design/download-pipeline.md` | `tests/test_book_llm_advisor.py`、`tests/test_prompt_template_ids.py` | 输出可审阅评估，不写资源事实。 |
| `src/qed_tracker/downloader.py` | 通用下载器：重试、PDF 校验、SHA-256、原子落盘；`accept_pdf` 机器验收门（魔数/可解析/非加密/页数/大小硬门槛 + 文本层软信号，QED-050-D） | Current | `docs/design/download-pipeline.md` | `tests/test_download_inventory.py`、`tests/test_book_acceptance.py` | `.part` 校验后原子替换。 |
| `src/qed_tracker/inventory.py` | 资源清单：单资源 JSON 事实源、登记/verify/scan/传输记录 | Current | `docs/design/download-pipeline.md` | `tests/test_download_inventory.py` | 路径限定数据根内。 |
| `src/qed_tracker/matching.py` | 冻结目录严格匹配（标题/作者/语言/版次） | Current | `docs/design/download-pipeline.md` | `tests/test_config_catalog_matching.py` | 不确定候选不自动落盘。 |
| `src/qed_tracker/catalog.py` | 冻结目录读取（包内 JSON） | Current | `docs/design/download-pipeline.md` | `tests/test_config_catalog_matching.py` | `math-qe` 永久 frozen。 |
| `src/qed_tracker/catalogs/math-qe.json` | 冻结目录数据（13 门课程 54 目标） | Current | `docs/design/download-pipeline.md` | `tests/test_config_catalog_matching.py` | 01 数学分析 13 目标含 `set_no`（QED-024 已实现；其余课程待人工定套）。课程数口径：本目录为 **catalog 线 13 门**（研究生 QE 方向），与主链路 courses 线（`docs/knowledge/` 确认导入）是两条线，勿混用。 |
| `src/qed_tracker/models.py` | 候选/目录目标/资源记录/下载方案模型 | Current | `docs/design/download-pipeline.md` | `tests/test_services.py` 等（被广泛引用） | `Candidate.links`（QED-021）。 |

### ④ 主链路与课程

| 代码路径 | 层级/职责 | 状态 | 设计关联 | 关联测试 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `src/qed_tracker/courses.py` | 学科课程体系加载（`qed_domain`/`qed_course` 共享表，无 DB 显式拒绝；课程数据经 `docs/knowledge/` 确认导入，DAG 先修关系） | Current | `docs/design/main-line-curriculum.md`、`docs/architecture/database-shared-tables.md` | `tests/test_courses.py` | 主链路课程梳理；与 catalogs/ 线并行（见该行口径备注）。 |
| `src/qed_tracker/main_line/advisor.py` | 主链路 LLM 预填（参照顶尖大学 + 防总评高校准，可审阅） | Current | `docs/design/main-line-curriculum.md` | `tests/test_main_line_advisor.py` | 模型不写资源事实。 |


### ⑤ 配置与数据库

| 代码路径 | 层级/职责 | 状态 | 设计关联 | 关联测试 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `src/qed_tracker/config.py` | 统一配置：直读根 `.env` `QED_*`，默认值 + 降级尾注 | Current | `docs/design/service-management.md` | `tests/test_config_catalog_matching.py` | TOML 与旧 `QED_TRACKER_*` 退役。 |
| `src/qed_tracker/db/engine.py` | 数据库连接管理（队列池参数化 + session_factory + utc_now + dispose；按 `QED_DB_*`） | Current | `docs/architecture/database-private-tables.md`、`docs/adr/0006-database-model-as-schema-rebuild.md` | `tests/test_schema.py` | 原 `database.py` 迁入并退役（ADR 0006）；所有数据库操作集中于 db/。 |
| `src/qed_tracker/db/schema.py` | `ensure_schema` 快照自愈：Base.metadata 7 张声明表缺表补建/列不一致重建（含共享表，MySQL 挂起 FK 检查）；`qed_llm_calls` 缺失建表 + 缺列增量补齐（绝不 DROP）；幂等 | Current | `docs/architecture/database-shared-tables.md`、`docs/architecture/database-private-tables.md`、`docs/adr/0006-database-model-as-schema-rebuild.md` | `tests/test_schema.py`、`tests/test_schema_mysql_smoke.py` | 取代 Alembic 迁移链（ADR 0006）。 |
| `src/qed_tracker/db/models.py` | 七表 ORM（QedDomain/QedCourse/QtKnowledge/QtBook/QtSource/QtTask/QtSelection）与状态枚举（KnowledgeStatus 两态、BookStatus 选用四态） | Current | `docs/architecture/database-shared-tables.md`、`docs/architecture/database-private-tables.md` | `tests/test_db_models.py` | schema 唯一实施事实源（ADR 0006）；表/列中文注释事实源 = 模型 `comment=`。 |
| `src/qed_tracker/db/knowledge_repository.py` | 五层仓库（QED-031）：qt_knowledge 两态（draft→confirmed）/qt_books 选用四态 + 下载生命周期（downloading/downloaded/verified/failed）+ holding 持有态 + 确定性幂等 ID + 领域/课程 CRUD | Current | `docs/architecture/database-private-tables.md`、`docs/architecture/database-shared-tables.md`、`docs/design/knowledge-import.md`、`docs/design/download-pipeline.md` | `tests/test_knowledge_repository.py`、`tests/test_knowledge_api.py`、`tests/test_book_fetch.py` | `adopt_tutorials` 承接课程知识采纳（建 draft + 书行 decided/parallel + refs 回填 book_id）；`mark_owned` 登记唯一写入口（同时置 status=downloaded，QED-050-D/QED-060）；`start_download`/`fail_download`/`verify_book`/`cancel_download` 生命周期迁移；`first_course_for_book` refs 反查默认桶；`add_source` 记录渠道事实；`update_course` 课程 5 态校验（REQ-076，拒绝「已生成」）。 |
| `src/qed_tracker/db/selection_repository.py` | qt_selections 读写层（论文选择报告，REQ-032；`SelectionStore`/`SelectionStoreError`） | Current | `docs/design/paper-discovery.md`、`docs/architecture/database-private-tables.md` | `tests/test_profiles_and_selections.py`、`tests/test_paper_selection_cli.py` | 原 `selection_store.py` 迁入并退役（ADR 0006）。 |
| `src/qed_tracker/db/tasks_repository.py` | qt_tasks 读写层（`TaskRecord`/`TaskStore`/`ActiveTaskExists`，REQ-032） | Current | `docs/design/service-management.md`、`docs/architecture/database-private-tables.md` | `tests/test_task_handlers.py` | `api/tasks.py` 仅留调度器 TaskManager（ADR 0006）。 |

### ⑥ 导入与迁移

| 代码路径 | 层级/职责 | 状态 | 设计关联 | 关联测试 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `src/qed_tracker/application/knowledge_import.py` | 手动知识录入校验器：`validate_domain`（manual@v1：slug/方向 kind/stages 值域/track∈已列方向/前置引用与无环/一句话契约）与 `validate_course`（数据文件版课程契约：顶层 domain_id/course_id/course_name + set_no/position 五档/intro ≥120 字/refs 数组 + original_title 可选） | Current | `docs/design/knowledge-import.md` | `tests/test_knowledge_import.py` | 正本 = `docs/knowledge/*.json`（契约守护，见守护测试块）。 |
| `src/qed_tracker/application/domain_file.py` | 领域/课程探索 JSON 文件读写层：`raw/<domain_id>/domains.json`（领域知识，已完成反写）、`raw/<domain_id>/courses.json`（领域课程探索/手动导入暂存，已完成删除）、`raw/<domain_id>/<course_id>/tutorials.json`（课程知识 JSON，已完成定稿）的幂等写入、合并与读取 | Current | `docs/design/knowledge-import.md`、`docs/design/exploration-pipeline.md`、`docs/architecture/api.md`（confirm 双分支） | `tests/test_task_handlers.py`、`tests/test_knowledge_api.py` | `POST /domains/import` 落盘、`GET /domains/{id}`/`GET /courses/{domain_id}` 确认视图与探索结果暂存的共用文件层；QED-061 落盘收口。 |
（Alembic 迁移链已随 ADR 0006 退役：迁移目录 migrations/ 全目录删除——0001~0018
迁移文件与 data 种子/注释 JSON 不再登记；schema 演进由 db/models.py + db/schema.py
承接，历史链仅作 Git 追溯。）

### ⑦ 运维脚本

| 代码路径 | 层级/职责 | 状态 | 设计关联 | 关联测试 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `scripts/qed_tracker_service.py` | 8901 服务生命周期托管（start/stop/restart/status，`--mode`；PID/日志落 `logs/`） | Current | `docs/design/service-management.md` | `tests/test_service_scripts.py` | 根仓库 8900 经此托管启停。 |

（`scripts/apply_table_comments.py` 已随 ADR 0006 退役：注释由 ORM `comment=` 建表即带。）

## 测试映射

### 代码测试（行为与契约）

| 测试路径 | 职责 | 设计关联 |
| --- | --- | --- |
| `tests/test_api.py` | API 路由、任务提交/轮询、幂等、CORS | `docs/architecture/api.md`、`docs/design/service-management.md` |
| `tests/test_services.py` | 应用层编排 | `docs/design/download-pipeline.md` |
| `tests/test_book_providers.py` | 来源解析/CJK/libgen_li 方案 | `docs/design/download-pipeline.md`、`docs/plans/2026-09-source-discovery.md` |
| `tests/test_arxiv_provider.py` | arXiv 适配器 | `docs/design/download-pipeline.md` |
| `tests/test_bailian_advisor.py` | 百炼顾问契约 | `docs/design/paper-discovery.md` |
| `tests/test_paper_application.py` | 论文应用层与报告重放 | `docs/design/paper-discovery.md` |
| `tests/test_paper_selection_cli.py` | 选择报告 CLI | `docs/design/paper-discovery.md` |
| `tests/test_profiles_and_selections.py` | 档案与选择存储 | `docs/design/paper-discovery.md` |
| `tests/test_download_inventory.py` | 下载器/清单/scan/verify | `docs/design/download-pipeline.md` |
| `tests/test_book_fetch.py` | 五阶段取书编排（检索词规则集/渠道顺序/verdict 门控/候选预算/验收门/登记幂等/教程级批处理；假 provider + MockTransport） | `docs/design/download-pipeline.md` |
| `tests/test_book_acceptance.py` | 机器验收门 accept_pdf（魔数/解析/加密/页数/大小矩阵 + 文本层软信号） | `docs/design/download-pipeline.md` |
| `tests/test_book_llm_advisor.py` | 书籍 LLM 顾问契约（检索词变体/两值确认/覆盖完整性/坏 JSON 修复/预算共享） | `docs/design/download-pipeline.md` |
| `tests/test_book_api.py` | 书库化书籍 API（创建矩阵/原地登记/人工导入/书级 fetch e2e/教程级 fetch e2e/并发 409） | `docs/architecture/api.md`、`docs/design/download-pipeline.md` |
| `tests/test_config_catalog_matching.py` | 配置/目录/匹配边界 | `docs/design/download-pipeline.md`、`docs/design/service-management.md` |
| `tests/test_cli_architecture.py` | CLI 命令树与退出码 | `docs/design/service-management.md` |
| `tests/test_axiom.py` | Axiom 客户端 | `docs/architecture/api.md`（外部接口：Axiom-Flow 消费面） |
| `tests/test_db_models.py` | ORM 模型与状态枚举 | `docs/architecture/database-private-tables.md`、`docs/history/three-table-schema.md` |
| `tests/test_knowledge_repository.py` | 五层仓库状态机/隐藏/幂等 | `docs/architecture/database-private-tables.md` |
| `tests/test_knowledge_api.py` | 五层 API 契约（knowledge 采纳/确认/教程级 fetch + courses/domains） | `docs/architecture/database-private-tables.md`、`docs/architecture/api.md` |
| `tests/test_exploration_stage.py` | 探索状态机（领域 6 态 / 课程 5 态）与 apply-results/re-explore 端点、课程 5 态校验 | `docs/architecture/database-shared-tables.md`、`docs/architecture/api.md` |
| `tests/test_schema.py` | ensure_schema 快照自愈（缺表补建/列不一致重建/幂等/未声明表不碰/qed_llm_calls 增量自愈） | `docs/architecture/database-shared-tables.md`、`docs/architecture/database-private-tables.md`、`docs/adr/0006-database-model-as-schema-rebuild.md` |
| `tests/test_schema_mysql_smoke.py` | 真实 MySQL ensure_schema 契约冒烟（默认 skip；仅允许 qed_test 库） | `docs/architecture/database-shared-tables.md`、`docs/architecture/database-private-tables.md`、`docs/adr/0006-database-model-as-schema-rebuild.md` |
| `tests/test_data_layout.py` | 数据布局与路径解析 | `docs/design/service-management.md` |
| `tests/test_courses.py` | 课程体系加载（14 门/阶段/前置/别名） | `docs/design/main-line-curriculum.md` |
| `tests/test_main_line_advisor.py` | 主链路 LLM 预填契约（MockTransport） | `docs/design/main-line-curriculum.md` |
| `tests/test_main_line_cli.py` | mainline/books CLI 命令面（download 经 8901、books fetch 双入口、verify 只读、channels 聚合） | `docs/design/main-line-curriculum.md`、`docs/design/download-pipeline.md` |
| `tests/test_encoding_regression.py` | 来源响应强制 UTF-8 解码回归 | `docs/design/main-line-curriculum.md` |
| `tests/test_llm_client.py` | llm_client 双模式（direct/gateway）+ 调用记录 | `docs/design/service-management.md` |
| `tests/test_prompt_lab.py` | 领域探索管线契约（domain@v4/courses@v8）与 priors 注入 | `docs/design/exploration-pipeline.md` |
| `tests/test_prompt_lab_course.py` | 课程探索管线契约（tutorials@v2） | `docs/design/exploration-pipeline.md` |
| `tests/test_prompt_lab_api.py` | 探索 dry-run API 契约（同步、唯一痕迹 qed_llm_calls） | `docs/design/exploration-pipeline.md`、`docs/architecture/api.md` |
| `tests/test_task_handlers.py` | domain_explore/course_explore 后台 handler 与 re-explore 端点契约 | `docs/design/exploration-pipeline.md` |
| `tests/test_cli_domains_explore.py` | CLI domains explore（dry-run 包装、名称确认、错误/不可达退出码） | `docs/design/exploration-pipeline.md` |
| `tests/test_knowledge_import.py` | 手动导入校验器（validate_domain/validate_course）+ `POST /domains/import` 契约 + 知识正本合规 | `docs/design/knowledge-import.md` |
| `tests/test_cli_knowledge_import.py` | CLI 链路（domains import / knowledge import） | `docs/design/knowledge-import.md` |
| `tests/test_service_scripts.py` | 服务生命周期脚本契约（PID/日志隔离） | `docs/design/service-management.md` |

### 守护测试（文档 / 契约 / 正本不变量）

| 测试路径 | 守护对象 | 备注 |
| --- | --- | --- |
| `tests/test_documentation.py` | 文档治理：入口清单（严格集合相等）/强元数据/链接解析/代码引用存在性/CLI 命令可解析/legacy 词禁令 | `docs/standards/doc-governance.md` |
| `tests/test_prompt_lab.py` | 模板文本学科中立——领域只由输入决定，专属知识一律走 priors.py | 兼领域管线行为测试（见代码测试块） |
| `tests/test_prompt_lab_course.py` | course-explore 模板学科中立守护 | 兼课程管线行为测试 |
| `tests/test_prompt_template_ids.py` | 模板编号落库契约：全部 LLM 调用点向 qed_llm_calls 传 `{task}/{step}@v{n}` | 共享表审计列契约 |
| `tests/test_knowledge_import.py` | 知识正本契约：`docs/knowledge/math-advanced.json` 及课程 JSON 均通过对应校验器（validate_domain / validate_course） | 兼 import 端点行为测试 |

变更规则：模块职责或 DesignRef 变化时同步本表、设计文档与关联测试；`__init__.py` 等豁免文件
不得承载业务规则。治理依据对齐根仓库 `code-document-traceability.md` 模式（守护测试增强属
QED-022 范围，见 `docs/history/baselines/2026-08-governance-contract-alignment.md`）。
