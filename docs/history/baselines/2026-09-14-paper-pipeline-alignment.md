# 论文探索与下载链路整合（paper-pipeline-alignment）

状态：已关闭（2026-10-15 收尾轮）
任务类型：Plan
最后更新：2026-10-15
需求方：用户
目标项目：QED-Tracker
评审方：用户
关联设计：[论文发现设计](../../design/paper-discovery.md)、[探索管线设计](../../design/exploration-pipeline.md)、[下载管线设计](../../design/download-pipeline.md)
关联调研：[DeepTutor 机制调研](2026-09-21-deeptutor-survey.md)（借鉴点 #1/#2/#9/#3/#5 已消化进本计划）
关联 Tracker：QED-068
排期裁决（2026-09-29）：068-2 后置于 QED-072 W-3~W-5，已裁并采纳；执行序列见「小步快跑执行序列」节；同日 D-7 裁决的**论文项已由 QED-074（LLM 双链路口径与 prompt 资产台账，2026-09-29 立项） W-2 改判作废**：`paper-plan` 两条内联 prompt 不再删除，改为**迁入注册表并在册改写 `plan@v2`/`assess@v2`**（W-8 步骤 4 落地当日回退），`papers recommend` 不再有模型面空窗；QED-074 W-2 已于 2026-09-30 交付（paper-plan 两条入册、`@v1` 保持；S3 的在册改写由此解锁）；**2026-09-30 Q74-b 裁决**：迁入注册表阶段保持 `plan@v1`/`assess@v1`（零文本改动、留痕连续），`@v2` 升代只发生在 068-S3 的在册改写
归档判定：待关闭时按 [ADR 0009](../../history/adr/0009-closed-plan-archival.md) 做 Retain/Delete 两态判定
需求裁决（2026-09-30，QED-Engine 根用户）：论文链路并入本计划「领域/课程 scope 化 + 书本化采纳」扩展——展示行数据来源回归 `qt_books` kind=paper（改判 QED-071 D2/D14 发现论文不进库口径）、课程级落盘=逻辑分组（物理维持领域级 `raw/<domain>/_general/papers/`）、对方不另开承接 ID；同日入口收敛裁决：论文探索仅领域级发起，pick 评审时逐条落位领域或课程；正文见「根侧需求扩展」节，根侧承载=其 REQ-101（请求）/REQ-102（消费面实现）两壳
链路复审裁决（2026-09-30，同裁决人）：全链复审后执行序列改**精简三步 A~D**——068-5 与
068-6a/6b/6c 合并为 B 步一次定稿（`paper_download` 直写端点不再实现，pick 只走 adopt 建书行
+ 复用书本下载链）、`qt_books` 加列与 books 枚举端点前置为 A 步、CLI 报告不落库缺陷并入 A 步修；
正本见「链路复审与执行序列精简」节

## 目标与成功标准

参照 DeepTutor 调研稿中已核实的确定性机制（arXiv 检索参数、查询收窄与 fallback、下载安全件），
形成贴合本仓的详细整合方案（子任务 QED-068-1~5）+ 总体性优化收口（068-4）。
**方案已评审（2026-09-21 细化 + 同日裁决），2026-09-29 起按「小步快跑执行序列」实施。**

成功标准：每个子任务的改动面、契约字段、失败语义、测试用例清单与验收命令可逐条执行；
「模型不写资源事实」「不自动下载」「默认测试零网络」「TLS 默认开启」边界保持不变。

## 用户裁决记录（2026-09-21 / 2026-09-24）

1. **fallback 语义接受**：`plan` 阶段模型调用最终失败时不再让整个 recommend 直接 failed，
   改走确定性兜底计划并在报告显式标注 `plan_source: "fallback"`（非静默降级）。
2. **`years_limit` 默认 3**：论文时效性强，recommend 缺省只看近 3 年（**行为变化**，
   现行为=不限年份；见「行为变化登记」）。
3. **v1.0 交付口径（2026-09-24，链条评审轮）**：本计划 068-1~5 **全量交付并收口**是 v1.0
   三主线口径中主线②的交付定义（B-1~B-5 全部落设计文档）；批次归属见
   [v1.0 任务链条梳理](2026-09-24-v1-task-chain.md)。
4. **S2 开工两裁决（2026-09-30，链路复审轮）**：① **arXiv ID 尾部 `v\d+` 剥离并入 S2**——
   复审发现 `providers/arxiv.py::_candidate` 取 `entry_id` 末段不剥版本（`2401.12345v1` 原样入库），
   跨版本去重/`excluded_existing`/068-6b「同 arXiv ID 二次 pick 命中查重」均会失效；
   口径=只剥尾部版本号（修正 DeepTutor `split("v")[0]` 误伤老式含 v ID 的缺陷）。
   ② **`plan_coverage` 持久化落点=折进 `search_plan` JSON**——每组计划条目落盘时携带
   `plan_index/fetched/kept`，读侧 `SelectionStore.load` 重建顶层 `plan_coverage` 数组；
   维持「不改 `qt_selections` 结构」边界（B-4），因新列会触发 `db/schema.py` 私有表
   DROP+CREATE 漂移（需先 ALTER 红线，且有丢历史报告与去重索引源风险）。
5. **S3 模板升代范围（2026-09-30）**：**只有 `paper-plan/plan` 升 `@v2`**（在册改写承载提示纪律）；
   `assess` 本轮零文案/契约改动、**不升代**（保持 `assess@v1`）——068-2 第 5 条与 Q74-b 裁决中的
   「assess@v2」表述作废，理由：注册表惯例「修改文案或契约 = version+1」，无改动升代违反惯例且
   切断 `qed_llm_calls` 按模板回读的留痕连续；未来 assess 有实质改动时按惯例升代。

## 现状（论文链路）

- 检索：`src/qed_tracker/providers/arxiv.py`（官方 `arxiv` 库；`page_size=100,
  delay_seconds=3, num_retries=3`；**排序硬编码 SubmittedDate 降序**，无相关度排序、
  无过量抓取、无年份窗口）。
- LLM 顾问：`src/qed_tracker/providers/bailian.py`（`plan@v1` ≤4 组检索计划、
  `assess@v1` 分批 10 条评分；严格 JSON + 一次修复调用；调用预算 6）。
- 服务：`src/qed_tracker/application/papers.py`（`recommend` = 计划 → `search_terms` 逐组检索
  （per-query 失败记 `search_failures`）→ ID 去重 → 排除 Inventory 已有 → ≤40 候选 → 评分
  50/30/20 → 阈值 70 → 报告 `status=ranked`；`download_selection` = 固定报告 + 一基序号显式下载）。
- 存储：`src/qed_tracker/db/selection_repository.py`（`qt_selections` 报告表，schema v1）。
- 入口：CLI `papers search/get/recommend/profiles/selections list|show|download`；
  8901 现**仅有** `GET /api/v1/papers/search` 即时端点，recommend/download 无任务化端点。
- 下载器：`src/qed_tracker/downloader.py`（httpx `follow_redirects=True` 自动重定向、
  流式写盘但**无字节硬顶**、无 SSRF 主机校验；`inspect_pdf` 已算 sha256）。

## 现状（教程探索链路，整合参照）

- 编排：`src/qed_tracker/prompt_lab/pipeline.py` + `templates.py`（domain@v4 / courses@v8 / tutorials@v2）。
- 状态机：`qed_domain`/`qed_course` 的 `exploration_stage` + `explore_pending`。
- 交互：dry-run（不写表，仅 `qed_llm_calls` 审计）→ 人工确认 → 采纳落库；
  入口为 8901 后台任务（202 + 轮询）+ CLI HTTP 客户端。

## 差异对照

| 维度 | 教程探索链路 | 论文链路 |
| --- | --- | --- |
| 管线编排 | `prompt_lab` 模板化（版本化模板 id） | `bailian.py` 内联 prompt（仅 template_id 记账） |
| 状态机 | `exploration_stage` 多态 + 人工采纳 | 报告快照 `status`（planning→ranked→downloaded/failed） |
| 落盘 | `domains.json`/`tutorials.json` 知识正本 | `qt_selections` 报告 |
| 下载 | 五阶段取书 + 通用登记 | 固定报告序号显式下载 |
| 审计 | `qed_llm_calls` + `qt_sources` | `qed_llm_calls` + `qt_selections` |
| 入口 | 8901 后台任务 + dry-run + CLI | CLI 直调 + 仅一条即时查询端点 |

dry-run→确认→采纳的**语义**论文链路已同构存在（recommend 不写资源事实、download 必须引用
固定报告 + 显式 pick），差异在**入口形态与编排治理**，不引入 `exploration_stage` 状态机。

## DeepTutor 论文下载链路深读（2026-09-29 复核，逐文件佐证）

调研稿 I 部分的全链路重读，四环各自落点：

1. **检索参数环**（`tools/paper_search_tool.py`）：`sort_by` relevance/date（L67~70）；
   过量抓取 `fetch_count = min(max_results*2, 30)` 先抓后截（L72、L137~138）；
   `years_limit` 默认 3 按发表年过滤（L39、L116~118）；429 单退避重试、其余异常吞成空列表
   （L94~110，不照搬——本仓要求失败可见）；`arxiv_id` 用 `split("v")[0]` 剥版本，对含 `v`
   的老式 ID（`math/0501001v1`）有隐患（L119~121）。
   → **落点：068-1 全部承接**（排序/过量/年份窗口的参数形状即 068-1 节所设）。
2. **查询计划环**（`tools/knowledge_frontier.py` + `prompting/hints/en/paper_search.yaml`）：
   LLM 出 `{"queries":[...]}` → 正则抠首个 JSON 数组（L157~169）→ 确定性清洗 `_clean_queries`
   （单行化、≤200 字符、≥2 词、大小写去重、截 3 条，L188~198）→ 失败走 seed fallback
   （`[seed, recent advances seed, open challenges seed]`，L172~185）；逐查询执行打
   `source_query` 溯源、按 `(arxiv_id, title)` 小写去重（L218~236）；产出只读报告，
   页脚声明「推荐 ≠ 入库内容」（L302~308）。提示纪律：≤3 英文词、禁整句、
   0 结果不得反复改写（paper_search.yaml L3~4）。
   → **落点：068-2 + 068-3**（清洗与 fallback 已吸收进 068-2；`source_query` 溯源对应
   068-3 `plan_index`/`plan_coverage`；本仓 `providers/arxiv.py` 的 `search_terms`
   已部分实现确定性清洗，068-2 把纪律与清洗口径补全）。
3. **e-print 源码下载环**（`tools/tex_downloader.py`）：`https://arxiv.org/e-print/{id}`
   直 `requests.get` 写 workspace（L79~92）——**绕过其自身 ingestion 链**（`queue_url` 只分
   WEB/YOUTUBE/BILIBILI 三类，L177~199）；无哈希/大小上限/限速（反面）；TarSlip 检查用
   `os.path.commonprefix` 字符串级比较（L161~165，有缺陷），zip 分支无路径防护（L177~180）；
   可借鉴：tar→zip→单 tex 容器嗅探顺序（L98~104）与主 tex 三级启发（L182~215）。
   → **落点：不照搬、存档观察**（现产品形态为论文 PDF，无 TeX 源码消费需求；且其直写通道
   违反本仓「来源适配器只给 URL，写入必须走通用下载服务」约束——复刻时绝不引入）。
4. **摄取状态机环**（`reading/ingestion.py`）：URL 归一→sha 前置判重（抓取前判重）、
   QUEUED→PROCESSING→DONE/FAILED、依赖注入全可注桩——调研稿 §3 已盘点，论文链不直连此环。
   → **落点：068-4 逐跳复检与字节硬顶的参照 + QED-069 评估面（调研稿 #3/#4/#7 待裁项）**。

**复刻结论**：DeepTutor 论文「下载」= 查询计划 + 过量检索 + e-print 直写三段；前两段以
068-1/2/3 吸收，第三段为本仓约束的反面样本。我们的复刻形态 = `recommend → selections
报告 → 显式 pick 走通用下载器`，把检索参数与计划纪律向 DeepTutor 对齐、把下载安全件
（逐跳复检/字节硬顶，068-4）向其 web_fetch 环对齐，落盘坚持走 `ResourceService` 统一管线。


## 行为变化登记

| 变化 | 现状 | 目标 | 影响面 |
| --- | --- | --- | --- |
| B-1 recommend 排序 | SubmittedDate 降序 | relevance 降序（`papers search` CLI 仍默认 date） | 候选池构成变化，评分/阈值不变 |
| B-2 年份窗口 | 不限 | 默认近 3 年（`years_limit` 可覆盖，0=不限） | 老论文需显式放宽；档案可固化 |
| B-3 plan 失败语义 | 整个 recommend failed | 确定性兜底计划 + `plan_source=fallback` | 报告新增字段；失败仍可见可审计 |
| B-4 报告 schema | v1 | v2（增量字段，v1 可读可下载） | 无表结构改动 |
| B-5 入口 | recommend/download 仅 CLI 直调 | 8901 后台任务化 + CLI 转 HTTP 客户端 | CLI 使用方式对齐 QED-010 模式 |

## QED-068-1 arXiv 检索参数对齐

**改动文件**：`src/qed_tracker/providers/arxiv.py`、`src/qed_tracker/application/papers.py`、
`src/qed_tracker/models.py`（`PaperProfile`）、CLI/API 参数透传。

1. `ArxivProvider._run_search(query, limit, *, sort_by="relevance")`；
   `search()` / `search_terms()` 增加 `sort_by` 参数，**默认 `"date"`**（CLI 现行为不变）；
   `PaperService.recommend` 内部调用 `search_terms(..., sort_by="relevance")`。
2. 过量抓取：`search_terms(..., limit, overfetch: bool = False)`——`overfetch=True` 时
   实际抓取 `min(limit * 2, 30)` 条，由调用方（recommend）做年份过滤与既有的
   去重/排除已有后，**每组截断回 limit 条**再合并；`overfetch=False` 行为不变。
3. 年份窗口：`recommend(..., years_limit: int | None = None)`；解析序
   `显式参数 > profile.years_limit > DEFAULT_YEARS_LIMIT = 3`；`0` = 不限。
   过滤口径：`published_at >= today - years_limit*365 天`（UTC；`today` 经
   `PaperService` 可注入参数提供，测试确定性）。非法值（<0 或非 int）→ `ValueError`（HTTP 422）。
4. `PaperProfile` 增加可选字段 `years_limit: int | None = None`（dataclass 默认值，
   旧档案 JSON 加载不受影响）；内置两档案不预置（走全局默认 3）。
5. CLI `papers recommend` 增 `--years-limit`（默认空=按解析序）；068-5 的任务请求体含同名字段。
6. 保留：官方库 delay/retries、per-query `search_failures` 记账、全部检索失败显式抛错
   （**不采纳** DeepTutor 吞错返空，调研稿 §6-5）；重排键不变（分数降序、发布日降序、ID 升序）。

**测试用例清单**（`tests/test_arxiv_provider.py`、`tests/test_paper_application.py`，零网络）：

- `test_search_terms_sort_by_relevance` / `..._date_default`：查询对象 sort 参数断言。
- `test_overfetch_caps_at_30`、`test_overfetch_truncates_per_group`。
- `test_years_limit_default_3_filters_old_paper`、`test_years_limit_zero_means_unlimited`、
  `test_years_limit_profile_override`、`test_years_filter_boundary_injected_today`。
- 回归：现有 search/recommend 全部用例保持绿（date 默认路径不变）。

**验收**：定向两测试文件全绿 + 全量门禁；真实冒烟一次（记录 query/排序/年份窗口与耗时）。

## QED-068-2 查询纪律与确定性 fallback（plan@v2）

**改动文件**：`src/qed_tracker/prompt_lab/templates.py` 家族（`paper-plan/plan@v2` 经 QED-074 W-2 迁入后在册改写；`assess` 按 2026-09-30 裁决**不升代**）、
`src/qed_tracker/application/papers.py`（fallback 编排）、顾问类本体（形态随 QED-074 W-2 改判：
`BailianPaperAdvisor` **不删除**，文案迁入注册表后该类改走 `get_template`）。

1. **提示纪律**（plan prompt v2 文本，来源调研稿 §1.3）：每个 term 为 1~3 个英文词、
   禁整句、禁堆叠名词短语；一次成型——不得为「结果太少」重写计划（重写=用户显式重新 recommend）。
   注：不采纳 DeepTutor「≥2 词」硬规则（数学术语如 "PDE" 单词合法），清洗只做格式归一。
2. **确定性清洗**（`bailian.py` validate 前）：term 去引号/折叠空白、单条 ≤200 字符、
   组内大小写不敏感去重；清洗后为空组/超 4 组/越界分类 → 仍按现契约失败（进修复调用路径），
   **不做静默丢条**（保持审计严格性）。
3. **fallback 触发**：`advisor.plan` 抛 `BailianError`（含修复后仍失败）时，
   `recommend` 捕获并生成兜底计划：seed = `goal` 非否则 `profile.topics[0]`
   （单行化、≤120 字符；两者皆空 → 原异常上抛，`status=failed` 不变）。
   兜底 ≤3 项：`[seed]`、`[recent advances <seed>]`、`[open challenges <seed>]`，
   category 取 `profile.allowed_categories[0]`，reason 固定 `"deterministic fallback"`。
   兜底计划仍过 `_validate_searches`（防御自身）。
4. **审计字段**：报告新增 `plan_source: "llm" | "fallback"`；fallback 时
   `search_plan` 记录的是实际执行的兜底计划；`model` 段保留失败摘要（现有 metadata 机制）。
   预算口径：失败的 plan+repair 消耗照记；fallback 不再新增调用。
5. **模板注册（2026-09-29 QED-074 W-2 改判 + 2026-09-30 范围裁决）**：注册表**在册改写
   `paper-plan/plan@v2`**（v1 文案已在册，直接升代）；**`assess` 不升代、保持 `assess@v1`**
   （见「用户裁决记录」第 5 条）。`plan@v2` 改写文本按本节纪律条目，
   `validate_for` 工厂承载 `allowed_categories` 白名单与
   期望 ID 全集校验（QED-072 W-8 目标形态 1）。
6. 运行参数（`max_tokens` 等）引用 QED-072 预算表定稿，不在本计划写死（见「QED-072 接口轮与排期口径」）。

**测试用例清单**（`tests/test_bailian_advisor.py`、`tests/test_paper_application.py`，
假顾问 / `httpx.MockTransport`）：

- `test_plan_prompt_contains_term_discipline`（捕获 messages 断言）。
- `test_clean_terms_dedupes_case_insensitive`、`test_empty_group_after_clean_fails_contract`。
- `test_fallback_plan_on_bailian_error`（报告 ranked + `plan_source=fallback`）。
- `test_fallback_without_seed_reraises`（`status=failed`）。
- `test_plan_template_id_v2_registered`（templates 注册表 + 版本拒绝规则）。

**验收**：定向全绿；`qed_llm_calls.prompt_template` 冒烟可见 `paper-plan/plan@v2`。

## QED-068-3 报告溯源与覆盖核对（schema v2）

**改动文件**：`src/qed_tracker/application/papers.py`、`src/qed_tracker/db/selection_repository.py`（读侧版本断言 + `plan_coverage` 重建）、`src/qed_tracker/providers/arxiv.py`（ID 规范化，并入项）。

1. 候选条目增 `plan_index: int`（1 基，来自计划第几组；fallback 组同样适用）。
2. 报告增 `plan_coverage`：`[{"plan_index": 1, "terms": [...], "category": "...",
   "fetched": n, "kept": m}]`——`fetched`=该组抓取条数（含后被过滤），`kept`=去重/排除已有/
   年份窗口后实际入池数；`kept=0` 的组是人工审阅的显式信号。**持久化落点（2026-09-30 裁决）**：
   `fetched/kept` 折进 `search_plan` 各条目落盘（JSON 列，零表结构改动），
   `load` 侧由 `search_plan` 重建顶层 `plan_coverage`。
3. `schema_version: 2`；`SelectionStore.load` 接受 `{1, 2}`（其余版本抛
   `SelectionStoreError`），v1 报告无新字段不报错，
   `download_selection` 仅依赖 `recommendations`/`assessments.rank`，v1 可正常下载。
4. 报告页脚口径显式化（设计文档层）：推荐是建议、不是入库事实；下载必须显式 pick。
5. **arXiv ID 规范化（2026-09-30 裁决并入）**：`providers/arxiv.py::_candidate` 对
   `entry_id` 末段只剥尾部 `v\d+`（`2401.12345v1`→`2401.12345`；`math/0501001v1`→`0501001`；
   无版本尾巴的 ID 不动），使跨版本去重、`excluded_existing` 与 068-6b 查重口径统一为
   无版本 ID；`page_url`/`download_url` 保持原样。

**测试用例清单**（`tests/test_paper_application.py`）：

- `test_plan_coverage_counts_fetched_and_kept`（含 0 命中组）。
- `test_candidate_entry_has_plan_index`。
- `test_v1_report_still_downloadable`（构造 v1 载荷回归）。
- `test_load_rejects_unknown_schema_version`。
- `tests/test_arxiv_provider.py`：`test_candidate_strips_trailing_version`、
  `test_candidate_id_without_version_unchanged`（并入项）。

**验收**：定向全绿；报告示例 JSON 贴入设计文档 v2 契约节（068-4）。

## QED-068-5 8901 后台任务化

**改动文件**：`src/qed_tracker/api/main.py`、task handlers（`application/` 或现有 handlers 模块）、
`src/qed_tracker/cli.py`（papers recommend / selections download 转 HTTP 客户端）。

1. 新任务 `paper_recommend`：`POST /api/v1/papers/recommend`，body
   `{"profile_id"?: str, "profile"?: object, "goal": str, "categories": [], "limit": 10,
   "top": 10, "years_limit": null}` → 202 `{"task_id": ...}`；
   任务 result 摘要 `{selection_id, status, plan_source, recommended_count}`，
   完整报告仍走 selections 端点。校验（档案/分类/参数）在**提交时**执行，非法即 422，不建任务。
2. 新任务 `paper_download`：`POST /api/v1/papers/selections/{selection_id}/download`，
   body `{"picks": [1,3]}`；报告不存在 404；`picks` 非该报告推荐序号 → 409
   （口径同 `INVALID_TRANSITION` handler）；报告 `status=failed` → 409。
3. 即时端点：`GET /api/v1/papers/selections`、`GET /api/v1/papers/selections/{id}`。
4. dedup：同 `profile+goal+years_limit` 哈希存在 running/queued 的 `paper_recommend` 任务时
   返回既有 task_id（复用 `TaskManager` 幂等；orphaned 恢复由 QED-066 机制兜底）。
5. CLI：`papers recommend` / `papers selections download` 转 HTTP 客户端（QED-010 同型，
   提交+轮询+打印）；`papers search/get/profiles` 维持现状；无服务端时给出明确错误。
6. 边界：任务 handler 只调 `PaperService` 既有用例，不新增自动下载路径；
   真实 arXiv/模型访问只发生在任务执行期。

**测试用例清单**（新文件 `tests/test_paper_api.py`，`httpx.ASGITransport` + 假 provider/advisor）：

- `test_recommend_202_poll_result_shape`、`test_recommend_invalid_profile_422`。
- `test_download_bad_pick_409`、`test_download_failed_report_409`、`test_selection_get_roundtrip`。
- `test_dedup_returns_existing_task`。
- CLI 契约：`test_paper_selection_cli` 回归改写为 HTTP 路径（假 transport）。

**验收**：定向全绿 + `api.md` 路由数同步（068-4）；真实 8901 冒烟（recommend→show→download 一单）。

## QED-068-4 总体性优化（收口轮，最后执行）

1. **下载器安全件**（`src/qed_tracker/downloader.py`，papers/books 共用；调研稿 §2.2）：
   - 手动逐跳重定向（≤5 跳）：httpx 客户端改 `follow_redirects=False`，每跳在连接前做
     主机校验——解析出的**每个** IP 属 private/loopback/link-local/multicast/reserved/
     unspecified 即拒（DNS 失败 fail-closed）；`file://` 等异 scheme 拒绝。
     `tls_verify=False` 显式配置口径不变。
   - 字节硬顶：流式写盘超 `max_bytes`（Settings 新增键，默认值 ≥ 书籍合法 PDF 上限，
     实施时按现库最大文件定，避免误伤）中断并删 partial。
   - 错误文案含「跳数/主机/上限」要素，落 `qt_sources`/task error 可诊断。
   - 注意：白名单内网代理场景（如有）由显式配置放行，默认拒绝——实施前在 069 渠道评估中核对
     现有可用渠道是否存在合法重定向到内网的用例。
2. **重复检测双报**（`application/resources.py` / 提交面）：查重响应区分
   `same_content`（sha256 命中→幂等返回既有记录）与 `same_name`（标题命中而哈希不同→
   返回冲突清单交人工裁决，不自动覆盖）；papers 的 `excluded_existing` 按同口径呈现。
3. **截断故障观察项**：reasoning effort 降级重试登记于 QED-070 台账观察列表，
   待 QED-067-1 确认 8900 网关透传参数后评估，不在本计划实施。
4. **文档收口**：[论文发现设计](../../design/paper-discovery.md)「检索与评分」节改写为 v2 口径
   （排序/过量抓取/年份窗口/纪律/fallback/coverage/溯源 + 报告示例）；
   [API 设计文档](../../architecture/api.md) 增补 papers 三端点两任务；
   `code-map.md` 行同步；[下载管线设计](../../design/download-pipeline.md) 登记逐跳复检与硬顶。

**测试用例清单**（`tests/test_downloader.py` 等）：

- `test_redirect_to_private_host_blocked`（MockTransport 逐跳 fixture）、
  `test_redirect_chain_within_limit`、`test_max_bytes_aborts_and_cleans_partial`。
- `test_same_name_conflict_reported`（不自动覆盖）。
- `test_documentation.py` 全绿（文档收口后）。

## 小步快跑执行序列（2026-09-29 定稿）

复刻目标口径：DeepTutor 论文链取其**确定性零件**（检索参数、查询纪律与 fallback、溯源与
coverage），落盘坚持走本仓 `ResourceService` 统一管线；其 e-print 直写环为反面样本，不引入。
交付终态 = 068-1~5 全量收口 + B-1~B-5 落设计文档。

| 步 | 内容 | 子任务 | 提交点 | 状态（2026-09-29） |
| --- | --- | --- | --- | --- |
| S1a | `arxiv.py` 增 `sort_by`/`overfetch` 参数（默认 `date`，CLI 行为不变） | 068-1 | 单一提交 | **已交付**（定向 12 passed + ruff clean） |
| S1b | `recommend` 接线 relevance+overfetch、每组截回 limit；`years_limit` 解析序（显式 > profile > 3）+ 窗口过滤；`PaperProfile.years_limit`；CLI `--years-limit` | 068-1 | 收口 068-1（B-1/B-2 生效） | **已交付（2026-09-29）** |
| S2 | 报告 schema v2：`plan_index` + `plan_coverage`（fetched/kept，0 命中组显式）+ v1 可读可下载；并入 arXiv ID 尾部版本剥离（2026-09-30 裁决） | 068-3 | 无模型依赖 | **已交付（2026-09-30，定向 32 passed + ruff clean；全量 565 passed/1 skipped/1 failed=并行 WIP 归因）** |
| G1 | **QED-072 闸门**：W-3~W-5（书籍/主线契约、窗口边界、预算表定稿）+ W-8（prompt 注册表收口；论文两条改由 QED-074 W-2 迁入注册表，「删论文模型面」裁决作废）收口 | 072 | — | 外部前置 |
| S3 | `plan@v2` 在册改写（提示纪律；**assess 不升代**，2026-09-30 裁决）+ 确定性清洗 + seed fallback + `plan_source`（B-3） | 068-2 | 依赖 G1；**无 `papers recommend` 模型面空窗**（Q72-f 已作废） | **已交付（2026-09-30；真实冒烟待用户窗口）** |
| S4 | 8901 任务化 `paper_recommend`/`paper_download` + selections 即时端点 + CLI 转 HTTP（B-5） | 068-5 | 依赖 S1~S3 签名 | 待做（**2026-09-30 复审改判**：与 068-6a/6b/6c 合并为 B 步、`paper_download` 直写端点不再实现，见「链路复审与执行序列精简」节） |
| S5 | downloader 逐跳复检 + 字节硬顶、重复双报、四份文档收口（B-1~B-5 落文档） | 068-4 | 最后 | 待做（=精简序列 C 步，内容不变） |

主线①（QED-072/073）与主线②并行：S1/S2 不依赖本地 9B，可先行；S3 之后必须由 G1 解锁。

**S1 交付记录（2026-09-29）**：B-1/B-2 已在代码生效，并同步[论文发现设计](../../design/paper-discovery.md)
「检索与评分」与档案/报告字段节（完整 v2 契约叙述仍归 068-4 收口轮）。实现中的两处偏离登记：
① 过量抓取的**截断点由 provider 移到调用方**（S1a 曾在 provider 内截断，会使年份过滤只剩
`limit` 条、过量抓取失效；provider 现返回整池，`recommend` 在去重+年份过滤后按组截回
`limit`）；② **发布日缺失或不可解析的候选保留**（不采纳 DeepTutor 按发表年直接过滤的口径，
避免元数据缺失被窗口静默吞掉；与既有「无日期排末」用例一致）。全量门禁
`pytest tests -q` = 552 passed + 1 skipped + 1 failed（唯一红为并行 WIP，见下）。

**S2 交付记录（2026-09-30）**：B-4 生效——新报告默认 `schema_version=2`；候选与评分条目带
`plan_index`（1 基）；报告带顶层 `plan_coverage`（每组 `fetched/kept`，检索失败组记
`fetched=0/kept=0` 且 `search_failures` 照记）。按裁决落地：`plan_coverage` 不占独立列，
`fetched/kept/plan_index` 折进 `search_plan` 条目落盘（零表结构改动），`SelectionStore.load`
重建顶层并断言版本 ∈ `{1, 2}`（其余抛 `SelectionStoreError`）；v1 报告可读可下载回归通过。
并入项同步交付：`providers/arxiv.py::_candidate` 剥 `entry_id` 末段尾部 `v\d+`（新旧式均覆盖，
`page_url`/`download_url` 原样），跨版本去重、`excluded_existing` 与 068-6b 查重口径统一为
无版本 ID；观察项——历史 `qt_selections.downloads` 中带版本的 ID 与新口径失配，是否对账归
S5/068-6d 窗口一并裁。定向 32 passed + ruff clean；全量 = 565 passed + 1 skipped + 1 failed
（唯一红仍为编排线并行 WIP 归因，口径不变）。

**S3 交付记录（2026-09-30）**：B-3 生效——`paper-plan/plan@v2` 在册改写（build_user 增查询纪律：
每词组 1~3 个英文词、禁整句与堆叠名词短语、一次成型不得反复改写；`assess@v1` 按裁决不升代）；
`providers/bailian.py` 增 `_clean_plan_value` 确定性清洗（去外围引号、折叠空白、单条 ≤200 字符截断、
组内大小写不敏感去重），校验前执行、清洗只规范化词形，空组/超组/越界分类仍按契约走修复→报错路径；
`application/papers.py` fallback 编排：捕获 `advisor.plan` 的 `BailianError` → `_fallback_seed`
（goal 优先否则 topics 首个非空，单行化 ≤120）→ 三组兜底计划（`seed`/`recent advances <seed>`/
`open challenges <seed>`，category=`allowed[0]`，reason=`deterministic fallback`），照过
`_validate_searches`；种子全空原异常上抛（`status=failed` 不变）、兜底不新增模型调用。审计字段
`plan_source`（llm/fallback）落报告顶层并同记 `model.plan_source`，兜底另记
`model.plan_fallback_error`；持久化折进 `model` JSON（零表结构改动，与 B-4 同法），`load` 重建
顶层、历史无标记报告按 `llm` 回填。`tests/test_prompt_template_ids.py` 三处 `plan@v1` 钉随升代
同步（含注册表清单 pin）。定向 59 passed + ruff clean；全量 = 575 passed + 1 skipped + 1 failed
（唯一红仍为编排线并行 WIP 归因，口径不变）。S3 计划的一次真实冒烟（`qed_llm_calls` 可见
`paper-plan/plan@v2`）尚未执行，待用户执行或明确授权（本地 9B 通路另受 G1 约束）。

**门禁口径（2026-09-29 用户裁决）**：每步跑「论文链定向测试 + ruff」为硬门禁；全量
`pytest tests -q` 每次照跑，但**并行会话未跟踪 WIP 造成的红单独归因登记、不计入本任务失败**
（当前已知：`tests/test_orchestration.py::test_evidence_packer_trims_deterministically_and_records_budget_omissions`，
属 QED-073/067 编排线 WIP，本任务不触碰）。真实冒烟（公网 arXiv / 8900 网关）集中在 S1、S3、S4
各一次，由用户执行或明确授权后驱动。

## 根侧需求扩展（2026-09-30，QED-Engine 根用户裁决；根侧承载 REQ-101/REQ-102）

根侧设计：8903 下载管理页**领域/课程各挂一行「前沿/核心论文」展示行**（清单=该 scope 下
`kind=paper` 书行，复用书目卡与五层态）并可行内探索。需求原文与消费侧验收判据正本在根仓库
`docs/plans/2026-09-30-req101-paper-scope-books-adoption-request.md`（QED-Engine 侧，跨仓库
引用不加链接），对方台账为实施事实源。三项裁决：① 书本化采纳——显式 pick 产出
`qt_books` 行（**改判 QED-071 D2/D14「发现论文不进库」**，本计划与
`docs/design/paper-discovery.md`「事实边界」节的相应收口由对方执行）；② 课程级落盘=
**逻辑分组**——物理仍落领域级 `raw/<domain>/_general/papers/`，课程归属由书行 refs 表达，
不开课程级 papers 目录（避免 dataset 布局破坏性变更）；③ **排期并入本计划**，不另开
QED 承接 ID（子任务编号 068-6 为暂记，对方评审可调）。

| 扩展项 | 内容 | 验收判据（消费侧观察） | 排期落点 |
| --- | --- | --- | --- |
| 068-6a scope 化 | recommend 入参增可选 `domain_id`/`course_id`（根侧**发起语境仅领域**——2026-09-30 入口收敛裁决；course_id 保留为 scope 过滤/表达维度）；goal 缺省从 `qed_domain.description` / `qed_course` 名称+描述推导（profile 保留为全局模板）；`qt_selections` 报告快照落 scope；selections 查询支持 scope 过滤 | 带 `domain_id=X` 提交→报告含 scope；`GET selections?domain_id=X` 仅返回该范围；不带参数时现行为不变（兼容） | 并入 068-5（S4）请求体与端点，一次定稿签名，避免二次改 |
| 068-6b 书本化采纳 | 显式 pick 改为创建 `qt_books` 行（kind=paper、归属=**pick 时逐条落位 refs**（domain_id 或该领域下 course_id，默认=发起领域）、内容标识=arXiv ID），后续下载/校验/验收走书本五层态链（arXiv 为渠道适配器给 URL）；`excluded_existing` 查重口径=书库标题/arXiv ID 命中；论文 ResourceService 直写路径退役 | pick 后书库出现 kind=paper 行且可自动下载至 verified；同 arXiv ID 二次 pick 命中查重不重复建行；`GET /books?domain_id=&kind=paper` 与 `?course_id=&kind=paper` 可枚举 | 新增子任务 068-6（S4 之后、068-4 收口轮前实施为宜） |
| 068-6c 前沿/核心配方 | 任务请求体增 `recipe: frontier \| core`：frontier=现默认（relevance + years_limit 3）；core=years_limit 0 + `foundational_value` 阈值筛选（阈值与排序键对方定）；assess 三项评分契约不动 | 两配方各跑一次：frontier 集中于窗口内、core 含窗口外经典且 foundational_value 达标；非法 recipe 提交即 422 | 并入 068-5 请求体 |
| 068-6d 存量回填 | 已下载至 `_general/papers/` 的历史论文（无书目行）一次性补登记为 kind=paper 书行（文件名 arXiv ID + sha8 对账），或声明维持只读不再展示 | 回执明确二选一；选补登记时抽验若干条与盘上文件一一对应、无幻影行 | D 类窗口，068-6 后；口径回执先行 |

**不变的边界**（与既有裁决一致）：不引入 `exploration_stage` 状态机（论文行状态由根侧按
任务态×报告态×书五层态派生，见根仓库 REQ-102 壳 W1 设计节）；模型不写资源事实、不自动
下载；默认测试零公网；TLS 默认开启；`qt_selections` 报告仍为候选/评分审计快照。

**根侧联动前置**：根仓库 `dataset-conventions.md` 的 kind=paper 发现论文落盘豁免注与
`downloads-flow/downloads-ui/api-contracts` 论文节晋升（REQ-102 W1）先行或同批，
口径不一致前 068-6b 不落实现。

## 链路复审与执行序列精简（2026-09-30，根用户裁决）

根侧对论文链做了一次全链复审（QED-Engine 会话，代码事实逐条自核）。结论：**检索/计划/报告
三环已由 S1~S3 交付到位，入口/落盘/入库三环仍是断点**；且原序列（S4 任务化 → 068-6b 书本化
→ S5 收口）会先建一条随即退役的下载路径。用户裁决改按精简三步执行，本节为该裁决的正本。

### 复审事实（断点逐条，含代码位置）

| # | 事实 | 位置 | 影响 |
| --- | --- | --- | --- |
| F1 | 8901 论文面只有 `GET /api/v1/papers/search` 一条即时端点；后台任务表只有 book/tutorial/domain/course 五类 | `api/main.py:484`、`:413-420` | recommend/pick 无服务化入口（068-5 目标） |
| F2 | `Application.papers` 构造未注入 advisor | `api/main.py:131-135` + `application/papers.py:119-120` | HTTP 侧调 `recommend()` 必抛「论文推荐需要配置百炼顾问」；服务化须按 `_advisor_kwargs()` 补建 `BailianPaperAdvisor` |
| F3 | CLI `_paper_service` 不传 `session_factory` → `PaperService` 回落 in-memory SQLite | `cli.py:290-312,397`、`application/papers.py:72-86` | **`papers recommend` 报告进程退出即失**，`papers selections list/show/download` 恒空；068-6d 存量对账基准不可信 |
| F4 | 论文直写路径不落库：`kind=paper` 明确不进 `qt_books`、不写 `qt_sources` | `application/resources.py:6-7,118-120`、`application/papers.py:233-266` | 与 068-6b／根侧 R2 改判直接冲突；下载留痕只存 `qt_selections.downloads` JSON |
| F5 | 落盘 domain 硬编码：`raw_general_dir(data_root)` 未传 `domain_id` → 恒 `raw/math/_general/papers/` | `application/papers.py:102-107`、`inventory.py:22,72-74` | scope 化须把 `domain_id` 一路传到目录 helper；068-6d 回填基准目录亦依赖此 |
| F6 | `qt_books` 无 `kind`/`course_id`/`knowledge_id` 列（课程归属只存在于 `qt_knowledge` 三个 refs JSON） | `db/models.py:175-238`、`db/knowledge_repository.py:799-813` | 068-6b「kind=paper 书行 + 逐条落位」需加列或等价表达 |
| F7 | 8901 无 books 枚举端点（repo `list_books(None)` 已能返回域级全量，只差端点与过滤） | 路由全表 `api/main.py:470-1545`、`knowledge_repository.py:799` | 根侧 R2 判据 `GET /books?domain_id=&kind=paper` 无实现面 |
| F8 | `book_id` 格式 `^[0-9a-z]+-b\d{2,}$`，abbr 由 `course_id` 推导 | `knowledge_repository.py:88,95-108`、`api/main.py:1147` | 领域级论文无课程缩写 → pick 建行时 book_id 无从生成，需约定 |
| F9 | 领域标识口径分裂：真库唯一领域 `domain_id='math-advanced'`（书行落 `raw/math-advanced/<course>/`），而 `DEFAULT_DOMAIN_ID='math'` → 论文默认桶 `raw/math/_general/papers/` | `inventory.py:22`、`application/book_fetch.py:517-520`、qed_test 实测（2026-10-01） | 同一领域的书本与论文落在两个 domain 目录 |

**F9 裁定（2026-10-01 用户裁决，随 A 步追加）**：**论文没有默认桶，必须先有对应领域**。
取消论文链路的一切 `DEFAULT_DOMAIN_ID` 兜底——`domain_id` 为**必填**且在 `qed_domain` **必须存在**，
缺失或不存在即拒绝（不落盘、不建书行）；论文因此只会落在真实领域的
`raw/<domain>/_general/papers/`，与书行的 `domain_id` 天然一致，目录分裂随该口径自然消失。
A 步随之做一处收敛性修正（见「A 步交付」节 ⑤′），B 步的 recommend/adopt 按同一判据设计。

### 裁决一：执行序列改精简三步（取代 S4 → 068-6b → S5 交错）

| 步 | 内容 | 归并子任务 | 前置 | 验收判据 |
| --- | --- | --- | --- | --- |
| **A 最小出数**（**已交付 2026-10-01**，证据见「A 步交付」节） | ① 手工 ALTER 给 `qt_books` 加 `kind`（存量默认 `book`）与落位列，模型同步；② 8901 增 `GET /api/v1/books`（过滤 `kind`/`domain_id`/`course_id`）；③ 修 F3（CLI 在 `db_configured` 时传 `session_factory`）；④ 修 F5（`domain_id` 传至 `raw_general_dir`） | 068-6b 的表结构前置 + R2 枚举判据 | 无模型依赖；ALTER 窗口先行 | 枚举端点三参数过滤可用；CLI recommend 报告可被 `selections list` 查到；定向 + 全量门禁绿 |
| **B 探索服务化 + 书本化一次到位**（展开契约见下「B 步设计节点」节，含五项待裁项） | `POST /api/v1/papers/recommend`（scope `domain_id` + `recipe`，202 + 任务轮询）；`GET /papers/selections[?domain_id=]`、`GET /papers/selections/{id}`；`POST /papers/selections/{id}/adopt`（逐条 refs 落位 → 建 `kind=paper` 书行 → 查重按书库标题/arXiv ID）；下载**复用既有** `POST /books/{book_id}/fetch`；HTTP 侧补建 `BailianPaperAdvisor`（F2）；CLI recommend/selections 转 HTTP 客户端 | 068-5 + 068-6a + 068-6b + 068-6c | A 步（表结构与枚举就绪）；G1 已解锁 | 探索→轮询→评审→adopt→书行→自动下载至 verified 端到端一单；同 arXiv ID 二次 adopt 命中查重不重复建行；非法 recipe 422；**不新增 `paper_download` 直写端点** |
| **C 收口** | downloader 逐跳复检 + 字节硬顶 + 重复双报；四份文档收口（`paper-discovery.md`「事实边界」节按改判重写、`api.md` 路由数同步、`code-map.md`、`download-pipeline.md`） | 068-4 + B-1~B-5 落文档 | B 步 | `tests/test_documentation.py` 绿 + 下载器定向用例绿 + 真实冒烟一单 |
| **D 存量回填** | 068-6d 维持 D 类人工窗口，排在 A 步之后（F3 修好后对账基准才可信） | 068-6d | A 步 | 回执二选一；选补登记时抽验若干条与盘上文件一一对应、无幻影行 |

**精简理由**：原 S4 的 `POST /papers/selections/{id}/download` 走 `ResourceService` 论文直写，
而 068-6b 紧接着要退役该路径改为建书行——先建后拆会多一个短命端点、一轮测试改写与一次契约
抖动。合并后 pick 只有一种形态：**adopt 建书行 → 复用书本五层态下载链**。

### 裁决二：F3（CLI 报告不落库）并入 A 步修复

不另开 DEFECT、不等服务化后自然消失：`_paper_service` 在 `settings.db_configured` 时建
`session_factory` 传入 `PaperService`，无库时保留 in-memory 回落（测试场景不变）。
理由=068-6d 的存量对账与用户当下能否看到 recommend 结果，都依赖报告真落 `qt_selections`。

### 前置红线：加列必须先 ALTER，不得靠自愈重建

`db/schema.py` 的 v0.1 自愈策略对**私有表列集漂移执行 DROP+CREATE**（`schema.py:7,104-166`；
仅共享审计表 `qed_llm_calls` 走 late-column 追加）。直接给 `QtBook` 加列会让下次 8901 启动
**清空生产书库**。口径=A 步先出 ALTER 脚本并在打算保留数据的库上人工执行（先例=QED-071
sha256/size_bytes/page_count 三列），模型改动与 ALTER 同批但执行窗口独立留痕；
ALTER 未执行又需保留数据的库不得启动新版服务。**生产 `qed` 库按 2026-10-01 改判不做本次
ALTER**（走 1.0 收尾重建），适用口径见下方「生产库口径」段。

### 需对方定夺的实现细节（根侧只给消费侧判据）

1. **落位表达形态**：加 `course_id` 列，还是沿用 refs 语义？根侧消费判据不变——**枚举行必须
   携带 `kind` 与落位字段**（`domain_id` + 课程归属，课程为空即领域级），否则 8903 无法分桶
   （其 W3 已按行内 `kind`/`course_id`/`knowledge_id` 实现分桶）。
2. **论文 `book_id` 约定**（F8）：领域级论文无课程缩写，需定 abbr 来源（领域 abbr／固定
   `paper`／其他），并保持 `^[0-9a-z]+-b\d{2,}$` 与列宽 32。
3. **评分理由留痕落点**：adopt 时把 `score`/`reason` 带进 `qt_books.notes` 还是
   `qt_sources.note`？报告与书行需可追溯（根侧展示行若要显示「为什么推荐」依赖此项）。
4. **`kind` 值域**：发现论文与教程附属资料（现挂 knowledge 的 paper 语义）是否共用同一值域、
   以 refs 有无区分（根侧 W3 现按「`kind=paper` 且无 `knowledge_id`」判定为发现论文）。

### A 步交付（2026-10-01，本仓执行）

按红线顺序落地，逐条证据：

1. **① ALTER（qed_test 已执行）**：`scripts/qed068_alter_book_kind.py`（幂等：现状勘查 →
   `--dry-run` 出 SQL → 备份 → ALTER → 复核）。执行结果＝备份
   `tmp/backups/2026-09-30-qed068-paper-kind/qt_books.sql`（26 行可重放 INSERT）、
   `qt_books` 22 列 → **24 列**、行数 26 不变、`ix_qt_books_kind` / `ix_qt_books_course_id`
   齐备、存量 26 行 `kind` 全为 `book`。**生产 `qed` 库不执行**（2026-10-01 改判：不做 ALTER，
   走 1.0 收尾重建，见「生产库口径」段）。
2. **② 模型同步**：`db/models.py` 新增 `BookKind`（`book`/`paper`）与 `QtBook.kind`
   （NOT NULL default `book`、indexed）、`QtBook.course_id`（String(64) NOT NULL default `''`、
   indexed）；`tests/test_schema_mysql_smoke.py::BOOK_COLUMNS` 同步两列。
   核验：模型列集与盘上列集**双向零差**，`ensure_schema(engine) → (0, 0)`、行数仍 26。
3. **③ 枚举端点（F7）**：`knowledge_repository.list_books()` 增 `kind`/`domain_id`/`course_id`
   AND 过滤（空串=不过滤，与 `GET /knowledge` 同口径）；`api/main.py` 增 `GET /api/v1/books`
   （行=`to_dict()` 全列，含 `kind`/`course_id`；`created_at` 升序；无命中空数组；
   `kind` 非法值 422 `INVALID_PARAMS`）；`create_book()` 增 `kind`/`course_id` 关键字参数。
   真库只读冒烟（qed_test）：全量 200/26 行且每行携带两新列、`kind=paper` → `[]`（B 步 adopt
   前属正常）、`kind=book` → 26、`kind=blog` → 422。
4. **④ F3 修复**：`cli._paper_service` 在 `settings.db_configured` 时建 engine + `session_factory`
   传入 `PaperService`（无库仍走 in-memory 回落，默认测试不写运行数据库）；`PaperService` 增
   `db_engine` 参数并在 `close()` 的 ExitStack 中**最后**释放连接池（先注册=后执行）。
5. **⑤ F5 修复**：`PaperService.download(candidate, *, domain_id=…)` 把
   `domain_id` 传至 `raw_general_dir`；`download_selection(..., *, domain_id=…)` 透传；
   CLI `papers search/get/selections download` 各增 `--domain`（该项初版默认 `math`，
   默认值随即由 ⑤′ 取消）。
6. **⑤′ F9 追加裁决落地（同日，取消默认桶）**：论文链路**去掉** `DEFAULT_DOMAIN_ID` 兜底——
   `PaperService.download`/`download_selection` 的 `domain_id` 改为**必填关键字参数**，
   服务侧统一经 `_require_domain()` 校验：空/纯空白 → `ValueError`「论文落盘需要显式指定领域
   （无默认桶）」；配了库时 `PaperService` 新增 `domain_exists` 可注入校验器，登记不存在 →
   `ValueError`「论文落盘领域不存在，需先创建该领域：<domain_id>」，且校验在拼目录**之前**，
   失败不产生任何盘上写入。`cli._paper_service` 在 `db_configured` 时以
   `KnowledgeRepository.get_domain` 装配该校验器（未配库只要求显式非空，不做存在性校验）。
   CLI `--domain` 默认改空串，**涉及落盘的分支**
   （`search --download` / `get` / `selections download`）在构造服务**之前**即检查缺 `--domain`
   → stderr 报错返回码 2，不触发下载；领域不存在同样经 `ValueError` 返回 2；
   纯检索/纯推荐分支仍不要求领域。
   理由=用户裁决「论文没有默认桶，需要先有对应领域」，同时消解 F9 的目录分裂。

**门禁（⑤′ 后复跑）**：`ruff check src tests scripts` All checks passed；`pytest tests -q` →
**589 passed | 1 failed | 1 skipped**，唯一红＝`test_orchestration.py::test_evidence_packer_trims_deterministically_and_records_budget_omissions`
（存量红：`orchestration/evidence.py` 与其测试文件均未在本轮工作树改动内，与 A 步无交集）；
`tests/test_documentation.py` 9 passed；`scripts/` 白名单守卫已登记新迁移脚本
（`tests/test_cli_architecture.py`，守卫自身要求「新增脚本需同步本守卫」）。

**「需对方定夺的实现细节」本轮落定两项**：#1 落位表达形态＝**加 `course_id` 列**
（空串=领域级，归属领域见 `domain_id`；课程级=逻辑分组，物理仍在领域通用桶）；
#4 `kind` 值域＝`{book, paper}`（`blog` 为裁决预留、未实现不进值域），发现论文判定＝
`kind=paper`（`qt_books` 无 `knowledge_id` 列，教程归属由 `qt_knowledge` refs 承载，
故与教程附属资料不混列）。#2（论文 `book_id` abbr）与 #3（评分理由留痕落点）仍待 B 步定夺。

**F9 已随 ⑤′ 关闭（2026-10-01 用户裁决）**：真库唯一领域为 `domain_id='math-advanced'`，
书行落盘在 `raw/math-advanced/<course>/…`；而 `inventory.DEFAULT_DOMAIN_ID='math'` 会把论文
落进 `raw/math/_general/papers/`，**与书库领域目录分裂**。裁決＝**论文没有默认桶**：
`DEFAULT_DOMAIN_ID` 从论文链路全部取消（`inventory.py` 的该常量仍供 `book_fetch`/
`raw_general_dir` 书本兜底使用，不在本轮范围），落盘领域必须显式传入且已在 `qed_domain` 登记，
分裂根因即消失。D 步回填的基准目录随之取各行 `domain_id`，不存在统一默认桶。

**生产库口径（2026-10-01 用户裁决改判，红线解除方式变更）**：`qed` 生产库**不做本次 ALTER**，
等 1.0 版本整体完成后走**重建**窗口。含义与约束：
① `qed` 库上若以本版模型（含 `kind`/`course_id`）启动服务，`db/schema.py` 私有表自愈会
**DROP+CREATE 重建 `qt_books`（清空生产书库）**——这是当前已知且被接受的状态，
根侧 8900/8903 走 `qed_test`，本机开发不受影响；
② 因此**在 1.0 收尾重建前，不得把本版代码指向 `qed` 库长期运行**（临时验证须先备份）；
③ 1.0 收尾的重建窗口＝重建后重导书目（`books import`/reconcile 链）+ 论文存量按 D 步口径处置；
④ `scripts/qed068_alter_book_kind.py` 保留但**不再用于 `qed`**（`qed_test` 已执行完毕），
若重建窗口改为「增量加列」而非「重建」，再按脚本走一次（脚本幂等，含备份与复核）。

**B/C 步承接补记（随 ⑤′ 留待办，勿丢）**：
① B 步 `Application.papers`（`api/main.py:131-135`）构造 `PaperService` 时须同时注入
**advisor（F2）与 `domain_exists`**（复用其已自建的 `KnowledgeRepository`），否则 HTTP 侧
落盘面要么无顾问、要么无领域校验（当前 8901 尚无论文落盘端点，⑤′ 只改了 CLI 路径）；
② C 步文档收口须同步 `docs/design/paper-discovery.md`「论文不进 `qt_books`（QED-071 D2/D14）」
句与 `docs/architecture/database-private-tables.md` 第 4 条「不承载论文」句——B 步 adopt 起
发现论文以 `kind=paper` 进 `qt_books`，现文按代码事实仍成立，改判落地后须一并改写。

### B 步设计节点（2026-10-01 落笔；同日晚些时候用户裁决五项实现细节后已执行，交付证据见「B 步交付」节）

本节把「裁决一」B 步行展开成可实现契约。形态口径沿用已裁决的两条边界：**探索入口/状态机独立**
（论文链自身是 搜索→确认→下载→验证，不与领域书籍的收集五阶段混用），**存储仍书本化**
（adopt 只产 `qt_books` 行 + 走书籍下载链）。根侧消费判据见其 `api-contracts.md` §③「论文面」，
本节与其逐字段对齐，不另造第二套形状。

**B-1 端点契约（四条，全部新增在 8901 `/api/v1/papers/` 面）**

| 端点 | 请求 | 响应 | 错误 |
| --- | --- | --- | --- |
| `POST /papers/recommend` | body：`domain_id`（**必填且须 `qed_domain` 已登记**——⑤′ 判据）、`recipe`（`frontier`\|`core`）、可选 `goal`、`categories`、`top`、`limit`、`years_limit` | `202 {task_id}`，任务类型 `paper_recommend`；轮询 `GET /tasks/{id}` 结果含 `selection_id` | 缺/非法 `domain_id`、非法 `recipe` → `422 INVALID_PARAMS`；领域不存在 → `422`（message 含 domain_id，**不补默认桶**） |
| `GET /papers/selections` | query：`domain_id`、`recipe`、`limit`（缺省全量） | `{selections:[{selection_id,domain_id,recipe,status,created_at,recommendation_count}]}` | — |
| `GET /papers/selections/{id}` | — | 现有 `selections.load()` 报告全量（`assessments`/`recommendations`/`model`/`downloads`） | 不存在 → `404 SELECTION_NOT_FOUND` |
| `POST /papers/selections/{id}/adopt` | body：`picks:[{rank, domain_id, course_id}]`（**逐条落位**；`course_id` 空=领域级） | `202 {task_id}`，任务类型 `paper_adopt`；结果含每条 `book_id` 与查重命中 | `404 SELECTION_NOT_FOUND`；`rank` 不在 `recommendations` → `422 INVALID_PARAMS`；落位领域缺失/不存在 → `422`；同 selection 任务在跑 → `409 TASK_ALREADY_RUNNING` |

`papers recommend`/`selections list|show|download` CLI 转 HTTP 客户端（复用 `TaskClient` 轮询），
不再本地直调 `PaperService`；**下载动作只有一条路**＝书行 fetch，`download_selection` 的论文直写
落盘面随 B 步退役（保留 `_require_domain` 校验语义，见 B-5）。

**B-2 任务面**：`paper_recommend`、`paper_adopt` 两个 handler 注册进 `api/main.py:412-419` 的
`all_handlers`（`TaskManager` 未知类型即 `ValueError`）；`submit(..., dedup={"domain_id":…,"recipe":…,"goal":…})`
防同配方并发重跑，`paper_adopt` 用 `dedup={"selection_id":…}`。任务参数只放 ID 与落位，
不放候选内容（模型审计仍进 `qt_selections`）。

**B-3 `Application.papers` 装配（F2 + ⑤′ 同批）**：现构造点 `api/main.py:131-135` 只传
`provider/resources/session_factory`，且 `advisor` 在**其后**（`:136-150`）才自建——B 步须把
顾问构造**前移**，再按 `_advisor_kwargs()`（`:186`：api_key/model/base_url/timeout/call_budget/
max_tokens/api_select/gateway_url/engine）建 `BailianPaperAdvisor`，与 `domain_exists`
（`self._knowledge_repository.get_domain`，复用 `:120-129` 自建 repo）一并注入 `PaperService`。
缺任一项即 HTTP 侧 recommend/adopt 不可用（无顾问抛「论文推荐需要配置百炼顾问」、无校验器则领域
不存在也能落盘）。

**B-4 scope 承载＝零表结构改动**：`domain_id`/`course_id`/`recipe` 折进 `qt_selections` 既有 JSON
袋（`model` 或顶层派生，与 A 步 `plan_source` 折进 `model` 同法），列表侧按 JSON 字段过滤。
**不加列**——加列即触发自愈漂移（`db/schema.py` 私有表 DROP+CREATE），与「`qed` 库不 ALTER、
1.0 重建」的裁决相抵。

**B-5 adopt 建书行与内容标识**：
① `create_book(kind='paper', domain_id=…, course_id=…)`，标题/作者取 `assessments[].candidate`；
② 内容身份写 `qt_sources(book_id, channel='arxiv', provider_id=<arXiv ID>, download_url=<pdf 链接>, ok=…)`
（`channel` 为 String(24) 自由值、`provider_id` String(200)，现无论文取值，B 步起占用）；
③ 查重＝`selections.downloaded_arxiv_ids()`（`papers.py:372-375`）**并**联书库
`kind='paper'` 行的 `qt_sources(channel='arxiv')`，命中不建行、回执标 `duplicated`；
④ `book_id` 仍须满足 `^[0-9a-z]+-b\d{2,}$`、列宽 32（F8），abbr 来源待定（见待裁项 #2）；
⑤ 评分/理由**不进书行**（见待裁项 #3），书行 `notes` 保持人工语义。

**B-6 下载承接＝`kind=paper` 分叉（关键事实，须用户确认形态）**：复核 `BookFetchService.fetch`
（`book_fetch.py:186`）＝**按书名在 `QED_SOURCES` 渠道多词检索**编排（`_hardcoded_queries` →
`service.providers` → 预筛 → staging → `promote_staged`），其中**没有 arXiv provider、也不读
`qt_sources.download_url`**——直接对 paper 书行调 `/books/{id}/fetch` 会走「拿 arXiv 标题去图书
渠道碰运气」的错误路径。故两案：

| 案 | 做法 | 代价 |
| --- | --- | --- |
| A | 把 arXiv 注册成 book provider 塞进 `create_book_providers` 链 | 仍走书名模糊匹配＋`verify_content(expected_titles)`，误配率高、与「标识＝arXiv ID」的事实不符 |
| **B（推荐）** | `fetch()` 入口按 `book.kind=='paper'` 分叉：取 `qt_sources(channel='arxiv')` 的 ID/URL → `ArxivProvider.get(id)` 解析下载地址 → **同一** staging/校验/哈希/`promote_staged`/五层态迁移（`start_download`→`mark_owned`/`fail_download`） | 编排器多一条分支；内容校验对论文改用「ID 解析到的即匹配」口径（不跑书名相似度） |

B 案保住「来源适配器只解析地址、写入/重试/校验/哈希/去重经通用服务」与书籍五层态复用，
且零新表零新渠道语义。

**B-7 落盘目录与命名**：`_destination_dir`（`book_fetch.py:513-523`）现按
`first_course_for_book` → 课程桶，否则 `raw_general_dir(domain_id)`，且 `domain_id` 空时回落
`DEFAULT_DOMAIN_ID`。`kind=paper` 须**强制**领域通用桶 + 年层：`raw/<domain_id>/_general/papers/<year>/`
（与 ⑤′ 的 `PaperService.download` 同目录），**取消 `DEFAULT_DOMAIN_ID` 回落**（论文无默认桶），
文件名沿用 `<arxiv_id>_<sha8>.pdf`。课程的论文落位是**逻辑分组**，物理仍在领域桶。

**B-8 红线与测试面**：零迁移（`qt_books` 用 A 步已就绪的两列）、模型不写资源事实、默认测试零公网、
TLS 默认开启、`qt_selections` 仍是候选/评分审计快照、不引入 `exploration_stage` 状态机。
TDD 先红清单（定向文件→用例）：`test_paper_api.py`（recommend 202+任务、`domain_id` 缺失/不存在 422、
非法 recipe 422、selections 过滤与 404、adopt 建 `kind=paper` 行 + `qt_sources(channel=arxiv)`、
二次 adopt 查重、409 dedup）、`test_paper_application.py`（recommend 注入 advisor 后 HTTP 侧可跑）、
`test_book_fetch*.py`（`kind=paper` 分叉：目录/命名/五层态/不复用书名检索）、
`test_cli_architecture.py`（CLI 转 HTTP 后不再本地直调落盘）。门禁口径同 A 步：
论文链定向 + `ruff check src tests scripts` + `pytest tests -q` 全量（并行 WIP 红单独归因）。

**五项实现细节已裁（2026-10-01，用户「确认接受你的建议，开始执行」——全部按建议落定）**：
#1 下载承接形态＝B-6 的 A/B 案（**建议 B**）；
#2 论文 `book_id` 的 abbr 来源（领域 abbr／固定 `paper`）＋序号并发下取 max+1（**建议领域 abbr**，
与既有 `course_id` 推导法同源、可读）；
#3 评分理由留痕落点（**建议只留 `qt_selections`**，书行 `notes` 不进模型判断——「模型不写资源事实」，
根侧展示行因此不显示「为什么推荐」，需要时另立项）；
#4 `recipe`→profile 的 `allowed_categories` 来源（现 profile 是打包 JSON：`math-research`/
`llm-engineering`，动态领域无分类表；**建议**新增 `paper_recipes.py` 内「领域关键词→arXiv 分类」
映射，映射不到即 422 要求 body 显式给 `categories`）；
#5 adopt 是否**自动**链式提交 `book_download`（**建议不自动**：adopt 只建行返回 `book_id`，
下载由调用方显式 POST `/books/{id}/fetch`，保持「不自动下载」边界；根侧 8903 若要一键下载，
在其 W 步按书籍既有五层态按钮走同一端点）。

### B 步交付（2026-10-01，本仓执行）

五项裁决按建议落定后一次定稿实现，逐条对照 B-1~B-8：

1. **B-1 四端点**：`api/main.py` 新增 `GET /papers/selections`（`domain_id`/`recipe` AND 过滤 +
   `limit` 截断，摘要取自报告 `model.scope`）、`GET /papers/selections/{id}`（不存在 → 404
   `SELECTION_NOT_FOUND`）、`POST /papers/recommend`（202）、`POST /papers/selections/{id}/adopt`
   （202）。全部 422/404/409 校验在 `manager.submit` **之前**——失败不建任务、不盘写
   （测试断言 `/api/v1/tasks` 列表不变）。
2. **B-2 任务面**：`paper_recommend`/`paper_adopt` 两个 handler 注册进 `all_handlers`；
   dedup 分别 `{domain_id,recipe,goal}` 与 `{selection_id}`；参数只放 ID 与落位。
3. **B-3 装配**：顾问构造前移，`PaperService` 注入 `advisor` + `domain_exists`（`get_domain`）；
   `BookFetchService` 注入 `paper_provider=app.papers.provider`（arXiv 来源实例归 `Application.papers`
   持有并关闭），论文分叉不新建来源。
4. **B-4 零表结构改动**：`domain_id`/`recipe` 折进 `qt_selections.model.scope`，列表侧按 JSON 过滤；
   未加列、未触发私有表自愈重建。
5. **B-5 adopt（裁决 #2/#3/#5）**：`knowledge_repository.adopt_paper()` 建 `candidate` 态
   `kind=paper` 行 + `qt_sources(channel=arxiv, ok=False, note="adopt 登记…")`；`book_id`＝领域
   abbr + 域内 `-bNN`（max+1，`_paper_abbr`）；同 arXiv ID 命中既有书行 → `duplicated` 不重复建行，
   历史直写留痕（`downloaded_arxiv_ids`）命中同样 `duplicated`；落位领域/课程存在性与归属在事务内
   再校验一次。评分理由**只留 `qt_selections`**，不写 `qt_books.notes`（模型不写资源事实）；
   adopt **不**链式提交下载，书行停在 `candidate`，下载由调用方显式 `POST /books/{id}/fetch`。
6. **B-6 下载承接（裁决 #1＝B 案）**：`book_fetch._fetch_paper()` 分叉——不跑书名多渠道检索
   （测试断言书名 provider `queries == []`），按 `qt_sources(channel=arxiv)` 身份经
   `paper_provider.get(arxiv_id)` 直取，内容校验＝「ID 解析到的即匹配」（不做书名比对）；
   缺 provider / 缺身份 / 缺领域三种缺件在 `start_download` **之前**拒绝，只留痕不污染
   `downloading` 态；真下载失败才 `fail_download` + 渠道 `ok=False` 留痕。
7. **B-7 落盘（⑤′）**：论文强制 `raw/<domain>/_general/papers/<year>/<arxiv_id>_<sha8>.pdf`，
   领域为空即 `ValueError`（不回落 `DEFAULT_DOMAIN_ID`，测试断言不产生 `raw/math/`）；教材路径不变。
8. **B-8 CLI 转 HTTP + 直写面退役**：`papers recommend`（`--domain` 必填、`--recipe` 值域
   `frontier|core`、`--top/--limit/--years-limit` 仅显式给出才透传，缺省由配方决定）与
   `selections list|show|adopt` 全部经 8901（复用 `_fetch_task_via_api` 轮询）；
   `papers selections download` 子命令与 `PaperService.download_selection`（含私有
   `_candidate_from_dict`）删除，`_require_domain` 校验语义保留在 `PaperService.download`
   （`papers search --download` / `papers get` 单条手动直写通道仍需显式 `--domain`）。
   同步文档：`README.md` 论文命令段、`docs/architecture/api.md`（新增「⑥ 论文探索」节 + 索引四行 +
   404 错误码补 `SELECTION_NOT_FOUND`）、`docs/architecture/code-map.md`（`paper_recipes.py` 新行 +
   api/main、cli、papers、book_fetch、models、knowledge_repository、selection_repository 七行改写）。

**门禁证据（2026-10-01）**：`ruff check src tests scripts` → All checks passed；论文链定向
（`test_paper_recipes` / `test_paper_api` / `test_paper_application` / `test_paper_selection_cli` /
`test_book_fetch` / `test_book_fetch_paper` / `test_profiles_and_selections` / `test_cli_architecture` /
`test_documentation`）→ **114 passed**；`pytest tests -q` 全量 → **629 passed, 1 failed, 1 skipped**，
唯一红＝`tests/test_orchestration.py::test_evidence_packer_trims_deterministically_and_records_budget_omissions`
（QED-067-2/3 编排在途，非本步引入，归因该线）。新增测试文件：`tests/test_paper_recipes.py`、
`tests/test_paper_api.py`、`tests/test_book_fetch_paper.py`；`tests/test_paper_selection_cli.py` 整体
重写为假 httpx 面（零公网、零服务依赖）。

**留给 C/D 步**：`docs/design/paper-discovery.md`「论文不进 `qt_books`（QED-071 D2/D14）」与
`docs/architecture/database-private-tables.md`「不承载论文」两句的改判改写、068-4 安全件、
存量回填（人工窗口）。

### W5 取证与围栏抽取交付（2026-10-07，根侧会话经用户授权在本仓执行）

**取证（正本在根仓库 REQ-102 壳 `docs/plans/2026-09-30-req102-paper-display-row-root-impl.md`，QED-Engine 侧跨仓库引用不加链接；截至 2026-10-15 根仓 `docs/plans/` 仍只有 req101，REQ-102 壳落地归根侧会话补）「过程与证据」2026-10-07 两条）**：真机 local 渠道（8901 `api_select=qed-engine` → 8900 网关 →
LM Studio `qwen/qwen3.5-9b`）跑 `POST /papers/recommend`，任务 `succeeded` 但报告
`sel-20261007T054356Z-4a835e78` 为 `no_candidates`、`model.plan_source="fallback"`；
`qed_llm_calls` 行 79 显示模型 39.6s 返回 **528 字、内容完全合规的 ` ```json ` 围栏正文**，
本仓 `providers/bailian.py::_structured` 用裸 `json.loads` 在 char 0 判失败，于是盲发 repair
二次长调用（行 80，71.6s 后正文空）并落回确定性检索计划（中文单 term ⇒ arXiv 必零候选）。
同形缺陷在 `providers/book_advisor.py`、`providers/explore_advisor.py`、
`main_line/advisor.py` 三处 `_structured` 同样存在，本次按用户裁决**只改论文顾问**，
余三处列为后续承接（不扩范围、不碰并行在途线）。

**交付（围栏抽取＝形态容错，不改契约）**：
- 新模块 `src/qed_tracker/llm_json.py::loads_model_json`：① 直接解析 →② 剥 ` ``` ` 围栏
  （含未闭合围栏）→③ 最外层 `{}`/`[]` 引号感知切片（串内花括号不破坏配平；未闭合则剥到文末
  交给 `json.loads` 报真实结构错）。三档全失败抛 `ValueError`，调用方 repair/报错口径不变。
  顺序与根仓库 `services/llm/local_adapt.parse_json_reply` 同形（直解→围栏→切片）。
- `providers/bailian.py::_structured` 首解析与 repair 后解析均改走 `loads_model_json`；
  错误文案「百炼结构化响应无效」**未改**（渠道归因属独立事项，本轮范围外，登记见根侧 M3 壳）。
- 文档同步：`docs/design/paper-discovery.md`「百炼边界」补形态容错一句；
  `docs/architecture/code-map.md` 新增 `llm_json.py` 行并在 `bailian.py` 行补注。

**门禁**：`tests/test_llm_json.py`（新增 8 例，纯函数）+ `tests/test_bailian_advisor.py`
（新增 5 例：围栏 plan/assess 一次过且 `calls==1`、散文包裹切片、纯文本仍 repair 一次、
围栏内越界分类仍按契约失败）先红后绿；论文链定向 `test_llm_json/test_bailian_advisor/
test_paper_application/test_paper_api` **67 passed**；`ruff check src tests` **All checks passed**；
全量 `pytest tests -q` **642 passed | 1 failed | 1 skipped**（唯一红＝存量
`test_orchestration.py::test_evidence_packer_trims…`，QED-067-2/3 在途线，非本次引入）、
`tests/test_documentation.py` 随定向批次全绿。**本仓 git 提交未做**（用户未要求）。
8901 需重启方在真机加载本次改动（重启由人工执行）。
### 2026-10-09 网关调用被系统代理劫持（root 侧取证驱动的本仓修复，用户授权改码）

**现象**：根侧 W5 端到端复跑（任务 `1383b037c8ea`）15s 即 `succeeded`，报告
`sel-20261009T025958Z-e8dc0004` 仍 `no_candidates` / `plan_source=fallback`，
`plan_fallback_error="网关返回 HTTP 502"`；同一时刻根仓 `qed_llm_calls` 零新增行＝请求没到 8900。

**根因（根侧对照实验定性）**：同一请求体在根侧 `trust_env=False` → HTTP 200 并落库；默认
`trust_env=True` → **502 空正文**；显式 `proxy=http://127.0.0.1:7890` → 同样 502。
`urllib.request.getproxies()` 在本机返回注册表系统代理 `127.0.0.1:7890`（进程环境无代理变量），
httpx 默认继承 ⇒ 对本机回环 `127.0.0.1:8900` 的调用被本地代理接管并返回 502。
本仓 `llm_client.LlmClient` 自带客户端未设 `trust_env`（`_gateway_complete` 抛
「网关返回 HTTP {code}」正对应此路径），是 10-07 那次「网关请求失败」的同一条链
（代理状态在/不在会交替出现）。

**修复**：`LlmClient.__init__` 自带客户端改为
`httpx.Client(timeout=timeout, trust_env=not self.is_gateway)`——gateway 恒旁路环境代理
（只打本机 8900），direct 保持默认可继承代理（公网厂商可能需要），注入客户端不覆盖
（测试/MockTransport 通道不变）。四份 advisor（`bailian.py`、`book_advisor.py`、
`explore_advisor.py`、`main_line/advisor.py`）统一经本层，一处修复全覆盖。

**TDD 与门禁**：`tests/test_llm_client.py` 新增 `test_gateway_built_client_bypasses_system_proxy`
（monkeypatch 设 `HTTP_PROXY` 后 gateway 客户端 `_trust_env is False`、direct 为 True）先红后绿 +
`test_injected_client_keeps_caller_transport_choice` 守护注入面；该文件 **18 passed**，
`ruff check src tests` **All checks passed**。模块 docstring 补该口径一句。
**8901 已重启加载**（经根侧 8900 控制中心 `/services/tracker/restart`）。**本仓 git 提交未做**（用户未要求）。


### 2026-10-09 真机复核：修复生效，论文链端到端首次跑通（root 侧 W5 取证）

**生效证据**：8901 重启后 `POST /papers/recommend` 两腿均取到 `ranked` 且 `plan_source=llm`
（不再 `fallback`）——`sel-20261009T031317Z-8a886b24`（21 候选 / 4 推荐）、
`sel-20261009T033359Z-62ac54a4`（30 候选 / recs 1-10），根仓 `qed_llm_calls` 同批新增行＝请求确实进了
8900 网关。这同时是 `llm_json.loads_model_json` 围栏抽取的真人验证：`plan@v2` 的围栏 JSON 正文
不再被 char 0 解析失败拖进 repair 长调用。

**下游全链**：adopt 建 `kind=paper` 书行三条（领域级 `mathadvanced-b19`/`b20`、课程级 `b22` 落位
`partial_differential_equations`）；显式 `POST /books/{id}/fetch` 成功落盘 `2604.14366_ac3527f8.pdf`
与 `2606.11607_441aa00c.pdf`；`b19` 经 8903 书目详情「验证通过」至 `verified`，`b22` 至 `downloaded`。
「自动链止于 `downloaded`、`verified` 由人工验收置位」与本仓 `application/book_fetch.py:322/463`
（`mark_owned(..., status="downloaded")`）一致，本仓无缺陷。

**新发现（本机配置面，非本仓代码缺陷）**：fetch 任务 `f96546ae9117`、`93c37d44edc7` 一度 `failed`
（`下载失败：[WinError 10061] 目标计算机积极拒绝`）。根因＝`settings.proxy='http://127.0.0.1:7890'`
取自**根 `.env` 的 `QED_PROXY`**（本仓 config 优先级「真实环境变量 > 自身 .env > 根 .env」，空值跳过
⇒ 以空 env 遮蔽不可行），而当时 Clash 未监听；同 URL 直连公网 `arxiv.org/pdf/...` 可 200 / 2.23 MB。
用户重启 Clash 后零改动即成功。**与上节是两个不同失败面**：公网下载依赖显式代理存活（代理进程下线＝10061），
回环调用必须旁路系统代理（不旁路＝假 502）——两条各自记账，不可互相顶替。

**负样本留档**：`recipe=core` 首跑 `no_candidates`（规划查询命中空 arXiv 页，非缺陷）；adopt 传越界
rank 得 422「picks[1].rank 不在推荐内（1）」且任务与书行均未落（提交前全量校验生效）。

### D 步裁决：存量不回填（2026-10-15，用户裁决）

068-6d 按「声明只读、不再展示」分支关闭，**不补登记、不搬迁、不注销**。理由：那批由 B 步退役的
论文直写路径落盘的 PDF 是开发期测试产物，无留存价值；补登记的收益（进 8903 展示、进查重）不抵代价。

1. **免除的两笔子账**：①历史 `qt_selections.downloads` 中带尾部版本号的 arXiv ID 与
   068-3 剥版口径的失配对账（S2 交付记录观察项）随本裁决关闭；②跨目录搬迁（F9 老
   `raw/math/_general/papers/` 与新 `raw/<domain>/_general/papers/<year>/`）不做。
2. **显式接受的代价**：遗留文件不进书库、不进五层态，也不参与采纳查重；同一 arXiv ID
   若再次采纳会正常建行并可能重复落盘一份，磁盘代价记入观察。
3. **与成功标准的关系**：todo 的 QED-068 行「A~D 四步全量交付并收口」口径冻结，不改写；本裁决
   作为 D 步的**关闭判定**登记于此，收口时 `completed.md` 按「D 步＝用户裁决不回填」记，
   不得静默砍项。
4. **文档落点**：`docs/design/paper-discovery.md`「事实边界」节已补遗留只读声明，
   `docs/architecture/database-private-tables.md` 第 4 条现状注记同步刷新（均随 C-4 落地）。

### 台账影响

068-6 编号保留（内容并入 A/B/D 三步）；「小步快跑执行序列」表 S4/S5 行状态口径改指本节；
`docs/trackers/todo.md` 的 QED-068 行需补 068-6 与三步序列描述（归本仓会话执行）。
**不变的边界**：模型不写资源事实、不自动下载、默认测试零公网、TLS 默认开启、
`qt_selections` 仍为候选/评分审计快照、不引入 `exploration_stage` 状态机。

### C 步交付（一）：C-1 逐跳复检 + C-2 字节硬顶（2026-10-15，本仓执行）

068-4 第 1 条的两个安全件按 TDD 先红后绿交付（红＝44 例全部 setup error，缺 `_resolve_host_ips`）：

1. **逐跳复检**（`downloader.py`）：客户端改 `follow_redirects=False`，`download()` 手动逐跳
   （`MAX_REDIRECT_HOPS = 5`）。新增 `_resolve_host_ips`（数字地址直返、其余 `socket.getaddrinfo`）
   与 `_guard_redirect_target`：在**发起连接前**校验 scheme 限 http/https、主机解析出的每个 IP
   `is_global` 须为真（private/loopback/link-local/multicast/reserved/unspecified 任一命中即拒），
   解析失败或无结果同样拒绝（fail-closed）。相对 Location 用 `urljoin` 按当前 URL 解析。
2. **字节硬顶**：`DownloadManager(max_bytes=...)`，`_write_stream` 累计字节超顶即中断并删 `.part`；
   Settings 新键 `max_download_bytes`（env `QED_MAX_DOWNLOAD_BYTES`，默认 512 MiB＝`qed_test` 库实测
   最大成品 127,353,789 B ≈ 121.5 MiB 的 4 倍余量，避免误伤合法书体）。五处构造点
   （`cli.py` 三处、`api/main.py:102`、`application/book_fetch.py:91`）全部接 `settings.max_download_bytes`。
3. **终止性拒绝**：新增 `DownloadBlockedError(DownloadError)`——异 scheme / 非公网主机 / 超跳数 /
   超字节四类拒绝不进重试循环（`test_security_rejection_is_terminal_not_retried` 以 retries=3
   守护「只发出 1 次请求」）；错误文案含跳数、主机、上限三要素（068-4 第 1 条末项）。
   `tls_verify=False` 的显式配置口径不变。
   **上线前核对（068-4 第 1 条注记要求，2026-10-15 实探）**：本机 DNS 解析四渠道主机（`arxiv.org`、`export.arxiv.org`、`archive.org`、`openlibrary.org`）**全为公网 IP**，不存在「合法重定向到内网」的用例，故默认拒绝不误伤现网。`QED_PROXY` 属传输层代理，主机校验只判定目标 URL 的解析结果，代理地址本身不参与判定。
4. **测试隔离**：`tests/conftest.py` 增 autouse `stub_dns` 打桩 `_resolve_host_ips`（未登记主机一律
   解析为公网 IP），SSRF 用例据此把主机指向 `10.0.0.5`/`127.0.0.1`——默认测试零公网、零真实 DNS；
   `manager_with` 的假客户端同步改 `follow_redirects=False`（与生产同构）。用例落
   `tests/test_download_inventory.py`（`DownloadManager` 既有用例与该 helper 均在此；计划原记
   `tests/test_downloader.py` 现为 `verify_content` 专用文件，不改名以免打断 code-map 锚点）。
5. **文档落位**：`design/download-pipeline.md`「可靠下载」节新增「下载安全件」段；
   `architecture/code-map.md` downloader 行补「逐跳重定向复检、字节硬顶」；
   `design/service-management.md` 全量键清单 27→28 键并登记新键；`guides/operations.md` 常用键行同步。
   `architecture/api.md` 无需改：C 步不新增路由，且该文档已声明「代码路由数以 `main.py` 为准」。
6. **门禁**：定向 `tests/test_download_inventory.py`、`tests/test_config_catalog_matching.py`
   **44 passed**；`ruff check src tests scripts` **All checks passed**；全量 `pytest tests -q`（串行）
   **653 passed / 1 skipped / 1 failed**——唯一红为已登记存量红
   `test_orchestration.py::test_evidence_packer_trims_deterministically_and_records_budget_omissions`
   （QED-067-2/3 编排线 WIP，归因口径见「门禁口径」节）；`test_documentation.py` 绿。
7. **待办**：C-3 重复双报（`same_content`/`same_name`，涉及提交面响应契约）单独一轮——已另轮交付，见下节「C 步交付（二）」；
   068-4 的「真实 8901 冒烟一单」需 8901 重启加载本次代码改动后由人工窗口执行（C-1/C-2 轮的冒烟回执与一处既有验收口径误伤见下节第 7 条与 BUG-005）。

8. **台账**：`docs/trackers/todo.md` 的 QED-068 行已给 C 步事项标「已交付／待做」、D 步改记「裁决关闭：旧 PDF 只读、不回填」；成功标准列未动。该表受 `test_todo_tables_have_no_process_narrative` 守护（事项/成功标准单元格禁日期与裁决史词），故行内不带日期，过程事实全部留在本计划。

### C 步交付（二）：C-3 重复双报（2026-10-15，本仓执行）

068-4 第 2 条「重复检测双报」单独一轮。契约先行，再按 TDD 先红后绿落实现：

1. **契约文档先行**：`design/download-pipeline.md` 新增「查重双报（same_content / same_name）」节
   （判据一处＋两桶命中/处置表＋不自动覆盖条款）；`design/paper-discovery.md` 第 4 条补报告顶层
   `duplicates` 两桶口径、schema 段补「折 `model` JSON 落盘＋读侧重建」；`architecture/api.md`
   `book_download`/`tutorial_fetch` 结果与 `paper_recommend` 结果加 `duplicates`（fetch 面标可选，
   已 owned 的 no-op 路径不返回）；`architecture/code-map.md` 四行登记新增查询面与只读原语。
2. **判据只有一处**：`ResourceService.duplicate_check(sha256=, title=, exclude_book_id=)`
   （`application/resources.py`）为只读原语——不写行、不删文件、不改状态，返回
   `{same_content[], same_name[]}`，条目形状两桶一致
   `{book_id, title, kind, status, file_path, sha256, size_bytes, page_count}`；
   标题查询面 `KnowledgeRepository.find_owned_by_titles(titles, *, exclude_book_ids=)`
   （`db/knowledge_repository.py`）只取 `holding=owned` 且**已填内容身份**的行，`title`/`original_title`
   在 Python 侧 `casefold` 比对（不用 MySQL `LOWER` 折叠），按 `created_at, book_id` 定序保证多次调用同结果。
3. **提交面挂载**：`application/book_fetch.py` 书本分支与 `kind=paper` 分叉同构挂 `_duplicates(...)`
   （登记完成后只读计算，不影响本次登记结果，自身书行由 `exclude_book_id` 剔除）；
   `application/papers.py` 推荐面 `_duplicates_report(...)` 用一次标题查询建折叠索引后逐候选归类，
   `same_content`＝`excluded_existing` 的逐项展开（附命中行摘要，历史直写留痕无书行时字段空串），
   两桶**均不**从候选池剔除；`api/main.py` 的 `paper_recommend` 任务结果透出 `duplicates`。
4. **零表结构改动**：`duplicates` 折进 `qt_selections.model` JSON 落盘、`SelectionStore.load()` 重建顶层
   （历史报告补空两桶，读侧形状恒定）——与 `scope`/`plan_source` 同手法，避开私有表 ALTER 红线窗口；
   `excluded_existing` 列与写入白名单不动。
5. **处置口径（均不自动覆盖）**：`same_content` 的复用只发生在登记原语内且仅限 `ResourceKind.BOOK`；
   `kind=paper` 以 `ResourceKind.PAPER` 落盘（D2/D14 不进 qt_books 复用链），故论文面 `same_content`
   **只报不复用**；`same_name` 一律出冲突清单交人工，既有行与既有文件不动，本次成品按内容指纹
   `<slug>_<sha8>.pdf` 独立命名落盘。DB 未配置（`books=None`）时两桶恒空。
   人工登记面（`/import`、`/register`）不加字段：既有「目标已存在不同内容 → 409 不覆盖用户文件」硬门已承接。
6. **TDD**：先红＝定向 5 文件 **12 failed / 75 passed**（`KeyError: 'duplicates'`、
   缺 `duplicate_check`、缺 `find_owned_by_titles`）；实现后同 5 文件 **87 passed**。
   计划命名用例 `tests/test_book_fetch_paper.py::test_same_name_conflict_reported_and_existing_row_untouched`
   验证同标题不同 arXiv ID 且内容不同 → 只出 `same_name` 清单、首册行 `sha256` 与首册文件均不变、
   两次成品独立落盘；`test_same_content_paper_hit_is_reported_without_reuse` 锁死论文面「只报不复用」；
   `tests/test_services.py` 四例锁 `exclude_book_id` 自不报冲突、`books=None` 恒空、空 sha/空标题不发查询；
   `tests/test_knowledge_repository.py` 三例锁 `casefold`＋`original_title`＋身份/持有门槛＋排除参数；
   `tests/test_paper_application.py` 两例锁 papers 同口径与 `model` JSON 往返。
7. **真实 8901 冒烟一单**（8901 重启加载 C-1/C-2 代码后执行；两册书行事后经
   `GET /api/v1/books?kind=paper` 只读复核）：`mathadvanced-b21`（arXiv `2511.03618`）→ `ok`、
   `status=downloaded`、`holding=owned`、落 `raw/math-advanced/_general/papers/2025/2511.03618_767b9a90.pdf`
   （`sha256=767b9a90c6d3e8b3...`）；`mathadvanced-b20`（arXiv `2504.15268`）下载与字节校验通过，
   却被既有机器验收口径判 `('PDF 已加密',)` 拒绝落盘→`status=failed`、`holding=missing`。
   两项旁证（探针只写仓库 `tmp/smoke/` 且测量后删除，不碰数据根）：① `DownloadManager` 直取
   `https://arxiv.org/pdf/2604.14366` → `200`、514,768 B、26 页、sha8 `ac3527f8`、硬顶余量 1042.9×
   （`QED_PROXY=http://127.0.0.1:7890`、`tls_verify=True`），C-1 主机复检与 C-2 硬顶不误伤现网；
   ② 直连取回 `2504.15268` → `200`、2,234,089 B、sha8 `b79ce3ac`、`is_encrypted=True` 且
   `decrypt("") -> 1`、50 页、可抽正文 121,239 字符，内容完全可读。加密误伤不是 C-1/C-2 回归，
   已按缺陷台账登记 **BUG-005** 待裁（空密码可解的属主权限加密是否放行）。
8. **门禁**：`ruff check src tests scripts` **All checks passed**；全量 `pytest tests -q`（串行）
   **665 passed / 1 skipped / 1 failed**——唯一红为已登记存量红 BUG-002
   `test_orchestration.py::test_evidence_packer_trims_deterministically_and_records_budget_omissions`
   （编排线并发会话遗留，归因口径见 BUG-002）；`test_documentation.py` 绿。
9. **人工窗口回执（2026-10-15 执行，8901 重启加载 C-3 代码后）**：驱动脚本
   `tmp/smoke_c3_duplicates.py`（新增 `--attach <task_id>` 续跑同一任务；`recipe` 合法值为
   `core`/`frontier`，脚本默认已由 `math-research` 改回 `core`；轮询对 `httpx.TransportError` 重试——
   8901 在 LLM 长调用期间会偶发 `Server disconnected without sending a response`，服务本身未挂）。
   四条判据逐条：
   ① 任务 `aec468e96fb1`（`math-advanced` / `core`）`succeeded`，结果
   `duplicates = {"same_content": [], "same_name": []}`——键恒在；
   ② 同报告 `GET /api/v1/papers/selections/sel-20261015T083608Z-cd970b47` 读回的两桶与任务结果
   **逐字相等**（`model` JSON 折/建往返成立，历史报告补空两桶同样可读）；
   ③ 取书面 no-op 已验证：`POST /api/v1/books/mathadvanced-b19/fetch` → 任务 `f1b7fb9a231b`
   `succeeded`、`result = {ok: true, skipped: true, reason: 已 owned，无需取书, ...}`，**不含**
   `duplicates` 键（与 `api.md` 的 fetch 面可选口径一致）；正向回执仍差一单非 owned 取书，见第 10 条；
   ④ 两轮真实 recommend（默认 goal 一轮＋定向 goal 一轮，后者报告
   `sel-20261015T084743Z-6db11c0c`）前后，`mathadvanced-b19/b21/b22` 三行的 `sha256` 与 `file_path`
   逐字节不变——只读性成立。
   两桶为空的成因已核到候选层，不是判据没跑到：定向轮候选池 20 篇（`2609.06924 … 2402.01479`）
   不含任何已 owned 的 arXiv ID，且没有 `title`/`original_title` 与 owned 行 `casefold` 全等者
   （最接近的 "Gradient estimates for parabolic nonlinear ..." 与 b19 的
   "Gradient estimates for a parabolic partial differential equation" 不相等），
   故 `excluded_existing` 也为空。命中路径由第 6 条定向用例锁死，不依赖冒烟构造。
   **HTTP 面无法合成 `same_content` 命中**：`KnowledgeRepository.adopt_paper` 以 arXiv ID 幂等
   （同 ID 二次采纳返回 `duplicated`、不建新行），库里不存在「同内容两行」的可造入口，
   正向命中只能在真实积累中出现。

10. **取书面正向回执（同窗口执行；写真实数据根经用户批准）**：驱动脚本
   `tmp/smoke_c3_fetch_positive.py` → `paper_adopt`（报告 `sel-20261015T083608Z-cd970b47` 的 `rank 1`）
   建 `mathadvanced-b23`（`kind=paper`、`candidate/missing`，**不**自动下载）→
   `POST /api/v1/books/mathadvanced-b23/fetch` → 任务 `a0aacbfa25b6` `succeeded`，结果键集
   `['attempts','book_id','duplicates','file_path','identity','manual_guidance','ok',
   'provider_failures','resource_id','skipped']` 含 **`duplicates`**
   ＝ `{"same_content": [], "same_name": []}`（两桶键恒在）；本次成品落
   `raw/math-advanced/_general/papers/2026/2603.10184_50040708.pdf`
   （`sha256=500407085870b9424eb592777cf7b69954869ea84fba2fbdb46519ef2d30f5f8`、`status=downloaded`），
   前后对比 `mathadvanced-b19/b21/b22` 三行 `sha256/file_path/status` **逐项不变**——提交面同样
   「只出清单、不自动覆盖」。四判据（推荐面键在、读回相等、fetch 面正向＋no-op 反向、owned 行不变）至此全绿。

11. **冒烟核到的一条读侧口径（非缺陷，登记以免后人误读）**：报告详情里 `recommendations` 是
   **名次表**（本次为 `[1,2,3,4,5]`），`rank → 论文` 的映射以 `assessments[].rank` 携带的
   `candidate` 为准（`_paper_adopt_handler` 正是这样取），**不能**按 `candidates[rank]` 下标解读——
   本次 `rank 1` 实为 arXiv `2603.10184`（Stabilizing Bandits…），而 `candidates[1]` 是 `2407.04045`。
   `api.md`「`GET /papers/selections/{id}`」条目只写了返回含 `assessments`/`recommendations`，未点明这层
   映射；是否补一句说明按[文档治理规范](../../standards/doc-governance.md)由用户裁决（`architecture/` 属大修改口径）。


### 收尾轮（2026-10-15，QED-068 关闭）

1. **关闭范围**：A~D 四步全量交付（A＝`qt_books` `kind`/`course_id` + `GET /books` 枚举 + CLI 报告落库与领域透传；
   B＝论文服务化四端点 + `paper_recommend`/`paper_adopt` 任务面 + adopt 建 `kind=paper` 行 + 取书分叉 + CLI 转 HTTP；
   C＝068-4 C-1 逐跳复检／C-2 字节硬顶／C-3 重复双报 + `paper-discovery`／`database-private-tables` 论文进库表述改写；
   D＝裁决关闭：存量旧 PDF 只读、不回填）。⑤′ 承接补记（计划第 514 行「B/C 步承接补记，勿丢」）两条核到已落地：
   `Application.papers` 构造 `PaperService` 时已同时注入 `advisor` 与 `domain_exists`
   （`src/qed_tracker/api/main.py:152`），论文进库表述改写随 C 步交付。
2. **门禁（收尾轮实跑，不引用前轮）**：全量 `python -m pytest tests -q` → **1 failed / 665 passed / 1 skipped**
   （41.16s），唯一红为已登记存量红 BUG-002 `tests/test_orchestration.py:244`（编排线并发会话遗留，
   归因口径见 BUG-002，与本任务无关，本会话不代改）；`ruff check src tests scripts` → **All checks passed!**；
   `qed-tracker --version` → `qed-tracker 0.5.0`；`qed-tracker --json catalog list` → `["math-qe"]`；
   `pytest tests/test_documentation.py -q` → **9 passed**；`git diff --check` 挑出一处
   `downloader.py:345` 的 EOF 空行（本任务 C-2 追加方法所致）已清，清后复跑
   `tests/test_download_inventory.py` → 17 passed 且 ruff 绿；仓库 `core.autocrlf` 带来的
   LF→CRLF warning 属全仓既有现象，不计入本轮改动。
3. **本轮并入的文档修订（经用户批准）**：`architecture/api.md` 的 `GET /api/v1/papers/selections/{selection_id}`
   条目补 `rank → candidate` 映射口径（`recommendations` 为名次表，论文以 `assessments[].rank` 携带的
   `candidate` 为准），`POST .../adopt` 输入行同步指向该口径；发现路径见上节第 11 条。
4. **BUG-005 处置（用户裁决）**：不作为本任务关闭前提——它是既有机器验收口径（`downloader.py` 的
   「已加密一律拒绝」）与 arXiv 权限加密的冲突，不是 C-1/C-2 引入的回归；继续在缺陷台账滚动，
   放行口径与修复归该条目 own。
5. **真实数据根产物（冒烟遗留，经用户批准写入）**：`mathadvanced-b23`
   → `raw/math-advanced/_general/papers/2026/2603.10184_50040708.pdf`（`sha256=500407085870b942…`）；
   本轮探针与输出按 ADR 0011 留在仓库 `tmp/`（`smoke_c3_duplicates.py`、`smoke_c3_fetch_positive.py`
   及各 `probe_*_out.txt`）。
6. **状态快照同步**：`docs/trackers/project-status.md` 追加 QED-068 关闭记录（A~D 交付 + 收尾轮门禁 + BUG-005 不阻塞裁决），「arXiv 与论文发现」服务行补采纳落库口径，并将 v1.0 立项行末句「各任务尚未排期实施」勘正为指向关闭记录与 todo；`最后更新` 改 2026-10-15。后续复跑 `tests/test_documentation.py` → 9 passed。

## 依赖与顺序

068-1 → 068-2 → 068-3 顺序实施（2 依赖 1 的 `sort_by`/`years` 参数形状，3 依赖 1/2 的报告字段）；
068-5 依赖 1~3 定稿的 `recommend` 签名；068-4 最后收口。
**068-2 另依赖 QED-072**（本地 9B 单通路 + 预算表定稿），口径见下节。

## QED-072 接口轮与排期口径（2026-09-29 登记，已裁）

2026-09-28 用户裁决（QED-072）：百炼退役、本地链路独占，论文评分/书籍检索词不得再到
云端 `qwen-plus`；`bailian.py` 现默认走 `qed-engine` 模式 → 8900 网关 → 本地 `qwen/qwen3.5-9b`。
QED-072 W-0 已实测论文 `plan`/`assess` 两契约在 9000 输出预算下**一次通过、零 repair**
（留痕 id=31~37），故 068-2 的本地可行性证据已具备。

1. 068-2 的 `plan@v2` 提示词与清洗/fallback 逻辑落在本地 9B 单通路上（模板名与模块名沿用
   现 `paper-plan/*` 口径，改名归 QED-072 命名同步面 W-6）。
2. `max_tokens` 等运行参数一律引用 QED-072 预算表定稿（W-5），本计划不写死数值，避免
   9B 吐空正文故障模式（Q67-a：≤256 必空、1024 硬下限）。
3. **排期口径（2026-09-29 用户裁决采纳）**：068-1 无模型依赖先行；068-2 排在 QED-072
   W-3~W-5 收口之后（否则 plan@v2 需云端/本地各验证一遍，重复烧预算且口径易漂移）；
   068-3/068-5 无模型依赖。
4. 068-4 收口轮真实冒烟同样只在本地通路执行（8900 网关在线时）。

每子任务一个提交，TDD 先红后绿。

## 边界与非目标

- 不改变「模型不写资源事实」「不自动下载」「来源适配器只给 URL，下载走通用服务」约束。
- 不照搬：客户端预计算哈希、异常吞成空列表、YouTube/Bilibili 链、自研 agent loop、
  0 结果反复改写（调研稿 §6）。
- 论文链路不引入 `exploration_stage` 状态机；报告快照 + 显式 pick 即其审阅态。
- 不新增表、不改 `qt_selections`/`qed_llm_calls` 结构；`assess@v1` 契约本轮不动。
- 默认测试不访问公网与真实模型（`httpx.MockTransport`/假顾问），真实连通性仅人工冒烟登记。

## 验证与验收（整计划）

1. 每子任务：定向测试先红后绿 → 全量 `pytest tests -q` + `ruff check src tests scripts`。
2. 真实冒烟（评审后排期执行）：8900 网关在线时 `papers recommend` 一次（断言
   `plan_source`、`qed_llm_calls` 落 `paper-plan/plan@v2`、`plan_coverage` 合理），
   经 8901 任务链 `selections download` 一单（显式 pick）。
3. 文档收口后 `tests/test_documentation.py` 全绿；`api.md` 路由数与代码一致。

## 回滚

068-1/2/3 为行为增量（新参数有默认、v2 报告可读 v1、fallback 可经配置开关退回直抛——
仅保留「seed 缺失即 failed」路径），回滚=恢复调用参数与 prompt 版本；
068-5 端点为新增面，CLI 旧直调路径过渡期保留一个版本周期。

## 关闭与归档

**收尾轮判定（2026-10-15）**：本计划关闭，状态行已改 `已关闭`；归档按默认 **Retain**——正文移入
`docs/history/baselines/`（保留原文件名），并在 `plans/index.md` 与 `docs/history/index.md` 双向登记；
`docs/trackers/todo.md` 的 QED-068 行原子移除并写入 `docs/trackers/completed.md`。

关闭时按 [ADR 0009](../../history/adr/0009-closed-plan-archival.md) 做 Retain/Delete 两态判定；
设计确定后按 [ADR 0003](../../history/adr/0003-pending-design-location.md) 迁入 `design/`。
