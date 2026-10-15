# arXiv 论文智能发现设计

设计状态：Accepted
实现状态：Implemented
确认状态：暂定
最后更新：2026-10-15
关联代码：`src/qed_tracker/application/papers.py`、`src/qed_tracker/providers/arxiv.py`、`src/qed_tracker/providers/bailian.py`、`src/qed_tracker/db/selection_repository.py`、`src/qed_tracker/db/knowledge_repository.py`、`src/qed_tracker/api/main.py`、`src/qed_tracker/application/book_fetch.py`
关联测试：`tests/test_paper_application.py`、`tests/test_bailian_advisor.py`、`tests/test_paper_selection_cli.py`、`tests/test_paper_api.py`、`tests/test_book_fetch_paper.py`
关联 ADR：—

## 事实边界

arXiv 提供标题、作者、分类、时间和摘要等候选事实。百炼只根据研究目标生成有限检索计划并评估候选，不提供客观质量或引用影响力结论。下载器负责 PDF 校验和落盘（`raw/<domain_id>/_general/papers/<year>/<arxiv_id>_<sha8>.pdf`）。

**入库口径（QED-068 B 步，2026-09-30 改判 QED-071 D2/D14「发现论文不进库」）**：显式采纳（adopt）产出 `qt_books` 的 `kind=paper` 书行，内容身份登记在 `qt_sources(channel=arxiv)`（幂等键=arXiv ID，命中即返回 `duplicated` 不重复建行），下载/校验/验收复用书本五层态链（`src/qed_tracker/application/book_fetch.py` 的 `kind=paper` 分叉）。课程落位是**逻辑分组**，物理文件仍在领域通用桶。`ResourceRecord` 为内存 DTO（D12），`meta/resources/` 资源岛与 `Inventory` 类均已退役；模型判断单独进入选择报告（`qt_selections`），书行 `notes` 不写模型判断（模型不写资源事实）。

**遗留只读（D 步裁决 2026-10-15）**：B 步退役的论文直写路径（`PaperService.download_selection` 与 `papers selections download`，均已删除）此前落盘的 PDF 不补登记、不搬迁、不再展示，也不参与采纳查重；它们在书库与 8903 展示行中不可见。单条手动直写通道（`papers search --download` / `papers get`）仍在，必须显式 `--domain`。

模型不能直接写 PDF、修改资源记录或选择任意 URL。推荐只生成报告；采纳必须由用户引用固定选择报告与推荐序号显式执行（`POST /api/v1/papers/selections/{id}/adopt` 或 CLI `papers selections adopt`，逐条落位领域/课程），采纳只建书行并停在 `candidate` 态，下载仍须由调用方显式 `POST /api/v1/books/{book_id}/fetch`（不自动下载）。

## 目标档案

档案 schema v1 包含 `id`、`name`、`description`、`audience`、`goals`、`topics`、`allowed_categories` 和 `exclude`，另有可选字段 `years_limit`（QED-068-1；缺省即不设，旧档案 JSON 无需迁移）。内置 `math-research` 与 `llm-engineering`，也允许从 JSON 路径加载自定义档案；内置档案不预置 `years_limit`，统一走全局默认 3。

调用时至少提供档案或临时目标。临时 `--category` 只扩展本次允许分类，不修改档案。所有档案和分类必须在模型调用前校验。

## 检索与评分

1. 模型返回最多 4 个 `searches`；每项包含最多 4 个普通关键词、一个允许分类和简短理由。
   查询纪律（`paper-plan/plan@v2`，QED-068-2）：每个检索词组 1~3 个英文词、禁止整句与堆叠名词短语、
   一次成型不得因结果少反复改写；响应先经确定性清洗（去外围引号、折叠空白、单条 ≤200 字符截断、
   组内大小写不敏感去重），再进契约校验——清洗只规范化词形，空组/超 4 组/越界分类仍按契约失败，
   不静默丢组。
2. arXiv 对关键词使用 OR，对分类使用 AND；每项默认最多返回 10 条。
   `papers recommend` 走相关度排序（`sort_by="relevance"`）并过量抓取 `min(limit*2, 30)` 条；
   `papers search` 仍默认提交日期降序（QED-068-1，B-1）。
3. 年份窗口（B-2）：`recommend(..., years_limit)` 解析序为
   `显式参数 > profile.years_limit > DEFAULT_YEARS_LIMIT = 3`，`0` 表示不限；
   口径 `published_at >= today - years_limit*365 天`（UTC，`today` 可注入保证测试确定性），
   发布日缺失或不可解析的候选保留（不因元数据缺失被静默吞掉）。非法值（负数、非整数、布尔）
   在进入模型调用前 `ValueError`。
4. 应用层按 arXiv ID 去重，并排除已下载论文（`qt_selections.downloads` 派生，QED-071 B-W3；原资源岛 `kind=paper` 读取路径已退役），最多向模型提交 40 条候选。排除面只覆盖 `downloads` 派生集合，**不含已采纳未下载的 `kind=paper` 书行**（`src/qed_tracker/application/papers.py` 的 `_existing_arxiv_ids`）；重复采纳由 adopt 面幂等键拦（返回 `duplicated`）。已采纳未下载的论文会被再次推荐，记为观察项，本轮不改。arXiv ID 口径（QED-068-3）：取 `entry_id` 末段并剥除尾部版本号（`v\d+`，如 `2401.00001v3`→`2401.00001`；`math/0501001v1`→`0501001`），`page_url`/`download_url` 保持原样。**重复双报（QED-068 C 步 / 068-4，同口径见[下载管线设计](download-pipeline.md)「查重双报」节）**：报告顶层 `duplicates` 两桶——`same_content`＝候选 arXiv ID 命中已下载留痕或已有 `kind=paper` 书行（即 `excluded_existing` 的逐项展开，附命中行 `book_id/file_path/sha256`，历史直写留痕无书行时为空串）；`same_name`＝ID 未命中但候选标题 `casefold` 命中书库 owned 且已填内容身份的他行（内容不同）。两桶**均不**从候选池剔除、不自动合并、不改已有行，只出清单交人工裁决；`excluded_existing` 仍是 ID 字符串列表（`qt_selections` 列与写入白名单不改）。
5. 年份过滤与去重在每组内进行，该组保留满 `limit` 条后截断，再与其他组合并（过量抓取的意义所在）。
6. 模型必须为每条候选返回 `goal_fit`、`foundational_value`、`readability` 三项 0–5 整数、理由和风险。
7. 应用层按 50%/30%/20% 计算 0–100 分；70 分及以上进入推荐列表，排序键为分数降序、发布日期降序、arXiv ID 升序。

候选标题和摘要是不可信输入，提示词必须把它们标记为数据并限制摘要长度。未知 ID、漏评、重复 ID、越界分数、越界分类或非法 JSON 均使本次模型阶段失败；允许一次格式修复调用，仍失败则不得下载。

计划阶段模型调用失败（任何 `BailianError`）走确定性兜底（QED-068-2）：种子取 `goal`，为空则取
`profile.topics` 首个非空项（单行化、≤120 字符），生成 `seed`、`recent advances <seed>`、
`open challenges <seed>` 三组，分类取 `allowed_categories[0]`、理由 `deterministic fallback`，
兜底计划同样过应用层校验；种子全空时原异常照上抛。兜底不新增模型调用，失败调用照常落
`qed_llm_calls`（max_tokens 预算见 QED-072 预算表，不在此写死）。

## 百炼边界

默认使用 DashScope OpenAI-compatible `chat/completions` 和 `qwen-plus`，`temperature=0`。任务最多调用 6 次，单次默认超时 60 秒；模型调用经 `llm_client.py` 兼容层（QED-037）：`local` 直连（密钥 `API_KEY`，自身 `.env` → 根 `.env` 兜底）或 `qed-engine` 经 8900 网关，密钥不进入 Settings 表示、TOML、日志或报告。

自动测试只能使用假顾问或 `httpx.MockTransport`，不得访问真实模型或 arXiv。
模型正文按**形态容错三档**解析（`llm_json.loads_model_json`：直解→剥 ` ``` ` 围栏→最外层 `{}`/`[]` 切片），容错只治形态不改契约——围栏内的越界分类、超组数等仍由模板校验器判失败并走一次 repair；三档都取不出可用 JSON 才抛错。

## 选择报告 schema v1/v2

报告写入 `qt_selections` 表（REQ-032 Phase 2，`meta/selections/` JSON 已退役），包含 `selection_id`、`schema_version`、`status`、时间、目标档案快照、临时目标、实际生效的 `years_limit`、模型与契约版本、检索计划、候选、评分、推荐序号、调用用量、响应哈希和下载尝试。

v2（QED-068-3，2026-09-30 起新报告默认）增溯源与覆盖核对：候选条目与评分条目带 `plan_index`（1 基，来自计划第几组）；报告带顶层 `plan_coverage`（每组 `{plan_index, terms, category, fetched, kept}`，`kept=0` 的组是人工审阅的显式信号）。持久化零表结构改动（B-4 裁决）：`fetched/kept/plan_index` 折进 `search_plan` JSON 条目落盘，`SelectionStore.load` 重建顶层 `plan_coverage`。S3（QED-068-2）另增 `plan_source`（`llm`/`fallback`）审计字段：顶层与 `model.plan_source` 同记，兜底路径另记 `model.plan_fallback_error`；同样折进 `model` JSON 落盘，`load` 重建顶层，历史无标记报告按 `llm` 回填。读侧接受 `{1, 2}`（v1 报告无新字段、可正常读取与下载），其余版本抛 `SelectionStoreError`。完整 v2 契约叙述归 068-4 收口轮。C 步另记顶层 `duplicates`（查重双报两桶清单）：同样折进 `model` JSON 落盘、`SelectionStore.load` 重建顶层（零表结构改动），历史报告读侧补空两桶。

报告先以 `ranked` 原子写入。后续显式下载只读取该快照并追加成功或失败尝试，再原子替换；成功项记录 `resource_id`。报告不保存密钥、完整提示词或完整原始模型响应。

## 失败与退出码

- 参数、档案或选择序号错误返回 `2`。
- 无候选或无达到门槛的推荐返回 `3`，仍保存可审计报告。
- 多篇下载部分失败返回 `4`，成功资源保留。
- 模型、arXiv、报告或全部下载运行错误返回 `5`。
