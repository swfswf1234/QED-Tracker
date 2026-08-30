# prompt 优化模块设计（领域/课程知识探索工作台）

状态：Accepted（2026-08-24 用户裁决：①独立并行模块，不动 QED-040/041 冻结契约；②分步管线，每步独立模板；③调用记录全部进共享表 `qed_llm_calls`，表改造通知 QED-Engine（REQ-060）；④~~run 聚合私有表 `qt_prompt_runs`~~（已废弃：2026-08-27 共享表重构，探索状态追踪移至 qed_domain/qed_course.exploration_stage）；⑤模板代码注册不建表（`prompt_lab/templates.py` 即审核入口）；⑥报告人工审核后手动应用入库；⑦方向分组 + 四档层级（基础/进阶/核心/冲刺）；⑧课程侧知识树→教程两步；⑨验收路径：模板审核后以「高等数学」真实冒烟，产出与 `tmp/高等数学探索.txt` 对比近似度）
最后更新：2026-08-26
进度追踪：[2026-08-prompt-optimization-progress.md](2026-08-prompt-optimization-progress.md)
关联任务：todo [QED-043（长期任务）](../trackers/todo.md)；需求方：QED-Engine 根仓库 REQ-060（qed_llm_calls 改造通知）；上游：根仓库 `docs/design/llm-gateway-and-model-management.md`（qed_llm_calls 契约）

## 背景与目标

QED-Tracker 现有 5 个 LLM 调用点（论文 plan/assess、教材评估、主链路预填、课程/领域探索），
prompt 全部硬编码于各 advisor、`qed_llm_calls.prompt_template` 恒空、无版本化、无人工审核入口。
本模块为「探索领域知识（确定领域内课程）」与「探索课程知识（探索教程）」建立独立的
prompt 工作台：分步管线的每个 prompt 模板集中注册、版本化；每次调用的**模板编号、完整问句、原始回答**
全部落共享表 `qed_llm_calls`；前端可查看并人工审核
（good/bad + 备注），合格后人工确认、手动应用领域/课程入库。后续新增 LLM 调用点按同一机制扩展。

与 QED-040/041 的关系：**独立并行**。040/041 按根仓库冻结契约（课程层探索 5 端点 + 新建领域 3 端点 +
手工维护 5 端点）继续实施，本模块不改动其任何端点、表与 advisor 行为（仅第 9 节涉及全仓库调用点补
`prompt_template` 编号，属审计字段补充，不改变调用行为）。

## 决策记录

| # | 决策点 | 裁决 |
| --- | --- | --- |
| P1 | 与 QED-040/041 关系 | 独立并行模块，不动 040/041 |
| P2 | 领域探索调用形态 | 分步管线：scope→courses→path→describe 四步，每步独立模板 |
| P3 | 调用记录载体 | 共享表 `qed_llm_calls`（prompt_template=模板编号、prompt=完整问句、response=原始回答） |
| P4 | 表改造归属 | 不自行改表；起草 REQ-060 通知 QED-Engine（扩展列+审核端点+检索过滤+控制台+文档） |
| P5 | ~~run 聚合存储~~ | **已废弃**（2026-08-27）：探索状态追踪移至 qed_domain/qed_course.exploration_stage；LLM 调用审计走 qed_llm_calls |
| P6 | 领域报告结构 | 方向分组（2~4）+ 四档层级（基础/进阶/核心/冲刺）+ 课程介绍；graph TD 由 edges 服务端渲染 |
| P7 | 课程侧形态 | 知识树（tree）→ 教程方案（tutorials）两步；**2026-08-26 修订：砍 tree，单步 tutorials**（用户裁决：课程已有介绍（note/summary），「一个 prompt 即可」——围绕课程介绍直接推荐「教材+习题集」成套方案） |
| P8 | 报告用途 | 人工审核后手动应用入库（qed_domain + qed_course） |
| P9 | 模板审核入口 | `src/qed_tracker/prompt_lab/templates.py` 全部集中；既有 5 advisor prompt 不迁移，只补编号 |
| P10 | 模板学科中立（2026-08-24 用户裁决） | 模板通用化：领域完全由输入决定，不得假设/套用特定学科划分（守护测试扫描学科绑定词）；领域专属知识（如高等数学的分析/代数/概率分线）一律经参考输入 text/doc 传入，探索物理/计算机等领域不得混入 |
| P11 | 评估模式先行（2026-08-24 用户裁决） | `POST /api/v1/prompt-explores/dry-run` 同步执行、只记录 LLM 日志（qed_llm_calls）、不入队/不 apply；用户先评估 LLM 效果与模板质量，再走正式流程（Phase B） |
| P12 | v3 三步管线 + 名称确认流（2026-08-24 用户裁决）：scope/describe 删除 → **domain@v1**（名称校验/规范化 final_name + 描述 ≤200 字 + classic_tracks 可空 + entry_requirements）/ **courses@v3**（清华命名基准、禁拆学期名、不过于抽象、aliases 别名、track∈主线、summary 60~200 字）/ **path@v3**（assignments: tier 四档 + prerequisites，服务端无环校验）；名称不一致时提前结束并返回 name_check 标记，人工确认后带 confirm_name_override 重发（正式流程 Phase B 做 run 待确认态 + 前端弹窗）；graph TD 由 prerequisites 服务端推导渲染 |
| P13 | 领域先验知识注册表（2026-08-24 用户裁决）：`prompt_lab/priors.py` 精确域名匹配（未命中不影响其它领域），首批高等数学（中文翻译的美版经典教材偏好/分析代数概率三主线提示/国内命名惯例/三门基石课锚点/QE 冲刺顶峰）；templates.py 保持学科中立（守护测试强制），后续课程侧管线复用同一份先验 |
| P14 | 调用审阅载体收口（2026-08-26 用户裁决）：REQ-060 已落地（qed_llm_calls 扩展列 task/step/review_status/review_note + GET 过滤增强 + PATCH review 端点 + web-ui 控制台审核页），取消 `tmp/prompt-eval/` 人工导出实践并删除该目录；调用审阅一律走共享表 + 根仓库前端，prompt 优化循环只以 qed_llm_calls call_id 为准 |
| P15 | 探索管线模型选型（2026-08-26 用户裁决）：采纳 QED-Engine 侧诊断——courses@v3 长结构化 JSON 生成在 qwen3.8 思考型大参数模型上推理延迟极端（>600s/>1200s 均未完成），prompt 本身无罪（qwen-plus 历史基线 42~56s 稳定）；**探索类管线步骤用 qwen-plus 级非思考型模型**；坚持推理型需单独放宽 `QED_LLM_TIMEOUT` 并接受分钟级等待。QED-Tracker 侧参照跑复核（calls 91~93，domain@v1 单步）：qwen3.8-max 39.8s / qwen3.7-plus 35.0s / qwen3.8-27b 28.3s 全部 name_check.valid=true **通过**——领域小步骤三模型均可用；课程检索优化后置（课程管线未重新规划前不做 courses 步模型对照）。配套落地：REQ-061 的 `QED_LLM_TIMEOUT` 键映射同步进本仓（默认 300s，原 60s 硬顶即基线 §7 超时预算开放问题的裁决落点=调大 timeout）；per-step 模型覆盖治理占位 todo QED-045 |
| P15a | 探索管线模型修订（2026-08-26 用户裁决）：探索管线切换 **qwen3.7-plus**——高等数学批全链验证可用（calls 97~99：domain 39.9s / courses 95.5s / path 47.3s 全 success；**courses@v3 95.5s 在旧默认 60s 下必死，REQ-061 同步必要性实证**）。P15 对 qwen3.8 思考型的禁用结论不变；性能代价：三步耗时约为 qwen-plus 的 2~5 倍 |

## 共享表改造通知（REQ-060，由 QED-Engine 实现）

**状态（2026-08-26）**：已落地（用户确认）。五件事全部完成：扩展列 / `GET /api/v1/llm/calls` 过滤增强 /
`PATCH /api/v1/llm/calls/{id}/review` 审核端点 / 控制台调用检索页增强 / 文档登记。下方"改造前的兼容路径"
（calls_review JSON 过渡）不再需要，Phase B 起审核态直接落共享表列。

`qed_llm_calls` 现有结构（根仓库 `backend/qed_engine/services/llm/call_log.py`）：
`id / service / mode / provider / model / endpoint / prompt_template VARCHAR(255) / prompt MEDIUMTEXT /
response MEDIUMTEXT / duration_ms / status / error / created_at`。

请求改造五件事（本子项目只发通知，不代改）：

1. **扩展列**（全部可空，兼容既有行）：
   - `task VARCHAR(64)`：调用任务域（如 `domain-explore` / `course-explore` / `paper-plan` / `book-eval` / `mainline-prefill`…）
   - `step VARCHAR(32)`：任务内步骤（如 `scope` / `courses` / `path` / `describe` / `tree` / `tutorials`）
   - `review_status VARCHAR(16) DEFAULT 'unreviewed'`：人工审核态（`unreviewed` / `good` / `bad`）
   - `review_note VARCHAR(1000) DEFAULT ''`：审核备注
2. **检索端点增强** `GET /api/v1/llm/calls`：支持按 `task` / `step` / `prompt_template` / `review_status` 过滤（与既有 service/mode/model/status 过滤并存）。
3. **新增审核端点** `PATCH /api/v1/llm/calls/{id}/review`：body `{review_status, review_note}`，落扩展列。
4. **控制台调用检索页增强**（`web-ui/src/pages/LlmCalls.tsx`）：模板聚类视图 + 逐条审核标注 UI + 新过滤条件。
5. **文档登记**：`docs/architecture/database-design.md`（qed_llm_calls 段）与 `docs/design/llm-gateway-and-model-management.md` 补新列与端点；契约测试随行。

**改造前的兼容路径（本模块可用现有列跑通）**：`prompt_template` 列编码 `{task}/{step}@v{version}`
（如 `domain-explore/scope@v1`），问句/回答入 `prompt` / `response`；审核态暂存 `qt_prompt_runs` 与
`qt_prompt_runs.calls_review` JSON（REQ-060 落地后迁回共享表列）。
`_record_call` 当前硬编码 `prompt_template=""`（`llm_client.py:186`），第 9 节修复。

## 模块落位

```
src/qed_tracker/prompt_lab/
├── templates.py          # 模板注册表（领域4步 + 课程2步；用户审核入口）
├── pipeline.py           # 领域管线 + 课程管线编排器
└── __init__.py
src/qed_tracker/db/prompt_repository.py   # qt_prompt_runs 仓储
src/qed_tracker/db/models.py              # 追加 QtPromptRun（迁移 0009）
src/qed_tracker/api/main.py               # /api/v1/prompt-* 端点组
src/qed_tracker/cli.py                    # qed-tracker promptlab 子命令
```

复用：`LlmClient`（local/gateway 双模式、预算、调用落库）+ `ExploreAdvisorBase._structured`
（严格 JSON 校验 + 坏 JSON 一次修复重试；修复调用另行落一行，`prompt_template` 同编号、内容含
repair 上下文）。管线不再复制骨架：`templates.py` 的模板对象携带 `build_user` 与 `validate`，
管线按步骤调用基类 `_structured`？——**否**：ExploreAdvisorBase 已含 _complete/_structured 通用骨架，
管线直接继承复用（contract_version=`prompt-optimize-v1`）。

## 数据模型：qt_prompt_runs（私有，用户已审核）

一行 = 一次探索运行（领域或课程）：

| 列 | 类型 | 说明 |
| --- | --- | --- |
| run_id | VARCHAR(32) PK | `prd_<12hex>` |
| task | VARCHAR(16) | `domain_explore` / `course_explore` |
| subject | VARCHAR(100) | 领域名（domain_explore）或课程 id（course_explore） |
| scope_hint | VARCHAR(500) | 默认范围说明（默认「大学往上的知识内容（本科-硕士）」） |
| params | JSON | mode/ref_text/ref_doc_path 快照 |
| status | VARCHAR(16) | running→ready→applied；failed；`running` 幂等查重 |
| report | JSON | 聚合报告（scope/courses/path(graph TD 文本)/describe 或 tree/tutorials） |
| review_status | VARCHAR(16) | run 级审核：unreviewed/approved/rejected |
| calls_review | JSON | REQ-060 落地前的过渡：[{call_id/prompt_template, review_status, review_note}] |
| error | JSON | {code, message}（LLM_UNAVAILABLE/INVALID_PARAMS/BUDGET_EXHAUSTED） |
| task_id | VARCHAR(32) | 关联 8901 内部任务 ID |
| created_at / updated_at | DATETIME | |

索引：`ix_qt_prompt_runs_task`、`ix_qt_prompt_runs_status`、`ix_qt_prompt_runs_subject`。
迁移 `0009_prompt_runs.py`（DDL ASCII-only，中文注释落库，风格同 0008）。

## 模板注册表（代码即审核入口）

```python
@dataclass(frozen=True)
class PromptTemplate:
    task: str        # domain-explore / course-explore
    step: str        # scope/courses/path/describe/tree/tutorials
    version: int     # v1 起步；修改 prompt = version+1（git 保留历史）
    name: str        # 展示名（如「领域范围定义」）
    system: str      # system 内容（含防注入 + 严格 JSON 约束）
    build_user: Callable[[dict], str]   # 由 payload 生成 user 内容（含输出格式契约）
    validate: Callable[[object], Any]   # 输出校验（非法触发一次修复重试）
```

- 编号编码：`f"{task}/{step}@v{version}"`（落 `qed_llm_calls.prompt_template`）。
- `list_templates()` / `get_template(task, step)` 供 API/CLI/管线使用；`GET /api/v1/prompt-templates`
  从代码导出（含每模板当前版本与内容全文），前端模板库视图直接消费；历史版本在 git。
- 新任务接入 = 新模板对象 + 管线步骤，无需改表。

## 领域管线（4 步，输入：domain_name + scope_hint + 可选参考文本）

1. **scope 范围定义**：`{level, description, boundaries[], directions[{name, summary}] 2~4}`；
   输入含 domain_name 与默认范围（本科-硕士）。validate：非空、数量、文本长度。
2. **courses 课程发现**（参照顶尖大学课程安排）：`{directions:[{name, courses:[{slug,name,university_basis,core:bool,keywords[]}]}]}`；
   slug 同 QED-041 规则、方向引用 step1、每方向 2~6 门、总数 6~16。validate 全量。
3. **path 路线编排**：`{stages:[{tier, name} 四档基础/进阶/核心/冲刺], nodes:[{slug, tier}], edges:[{from,to}], notes:[]}`；
   tier 仅四档枚举、节点 ⊆ step2 课程、edges 引用本批节点、无自环。**graph TD 文本由服务端渲染**
   （mermaid：按 tier 分层 + edges 连边，格式参照 tmp/高等数学探索.txt）。
4. **describe 课程阐述**：`{courses:[{slug, intro 100~200字, tier, direction}]}`；
   tier 与 step3 一致，direction ∈ step1 directions，intro 长度校验，课程全覆盖。

聚合 `report = {scope, courses(合并 tier/direction/intro), path({stages,edges,graph_td}), university_basis 汇总}`。

## 课程管线（1 步，输入：course 行 + 领域名（先验注入）+ 可选参考文本）

**2026-08-26 用户裁决重新设计**：砍 tree，单 prompt（P7 修订）。

1. **tutorials 教程方案**（`course-explore/tutorials@v1`）：
   输入 payload：`{course（含 note 课程介绍）, book_preference（priors 教材偏好注入）, reference}`；
   输出 `{tutorials:[{set_no, set_name, textbook, exercise|null, reason}] 2~4 套}`。
   契约细目（2026-08-26 用户裁决）：
   - `set_name` = 中文教程名+作者（如「教程1：课程名（作者）」）；`set_no` 本批唯一；
   - `textbook.title` 必须**中文书名**（真实中文译名/原名）；外文原版名进 `original_title`（禁全外文主标题）；
   - `authors` 非空（谁的书）；`version{edition, publisher, year}` 附注（可空）；
   - `roles` 对齐 qt_books：教材 `["textbook"]`；教材自带习题集 `["textbook","exercises"]`；
     纯习题集条目 `["exercises"]`；textbook 条目必须含 textbook、exercise 条目必须含 exercises；
   - `position ∈ {beginner, comprehensive, advanced}`（新手入门/全面系统/深度研究；英文枚举防变体污染）；
   - `intro` 100~300 字，六要素：作者与学派背景 / 经典地位依据（顶尖大学指定、社区公认）/
     风格与学理特点 / 版本与语言（中译本对应原版） / 适合人群与用法 / 教材-习题集配套关系；
   - `exercise`：教材自带习题集（roles 含 exercises）时可 null（同源）；否则必须给出独立习题集；
     至少一套方案须含习题集；
   - 各套不得重复同一主教材，风格互补（一套初学者向 + 一套深入向为佳）；`reason` ≤50 字。
   聚合 `report = {course, tutorials}`（enrich：proposal_id=pp_*）。

落库映射（Phase C 预备，沿 2026-08-25 约定）：set_name+authors → knowledge.name；
textbook → textbook_ref{title, authors, version}+textbook_intro；exercise → exercise_ref+exercise_intro；
roles 含 exercises → qt_books roles=[textbook, exercises]（同陈纪修现存行）。

## API 端点组（8901，/api/v1/prompt-*）

| 端点 | 语义 |
| --- | --- |
| `POST /api/v1/prompt-explores` | 发起（body: task/subject/scope_hint?/mode/ref_text?/ref_doc_path?）；202 入队；同对象 running 幂等返回既有 run_id；400/409 同现有风格 |
| `GET /api/v1/prompt-runs?task=&status=&review_status=&limit=&offset=` | 历史列表 |
| `GET /api/v1/prompt-runs/{run_id}` | 详情（report + 关联 qed_llm_calls 调用明细按 prompt_template 查） |
| `POST /api/v1/prompt-runs/{run_id}/apply` | 领域报告人工确认后落库：create domain（name/description/stages=四档）+ courses（stage=tier、note=方向、sort_order 按 path 顺序、prerequisites 由 edges 推导）；冲突 409 不覆盖 |
| `PATCH /api/v1/prompt-runs/{run_id}/review` | run 级审核（approved/rejected + note）；写入 calls_review 过渡 JSON（REQ-060 落地后改共享表列并保留端点） |
| `GET /api/v1/prompt-templates` | 模板库导出（task/step/version/name/content） |

CLI：`qed-tracker promptlab domain "高等数学"`（`--scope`/`--ref-doc`）、`qed-tracker promptlab course <course_id>`
（同参数）、`qed-tracker promptlab runs list|show|apply|review`、`qed-tracker promptlab templates`。
探索为后台任务（AsyncTask，与既有任务编排一致），CLI 默认 `--wait` 轮询。

## 测试策略（零公网）

- 管线每步：httpx.MockTransport 夹具——正常流 / 坏 JSON 一次修复成功 / 修复仍失败抛错 / 预算耗尽；
- validate 单测：数量越界、方向/tier 枚举越界、edges 引用不完整、自环、intro 超长、slug 非法；
- graph TD 渲染单测：四档分层 + 边 + 节点名（含中英文）；
- 聚合单测：四步 report 合并、冲突标记（tier 不一致）、apply 幂等与 409；
- 仓储单测（qt_prompt_runs CRUD + 状态机）；API 契约测试（发起/列表/详情/apply/review/templates ，
  含 400/404/409/running 幂等）；`_record_call` 修复测试（prompt_template 落库）；
- 既有 5 调用点补编号测试（各 advisor 实例化后调用,断言 qed_llm_calls 参数）。

## 实施阶段

- **Phase 0**（已完成 2026-08-24）：REQ-060 登记根仓库 todo；`_record_call` 修复 +
  5 调用点补编号（TDD，零行为变化）+ 文档白名单与 plans/index 登记。
- **Phase A**（已完成 2026-08-24）：迁移 0010 + `prompt_lab/templates.py`（领域 4 步，
  学科中立化 P10）+ 管线（step_calls 明细）+ 仓储 + 全部单测。
- **Phase B0 评估模式**（已完成 2026-08-24）：`POST /api/v1/prompt-explores/dry-run`
  （P11：同步执行、只留 LLM 日志、不落正式表）+ 契约测试；**v3 三步管线重构落地（P12/P13，
  经四轮真实评估迭代：path 缺 slug→payload 补对照、describe 缺方向清单→并入 courses、
  日志缺编号→逐步透传、slug 连字符→v3 文案强化）**；「高等数学」（确认流实战：LLM 建议"数学"，
  人工裁决保留原名后 confirm_name_override 重跑成功，16 门课清华课程代码依据）与
  「计算机科学与技术」（direct 一次通过，16 门课）双领域 ready；审阅文件导出 `tmp/prompt-eval/`
  （**该通道已取消**：P14，2026-08-26 REQ-060 落地后审阅走共享表 + 根仓库前端，目录已删除）；
  模型选型参照跑（2026-08-26，P15）：domain@v1 单步三模型复核全通过（calls 91~93，
   见基线文档 §3 参照跑台账），课程检索优化后置。
- **探索轮 v2/v4/v4（P16，2026-08-26，calls 100~102）**：domain@v2 / courses@v4 / path@v4 全链
  验证通过（qwen3.7-plus，高等数学）；domain 文案五项落地（括号限定名/scope 权威边界/description
  质量锚点/下游用途/中文输出）；priors 四主线对齐 + 分步裁剪注入；pipeline scope_hint 贯穿 +
  tracks 全量含 summary + count_range + university_basis 可空；输出 13 门（10 slug 直接命中 + 2
  slug 漂移 + 1 extra 高等概率论）；DAG 5/10 完全一致；classic_tracks 漂移（LLM 输出"基础
  数学/应用数学/概率论与数理统计"三主线而非 golden 四主线），需后续优化 priors tracks_hint 文案。
  知识文档 `docs/knowledge/math-advanced.json`（12 门 + 17 扩展 + DAG）已定稿并迁入
  `docs/knowledge/`（2026-08-29 正本位置；旧副本 plans/guides 已删除）。
- **Phase B 正式流程**：`/api/v1/prompt-explores`（202 入队）
  + runs 列表/详情/review/apply 端点组 + CLI（依据 B0 评估结论启动）。
- **Phase B0' 课程管线单步落地（2026-08-26，本轮）**：`course-explore/tutorials@v1` 模板注册
  （中文书名优先/original_title 承载原版/roles 角色/position 三档/六要素 intro/同源可空）+ priors
  tutorials 步键集（textbook_preference 注入）+ `CoursePipeline`（单步调用 + enrich proposal_id；
  contract=prompt-optimize-v3）；守护测试 20 条全过（模板全边界 + payload 注入断言 + 坏 JSON 修复 +
  预算耗尽）；全量 378 passed + 3 skipped + ruff clean。**真实评估待执行**：评估脚本
  `tmp/run_course_tutorials.py` 待执行。
- **Phase C**：apply 落库（领域报告 → qed_domain/qed_course）+ 模板按审核反馈迭代
  （version+1）+ 全量门禁全绿 + QED-043 台账更新 + 回执 REQ-060。

## 后续 LLM 调用点评估（用户预研要求）

| 调用点 | 归属 | 状态 |
| --- | --- | --- |
| 论文 plan / assess | 既有（bailian） | 已存在，补编号 |
| 教材评估 book-eval | 既有（book_advisor） | 已存在，补编号 |
| 主链路预填 mainline-prefill | 既有（main_line/advisor） | 已存在，补编号 |
| 课程/领域探索 course/curriculum-explore | 既有（QED-040/041） | 已存在，补编号 |
| 领域/课程知识探索（本模块） | 新（prompt_lab） | 本次 |
| 知识行材料简介预填 | 预留（migrate_knowledge 注释「简介留空待 LLM 预填」） | 后续候选 |
| 课程介绍/领域描述补全 | 未启动 | 后续候选 |
| 下载资源元数据预填 | 未启动 | 后续候选（API 摘要仍归 Axiom-Flow 边界外） |

**结论**：qed_llm_calls 扩展列（task/step/review_*）与模板注册机制按「通用多点」设计，新调用点
只需「注册模板 + 补传编号」即自动可审，无需再改表。模板库与审核界面为根仓库 web-ui 职责
（已含 REQ-060 控制台增强），8901 侧透出数据即可。
