# QED-Engine 探索对齐承接设计（根仓库 REQ-064/065 配合清单）

状态：Draft（待用户评审）
最后更新：2026-08-28
需求方：QED-Engine（根仓库 REQ-064、REQ-065；流程计划 PLAN-022）
关联文档：根仓库 [2026-08-exploration-download-flow.md](../../../docs/plans/2026-08-exploration-download-flow.md)（三端架构与数据流，含四项用户裁决 D1~D4）、本仓库 [shared-tables.md](../design/shared-tables.md)（Accepted）、[2026-08-api-design.md](2026-08-api-design.md)（Draft）、[2026-08-prompt-optimization.md](2026-08-prompt-optimization.md)（Accepted）
关联任务：todo [QED-047](../trackers/todo.md)（课程层探索 dry-run 端点）、[QED-048](../trackers/todo.md)（写权限修订与 API 设计补充）

## 背景与时间线

根仓库 2026-08-27 完成 ARCH-019 冲突排查（见其 REQ-064 证据列与 PLAN-022「工作项」节），确认本仓库
migration 0013（删除 qt_explore_runs / qt_prompt_runs、旧探索端点全部下线）之后，双方需在以下四项上
对齐，根仓库侧探索会话（explore-sessions）改造才能安全推进。时间线佐证：

```
2026-08-24/25  根仓库冻结旧探索契约（REQ-055/056）→ 本仓库 QED-040/041 按旧契约实现完成
2026-08-26     本仓库 prompt-optimization 设计 Accepted（P1：独立并行，不受旧契约约束）
2026-08-27     本仓库 migration 0013 删表 + 旧探索端点下线；api-design 改 16 端点新契约（Draft）
2026-08-28     根仓库排查通过，立本承接设计（QED-047/048）
```

本设计遵守跨项目边界：需求方只提契约与文档修订诉求，代码实现由本仓库按自身门禁执行。

## 配合事项一：课程层探索 dry-run 端点（QED-047，承接 REQ-065）

### 诉求

新增 `POST /api/v1/courses/{course_id}/prompt-explores/dry-run`，暴露 course-explore tutorials@v1
管线（模板已注册 `src/qed_tracker/prompt_lab/templates.py`，QED-043 记载实现完成 378 passed），
与领域探索 `POST /prompt-explores/dry-run` 对称：

- 同步执行、**不写任何表**（qt_* 与 qed_* 均不写），唯一痕迹 qed_llm_calls；
- 请求：course_id 路径参数 + 可选 mode/ref_text/ref_doc_path（与领域端点同风格，按 tutorials@v1
  实际入参裁剪）；
- 响应 200：推荐套列表（每套 = 教材 + 配套习题集 + 推荐理由，套数受根仓库 ≤4 上限约束，
  上限逻辑在根仓库侧，本仓库只返回候选）；
- 错误：400 INVALID_PARAMS / 404 COURSE_NOT_FOUND / 409 LLM_UNAVAILABLE / 502 LLM_UNAVAILABLE
  / BUDGET_EXHAUSTED（对齐 api-design 错误码表）。

### 需求理由（需求方视角）

ARCH-019 主线找书链路「探索教程 → 用户勾选 → 采纳建 draft 知识行」依赖本端点；无它则 LLM 选书
能力落空，用户只能手工经 books/search 找渠道。管线已存在，仅差端点暴露，成本低。

### 顺带确认（X3）

课程层探索的 8901 离线降级语义：采纳步骤需写 qt_knowledge（私有表必须经 API），8901 离线时
根仓库侧会话将挂起等待——本仓库无需实现额外逻辑，但请在 QED-047 设计确认时明确该行为边界。

## 配合事项二：shared-tables.md 写权限修订（QED-048，承接 REQ-064④）

### 诉求

shared-tables.md（Accepted）当前规定 qed_domain / qed_course「写：QED-Tracker，其他项目只读」。
根仓库用户裁决（D2）要求增加例外——**8900 离线降级时可直写**：

| 表 | 8900 离线直写允许列 | 仍然禁止列（探索产物，只归本仓库写） |
|---|---|---|
| qed_domain | description、stages、exploration_stage | level、scope、classic_tracks、path_results |
| qed_course | stage、sort_order、description、aliases、exploration_stage | track、related_targets |

修订方式建议：写权限表加例外行 + 注明裁决来源（根仓库 REQ-064，2026-08-27 用户裁决 D2），
Accepted 文档按贵仓库治理做修订留痕。

### 需求理由

根仓库「服务独立性铁律」要求 8901 离线时 8903 下载管理仍可维护领域/课程并推进探索流程；
无此例外，8900 直写即违反贵仓库 Accepted 契约。这是根仓库代码改造的合法性地基。

## 配合事项三：exploration_stage 写主体澄清（QED-048，承接 REQ-064⑤）

### 矛盾点

本仓库两份文档现存表述冲突：

- shared-tables.md 状态机表：「已生成 = dry-run 完成」触发；
- 2026-08-api-design.md：「dry-run **不写任何表**」。

### 建议澄清口径（根仓库 PLAN-022 已按此设计）

| 状态 | 写主体 | 触发时机 |
|---|---|---|
| 未开始 | 领域/课程创建方（8900 直建或本仓库 API） | 手动创建 |
| 探索中 | **8900**（依赖事项二例外落地） | 探索会话启动 |
| 已生成 | **8900**（同上） | dry-run 报告返回、待用户确认 |
| 已完成（领域） | **8900** | apply 变更落库完成 |
| 已完成（课程） | **本仓库 8901**（写权限方，天然合规） | 验收聚合：knowledge complete 时顺带回写 |

即：8900 负责探索过程状态流转，本仓库负责验收终态。请在 shared-tables.md 状态机表与
api-design 相应位置同步该口径，避免双方各自实现造成双写冲突。

## 配合事项四：api-design GET /courses 响应字段补充（QED-048，承接 REQ-064②）

### 诉求

2026-08-api-design.md ③「课程体系只读」端点的响应示例中，领域行仅含
domain_id / name / description / stages，缺四个领域级探索字段：

- `exploration_stage`（根仓库前端探索按钮状态机从共享表直读的数据源）；
- `level`、`classic_tracks`、`path_results`（领域信息卡与学习路径图渲染数据源）。

api-design 尚为 Draft（QED-044 承载中），请在 Draft 审阅窗口一并补齐；否则根仓库「直读 /
API 双链路」（其裁决 D1）返回数据不一致，双链路打通失去意义。课程行 exploration_stage 已在
示例中，无需变更。

## 待移交项（属代码改动，移交本仓库审阅后自行提交）

根仓库 agent 已按跨项目先例（REQ-057/058 同构）执行以下最小侵入改动，**登记移交审阅**：

- `tests/test_documentation.py` REQUIRED_CURRENT_DOCS 白名单补 1 行
  （`docs/plans/2026-08-engine-exploration-alignment.md`），否则新计划文档触发
  `test_documentation_entrypoints_are_intentional` 失败。

## 评审记录（2026-08-28，QED-Tracker 侧评审）

评审人：QED-Tracker 会话（QED-026 主链路轮内评审）；结论：**四项配合事项全部承接**，细化如下。

### 事项一（QED-047 课程层探索 dry-run 端点）：确认承接

- 路径形态 `POST /courses/{course_id}/prompt-explores/dry-run`（嵌套式）与领域 `POST /prompt-explores/dry-run`（平铺式）并存，REST 语义清晰，维持 REQ-065 原形态；
- 前置全部就绪：`CoursePipeline`（tutorials@v1，QED-043 已验证）、`KnowledgeRepository.get_course`（QED-026 数据轮已建）、错误码表对齐 api-design；
- 响应契约：`{"dry_run": true, "report": {"course": {...}, "tutorials": [...]}, "calls": [{"step": "tutorials", "template_id": "course-explore/tutorials@v1", "duration_ms": ...}]}`；
- 五要素定义已入 [api-design](2026-08-api-design.md) ⑥ 组（本次评审同步落档）。

### X3 确认（课程层探索 8901 离线降级语义）

确认需求方理解正确：**采纳步骤需写 qt_knowledge（QED-Tracker 私有表，必须经 8901 API），
8901 离线时根仓库侧探索会话挂起等待**；本仓库不为此实现额外降级逻辑（服务独立性铁律由
根仓库侧会话挂起策略保证）。dry-run 步骤同理——LLM 调用与管线执行都在 8901。

### 事项四（GET /courses 补四字段）：已全部完成（2026-08-28 实现轮）

- ✅ `level`、`classic_tracks`：QED-026 数据轮落地（API 透出 + api-design ③ 示例 + 契约测试守护）；
- ✅ `exploration_stage`、`path_results`：**同日实现轮落地**（`_domain_view` 透出 +
  `test_courses_view_exposes_exploration_stage_and_path_results` 守护）；领域行四字段齐备，
  根仓库前端探索状态机与路径图渲染数据源完整。

### 实现记录（2026-08-28，A1 + A3 + 事项四剩余）

| 工作项 | 实现 | 测试 |
|---|---|---|
| A1（QED-047） | `POST /api/v1/courses/{course_id}/prompt-explores/dry-run`（main.py，校验序 mode→key→404→管线；对称领域 dry-run） | test_prompt_lab_api.py 五用例（200 结构/404/400 mode/400 doc/409 key） |
| A3 | `PATCH /domains` 增补 `path_results`/`exploration_stage`（仓储 update_domain 扩参） | test_knowledge_api.py `test_patch_domain_updates_path_results_and_stage` |
| 事项四剩余 | `GET /courses` 领域行补 `exploration_stage`/`path_results` | test_knowledge_api.py `test_courses_view_exposes_exploration_stage_and_path_results` |
| A2（同日追加，用户裁决实现） | `POST /api/v1/courses/{course_id}/knowledge`（仓储 `adopt_tutorials` 单事务批量；幂等=同 set+name 返回既有 `existing:true`；同 set_no 异名 → 409 SET_NO_CONFLICT；预填六字段） | test_knowledge_api.py 五用例（201 预填/幂等/409 冲突/同源可空/422 校验） |

门禁：全量 **339 passed + 3 skipped + ruff clean**（327 → 339，A1/A3/事项四/A2 共新增 12 用例）。
A1→A2 串接即完整课程探索链路：dry-run 出候选 → 用户勾选 → 采纳建 draft → confirm → books。
**联调通知（2026-08-28）**：8901 侧 A1/A2/A3 已就绪，根仓库 explore-sessions 可开始真实联调
（真实 LLM 冒烟待 8901 上线执行）；回执材料：提交号 + 门禁输出（提交由用户执行）。

### 补充 API 评估（评审产出，经用户裁决）

| # | 端点 | 裁决状态 |
|---|---|---|
| A2 | `POST /courses/{course_id}/knowledge`——采纳探索推荐建 draft qt_knowledge 行（预填 set_no/set_name/textbook_ref/exercise_ref/textbook_intro/exercise_intro，修根仓库反馈 §8 缺陷 3） | **已裁决采纳此嵌套形态**（2026-08-28 用户裁决），实现等通知 |
| A3 | `PATCH /domains` 补 `path_results`/`exploration_stage` 两可选列——探索产物落库收口（这两列属"探索产物只归本仓库写"，当前无任何端点可写） | 已纳入设计（api-design ④ 附注），实现等通知 |

### 文档同步记录

- [shared-tables.md](../design/shared-tables.md)：写权限例外行 + 两表 exploration_stage 状态机写主体列已修订（同日，事项一/三落地）；
- [2026-08-api-design.md](2026-08-api-design.md)：⑥ 组补 A1 五要素 + A2 草案（新 ⑧ 组）+ A3 附注（④ 组）。

## 验收与回执

- QED-047：端点契约测试（对称结构 + 错误码对齐）+ 全量门禁全绿 → 回执根仓库 REQ-065；
- QED-048：shared-tables.md / api-design 修订经用户评审 → 回执根仓库 REQ-064；
- 双方联调：根仓库 explore-sessions 前端交互按对称设计先行（mock），本端点上线后真实联调。
