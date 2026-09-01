# LLM 探索管线设计

状态：Draft
任务类型：B
最后更新：2026-09-01
需求方：QED-Engine（REQ-064/REQ-065/REQ-067）
目标项目：QED-Tracker
评审方：用户

## 背景

QED-Tracker 的探索能力基于 LLM 模板管线，分两条链路：
- **领域探索**（三步）：domain@v1 → courses@v3 → path@v3，输出领域结构 + 课程体系 + 学习路径
- **课程探索**（单步）：tutorials@v1，输出教材+习题集推荐方案

两条链路均支持 dry-run（同步评估、不写表）和正式 run（异步、写状态机）。探索结果经用户审阅后通过 apply-results/re-explore 端点确认或重试。

## 当前实现

### 管线架构

| 管线 | 步骤 | 模板版本 | 代码位置 | 测试 |
|---|---|---|---|---|
| 领域三步 | domain@v1 → courses@v3 → path@v3 | domain-explore/domain@v3, courses@v5, path@v5 | `prompt_lab/pipeline.py` DomainPipeline | `test_prompt_lab.py` 27+ 用例 |
| 课程单步 | tutorials@v1 | course-explore/tutorials@v1 | `prompt_lab/pipeline.py` CoursePipeline | `test_prompt_lab.py` + `test_prompt_lab_api.py` 6 用例 |

### 端点清单

#### dry-run 端点（同步评估，不写任何表）

| 端点 | 语义 | 响应 |
|---|---|---|
| `POST /api/v1/prompt-explores/dry-run` | 领域探索同步评估（三步管线） | `{dry_run, report: {domain, courses, path}, calls}` |
| `POST /api/v1/courses/{course_id}/prompt-explores/dry-run` | 课程探索同步评估（单步管线） | `{dry_run, report: {course, tutorials}, calls}` |

错误码：400 INVALID_PARAMS / 404 NOT_FOUND / 409 LLM_UNAVAILABLE / 502 LLM_FAILURE

#### 用户审阅端点（explore_pending 载荷操作）

| 端点 | 语义 | 前置条件 |
|---|---|---|
| `POST /domains/{id}/apply-results` | 确认领域探索结果 → exploration_stage=已完成 | exploration_stage=待确认 |
| `POST /domains/{id}/re-explore` | 重置领域探索 → exploration_stage=探索中 | exploration_stage=待确认 |
| `POST /courses/{id}/apply-results` | 确认课程探索结果 → exploration_stage=已完成 | exploration_stage=待确认 |
| `POST /courses/{id}/re-explore` | 重置课程探索 → exploration_stage=探索中 | exploration_stage=待确认 |

#### 探索发起端点（异步，写表）

| 端点 | 语义 | 写入 |
|---|---|---|
| `POST /api/v1/prompt-explores` | 发起领域探索（后台任务） | qed_llm_calls |
| `GET /api/v1/prompt-runs` | 探索运行历史列表 | — |
| `GET /api/v1/prompt-runs/{run_id}` | 探索运行详情 | — |
| `POST /api/v1/prompt-runs/{run_id}/apply` | 领域报告确认后落库 | qed_domain/qed_course |
| `PATCH /api/v1/prompt-runs/{run_id}/review` | run 级审核 | — |

### 状态机（6 态）

```
未开始 → 已生成 → 探索中 → 待确认 → 已完成
                                  ↘ 失败
```

- 8900 写：未开始→探索中、探索中→已生成、已生成→待确认
- 8901 写：待确认→已完成（apply-results）、待确认→探索中（re-explore）、探索中→失败（lifespan 清理）

### explore_pending 载荷

```json
// 领域
{"kind": "review_results", "courses": [...], "domain_report": {...}}
// 课程
{"kind": "review_results", "tutorials": [...]}
```

### 写权限例外（8900 离线降级）

| 表 | 8900 可写列 | 禁写列 |
|---|---|---|
| qed_domain | description, stages, exploration_stage, explore_pending | level, scope, classic_tracks, path_results |
| qed_course | stage, sort_order, description, aliases, exploration_stage, explore_pending | track, related_targets |

### 先验注入

- `priors.py`：math-domain priors（tracks_hint 四档同步）
- `priors.py`：CS-domain priors（`DOMAIN_PRIORS["计算机科学与技术"]`）

### 模板版本化

- 模板注册于 `prompt_lab/templates.py`，版本化管理
- 审核入口：模板代码即审核依据，不建表

## 优化目标

| 优化项 | 目标 | 关联任务 |
|---|---|---|
| 领域管线模板审核 | domain@v3 + courses@v5 + path@v5 模板输出质量达标 | QED-050-A |
| 课程管线真实冒烟 | tutorials@v1 真实 LLM 调用输出可用 | QED-050-B |
| 错误处理完备 | 400/404/409/502 全覆盖，PipelineError 语义清晰 | QED-050-A/B |
| 基线冻结 | 优化前后对照基线（call 73-79） | QED-043 |

## 测试覆盖

| 测试文件 | 覆盖内容 |
|---|---|
| `test_prompt_lab.py` | 模板输出结构、先验注入、四档 tier、kind 语义、跨步骤校验 |
| `test_prompt_lab_api.py` | dry-run 端点 200/400/404/409/502（领域 9 用例 + 课程 6 用例） |
| `test_exploration_stage.py` | apply-results/re-explore 成功/错误/404/422 + 6 态流转 |

## 关联文档

| 文档 | 关系 |
|---|---|
| [exploration-overview.md](2026-09-exploration-overview.md) | 探索功能总览（端点清单 + 状态机 + 跨项目对齐） |
| [prompt-optimization.md](2026-08-prompt-optimization.md) | 模板优化模块设计（Accepted） |
| [prompt-explore-baseline.md](2026-08-prompt-explore-baseline.md) | v3 管线基线冻结 |
| [2026-08-engine-exploration-alignment.md](../history/baselines/2026-08-engine-exploration-alignment.md) | 跨项目对齐（QED-047/048） |
| `architecture/shared-tables.md` | 写权限例外 + 状态机写主体（Accepted） |
| `architecture/api.md` | 端点路由定义（Accepted） |

## 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-09-01 | 初始创建 | 从 exploration-overview + prompt-optimization + engine-exploration-alignment 整合 |
