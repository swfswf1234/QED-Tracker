# 下载登记实现计划

状态：Current
任务类型：B
最后更新：2026-09-04
需求方：QED-Engine（QED-050-D）
目标项目：QED-Tracker
评审方：用户

> 本计划承接已确认的[下载管线设计](../design/download-pipeline.md)
> （2026-09-04 九项裁决），把五阶段下载链落为代码。设计是唯一语义事实源；本计划只登记
> 实现顺序、文件落点与验证门。

## Phase 0：前置门（迁移 + 失效引用修复）

| 项 | 文件 | 内容 |
|---|---|---|
| 迁移 0018 | `src/qed_tracker/migrations/versions/0018_rebuild_qt_library.py` | qt_knowledge/qt_books 无条件 DROP+重建（2026-09-04 裁决：两表当前为空，不保数据、不做旧结构探测）+ qt_books.original_title 可空列（裁决 5）；qt_sources 存量保留（MySQL 挂起 FK 检查后重建） |
| 失效引用修复 | `src/qed_tracker/db/knowledge_repository.py` | `apply_domain_results`/`apply_course_results`/`list_books(knowledge_id=)` 改经 refs 聚合（删除子表语义），消除 QtBook.knowledge_id AttributeError；采纳时书行先建、refs 回填后再入 session（JSON 列原地变更不落 UPDATE） |
| refs 契约扩展 | `src/qed_tracker/application/knowledge_import.py`、`src/qed_tracker/db/knowledge_repository.py`（adopt_tutorials） | ref 条目可选 `original_title`，采纳时回填 qt_books.original_title；docs/knowledge 数据文件可选补 |
| 校验器对齐 | `src/qed_tracker/application/knowledge_import.py`（validate_course） | 对齐 knowledge-import.md 数据文件版契约（顶层 domain_id/course_id/course_name + 显式 knowledge_id/book_id 格式校验），替代旧 envelope |
| CLI 适配 | `src/qed_tracker/cli.py`（knowledge import） | 按数据文件版契约上传 A2，采纳即建册 + 逐套确认，去独立建册循环 |
| 关联测试 | `tests/test_migration_0018.py`（新）、`tests/test_db_models.py`、`tests/test_knowledge_repository.py`、`tests/test_knowledge_import.py` | 无条件重建矩阵、新模型列断言、D4 id 规则/书幂等键/original_title 回填/refs 级联；旧 book-import 与 G2 回写测试移出（随 Phase 4 以新 holding=owned 语义重建） |

## Phase 1：配置 + 验收原语 ✅（2026-09-06 完成）

| 项 | 文件 | 内容 |
|---|---|---|
| QED_BOOK_* 配置 ✅ | `src/qed_tracker/config.py` | 8 个新键（CANDIDATE_BUDGET/MIN_PAGES/MIN_SIZE_BYTES/SEARCH_LIMIT/QUERY_VARIANTS/LLM_QUERY/LLM_CONFIRM/LLM_BUDGET）；`fetch_attempt_timeout` 字段删除，`QED_FETCH_ATTEMPT_TIMEOUT` 作旧键别名一版（新键覆盖优先），`api/main.py` 引用同步 |
| 验收门 ✅ | `src/qed_tracker/downloader.py` | `AcceptanceResult` + `accept_pdf(path, *, min_pages=10, min_size=204800)`：五项硬门槛（魔数/strict=False 可解析/is_encrypted 非加密/页数/大小，拒绝项逐条收集）+ 软信号 text_chars（-1 无法评估/0 无文本层，只记录不拒绝）；加密文件取页数前先判（pypdf 6.11 实测 is_encrypted=True 且 pages 抛 FileNotDecryptedError） |
| 关联测试 ✅ | `tests/test_book_acceptance.py`（新 8 项）+ `tests/test_config_catalog_matching.py`（+3 项） | 门槛矩阵（pypdf 生成多页/加密/损坏/非 PDF/手写文本页 fixture，默认值签名守护）；键映射/默认值/旧键别名 |
| 当前基线注 | — | 全量套件余 70 失败均为旧契约待重写文件：test_main_line_cli(26)/test_knowledge_api(22)/test_book_fetch(10)/test_migrate_knowledge(9)/test_cli_knowledge_import(3)，分别归 Phase 5/4/3/6/5 处置；Phase 0+1 文件与共享层全绿 |

## Phase 2：LLM 顾问 + 渠道 enrich ✅（2026-09-06 完成）

| 项 | 文件 | 内容 |
|---|---|---|
| 检索词变体 ✅ | `src/qed_tracker/providers/book_advisor.py` | `propose_queries`：book-query/variants@v1，≤variants 条变体（超量按契约拒绝、修复后仍超量上抛），坏 JSON 一次修复，预算耗尽上抛由编排层转人工指引；输入为新增 `BookExpectation`（models.py，阶段2 预筛/确认共用） |
| 确认评估 ✅ | 同上 | `confirm`：book-confirm/assess@v1，一批候选一次调用逐条 verdict ∈ {confirmed, uncertain} + summary，必须完整覆盖输入候选（不得新增/遗漏/重复 provider_id）；候选介绍（enrich 产物）进入确认输入；与 propose_queries 共享书级调用预算（QED_BOOK_LLM_BUDGET） |
| 渠道 enrich ✅ | `src/qed_tracker/providers/books.py`、`src/qed_tracker/models.py` | 零新增 HTTP：IA search `fl[]` 增 description/publisher + resolve 顺带读 metadata description/publisher/date（只回填 search 缺失字段，不覆盖已有值）；OL fields 增 publisher/subtitle/first_sentence/number_of_pages_median；GB 解析 volumeInfo description/publisher/pageCount；libgen_li 回填 Publisher + Pages；Candidate 增 description/publisher/page_count 字段（默认值向后兼容） |
| 关联测试 ✅ | `tests/test_book_llm_advisor.py`（新 10 项）、`tests/test_book_providers.py`（+4 enrich fixture）、`tests/test_prompt_template_ids.py`（+1 模板编号落库） | 假 LLM 契约（两值 verdict / 旧三态拒绝 / 覆盖完整 / 坏 JSON 修复 / 预算共享 / 介绍入参）、模板 ID 守护（direct 落 qed_llm_calls + gateway payload）、四渠道 enrich fixture（solr 多值/OL dict 形状/GB pageCount/libgen Pages） |
| 基线注 | — | 全量套件（除 5 个旧契约文件）374 通过 + ruff 全绿；顺手清理 8 处 Phase 0 遗留 ruff 违例（F401/F841/I001，涉及 api/tasks.py、knowledge_import.py、papers.py 及 3 个测试文件） |

## Phase 3：五阶段编排 + 登记服务 ✅（2026-09-06 完成）

| 项 | 文件 | 内容 |
|---|---|---|
| 编排重写 ✅ | `src/qed_tracker/application/book_fetch.py` | `BookFetchService.fetch` 五阶段（检索→预筛→enrich→LLM 确认→预算下载→staging 验收→mark_owned 登记）；渠道×query 循环（渠道内命中即止、跨渠道独立、搜索失败留痕续跑）；LLM 变体兜底一次（不可用进失败消息 notices）；已 owned no-op；任务异常兜底留痕 |
| 候选级预算 ✅ | 同上 + `src/qed_tracker/downloader.py` | `_download_with_budget`：resolve→开始稳定下载（on_start 首个 chunk 写 .part）受 candidate_budget 约束，未到释放点超时换下一候选（孤儿线程随 service.close() 自灭）；downloader.download 增 on_start 回调并改无参 `iter_bytes()`（带 chunk_size 时 httpx ByteChunker 攒满才吐首块，小文件整个下载期无 chunk 落 .part，释放点语义失效——已实测确认的 httpx 0.28 行为） |
| staging 验收接线 ✅ | `src/qed_tracker/application/resources.py` | download_candidate 拆为 `stage_download`（staging slug+唯一 tag，md5 校验）+ `promote_staged`（最终名不含 tag：{slug}_{sha8}.pdf 内容指纹确定性，sha 去重复用，os.replace 进 raw，register_candidate）；验收门在两者之间执行，未过门槛文件 unlink 永不进 raw/ |
| 教程级批处理 ✅ | `src/qed_tracker/application/book_fetch.py` | `fetch_tutorial`：refs 聚合去重 → 排除 owned/retired → 默认 textbook_ref+exercise_ref（include_parallel 纳入 parallel_ref）→ 顺序逐书 → 部分失败汇总（processed + failed_count） |
| 登记服务 ✅ | `src/qed_tracker/db/knowledge_repository.py` | `mark_owned(book_id, file_path)` 唯一写入口（同路径幂等/换路径重登/空路径 ValueError）；`first_course_for_book` refs 反查成品桶（反查不到 → raw/<domain>/_general/）；`course_closure` 派生只读查询（decided 全 owned，parallel/candidate 不参与） |
| 关联测试 ✅ | `tests/test_book_fetch.py` 重写（24 项） | 检索词规则集 ①~④/渠道顺序与命中即止/渠道失败续跑/去重/预筛硬失配换 query/metadata_only 人工指引/verdict 门控与留痕/LLM 失败降级/llm_confirm=false/变体兜底与不可用指引/预算超时换候选/已开始允许跑完/验收门拒绝不进 raw/大小预检/异常兜底/mark_owned 幂等/course_closure/first_course_for_book/教程级三连（顺序、部分失败、幂等重跑、include_parallel）/build_book_service 形状 |
| 基线注 | — | 全量套件（除 4 个旧契约文件）398 通过 + 3 skip + ruff 全绿；test_api::test_task_records_are_persisted 首轮跑出一次轮询超时抖动，复跑两轮（含单测）均绿——预存在计时敏感项，与 Phase 3 无关 |

## Phase 4：API 重接 ✅（2026-09-06 完成）

| 项 | 文件 | 内容 |
|---|---|---|
| 端点处置 ✅ | `src/qed_tracker/api/main.py` | POST /books 重接书库化创建（book_id 显式 `{abbr}-b{NN}` 校验，201/409 BOOK_ALREADY_EXISTS/422 值域矩阵）；/register 重接登记服务（数据根内原地登记 → 完整性校验 → mark_owned，channel=local_import）；/import 重接人工导入（D9 命名补 _<sha8>、默认桶经 first_course_for_book refs 反查（无归属 422 NO_COURSE_REF）、同 sha 复用不重复落盘、异内容 409 TARGET_CONFLICT 不覆盖用户文件、跳过初筛门槛、tmp 暂存原子落盘）；/fetch 重接五阶段编排（retired 409 BOOK_RETIRED）；**新增** POST /knowledge/{id}/fetch（include_parallel 显式纳入 parallel_ref）；decide/start/fail/retry/complete/verify/reject/supersede/cancel **9 端点删除** |
| 并发防护 ✅ | `src/qed_tracker/api/tasks.py` | TaskManager.submit 增 dedup 标识参数查重（仅 queued/running 计入活动，失败/完成不阻塞重提），命中 ActiveTaskExists → 端点映射 409 TASK_ALREADY_RUNNING（书级按 book_id、教程级按 knowledge_id） |
| 关联测试 ✅ | 新 tests/test_book_api.py（17 项）+ tests/test_knowledge_api.py 重写（28 项） | 书库化创建矩阵/原地登记（owned+留痕、非 PDF 400 不登记）/人工导入（默认桶+D9、无归属 422、显式 target、同 sha 复用、冲突 409、非 PDF 400、越界 400）/书级 fetch e2e（owned 落盘+重跑 no-op、retired 409）/教程级 fetch e2e（decided 三书、include_parallel、404）/并发 409（同书、同教程、不同书不受影响、结束不阻塞重提）；knowledge 文件剥离八态书测试，adopt 用例对齐 tutorials@v2 载荷（textbook_ref[] 形状），courses/domains/领域管理用例保留 |
| 基线注 | — | 全量套件（除 3 个旧契约文件）443 通过 + 3 skip + ruff 全绿；test_book_api LLM 键双引用 monkeypatch（main 直用 + settings.llm_configured）隔离本机 .env 真实键 |

## Phase 5：CLI 重接 ✅（2026-09-06 完成）

| 项 | 文件 | 内容 |
|---|---|---|
| mainline download ✅ | `src/qed_tracker/cli.py` | 重接教程级 fetch（经 8901：POST /knowledge/{id}/fetch + 轮询 GET /tasks/{id}），与新增 books fetch 共享 `_fetch_task_via_api` 提交+轮询助手；退出码 0/2/3/6（任务失败或部分失败→3） |
| mainline verify ✅ | 同上 | 改只读复核（inspect_pdf 重算，无状态迁移）：ok/missing/invalid/changed 四态，文件名带 `_sha8` 指纹时 sha256 前缀比对失配→changed（exit 4） |
| mainline approve ✅ | 同上 | 删除（废弃，设计裁决 6）；reject 同步删除（知识录入链归 review/new） |
| mainline channels ✅ | 同上 | 修复聚合（repo.list_books() 域级全量遍历，refs 多归属不重复计数，含回归测试） |
| books fetch ✅ | 同上 | 新增书级取书命令（POST /books/{id}/fetch，设计裁决 9 双入口）；mainline download 路由前置到 db_configured 门之前（纯 HTTP 命令无需本地库） |
| books import ✅ | 同上 | 经重接后的 /import 端点（Phase 4 完成即通），帮助文案对齐 mark_owned 登记 |
| 关联测试 ✅ | `tests/test_main_line_cli.py` 重写（57 项）、`tests/test_cli_architecture.py`、`tests/test_cli_knowledge_import.py` 重写（4 项） | download 提交+轮询全矩阵（成功/部分失败/任务失败/404/连接失败/超时/载荷）、books fetch 矩阵、verify 四态+指纹、channels 聚合、导入即确认契约（adopt→建册回填 refs→逐套 confirm→幂等重放）；mainline migrate 旧用例遗留 1 失败，随 Phase 6 migrate 退役处置 |
| 基线注 | — | 三个 CLI 测试文件 65 通过 + 1 migrate 遗留失败 + ruff 全绿 |

## Phase 6：文档同步 + 全量门禁 ✅（2026-09-06 完成）

| 项 | 文件 | 内容 |
|---|---|---|
| api.md ④ 组重写 ✅ | `docs/architecture/api.md` | 35 路由口径：④ 组 7 端点新契约（books fetch/import/register、knowledge/{id}/fetch、409 并发防护），删除失效告警块 |
| database-private-tables.md ✅ |（原 database-schema.md，ADR 0007 改名）| 迁移史 0018（无条件 DROP+重建）、original_title DDL、多对多 refs 契约、接口/契约影响重写 |
| code-map.md ✅ | 同名 | book_fetch/resources/downloader/book_advisor 模块登记 + 测试映射（migrate 行删除、0018/验收/顾问/测试行新增） |
| main-line-curriculum.md ✅ | 同名 | §4 CLI 命令表重接（approve/reject 删除、review 确认化、download 经 8901、verify 只读、books fetch/import 双入口）；§2 加历史模型注；design/index、tutorial-naming、system-overview、main-line.md、README 同步 |
| 指南 + trackers ✅ | `docs/guides/operations.md`、`development.md`、`docs/trackers/project-status.md`、`todo.md` | §3.3 书籍取书与登记实操 + QED_BOOK_* 8 键 + 退出码口径；主链路约束改书库化语义；CLI 入口行、QED-050-D Phase 0~6 完成证据登记；AGENTS.md 任务路由行去 migrate_knowledge |
| migrate 退役 ✅ | `src/qed_tracker/cli.py`、`src/qed_tracker/application/migrate_knowledge.py`（删）、`tests/test_migrate_knowledge.py`（删） | CLI migrate 子命令与存量迁移脚本删除，幂等键语义由 adopt_tutorials 承接；AGENTS.md 任务路由行去 migrate_knowledge |
| 门禁 ✅ | — | `tests/test_documentation.py` 8 passed；全量定向测试 + ruff 见下 |

## 验证口径

- 每 Phase 收尾运行其关联测试 + `tests/test_documentation.py`；全量门禁在 Phase 6。
- 默认测试不访问公网（渠道协议 fixture 化）；真实连通性人工冒烟（QED-050-D 成功标准：
  00/01/02 三门课闭环）。
- 不读取/修改真实数据根；迁移在测试库验证。
