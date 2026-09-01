# QED-Tracker 探索功能总览

状态：Current
最后更新：2026-09-01
任务类型：参考文档（非实施计划）
需求方：QED-Engine（跨项目探索流程）
执行方：QED-Tracker（8901 探索管线 + 端点 + 状态机）

## 1. 概述

QED-Tracker 的探索功能是 QED 知识体系构建的核心能力——通过 LLM 驱动的管线自动发现
领域内的课程结构与每门课程的教材方案，供用户审阅后落库为正式知识条目。

探索功能在两个层级运作：

| 层级 | 管线 | 输入 | 输出 |
|---|---|---|---|
| 领域探索 | domain@v1 → courses@v3 → path@v3 | 领域名 + 范围说明 + 可选参考文本 | 课程清单 + 先修 DAG + 层级分布 |
| 课程探索 | tutorials@v1 | 课程行 + 领域名 + 可选参考文本 | 2~4 套教材+习题集方案 |

### 与 QED-Engine 8900 的分工

| 职责 | 8900（QED-Engine） | 8901（QED-Tracker） |
|---|---|---|
| 探索会话管理 | ✅ 创建/启动/状态流转 | — |
| LLM 管线执行 | — | ✅ 模板/priors/管线/LLM 调用 |
| explore_pending 写入 | ✅ 探索结果载荷 | — |
| apply-results/re-explore | — | ✅ 用户确认应用/重新探索 |
| exploration_stage 写入 | ✅ 未开始→已生成→探索中→待确认 | ✅ 待确认→已完成（apply 时） |
| 离线降级直写 | ✅ description/stages/exploration_stage | — |

## 2. 探索管线架构

### 2.1 领域探索管线（三步）

```
输入：domain_name + scope_hint + 可选 reference
  ↓
step1: domain@v1（名称校验 + 描述 ≤200字 + classic_tracks + entry_requirements）
  ↓  → name_check.valid=false 时抛 NameConfirmationRequired，人工确认后带
  ↓     confirm_name_override 重发
step2: courses@v3（课程发现：每方向 2~6 门，总数 6~16；slug/name/track/summary 60~200字）
  ↓  → track 必须逐字 ∈ classic_tracks；summary 长度校验
step3: path@v3（路线编排：四档 tier + prerequisites DAG + 无环校验）
  ↓  → graph_td 由服务端 Mermaid 渲染
输出：report = {scope, courses(合并 tier/direction/intro), path({stages,edges,graph_td})}
```

**代码位置**：
- 管线编排：`src/qed_tracker/prompt_lab/pipeline.py`（DomainPipeline）
- 模板注册：`src/qed_tracker/prompt_lab/templates.py`（domain-explore/domain@v1, courses@v3, path@v3）
- 先验注入：`src/qed_tracker/prompt_lab/priors.py`（领域专属知识，精确域名匹配）

### 2.2 课程探索管线（单步）

```
输入：course 行（含 note 课程介绍）+ 领域名 + 可选 reference
  ↓
step1: tutorials@v1（教程方案：2~4 套，每套=教材+习题集+推荐理由）
  ↓  → textbook.title 必须中文；authors 非空；position ∈ {beginner,comprehensive,advanced}
  ↓  → intro 100~300 字（六要素：作者/地位/风格/版本/适合人群/配套关系）
  ↓  → 至少一套须含习题集；各套不得重复同一主教材
输出：report = {course, tutorials}
```

**代码位置**：
- 管线编排：`src/qed_tracker/prompt_lab/pipeline.py`（CoursePipeline）
- 模板注册：`src/qed_tracker/prompt_lab/templates.py`（course-explore/tutorials@v1）
- 先验注入：`src/qed_tracker/prompt_lab/priors.py`（教材偏好注入）

### 2.3 模板版本化与审核

模板集中注册于 `templates.py`，每个模板对象包含：
- `task/step@v{version}` 编号（落 `qed_llm_calls.prompt_template`）
- `system` 内容（含防注入 + 严格 JSON 约束）
- `build_user` 函数（由 payload 生成 user 内容）
- `validate` 函数（输出校验，非法触发一次修复重试）

模板修改 = version+1，git 保留历史。新任务接入 = 新模板对象 + 管线步骤，无需改表。

## 3. 端点清单

### 3.1 dry-run 端点（同步评估，不写任何表）

| 端点 | 语义 | 响应 |
|---|---|---|
| `POST /api/v1/prompt-explores/dry-run` | 领域探索同步评估 | `{dry_run: true, report: {...}, calls: [...]}` |
| `POST /api/v1/courses/{course_id}/prompt-explores/dry-run` | 课程探索同步评估 | `{dry_run: true, report: {...}, calls: [...]}` |

- 同步执行、**不写任何表**（qt_* 与 qed_* 均不写），唯一痕迹 `qed_llm_calls`
- 错误码：400 INVALID_PARAMS / 404 NOT_FOUND / 409 LLM_UNAVAILABLE / 502 LLM_FAILURE / BUDGET_EXHAUSTED

### 3.2 用户审阅端点（REQ-067-B12，已实现）

| 端点 | 语义 | 响应 | 前置条件 |
|---|---|---|---|
| `POST /api/v1/domains/{domain_id}/apply-results` | 确认领域探索结果 | `{domain_id, courses_kept}` | exploration_stage=待确认 |
| `POST /api/v1/domains/{domain_id}/re-explore` | 重置领域探索 | `{task_id}` (202) | exploration_stage=待确认 |
| `POST /api/v1/courses/{course_id}/apply-results` | 确认课程探索结果 | `{course_id, tutorials_kept}` | exploration_stage=待确认 |
| `POST /api/v1/courses/{course_id}/re-explore` | 重置课程探索 | `{task_id}` (202) | exploration_stage=待确认 |

- apply-results：设 exploration_stage=已完成，清空 explore_pending，删除未选课程/教程
- re-explore：设 exploration_stage=探索中，清空 explore_pending，提交后台任务
- 错误码：404 NOT_FOUND / 409 INVALID_TRANSITION / 422 INVALID_PARAMS

### 3.3 探索发起端点（由 8900 调用）

| 端点 | 语义 |
|---|---|
| `POST /api/v1/prompt-explores` | 发起领域探索（入队） |
| `GET /api/v1/prompt-runs` | 探索运行历史列表 |
| `GET /api/v1/prompt-runs/{run_id}` | 探索运行详情 |
| `POST /api/v1/prompt-runs/{run_id}/apply` | 领域报告确认后落库 |
| `PATCH /api/v1/prompt-runs/{run_id}/review` | run 级审核 |

## 4. 状态机（6 态）

领域和课程共用同一状态机（`exploration_stage` 字段）：

```
未开始 → 已生成 → 探索中 → 待确认 → 已完成
                        └──────────────→ 失败

待确认 --re-explore--> 探索中
失败 --8900 重新发起--> 探索中
```

### 状态定义与 explore_pending 载荷

| 状态 | 触发时机 | 写主体 | explore_pending |
|---|---|---|---|
| 未开始 | 手动创建 | 创建方 | NULL |
| 已生成 | 探索会话产出报告 | 8900 | NULL |
| 探索中 | 探索会话启动 | 8900 | NULL |
| **待确认** | **探索完成，等待用户审阅** | **8900** | **领域：`{kind:"review_results", courses:[...], domain_report}`；课程：`{kind:"review_results", tutorials:[...]}`** |
| 已完成 | 用户确认应用 | 8901（apply-results） | NULL（采纳时清空） |
| 失败 | 探索失败/服务重启中断 | 8901（lifespan 清理） | `{kind:"failed", error:"..."}` |

### explore_pending 载荷结构

**领域（待确认态）**：
```json
{
  "kind": "review_results",
  "courses": [
    {"course_id": "mathematical_analysis", "name": "数学分析", "track": "分析学", "tier": "基础"}
  ],
  "domain_report": {"scope": {...}, "path": {"stages": [...], "edges": [...]}}
}
```

**课程（待确认态）**：
```json
{
  "kind": "review_results",
  "tutorials": [
    {"set_no": "1", "set_name": "教程1：数学分析（Rudin）", "textbook": {...}, "exercise": {...}, "reason": "..."}
  ]
}
```

**失败态**：
```json
{"kind": "failed", "error": "服务重启，探索任务中断"}
```

## 5. 跨项目对齐

### 5.1 写权限例外（用户裁决 D2，2026-08-27）

| 表 | 8900 离线直写允许列 | 仍然禁止列 |
|---|---|---|
| qed_domain | description、stages、exploration_stage、explore_pending | level、scope、classic_tracks、path_results |
| qed_course | stage、sort_order、description、aliases、exploration_stage、explore_pending | track、related_targets |

### 5.2 探索流程时序

```
1. 8900 创建探索会话
2. 8900 设 exploration_stage=探索中
3. 8900 调用 8901 dry-run 端点（同步，返回结果）
4. 8900 将结果写入 explore_pending 字段
5. 8900 设 exploration_stage=待确认
6. 前端轮询显示「待确认」，用户点击「查看结果」
7. 用户选择：
   a. 确认应用 → 8901 POST /apply-results → 设 exploration_stage=已完成
   b. 重新探索 → 8901 POST /re-explore → 设 exploration_stage=探索中 → 回到步骤 2
```

### 5.3 exploration_stage 写主体分工

| 状态 | 写主体 | 说明 |
|---|---|---|
| 未开始→探索中 | 8900 | 探索会话启动 |
| 探索中→已生成 | 8900 | dry-run 报告返回 |
| 已生成→待确认 | 8900 | 用户确认后 |
| 待确认→已完成 | **8901** | apply-results 端点 |
| 待确认→探索中 | **8901** | re-explore 端点 |
| 探索中→失败 | **8901** | lifespan 启动清理 |

## 6. 基线与优化

### 6.1 v3 管线基线数据

基线数据冻结于 `docs/plans/2026-08-prompt-explore-baseline.md`，包含：

- **高等数学批**（qed_llm_calls 74~76）：12 门课程，四主线（分析学/代数学/概率与统计/几何与拓扑）
- **计算机科学与技术批**（qed_llm_calls 77~79）：16 门课程
- **模型选型参照**（calls 91~93）：qwen3.8-max / qwen3.7-plus / qwen3.8-27b 三模型对照
- **Round-1 重跑**（calls 97~99）：qwen3.7-plus 全链验证（domain 39.9s / courses 95.5s / path 47.3s）

### 6.2 模型选型结论（用户裁决 P15/P15a）

- 领域小步骤：三模型均可用（28~40s）
- 课程管线（courses@v3 长 JSON）：**必须用 qwen-plus 级非思考型模型**
- qwen3.8 思考型：推理延迟极端（>600s/>1200s 未完成），禁用
- 探索管线当前用 qwen3.7-plus（用户裁决 2026-08-26）

### 6.3 优化循环机制

```
改 templates.py / priors.py → 模板 version+1 → dry-run 重跑（qed_llm_calls 新 call_id）
→ 与基线（§6.1）对比 → 差距登记回基线文档第 6 节 → 用户审核裁决
```

## 7. 手动探索

手动探索（用户裁决 D1~D10，2026-08-29）与 LLM 探索共用同一状态机链路：

| 操作 | 端点/CLI | 语义 |
|---|---|---|
| 领域 JSON 导入 | `POST /api/v1/domains/import` / `qed-tracker domains import` | 写 qed_domain + qed_course，exploration_stage=已完成 |
| 课程 JSON 导入 | `POST /api/v1/knowledge` / `qed-tracker knowledge import` | 复用 A2 建 draft qt_knowledge |
| 手动下载 | `POST /api/v1/books/{id}/import` / `qed-tracker books import` | 本地 PDF → 校验 → 拷入数据根 → 登记 downloaded |

详细设计见 `docs/plans/2026-08-knowledge-dual-flow.md`。

## 8. 关联文档索引

| 文档 | 状态 | 内容 |
|---|---|---|
| [prompt 优化模块设计](2026-08-prompt-optimization.md) | Accepted | 模板注册/priors/管线/API/调用审计 |
| [领域探索 prompt 优化基线](2026-08-prompt-explore-baseline.md) | Active | v3 管线基线数据 + 优化循环 |
| [QED-Engine 探索对齐承接设计](../history/baselines/2026-08-engine-exploration-alignment.md) | 已归档 | 跨项目对齐（QED-047/048） |
| [REQ-067-B10/B12 实现计划](../history/baselines/2026-08-31-req067-b10-b12-exploration-stage.md) | Completed | 待确认状态 + apply-results/re-explore 端点 |
| [教材探索与下载双轨](2026-08-knowledge-dual-flow.md) | Draft | 手动+自动双轨 + 知识体系梳理 |
| [共享表设计](../architecture/shared-tables.md) | Accepted | 状态机 6 态 + explore_pending 载荷 + 写权限 |
| [API 设计](2026-08-api-design.md) | Draft | 端点五要素契约 |

## 9. 已完成事项记录

| 日期 | 事项 | 验证 |
|---|---|---|
| 2026-08-24 | prompt 优化模块设计 Accepted（P1~P9） | 用户裁决 |
| 2026-08-25 | v3 管线基线数据冻结（高等数学/计算机科学双批） | qed_llm_calls 74~79 |
| 2026-08-26 | 模型选型结论（P15/P15a）+ timeout 调大（REQ-061） | 用户裁决 |
| 2026-08-27 | 共享表重构（migration 0013 删旧探索表） | 测试通过 |
| 2026-08-28 | 跨项目对齐四项承接（QED-047/048） | 评审通过 |
| 2026-08-28 | 课程 dry-run 端点实现（POST /courses/{id}/prompt-explores/dry-run） | 339 passed |
| 2026-08-28 | 写权限例外 + exploration_stage 写主体澄清 | shared-tables.md Accepted |
| 2026-08-29 | 手动+自动双轨设计（用户裁决 D1~D10） | 用户裁决 |
| 2026-09-01 | REQ-067-B12：待确认状态 + apply-results/re-explore 端点 | 86 passed（17 新测 + 69 回归） |
| 2026-09-01 | QED-047：课程层探索 dry-run 端点（502 测试补全） | 428 passed（契约 6 条全绿，错误码 400/404/409/502 对齐） |
| 2026-09-01 | QED-048：写权限例外 + exploration_stage 写主体 + api-design Draft 同步 | shared-tables.md Accepted；api-design Draft 补入 exploration_stage/path_results；428 passed |

## 10. 待办事项

| 任务 | 状态 | 关联 |
|---|---|---|
| QED-047：课程层探索 dry-run 端点 | 已完成 | `docs/trackers/completed.md` |
| QED-048：写权限修订与 API 设计补充 | 已完成 | `docs/trackers/completed.md` |
| QED-043：prompt 优化长期任务 | 进行中 | `docs/trackers/todo.md` |
| QED-050：教材探索与下载双轨 | 进行中 | `docs/trackers/todo.md` |
| Phase B 正式流程（run 待确认态 + 前端弹窗） | 待开始 | prompt-optimization.md |
