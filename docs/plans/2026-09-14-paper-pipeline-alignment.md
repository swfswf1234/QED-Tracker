# 论文探索与下载链路整合（paper-pipeline-alignment）

状态：Draft
任务类型：Plan
最后更新：2026-09-24
需求方：用户
目标项目：QED-Tracker
评审方：用户
关联设计：[论文发现设计](../design/paper-discovery.md)、[探索管线设计](../design/exploration-pipeline.md)、[下载管线设计](../design/download-pipeline.md)
关联调研：[DeepTutor 机制调研](2026-09-21-deeptutor-survey.md)（借鉴点 #1/#2/#9/#3/#5 已消化进本计划）
关联 Tracker：QED-068
归档判定：待关闭时按 [ADR 0009](../history/adr/0009-closed-plan-archival.md) 做 Retain/Delete 两态判定

## 目标与成功标准

参照 DeepTutor 调研稿中已核实的确定性机制（arXiv 检索参数、查询收窄与 fallback、下载安全件），
形成贴合本仓的详细整合方案（子任务 QED-068-1~5）+ 总体性优化收口（068-4）。
**本计划评审通过后另行排期实施，本轮不实现。**

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

**改动文件**：`src/qed_tracker/providers/bailian.py`、`src/qed_tracker/prompt_lab/templates.py`
（注册 `paper-plan/plan@v2`）、`src/qed_tracker/application/papers.py`（fallback 编排）。

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
5. **模板注册**：`templates.py` 登记 `paper-plan/plan@v2`（含 plan 与 assess 两段基础 prompt 文本，
   `assess@v1` 内容原样、本轮不升版）；`BailianPaperAdvisor.plan_template_id` 改引 v2。

**测试用例清单**（`tests/test_bailian_advisor.py`、`tests/test_paper_application.py`，
假顾问 / `httpx.MockTransport`）：

- `test_plan_prompt_contains_term_discipline`（捕获 messages 断言）。
- `test_clean_terms_dedupes_case_insensitive`、`test_empty_group_after_clean_fails_contract`。
- `test_fallback_plan_on_bailian_error`（报告 ranked + `plan_source=fallback`）。
- `test_fallback_without_seed_reraises`（`status=failed`）。
- `test_plan_template_id_v2_registered`（templates 注册表 + 版本拒绝规则）。

**验收**：定向全绿；`qed_llm_calls.prompt_template` 冒烟可见 `paper-plan/plan@v2`。

## QED-068-3 报告溯源与覆盖核对（schema v2）

**改动文件**：`src/qed_tracker/application/papers.py`、`src/qed_tracker/db/selection_repository.py`（读侧版本断言）。

1. 候选条目增 `plan_index: int`（1 基，来自计划第几组；fallback 组同样适用）。
2. 报告增 `plan_coverage`：`[{"plan_index": 1, "terms": [...], "category": "...",
   "fetched": n, "kept": m}]`——`fetched`=该组抓取条数（含后被过滤），`kept`=去重/排除已有/
   年份窗口后实际入池数；`kept=0` 的组是人工审阅的显式信号。
3. `schema_version: 2`；`SelectionStore.load` 接受 `{1, 2}`，v1 报告无新字段不报错，
   `download_selection` 仅依赖 `recommendations`/`assessments.rank`，v1 可正常下载。
4. 报告页脚口径显式化（设计文档层）：推荐是建议、不是入库事实；下载必须显式 pick。

**测试用例清单**（`tests/test_paper_application.py`）：

- `test_plan_coverage_counts_fetched_and_kept`（含 0 命中组）。
- `test_candidate_entry_has_plan_index`。
- `test_v1_report_still_downloadable`（构造 v1 载荷回归）。

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
4. **文档收口**：[论文发现设计](../design/paper-discovery.md)「检索与评分」节改写为 v2 口径
   （排序/过量抓取/年份窗口/纪律/fallback/coverage/溯源 + 报告示例）；
   [API 设计文档](../architecture/api.md) 增补 papers 三端点两任务；
   `code-map.md` 行同步；[下载管线设计](../design/download-pipeline.md) 登记逐跳复检与硬顶。

**测试用例清单**（`tests/test_downloader.py` 等）：

- `test_redirect_to_private_host_blocked`（MockTransport 逐跳 fixture）、
  `test_redirect_chain_within_limit`、`test_max_bytes_aborts_and_cleans_partial`。
- `test_same_name_conflict_reported`（不自动覆盖）。
- `test_documentation.py` 全绿（文档收口后）。

## 依赖与顺序

068-1 → 068-2 → 068-3 顺序实施（2 依赖 1 的 `sort_by`/`years` 参数形状，3 依赖 1/2 的报告字段）；
068-5 依赖 1~3 定稿的 `recommend` 签名；068-4 最后收口。
每子任务一个提交，TDD 先红后绿；实施排期由用户在方案评审通过后指定。

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

关闭时按 [ADR 0009](../history/adr/0009-closed-plan-archival.md) 做 Retain/Delete 两态判定；
设计确定后按 [ADR 0003](../history/adr/0003-pending-design-location.md) 迁入 `design/`。
