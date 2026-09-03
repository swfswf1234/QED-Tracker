# 探索管线设计（领域与课程知识探索）

设计状态：Accepted
实现状态：In Progress
确认状态：暂定
最后更新：2026-09-03
关联代码：`src/qed_tracker/prompt_lab/`（pipeline/templates/priors）、`src/qed_tracker/providers/explore_advisor.py`、`src/qed_tracker/api/main.py`（探索段）、`src/qed_tracker/cli.py`（domains explore）
关联测试：`tests/test_prompt_lab.py`、`tests/test_prompt_lab_course.py`、`tests/test_prompt_lab_api.py`、`tests/test_task_handlers.py`、`tests/test_cli_domains_explore.py`
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)

> 本文档整合原 plans 中 `2026-09-exploration-pipeline.md`、`2026-09-exploration-overview.md`、
> `2026-08-prompt-optimization.md`（Accepted 设计）的当前契约与已确认裁决，作为探索管线
> 的**唯一设计事实源**。跨项目时序（8900 探索会话管理）、状态机 6 态写主体、explore_pending
> 载荷、写权限例外一律以 [共享表设计](../architecture/shared-tables.md) 为准，本文档只
> 链接不复制。

## 目的与边界

QED-Tracker 的探索能力基于 **LLM 模板管线**，用于自动发现领域内的课程结构与每门课程的
教材+习题集配套方案，供用户审阅后落库为正式知识条目。探索管线只**生成报告**，经
`llm_client.py` 调用模型并写入 `qed_llm_calls` 审计；不直接写任何 `qt_*`/`qed_*` 的表，
落库与状态推进由用户审阅端点（apply-results / re-explore）与共享表状态机承接。

探索分两条链路：

| 链路 | 步骤 | 模板编号 | 输出 |
| --- | --- | --- | --- |
| 领域探索 | 两步 | domain-explore/`domain@v4` → `courses@v8` | 领域结构 + 课程体系（每门课 stage+prerequisites 内联） |
| 课程探索 | 单步 | course-explore/`tutorials@v2` | 该课程的教材+习题集配套方案 |

- 领域探索的 `courses@v8` 已**并入原 path@v5**（2026-09-03 v8 裁决 P17）：输出即标准答案同构
  （`docs/knowledge/*.json` 正是 stage+prerequisites 内联的单层 `courses` 数组），消除跨步
  `course_id` 漂移、少一次 LLM 调用；层级字段由 `tier` **对齐更名为 `stage`**。
- 课程探索的 `tutorials@v2`：ref 结构化（textbook_ref/exercise_ref/parallel_ref 数组）、
  CJK 废止（英文原版 `title` 直接用英文）、`position` 五档、`intro` 100~200 字散文、
  `set_no` 纯数字 1~4、`name` 格式校验、part 全本/Vol.N 通配。

## 管线架构

### 领域两步管线（DomainPipeline）

```
输入：domain_name + scope_hint + 可选 reference + 可选 confirm_name_override
  ↓ step1 domain@v4：名称校验（name_check → NameConfirmationRequired 分支）+ 领域描述 +
  │     classic_tracks（0~4，kind=main/branch）+ entry_requirements + prior_knowledge
  ↓ step2 courses@v8：核心课程（course_id/name/aliases/track/summary/university_basis/stage/prerequisites）
  ↓     跨步校验：track ∈ classic_tracks；stage ∈ 四档；prerequisites 无自环/无环/引用合法
输出：report = {domain{final_name, description, level, stages, classic_tracks,
                      entry_requirements, prior_knowledge},
               courses[{course_id, name, aliases, track, summary, university_basis, stage, prerequisites}],
               path{notes, edges, graph_td}}
```

- 图 `graph_td` 由服务端按 `stage` 分组 + `prerequisites` 推导渲染（`render_graph_td`），
  LLM 不输出。
- 模型只生成报告；`DomainPipeline` 强制宽松 `max_tokens ≥ 16384`（courses@v8 单次输出较长，
  4096 会 `finish_reason=length` 截断；用 `max` 下限替代 `setdefault`，避免被
  `settings.llm_max_tokens`(4096) 覆盖）。
- **course_id 命名**：LLM 输出的 course_id 是**提案**（dry-run 预览），事实以领域标准答案为准
  （catalog 对齐课程编号式 `01_math_analysis`；扩展课程语义 slug，见[知识录入设计](knowledge-import.md)）。

### 课程单步管线（CoursePipeline）

```
输入：course 行（含 course_id/name/aliases/stage/prerequisites/note 课程介绍）+ domain_name + 可选 reference
  ↓ step tutorials@v2：2~4 套方案；每套 = set_no/name/position/intro/textbook_ref[]/exercise_ref[]/parallel_ref[]
输出：report = {course, tutorials[{...每套...，proposal_id 服务端追加}]}
```

### 模板版本化与审核

- 模板集中注册于 `src/qed_tracker/prompt_lab/templates.py`（唯一事实源），每个
  `PromptTemplate` 含 `task/step/version/name/system/build_user/validate`。
- 编号格式 `{task}/{step}@v{version}`，随调用写入 `qed_llm_calls.prompt_template`
  （`tests/test_prompt_template_ids.py` 守护）。
- `register()` 拒绝低版本覆盖；修改 prompt 文案或输出契约 = version+1，git 保留历史。
- **审核入口：模板代码即审核依据**，不建表；`list_templates()` 导出供
  `/prompt-templates` 与后续 CLI `templates` 使用。

### 先验注入

领域专属知识一律走 `src/qed_tracker/prompt_lab/priors.py`（`DOMAIN_PRIORS`，精确域名匹配），
模板本体保持学科中立（`tests/test_prompt_lab.py`、`tests/test_prompt_lab_course.py` 学科中立守护）。当前注册：
`math-domain`（tracks_hint 四档同步）与 `计算机科学与技术` 先验；`courses`/`tutorials`
按需注入 `get_prior_for_step(domain_name, step)`。

## 输入模式（direct / text / doc）

`providers/explore_advisor.py#_read_reference` 归一化参考输入（视为不可信数据，防注入）：

| 模式 | 说明 | 约束 |
| --- | --- | --- |
| `direct` | 无参考文本 | 默认 |
| `text` | 直接传入参考文本 | 必须非空 `ref_text`，截断至 `REF_TEXT_LIMIT` |
| `doc` | 读取本地 UTF-8 文本文件 | 必须存在 `ref_doc_path` |

非法 mode → `ExploreAdvisorError(INVALID_PARAMS)`（管线包装为 PipelineError）。
> 注：`re-explore`（run 路径）`mode` 默认值应为 `direct`，不得使用旧契约的 `web`。

## dry-run 语义（同步评估，不写任何表）

| 端点 | 管线 | 响应 |
| --- | --- | --- |
| `POST /api/v1/prompt-explores/dry-run` | 领域两步（整体评估） | `{dry_run: true, report, calls}` |
| `POST /api/v1/courses/{course_id}/prompt-explores/dry-run` | 课程单步 | `{dry_run: true, report, calls}` |

- **同步执行**、不写任何表（`qt_*` 与 `qed_*` 均不写），唯一痕迹是 `qed_llm_calls` 的
  LLM 日志（engine 置 None）。
- 领域 dry-run **整体输出两步报告预览**（两步管线都跑完），供用户评估与比对；不拆分两轮。
- 名称确认分支：`{"dry_run": true, "confirmation_required": true, "name_check": {...}}`，
  人工确认后以 `confirm_name_override` 重新发起。
- 错误码：`400 INVALID_PARAMS`（参数/doc 文件不可读/非法 mode/管线 INVALID_PARAMS）、
  `404 COURSE_NOT_FOUND`（课程 dry-run）、`409 LLM_UNAVAILABLE`（未配置 API_KEY 或管线初始化失败）、
  `502 LLM_FAILURE/BUDGET_EXHAUSTED`。

## run 语义（re-explore 后台任务，写状态机）

由 8900 探索会话管理经 `apply-results`/`re-explore` 推进（异步 run）。`re-explore` 提交
`domain_explore`/`course_explore` 后台任务（handler 注册于 `api/main.py`，`mode` 默认
`direct`）；探索完成后把结果写入 `explore_pending` 并按轮次置状态（领域第一轮 → `已生成`、
第二轮 → `待确认`；课程单轮 → `待确认`）。

- 领域 run 按**两轮审阅**推进（见下），`explore_pending` 增 `stage` 标记（`domain` / `courses`）。
- 失败或名称待确认时写入 error / name_confirmation 载荷。

### 统一两轮审阅时序（2026-09-03 用户裁决）

领域探索与手动录入统一为「两轮审阅」；dry-run 预览仍为整体，正式 run 拆两轮。
**整条链路每个状态只走一次**（线性），每轮语义与课程探索一致：生成 → 等待确认（可修改）
→ 人工完成一轮 prompt 结果确认：

```
第 1 轮（domain@v4 半场）：
  未开始 → 已生成（domain 报告生成，等待确认，可修改；explore_pending = review_results + step=domain）
  → 用户修改+确认 → 探索中（进入第 2 轮）
第 2 轮（courses@v8 半场）：
  探索中 → 待确认（courses 报告生成，等待确认，可修改；explore_pending = review_results + step=courses）
  → 用户修改+确认 → 已完成（领域探索结束）
```

- **已生成** = 领域探索第一轮（domain@v4 半场）报告就绪的待确认点；**探索中** = 第一轮已确认、
  第二轮（courses@v8 半场）进行中；**待确认** = 第二轮报告就绪的待确认点；**已完成** = 第二轮
  确认采纳，领域探索结束。
- 课程探索为单步、单轮（tutorials@v2）：`生成 → 待确认（等待确认，可修改）→ 确认 → 已完成`。
- 写主体：（LLM 轨由 8900 驱动生成与推进，8901 提供轮次确认与采纳端点；手动轨全程经 8901
  端点推进）详见[共享表设计](../architecture/shared-tables.md)状态机节。

## 探索状态机与载荷

- 领域与课程共用 6 态状态机（`未开始 → 已生成 → 探索中 → 待确认 → 已完成`，`探索中/待确认 → 失败`），
  写主体分工、`explore_pending` 载荷 structure 见[共享表设计](../architecture/shared-tables.md)状态机节。
- 手动导入（`/domains/import`）复用同一状态机：API 路径走 `已生成` 与 `待确认` 两极（分别对应
  第一轮/第二轮待确认点）；CLI 路径跳过两极直接 `已完成`（见[知识录入设计](knowledge-import.md)）。

## CLI（domains explore）

`qed-tracker domains explore` 经 8901 dry-run 同步执行（示例均为可解析用法）：

```
qed-tracker domains explore 高等数学
qed-tracker domains explore 高等数学 --scope "本科-硕士" --timeout 600
qed-tracker domains explore 高等数学 --mode text --ref-text "用户探索笔记内容"
qed-tracker domains explore 高等数学 --mode doc --ref-doc docs/notes.md
qed-tracker domains explore 高等数学 --confirm-name 高等数学
```

- `confirmation_required`（名称需人工确认）→ 打印 `name_check` 并以退出码 2 结束，带
  `--confirm-name` 重跑；8901 服务不可达 → 退出码 6；HTTP 错误 → 退出码 2。

## 实现状态与待对齐（Phase 2 清单）

| 项 | 当前 | 目标 |
| --- | --- | --- |
| 领域 run 审阅轮数 | 单轮 pending（domain+courses+path 合一） | 两轮（本轮裁决） |
| `re-explore` mode 默认值 | `web`（旧契约，属非法 mode） | `direct` |
| 模板版本残留 | 文档多处仍记 `tutorials@v1`/`path@v5`/三步 | 统一 `tutorials@v2`/`courses@v8`/两步 |
| 探索"发起端点"（prompt-explores/prompt-runs） | 文档残留 | 已随 0013 退役，删除残留 |

## 关联文档

| 文档 | 关系 |
| --- | --- |
| [知识录入设计](knowledge-import.md) | 手动入口（跳过 LLM 直接落库，复用同一状态机） |
| [共享表设计](../architecture/shared-tables.md) | 6 态状态机写主体、explore_pending 载荷、写权限例外（唯一事实源） |
| [数据库设计](../architecture/database-schema.md) | qed_domain/qed_course 探索字段、qt_knowledge/qt_books 落库 |
| [基线数据](../history/baselines/2026-08-prompt-explore-baseline.md) | 优化前后对照基线（qed_llm_calls 073~079） |
| [架构 API](../architecture/api.md) | dry-run / apply-results / re-explore 端点定义 |
