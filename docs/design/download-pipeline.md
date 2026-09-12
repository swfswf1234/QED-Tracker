# 下载管线设计（download-pipeline）

设计状态：Accepted
实现状态：Implemented
确认状态：已确认
最后更新：2026-09-11
关联代码：`src/qed_tracker/application/book_fetch.py`（编排母本）、`src/qed_tracker/downloader.py`、`src/qed_tracker/application/resources.py`、`src/qed_tracker/inventory.py`、`src/qed_tracker/catalog.py`（catalog run 与冻结目录）、`src/qed_tracker/matching.py`（严格匹配）、`src/qed_tracker/catalogs/math-qe.json`（math-qe 冻结书单）、`src/qed_tracker/db/knowledge_repository.py`、`src/qed_tracker/providers/books.py`、`src/qed_tracker/providers/book_advisor.py`、`src/qed_tracker/api/main.py`（书籍组端点）、`src/qed_tracker/cli.py`（mainline/books/catalog 命令）
关联测试：`tests/test_book_providers.py`、`tests/test_book_fetch.py`、`tests/test_book_llm_advisor.py`、`tests/test_book_acceptance.py`、`tests/test_book_api.py`、`tests/test_download_inventory.py`、`tests/test_services.py`、`tests/test_config_catalog_matching.py`
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)、[ADR 0003](../adr/0003-pending-design-location.md)、[ADR 0008](../adr/0008-design-doc-scope-reshuffle.md)

> 本文档是**下载全链的唯一设计事实源**：来源协议、math-qe 冻结书单与 catalog 冻结目录链、
> 书级/教程级自动取书五阶段、人工导入、通用下载器与资源登记原语（整合 2026-09-04 用户
> 五阶段流程裁决与书库化后的登记语义；2026-09-07 按 ADR 0008 吸收原
> acquisition-and-inventory 与 tracker-service 书单规格，见变更记录）。
> qt_books/qt_knowledge/qt_sources 表 DDL 与状态机以
> [数据库专用表设计](../architecture/database-private-tables.md)
> 为准，本文档只链接不复制；论文链与 8901 端点契约、8902 Axiom 消费面不在本文档范围
> （见[架构 API](../architecture/api.md)）。
> 实现按下载登记计划完成（QED-050-D 已关闭，见[已完成任务台账](../trackers/completed.md)）；
> schema 落地由 ensure_schema 承担（ADR 0006，无迁移 0018），代码模块与端点签名以
> `src/qed_tracker/application/` 与[架构 API](../architecture/api.md) 为准。

## 背景与问题

2026-09-03 书库化裁决（QED-050-B/C）把 qt_books 重构为「选用四态
（candidate/decided/parallel/retired）+ 持有态（holding=owned/missing）」，下载执行态与
哈希/来源移交 qt_sources 与资源清单，**旧八态下载状态机**及其仓储方法
（decide/retry/complete/reject/supersede 等）随之删除（2026-09-11 QED-060 另立**四态下载
生命周期** downloading/downloaded/verified/failed，与选用四态并存，非旧机恢复）。书库化后
曾出现的半重构中间态（书籍组端点与 mainline 命令调用已删仓储方法、书籍搜索层无 LLM）已由
QED-050-D（2026-09-06）收口：API 35 路由重接、旧八态端点删除（其中 start/fail/verify/cancel
4 个于 QED-060 以新语义恢复）、mainline 命令组重接、TaskManager 并发 409 防护、`mark_owned`
唯一登记入口；LLM 已接入取书链（检索词变体生成 + 候选确认评估，见阶段 1/2）。

2026-09-11 QED-060 裁决：为对齐前端五阶段（待下载/下载中/待验证/已完成/失败），qt_books
**重新引入下载生命周期四态**（downloading/downloaded/verified/failed），与选用四态并存；
`holding` 继续表达持有状态。下载执行事实仍同时落 qt_sources + 资源清单，但状态迁移由
qt_books.status 承载（详见[数据库专用表设计](../architecture/database-private-tables.md)状态机节）。

## 目的与边界

**管**：来源协议（search/resolve/libgen_li 发现专用）、math-qe 冻结书单与 catalog run
冻结目录链（`run_catalog` 严格匹配、不确定候选不自动落盘）、数学课程选书要求、
书级与教程级自动取书五阶段（检索→确认→下载→机器验收→登记）、人工导入、
通用下载器与资源登记原语（资源 JSON/Inventory）、书级完成与课程闭环口径、
失效端点与 mainline 命令的处置方向。

**不管**：论文链（[论文发现设计](paper-discovery.md)）、探索管线
（[探索管线设计](exploration-pipeline.md)）、知识/探索/书籍生命周期状态机契约
（[数据库专用表设计](../architecture/database-private-tables.md) 与
[数据库共享表设计](../architecture/database-shared-tables.md)）、知识录入主体
（[知识录入设计](knowledge-import.md)，本文档只承接其「书籍 PDF 导入」一段）、
服务运行面与配置（[服务管理中心设计](service-management.md)）、8901 端点契约与
8902 Axiom 交付（[架构 API](../architecture/api.md)）。

## 来源协议

教材来源实现 `search(query, limit)`、`resolve(candidate)` 和 `close()`。搜索结果统一为 `Candidate`，包含来源身份、标题、作者、语言、年份、版次、格式、大小、页面 URL、下载 URL、可用性、外部标识和可选摘要。

内置教材来源为 Internet Archive、Open Library、Google Books 和 **libgen_li**。来源可以只返回元数据；只有 `availability=downloadable` 的候选能够进入下载器。单个来源的协议变化不得中断其他来源。

**libgen_li 为「发现专用」来源**（2026-08-07 用户裁决恢复，边界约束见
[来源探索与评估计划](../plans/2026-09-source-discovery.md)）：只搜索与解析书目信息及下载方案（torrent / IPFS CID / ed2k 链接，写入 `Candidate.links`），候选恒为 `availability=metadata_only`，**永不自动写文件**。文件落地必须由人工下载后经登记端点（`POST /resources/{id}/register`）进入资源体系；登记端点执行 PDF 校验、SHA-256 计算与去重，与自动下载同一套通用逻辑。annas_archive / zlib 保持退役（`RETIRED_PROVIDERS`）。

论文只使用 arXiv 客户端，支持关键词、分类、作者、arXiv ID 和 URL。arXiv ID 同时作为外部标识，并用于确定论文保存年份和文件名。

基于研究目标的检索规划与排序属于[论文发现设计](paper-discovery.md)。它复用本文的 arXiv 候选、通用下载和 Inventory，不改变资源 schema。

## math-qe 冻结书单与 catalog 冻结目录链

冻结书单 `math-qe`（`src/qed_tracker/catalogs/math-qe.json`，原 id `math-qe-v2`，QED-013
建立）：以 `dataset/textbooks` 现有索引为蓝本（用户已筛选，覆盖 13 门课程），每门课程两组：
**中文教材组**（优先中文版经典教材中译本）与**对应习题集组**；英文经典原版作对照补充
（en 套）。target 字段：`course_id` / `title` / `authors` / `language(zh|en)` /
`kind(textbook|exercise)` / `edition` / `set_no`（可选，见下）/ `note`（可选）。

catalog run 冻结目录链路（`run_catalog` + `matching.py` 严格匹配）：

- `books get` 无 `--pick` 时只预览教材结果；只有显式提供序号才下载。
- 冻结目录自动下载必须同时满足标题、作者、语言和版次要求；缺少必需元数据视为不严格匹配。
- 目录运行默认只预览。只有显式 `--download` 才允许严格匹配项进入下载流程。
- 目录 target 可选字段 `set_no`（QED-024）：`1`~`4`=中文套 / `en`=英文对照套 / 空=无配套。
  同一课程内 `set_no` 相同的 target 属于同一套（一套须含 ≥1 book 与 ≥1 exercise，配套题解归
  exercise）；前端按「套」显示课程完成判定（套内完成口径见下文「阶段 5：登记与课程闭环」）。
  `GET /api/v1/catalogs/{id}` 响应透出该字段。

LLM 辅助评估（书单筛选，`POST /tasks/catalog/evaluate` 按课程批量）：对每门课程的书目做
结构化补全与候选评分（是否推荐、理由）；**宁缺勿滥**——模型不确定的候选不收录；模型输出只
生成可审阅评估（写 `llm_evaluation` 与 qed_llm_calls 审计），不写资源事实、不自动下载。

## 数学课程选书要求（2026-08-07 用户裁决，01 起执行）

面向全部数学课程（01–13）的教材与习题集采集原则，**贵精不贵多**：

1. **每门数学课程目标 2–4 套教程**。一套教程 = 教材 + 高质量配对的习题集；习题集不要求
   与教材严格一一对应，但必须是高质量配对（经典习题集即可）。
2. **先探索两门经典教程**作为核心；发现额外经典时允许加第三套；有对应的优秀英文版教程
   时**同步下载作为对照**（中英对照阅读）。超出 4 套的部分 **PASS（拒绝）**，避免同课程
   多版本冲突。
3. **翻译版优先**：优先选择经典教材的中文翻译版（便于人工评审与对照阅读）；翻译版不可得
   时按 archive.org 中文扫描件 → 英文原版顺序降级，不因链路困难降低对教材与习题集质量的要求。
4. **项目优先自动拉取**：候选走自动链路（archive 等）能下载即下载；**自动链路拉取不到时，
   提示人工下载并给出下载方案**（来源链接、torrent / IPFS / ed2k 等，见 `Candidate.links`），
   人工下载后经登记端点入资源体系，不阻塞课程闭环。
5. 分类口径：**教材（book）/ 习题集（exercise）**（QED-034 退休 supplement：配套习题答案、
   题解等与教材同源文件归入 exercise，不重复下载为独立习题集）。
6. 每门课程的定稿书单与下载来源记录在冻结书单 `math-qe` 与课程评估报告（evaluate
   任务 result）中，人工评审以 8903 前端为准。

## 已确认裁决（2026-09-04）

以下九项裁决是本设计的不可变更约束，后续实现不得偏离：

1. **确认即自动下载**：LLM verdict=confirmed → 自动下载该候选；uncertain → 留痕换下一
   候选/渠道；渠道用完 → 输出人工下载指引。
2. **机器验收 = 硬门槛 + 文本层软信号**：硬门槛（魔数 + pypdf 可解析 + 非加密 + 页数≥N +
   大小≥M，默认 10 页/200KB，可配置）任一不满足即拒绝换下一候选；文本层可抽取与否只记录
   不拒绝（避免误杀扫描版）。
3. **候选级 300s 预算**：计时起点 t0 = 候选通过确定性预筛、进入「介绍查取→LLM 确认→
   resolve→建流」的时刻（渠道 search 不计入候选预算，由 httpx 超时兜底）；已开始的下载
   允许跑完。
4. **书级 owned 即完成**：单本书完成 = qt_books.holding=owned + file_path 回填 +
   qt_sources 渠道留痕完备；课程闭环 = 课程下 decided 书全部 owned（parallel 不计入），
   派生只读查询，不动 exploration_stage。（2026-09-11 补充：登记同时置
   `status=downloaded`，人工 verify 后 `status=verified`。）
5. **增 original_title 可选列**：qt_books 重建时（模型 + ensure_schema，零成本）加
   nullable original_title；refs 数据契约增可选 original_title 字段（向后兼容）。
6. **mainline CLI 处置**：download 重接新五阶段编排（教程级入口）；verify 改只读复核；
   approve 废弃；channels 保留。
7. **人工导入跳过初筛门槛**：跳过下载与机器验收，但保留完整性校验（魔数+pypdf+sha256，
   用于命名与去重，失败 400 拒绝）；登记具体情况进 qt_sources note。
8. **LLM 角色边界修订**：扩展到书籍检索词变体生成与书籍匹配确认（可审阅评估）；模型仍
   不得直接下载、不得把判断写入资源事实（判断只落 qt_sources 留痕与 qed_llm_calls 审计）。
9. **双取书入口**：书级（单册）+ 教程级（按 qt_knowledge 一套教程批量，先排除已 owned，
   默认仅 decided，parallel 显式参数纳入）；课程级批量属后续扩展。

### 补充裁决（2026-09-11，QED-060）

1. **保留选用四态 + 下载生命周期四态并补齐闭环**：`decided → downloading → downloaded →
   verified`，失败 `→ failed` 可重试（再次 fetch/start）；卡死 `downloading` 可
   `POST /books/{id}/cancel` 复位 `decided`。写状态端点 = `start`/`fail`/`verify`/`cancel`；
   非法迁移由全局 `InvalidTransition` 处理器统一映射 **409 `INVALID_TRANSITION`**。教程级
   批处理遇单本非法状态**不整批中断**（该书失败继续下一本）。
2. **下载落盘统一用书籍真实 `domain_id`**：`raw/<domain_id>/<course_id>/`，
   不得回落默认 `math`；与探索产物（`raw/<domain_id>/...`）同域。
3. **落盘收口口径**（与[探索管线设计](exploration-pipeline.md)对齐）：`mark_owned` 为
   `downloaded` + `holding=owned` 的唯一写入口；import/register 直达 `downloaded`。

### 成品命名规则（唯一事实源）

- **最终成品**：`<slug>_<sha8>.pdf`（`sha8` = sha256 前 8 位，内容指纹确定性 → 同内容必同路径）。
- `slug`：论文 = arXiv ID；教材/习题 = `safe_filename(title).stem`（CJK 保留、空白→`_`、
  非法字符剔除、截断 120）；catalog run 追加 `{target.id}_` 前缀。
- **落盘目录**：自动取书 `raw/<domain_id>/<course_id>/`（refs 反查课程），无归属 →
  `raw/<domain_id>/_general/`；论文 → `raw/<domain_id>/_general/papers/<year>/`；
  人工导入 → 显式 `target_path` 或 `raw/<domain_id>/<course_id>/`。
- **staging**：`tmp/qed-tracker/downloads/<slug>[_<tag>].download`，机器验收通过后
  `os.replace` 进 `raw/`。

## 五阶段流程总览

```
书级 fetch（单册 qt_book）──────────────────────────────────────────────┐
教程级 fetch（qt_knowledge refs 聚合 → 排除已 owned → 默认仅 decided      │
→ 顺序逐书）                                                            │
                                                                        ▼
阶段1 检索    渠道×硬编码 query → 候选去重 ──全部无候选──→ LLM 检索词变体兜底（一次）
  │
  ▼
阶段2 确认    确定性预筛（硬失配跳过）→ 介绍查取（enrich）→ LLM 确认（confirmed/uncertain）
  │                                    │预筛硬失配 / uncertain
  ▼                                    └────→ 换下一候选
阶段3 下载    resolve 直链 → 建流（候选级 300s 预算，首 chunk 释放）→ .part 下载
  │
  ▼
阶段4 机器验收（staging 上）  硬门槛：魔数/可解析/非加密/页数≥N/大小≥M
  │                          文本层软信号只记录；未过门槛文件永不进 raw/
  ▼
阶段5 登记    sha256 去重 → 原子落盘 raw/<domain_id>/<course_id>/
              → qt_books.holding=owned + file_path 回填 + status=downloaded + qt_sources(ok=1) + 资源 JSON
  │
全部耗尽 ──→ qt_books.status=failed（holding 仍 missing）+ qt_tasks failed + 人工下载指引（file_keywords + links）
```

各阶段失败出口与留痕见「事实落点表」节。

## 阶段 1：检索

- **输入**：qt_books 单行（title/original_title/part/authors/publisher/edition/year/language）。
- **渠道遍历顺序** = `QED_SOURCES` 声明顺序（internet_archive → open_library →
  google_books → libgen_li）；删项即禁用，不另设渠道开关。libgen_li 恒 metadata_only，
  只产人工指引候选，永不进入自动下载循环。
- **硬编码检索词规则集**（渠道内命中即止，跨渠道独立执行；出版社/丛书/年份不进检索词，
  只作确认线索）：

| # | 检索词 | 说明 |
|---|---|---|
| ① | `original_title + 第一作者姓` | 有原题时优先；英文原题在 IA/OL/GB 命中率最高 |
| ② | `title + 作者` | authors 中 role=author 的 name，**排除 translator**（译者名污染结果） |
| ③ | `title` | 中文书名；IA 走 CJK 短语查询（`title:"数学分析" AND 陈纪修`） |
| ④ | `title + part` | 分卷书卷名合并检索 |

- **候选去重**：跨渠道按 `(provider, provider_id, title.casefold())` 去重，只留
  DOWNLOADABLE；metadata_only 候选（libgen_li）单独收集为人工指引。
- **LLM 检索词回退 = 书级全局兜底**（不逐渠道触发：检索词质量与渠道无关，逐渠道会把
  LLM 调用量放大渠道数倍）：全部渠道 × 全部硬编码 query 均无可用候选（含渠道级搜索失败）
  后，调 LLM 一次生成 ≤3 条变体（模板 `book-query/variants@v1`，写 qed_llm_calls），变体
  按同样规则重走「渠道×query」循环；LLM 不可用/预算耗尽 → 直接转人工指引，不阻塞。
- **失败分支**：单渠道 search 异常 → 留痕继续下一渠道；零候选 → 触发 LLM 兜底；
  兜底后仍零候选 → 书级失败转人工。

## 阶段 2：确认（两层门）

**第一层：确定性预筛（不耗 LLM）**。构造 BookExpectation
（title/original_title/part/authors/language/publisher/edition/year），复用 matching.py
相似度函数；**硬失配才跳过**：

| 失配项 | 判定 |
|---|---|
| 语言 | 期望语言与候选语言明确冲突（zh 期望命中 en 候选） |
| 标题 | 相似度 < 0.82 |
| 作者 | 候选作者非空且与期望作者全部 < 0.72 |

**元数据缺失不硬拒**（IA 语言/作者字段常缺）——预筛只取 match_candidate 的硬失配子集，
不复用其 strict 判定与 CatalogTarget 语义（冻结目录链路不动）。

**第二层之一：介绍查取（enrich，零新增 HTTP）**。候选介绍来自既有响应的未读字段：

| 渠道 | 方案 |
|---|---|
| internet_archive | search `fl[]` 增 description/publisher；resolve 顺带读 metadata 的 description/publisher/date |
| open_library | search fields 增 publisher/subtitle/first_sentence/number_of_pages_median |
| google_books | 解析 volumeInfo 的 description/publisher/pageCount |
| libgen_li | 回填已解析但丢弃的 Publisher；页数进 Candidate |

**第二层之二：LLM 确认评估**。复用 Bailian 结构化输出模式（坏 JSON 一次修复重试、调用
预算、qed_llm_calls 审计），contract `book-confirm/assess@v1`：输入 = 期望元数据 + 候选
介绍（书名/作者/语言为关键字段，出版社/版本/年份为辅助），输出 verdict ∈
{confirmed, uncertain} + summary。

- verdict=**confirmed** → 自动进入下载（裁决 1）；**uncertain** → qt_sources 留痕
  （verdict+summary 摘要）换下一候选。
- LLM 调用失败/预算耗尽 → 该候选按 uncertain 处理，降级不阻塞后续候选预筛。
- `QED_BOOK_LLM_CONFIRM=false` 时跳过 LLM 层，预筛通过即下载（明示降级风险：匹配精度下降）。

## 阶段 3：下载

- **候选级预算**（`QED_BOOK_CANDIDATE_BUDGET`，默认 300s）：覆盖该候选的「介绍查取→
  LLM 确认→resolve 拿直链→开始稳定下载」；渠道 search 不计入（httpx
  `QED_TIMEOUT_SECONDS` 兜底，失败按渠道失败留痕换下一渠道）。
- **开始稳定下载** = GET 发出、收到 2xx 响应头、首个 chunk 已写入 `.part`——此时预算
  释放，该候选允许继续跑完（传输中断仍按候选失败处理，重试走 `QED_RETRIES` 指数退避）。
  未到释放点即超时 → 候选失败换下一个。
- **孤儿隔离**：沿用 `_timed_download` 模式（ThreadPoolExecutor + 唯一 staging_tag）；
  超时候选的孤儿线程与后续候选不写同名 `.part`，`service.close()` 断连自灭。
- **完整性**：来源声明 md5 校验（IA/libgen identifiers.md5）保留，不一致 → 候选失败 +
  staging 清理。
- resolve 无直链（IA 无公开 PDF、GB 无 downloadLink）→ 候选失败。

## 阶段 4：机器验收（无 LLM）

验收在 **staging（tmp/qed-tracker/downloads）** 上执行，通过后才 os.replace 进 raw/；
**未过门槛的文件停留在 tmp 由下载器清理，永不进入数据根成品区**（对齐「不得隐式删除
用户数据根内 PDF」约束，规避「先落 raw 再删」）。

| 硬门槛（任一不满足即拒绝该候选换下一个） | 说明 |
|---|---|
| 魔数 `%PDF-` | 文件头校验 |
| pypdf 可解析 | strict=False 读取 |
| 非加密 | `PdfReader.is_encrypted` 检查（现有 inspect_pdf 缺此检查，验收门新增） |
| 页数 ≥ N | 默认 10（`QED_BOOK_MIN_PAGES`） |
| 大小 ≥ M | 默认 200KB（`QED_BOOK_MIN_SIZE_BYTES`）；resolve 已知 size 时可预检提前拒绝 |

文本层可抽取与否（pypdf extract_text 字符数）为**软信号**，只记录进 qt_sources.note，
不拒绝（防误杀扫描版）。资源 JSON schema v1 不动。

## 阶段 5：登记与课程闭环

- **书级完成判据**（裁决 4）：`qt_books.holding='owned'` + `file_path` 回填（数据根相对
  路径）+ `status='downloaded'`（2026-09-11 QED-060：下载生命周期由 qt_books 承载，不再
  只靠 holding）+ qt_sources 存在 ≥1 条 ok=1 记录指向最终文件来源。人工 verify 后
  `status='verified'`（`POST /books/{id}/verify`）。
- **落盘**：`raw/<domain_id>/<course_id>/<safe_name>_<sha8>.pdf`（D9 规则：期望路径不含
  sha 后缀，落盘自动补 `_<sha8>`）；**`domain_id` 必须取书籍/课程行的真实领域标识**
  （2026-09-11 裁决：统一 `raw/<domain_id>/<course_id>/`，不得回落默认 `math`）；sha256
  去重命中复用既有记录不重复落盘；资源 JSON `register_candidate` 登记
  （provider/provider_id/page_url/download_url/retrieved_at）。
- **课程闭环口径**：经 qt_knowledge 的 textbook_ref/exercise_ref/parallel_ref 聚合
  book_id（去重）→ 其中 `status=decided` 的书全部满足书级完成。**派生只读查询，不写任何
  表**；`exploration_stage` 不动；candidate/parallel 书不参与判定。
- **下载生命周期写状态端点**（2026-09-11 QED-060 恢复）：`POST /books/{id}/start`
  （decided→downloading）、`/fail`（downloading→failed）、`/verify`（downloaded→verified）、
  `/cancel`（downloading→decided，仅 downloading 可取消）；非法迁移统一 **409
  `INVALID_TRANSITION`**（全局处理器）。课程闭环仍是**查询口径**而非状态迁移（不写任何表）。

## 双入口与教程级批处理

| 入口 | 范围 | 语义 |
|---|---|---|
| 书级 fetch | 单册 qt_book | 完整五阶段；已 owned → no-op |
| 教程级 fetch | qt_knowledge 一套教程 | refs 聚合书集（去重）→ **先排除已 owned** → 默认仅 decided（textbook_ref+exercise_ref），`include_parallel=true` 显式纳入 parallel_ref → 单一后台任务顺序逐书五阶段 |

- 教程级顺序执行：预算逐书独立、日志可读、TaskManager（max_workers=2）下不互相挤占。
- 部分失败不中断：成功的书保持 owned，失败的书汇总进任务结果 + 人工指引。
- 幂等：重跑自动跳过已 owned，只补缺。
- 入口面：书级 = `POST /books/{id}/fetch` + CLI books fetch；教程级 = `POST /knowledge/{id}/fetch`
  + CLI `mainline download` 重接为教程级取书入口。课程闭环查询独立于 fetch 入口存在。

## 人工导入路径

```
自动路径：检索→确认→下载→staging 机器验收（硬门槛）→ os.replace 进 raw ─┐
                                                                      ├→ 汇合点：登记服务
人工路径：用户提供 file_path（可在数据根外）                            │  （唯一写 qt_books.holding/file_path
  → 完整性校验（魔数+pypdf 可解析+sha256，用于命名与去重）              │   与资源 JSON 的入口）
  → target_path（D9：不含 sha 后缀，落盘补 _<sha8>）                   │
    缺省经 qt_knowledge.refs 反查归属课程 → raw/<domain_id>/<course_id>/ ┘
  → tmp/qed-tracker/downloads 暂存 → 原子 os.replace → 跳过初筛门槛
  → qt_sources(channel=local_import, ok=1, note=具体情况：来源说明+跳过初筛标记)
```

- 反查不到归属课程（多教程引用/独立登记）→ 422 要求显式 target_path。
- 完整性校验失败（魔数/不可解析）→ 400 拒绝；不因页数/大小/文本层拒绝人工文件。
- 入口：API `POST /books/{id}/import` 重接线（保留语义）；`POST /books/{id}/register`
  （数据根内已有文件原地登记）共用登记服务；CLI `books import <book_id> <path>` 重接
  （现有命令经 8901 调用该端点）。
- 显式触发，绝不扫描数据根（治理约束）。

## 事实落点表

| 事件 | qt_books | qt_sources | qt_tasks | qed_llm_calls | 资源 JSON | staging |
|---|---|---|---|---|---|---|
| 检索（硬编码） | 不写 | 零候选时 1 条（channel=search, ok=0, note=queries） | progress | 不写 | 不写 | 不产生 |
| LLM 检索词变体 | 不写 | 可选 1 条（channel=search） | — | **1 条**（book-query/variants@v1） | 不写 | 不产生 |
| 确定性预筛 | 不写 | 不逐条（进批次摘要） | — | 不写 | 不写 | 不产生 |
| LLM 确认评估 | 不写 | 1 条/候选（ok=0, note=verdict+summary） | — | **1 条/批**（book-confirm/assess@v1） | 不写 | 不产生 |
| 开始取书 | **status=downloading** | 不写 | progress | 不写 | 不写 | 不产生 |
| resolve/下载失败 | 不写 | 1 条/候选（ok=0, note=原因） | — | 不写 | 不写 | .part 由下载器清理 |
| 下载成功 | **holding=owned + file_path + status=downloaded** | 1 条（ok=1, note=resource_id） | succeeded+result | 不写 | register_candidate | 原子 replace 进 raw |
| 硬门槛拒绝 | 不写 | 1 条（ok=0, note=门槛项+软信号） | — | 不写 | **不登记** | 删除 |
| 人工导入 | **holding=owned + file_path + status=downloaded** | 1 条（channel=local_import, ok=1, note=具体情况） | 可选任务 | 不写 | 登记 | tmp→os.replace |
| 全部耗尽 | **status=failed**（holding 仍 missing） | 1 条（ok=0, note=人工指引摘要） | failed+error=人工指引 | — | 不写 | — |

**「LLM 判断不写入资源事实」的精确含义**：

1. verdict/summary 只落两处——qt_sources.note（人类可读摘要）与 qed_llm_calls（全量审计，
   prompt_template 可审阅）。
2. qt_books.holding/file_path 只由确定性登记服务依据「下载成功+硬门槛通过」或「人工导入+
   完整性校验」写入，LLM 判断不参与任何字段取值。
3. 资源 JSON 的 source/file 字段保持 register_candidate 现有内容，不含任何 LLM 输出；
   软信号 v1 只进 qt_sources.note（后续若结构化再 bump schema_version 并同步契约测试）。

## 通用下载器与资源登记原语

五阶段与人工导入共用的底层原语（原 acquisition-and-inventory 承载，2026-09-07 按 ADR 0008
并入本文档；论文链与 catalog run 同样复用，不改变语义）。

**可靠下载**：所有来源最终只提供候选和 URL，通用下载器统一负责：

1. 使用 `<target>.part` 保存本次未完成内容；每次重试都从头覆盖临时文件，不拼接未知远端版本。
2. 按配置的次数重试网络和文件错误。
3. 校验 `%PDF-` 文件头、可读取的 PDF 结构和至少一页内容。
4. 计算完整内容的 SHA-256、字节数和页数。
5. 只在全部检查通过后用原子替换生成正式文件；最终失败时移除临时文件。

资源服务把下载器已经计算的 SHA-256、大小和页数直接交给 Inventory，不重复解析 PDF。如果相同 SHA-256 已有有效记录，则复用既有记录并移除本次新产生的重复文件。

**资源 schema v1**：资源身份固定为 `sha256:<digest>`。单资源 JSON 写入 `meta/resources/<sha256>.json`，字段如下：

| 字段 | 内容 |
| --- | --- |
| `resource_id`、`schema_version`、`kind`、`created_at` | 稳定身份、schema 版本、资源类型和 UTC 创建时间。`kind` 取值 `book`（教材）/ `exercise`（习题集，含题解与配套答案）/ `paper`。 |
| `title`、`authors`、`language`、`year`、`identifiers` | 规范化书目信息和外部标识。 |
| `source` | 来源名、来源 ID、页面地址、下载地址和获取时间；本地扫描记录为 `provider=local`；libgen 发现候选另含 `links`（下载方案：torrent / IPFS / ed2k）。 |
| `file` | 数据根相对路径、SHA-256、字节数、`application/pdf` 和页数。 |
| `catalog_ref` | 可选的目录 ID、目标 ID 和课程 ID。 |

人工评审备注机制（曾存 MySQL `qt_resources.review_note`，QED-020）已随 QED-030 退役，
评审备注语义由专用表 `notes` 字段承接；单资源 JSON 事实源不包含评审备注。

资源 JSON 使用 UTF-8、稳定键排序和原子替换写入。单资源 JSON 是唯一清单事实源；0.5 不再生成 `manifest.jsonl`，已有文件不会被主动删除。

**已有文件与完整性**：`inventory scan` 递归查找用户明确指定的目录；所有路径必须解析到数据根内部。扫描只登记文件，不移动或删除原件。`inventory verify` 重新检查文件存在性、PDF 结构、SHA-256、大小和页数，并返回 `ok`、`missing`、`invalid` 或 `changed`。

## 失败与重试语义

**耗尽链（单次 fetch 任务内）**：

```
渠道×硬编码 query 检索
  → 预筛硬失配 / LLM uncertain / resolve 失败 / 预算超时 / 传输或 md5 失败
      → 换下一候选 → 本渠道候选耗尽 → 下一渠道（QED_SOURCES 顺序）
  → 全渠道×全硬编码 query 无可用候选 → LLM 检索词变体兜底（一次）→ 重走渠道×变体循环
  → 仍失败 → 书级失败：qt_tasks failed + error=人工下载指引
      （file_keywords + metadata_only 候选 links：torrent/IPFS/ed2k）
```

- **幂等保证**：sha256 身份 + Inventory 去重（同文件复用既有记录）；文件名
  `<safe_name>_<sha8>.pdf` 内容指纹确定性；qt_sources 按尝试追加留痕；已 owned 书重复
  fetch → no-op；教程级重跑自动跳过已完成书。
- **状态复位与重试**（2026-09-11 QED-060）：书级失败置 `status=failed`（holding 仍 missing）；
  重试 = 再次提交 fetch（`failed → downloading`，幂等重放）；卡死的 `downloading` 经
  `POST /books/{id}/cancel` 复位到 `decided`（`cancel` 仅允许 downloading 态）。教程级
  批处理遇单本非法状态**不整批中断**，汇总为该书失败继续下一本。
- **并发防护**：同书仅允许一个活动 fetch 任务（提交前查 qt_tasks 同 params 的
  queued/running → 409；TaskManager 现无去重，实现轮新增）。
- qt_sources.file_keywords 语义 = 人工下载检索关键词（DDL 注释口径）；IA 渠道内部按文件名
  匹配 file_keywords 属 resolve 实现细节，两者不混淆。

**通用失败语义**（承接原 acquisition-and-inventory，适用于全部下载与登记链路）：

- 单个教材来源失败时记录来源名和错误摘要，并继续汇总其他来源。
- 没有候选或没有可下载候选时不创建文件。
- 非 PDF、损坏 PDF 或零页 PDF 永远不能成为正式资源。
- 批处理中的部分失败返回部分失败退出码，并保留已经成功登记的独立资源。
- 真实外部来源连通性不作为默认 CI 门禁；自动测试只使用固定响应和临时目录。

## 与现有链路的边界

**catalog run 冻结目录链路完全不动**：`run_catalog` + `match_candidate`（strict 严格匹配、
不确定候选不自动落盘）保持现状；本设计的预筛/确认逻辑不触碰两模块公开语义。

**books API 端点处置**（QED-050-D 重接 + QED-060 恢复下载生命周期端点，api.md ⑤ 组同步）：

| 端点 | 处置 |
|---|---|
| POST /books | 重接线：书库化创建（book_id 显式、无 knowledge_id） |
| GET/POST /books/{id}/sources | 保留 |
| POST /books/{id}/import | 重接线（人工导入新语义） |
| POST /books/{id}/register | 保留，与 import 共用登记服务 |
| POST /books/{id}/fetch | 重接线：202 + 后台任务跑新五阶段编排 |
| POST /knowledge/{id}/fetch | **新增**：教程级批量取书 |
| POST /books/{id}/start、/fail、/verify、/cancel | **2026-09-11 QED-060 新增**：下载生命周期迁移（decided→downloading→downloaded→verified；failed 可重试；cancel 仅 downloading 复位 decided） |
| decide/retry/complete/reject/supersede | **删除**（旧八态下载机无对应语义） |
| GET /books/search | 保留不动（⑥ 组，无 repo 依赖） |

**mainline CLI 处置**（裁决 6）：

| 命令 | 处置 |
|---|---|
| mainline download | 重接：教程级取书入口（同一五阶段编排） |
| mainline verify | 改只读复核（重算 inspect_pdf 比对 sha/size/pages，复用 Inventory.verify 语义），不做状态迁移 |
| mainline approve | **废弃**（raw/ 已是下载与人工导入共用成品区，「复制移交」语义消失；课程闭环为派生查询） |
| mainline channels | 保留（qt_sources 渠道聚合，修复 list_books 调用） |
| new/review/reject | 属知识录入链，见[知识录入设计](knowledge-import.md)，本文档只声明边界 |

## 配置项清单

| 键 | 默认 | 说明 |
|---|---|---|
| `QED_BOOK_CANDIDATE_BUDGET` | 300.0 | 候选级预算（秒）；**取代** `QED_FETCH_ATTEMPT_TIMEOUT`（600，旧键一版别名后废弃） |
| `QED_BOOK_MIN_PAGES` | 10 | 硬门槛页数下限 |
| `QED_BOOK_MIN_SIZE_BYTES` | 204800 | 硬门槛大小下限 |
| `QED_BOOK_SEARCH_LIMIT` | 8 | 每 query 每渠道候选上限 |
| `QED_BOOK_QUERY_VARIANTS` | 3 | LLM 检索词变体上限 |
| `QED_BOOK_LLM_QUERY` | true | LLM 检索词兜底开关（关闭时零候选直接人工指引） |
| `QED_BOOK_LLM_CONFIRM` | true | LLM 确认开关（关闭时预筛通过即下载，匹配精度下降） |
| `QED_BOOK_LLM_BUDGET` | 8 | 单次 fetch 的 LLM 调用预算 |

复用不动：`QED_SOURCES`（渠道顺序=遍历顺序）、`QED_TIMEOUT_SECONDS`/`QED_RETRIES`/
`QED_PROXY`/`QED_TLS_VERIFY`（默认开，仅显式关）/`QED_DATA_ROOT`、LLM 组
（QED_MODEL/QED_LLM_TIMEOUT/QED_API_SELECT/QED_LLM_GATEWAY_URL）。

## 测试覆盖（默认测试不访问公网）

| 测试面 | 文件 | 手段 |
|---|---|---|
| 渠道协议 fixture | `tests/test_book_providers.py` 扩展 | httpx.MockTransport；description/publisher 解析 fixture（IA metadata/OL search/GB volumes/libgen edition 页） |
| 书籍 LLM 顾问 | `tests/test_book_llm_advisor.py` | 假 LLM：变体生成契约、confirm 评估契约、坏 JSON 一次修复、预算耗尽、模板 ID 守护 |
| 五阶段编排 | `tests/test_book_fetch.py` 改造 | FakeProvider + FakeConfirmAdvisor：渠道顺序、跨渠道去重、候选耗尽换渠道、LLM 兜底时机、verdict 门控 |
| 候选级预算 | 同上 | 注入短预算：超时换候选、已建流跑完、owned no-op |
| 验收规则集 | `tests/test_book_acceptance.py` | pypdf 生成多页/加密/空白页 fixture：全拒绝且不落 raw；空白页软信号不拒绝 |
| 人工导入 | `tests/test_book_api.py` | 数据根外→tmp→原子落盘；D9 补 sha8；无归属 422；完整性失败 400；同 sha 复用 |
| 教程级批处理 | 同上 | refs 聚合、排除 owned、include_parallel、部分失败不中断、重跑补缺 |
| 并发防护 | 同上 | 同书双 fetch 409 |
| catalog 严格匹配与 set_no | `tests/test_config_catalog_matching.py` | 冻结目录严格匹配（缺元数据不严格）、`set_no` 透出、`.env` 来源优先级 |
| 回归 | 既有门禁 | `test_download_inventory.py`/`test_services.py` 通用层不动 |

## 实现状态

实现状态：Implemented——QED-050-D 2026-09-06 Phases 0~6 完成（0018 书库化重建 + original_title、
QED_BOOK_* 8 配置键 + accept_pdf 验收门、LLM 顾问扩展与渠道 enrich、五阶段编排 + mark_owned
登记服务、API 35 路由重接 + 并发 409 防护、CLI mainline/books 重接 + migrate 退役）；
2026-09-07 人工闭环验证（qed_test 库：12 门导入 → 11 套 21 书行 → 17 本 books import owned →
mainline verify 17/17 ok；纯 8901 API 链重放冒烟完成，回执 ARCH-019）。
catalog run 冻结目录链与严格匹配、资源 JSON/Inventory 原语为 QED-013/QED-024 起的既有实现
（`src/qed_tracker/catalog.py`、`src/qed_tracker/matching.py`、`src/qed_tracker/inventory.py`），
本文档 2026-09-07 收编其契约（ADR 0008），行为不变。

原在途收尾项（00/01/02 真实环境闭环）已随 QED-014 验收关闭（2026-09-09，见[完成台账](../trackers/completed.md)）；
定向测试预存在失败修复（L-14，签名对齐）已随 QED-057 修复（2026-09-11），遗留清单归档于
[历史基线](../history/baselines/2026-09-doc-cleanup-leftovers.md)。

2026-09-11 QED-060 更新：选用四态 + 下载生命周期四态 + cancel/retry 闭环、教程级批处理不中断、
落盘统一真实 `domain_id`、成品命名规则入文；实现轮由
[完成台账](../trackers/completed.md)（QED-060）承接。实现轮已完成（2026-09-11），全量测试通过。

## 关联文档

| 文档 | 关系 |
|---|---|
| [知识录入设计](knowledge-import.md) | 上游：qt_books 行与 refs 的产生；书籍 PDF 导入另一入口 |
| [数据库专用表设计](../architecture/database-private-tables.md) | qt_books/qt_sources DDL、状态机、Schema 自愈（唯一事实源）；三条生命周期状态机以该文档与本文档为准（原数据生命周期计划 2026-09-09 随 QED-050-E 关闭删除） |
| [架构 API](../architecture/api.md) | 端点契约（④ 组重接线后同步）；8902 Axiom 交付消费面 |
| [来源探索与评估计划](../plans/2026-09-source-discovery.md) | 渠道评估矩阵与持续探索工作（2026-09-07 自 design/ 移入 plans，ADR 0008） |
| [服务管理中心设计](service-management.md) | 下载链运行面（服务启停、`.env` 与模型模式） |
| [下载与清单设计（已归档）](../history/baselines/2026-07-acquisition-and-inventory.md) | 已并入本文档（2026-09-07，ADR 0008）：来源协议、选书要求、通用下载器与资源登记原语 |
| [服务与外部接口设计（已归档）](../history/baselines/2026-08-tracker-service.md) | 已拆散退役（2026-09-07，ADR 0008）：math-qe 书单规格迁入本文档 |

## 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-09-11 | QED-060 补充裁决与命名规则 | 选用四态 + 下载生命周期四态（downloading/downloaded/verified/failed）与 start/fail/verify/cancel 闭环、教程级批处理不中断、落盘统一真实 `domain_id`、成品命名规则唯一事实源；事实落点表与状态机同步 |
| 2026-09-07 | 改名 download-pipeline + 吸收合并（ADR 0008） | 自 book-download-registration.md 改名；并入 acquisition-and-inventory.md（来源协议/选书要求/通用下载器与资源登记原语/通用失败语义）与 tracker-service.md 的 math-qe 书单规格（id 修正为 math-qe）；catalog 冻结目录链纳入本文档职责 |
| 2026-09-07 | 确认状态转正 + 实现状态 Implemented | QED-050-D Phases 0~6 完成与人工闭环验证；设计文档域重整轮（头部实现状态、关联测试、背景与实现状态节按收口事实更新） |
| 2026-09-04 | 用户确认设计，自 plans 晋升（ADR 0003 路径） | 设计状态 Accepted，确认状态暂定 |
| 2026-09-04 | 整体重写 | 书库化后五阶段下载链设计（用户 2026-09-04 九项裁决）；2026-09-01 版基于旧八态下载机契约，整体作废 |
| 2026-09-01 | 初始创建 | 从 acquisition-and-inventory + download-flow + knowledge-dual-flow 整合 |
