# 探索运行表设计详规（QED-040/041 · 数据库线）

状态：Accepted（2026-08-23 用户评审通过：D1~D5 推荐值生效；实现轮迁入 docs/design/ 并同步 database-schema 固定文档）
最后更新：2026-08-23
关联计划：[承接设计与详规拆分](2026-08-exploration-api-adoption.md)
上游契约：根仓库 `docs/plans/2026-08-arch019-exploration-api.md` §0~8（冻结，本文不复制契约正文）

## 背景与输入

课程层探索与新建领域探索共用一张运行记录表。用户已裁决（2026-08-23）：

1. **单表 JSON 列方案**：运行记录是过程性数据，契约查询全部在 run 级别
   （详情轮询、历史列表仅计数），无需关系化 proposals；proposals/changes/params/
   conflicts/error 以 JSON 列存储。
2. 表为 qt_* 私有表（ADR 0009 命名空间），所有权 QED-Tracker。
3. 本文档经用户评审确定后迁入 `docs/design/` 并同步 database-schema 固定文档。

## 表定义：qt_explore_runs

一行 = 一次探索运行（课程层或领域层）。

| 列 | 类型 | Null | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| run_id | VARCHAR(32) | 否 | — | 主键，`exp_` + 12 位 hex（复用 `_id("exp", ...)` 生成模式） |
| scope | VARCHAR(16) | 否 | — | `course`（课程层）/ `curriculum`（领域层） |
| course_id | VARCHAR(64) | 是 | NULL | scope=course 必填（qed_course.course_id）；curriculum 时 NULL |
| domain_name | VARCHAR(100) | 是 | NULL | scope=curriculum 必填（提议的新领域名）；course 时 NULL |
| status | VARCHAR(24) | 否 | running | 状态机见下节 |
| params | JSON | 否 | — | 参数快照 `{mode, ref_text?, ref_doc_path?}`（提交时定档） |
| proposals | JSON | 是 | NULL | ready 后非空：course=Proposal[] / curriculum=Change[]（结构见契约 §2/§7.1）；running 态为 NULL，序列化输出时转 `[]` |
| adopted_ids | JSON | 否 | `[]` | 已采纳 proposal_id / 已应用 change_id（ORM 级 default=list，对齐既有 JSON 列风格） |
| conflicts | JSON | 是 | NULL | 仅 curriculum apply 后：`[{change_id, reason}]` |
| error | JSON | 是 | NULL | failed 时 `{code, message}`（code 取值见 API 详规线） |
| task_id | VARCHAR(32) | 是 | NULL | 关联 8901 tasks 机制的任务 ID（孤儿兜底依据） |
| meta | JSON | 是 | NULL | LLM 审计快照：model / usage / response_sha256（与 qed_llm_calls 记录互查） |
| created_by | VARCHAR(16) | 否 | "" | 审计惯例对齐五表（web 发起填 "web"） |
| created_at | DATETIME | 否 | — | 创建时间 |
| updated_at | DATETIME | 否 | — | 最后更新时间 |

**互斥约束**：`(scope=course AND course_id IS NOT NULL AND domain_name IS NULL)` 与
`(scope=curriculum AND domain_name IS NOT NULL AND course_id IS NULL)` 由应用层保证，
不加数据库 CHECK（对齐既有五表无 CHECK 的先例；SQLite 测试环境行为一致性优先）。

**索引**（个人部署行数量级极小，只建最小集）：

| 索引 | 列 | 服务查询 |
| --- | --- | --- |
| PRIMARY | run_id | 详情/adopt/discard 定位 |
| ix_qt_explore_runs_course | course_id | 课程层幂等（running 查重）+ 历史列表 |
| ix_qt_explore_runs_domain | domain_name | 领域层幂等查重 |
| ix_qt_explore_runs_status | status | running 态扫描 |

## 状态机

```
                    ┌────────── 任务失败 ──────────▶ failed（终态；重试 = 新建 run）
running ── 任务成功 ─▶ ready ─┬─ adopt（仅 course）─▶ adopted（终态）
                            ├─ discard ──────────▶ discarded（终态）
                            └─ apply（仅 curriculum）─▶ applied | partially_applied（终态）
```

迁移守卫（服务层执行，repository 层提供带守卫的状态迁移方法）：

| 当前态 | 动作 | 行为 |
| --- | --- | --- |
| 非 ready | adopt / apply | 409 RUN_STATE_CONFLICT |
| 非 ready 且非 discarded | discard | 409 RUN_STATE_CONFLICT |
| discarded | discard | 幂等成功：200 返回终态对象（契约 §4），状态不变 |
| running | 详情读取 | 正常返回 running（孤儿 running 兜底属 API 详规线，不在本表层） |

终态集合：`adopted / discarded / failed / applied / partially_applied`；
ready 可多次读取（历史回看 + 待选补采纳场景由 adopt 守卫约束：仅首个 adopt 成功，
其后 RUN_STATE_CONFLICT——与 UI「历史 ready 运行可查看但采纳置灰」一致）。

## Repository 层新增方法（db/exploration_repository.py 新文件）

| 方法 | 职责 |
| --- | --- |
| create_run(scope, *, course_id/domain_name, params, task_id) | 插入 running 行 |
| get_run(run_id) / list_runs(scope, target_id, limit, offset) | 读取；历史按 created_at 倒序分页 |
| find_running(scope, target_id) | 幂等去重查询（status=running 单条） |
| finish_ready(run_id, proposals, meta) | running→ready 写回结果（守卫迁移） |
| finish_failed(run_id, error) | running→failed 写回错误 |
| adopt_run(run_id, adopted_ids) | ready→adopted |
| discard_run(run_id) | ready→discarded / discarded 重入返回自身 |
| apply_run(run_id, applied_ids, conflicts) | ready→applied / partially_applied（conflicts 非空即后者） |

状态守卫统一抛 `InvalidRunState`（仿 KnowledgeRepository.InvalidTransition 先例）。

## 迁移 0008_exploration_runs

- upgrade：create_table qt_explore_runs（DDL ASCII-only）+ 中文注释落库。
  注释机制沿用 0007 模式：注释文本追加进 `migrations/data/table_comments.json`
  （qt_explore_runs 段），0008 内对该表应用 table/column COMMENT。
- downgrade：drop_table（过程性数据表，可逆无数据风险）。
- ORM 同步：db/models.py 新增 QtExploreRun（StrEnum ExploreRunStatus 七态常量）。

## 决策点（请逐条确认）

| # | 决策点 | 推荐 | 备选 |
| --- | --- | --- | --- |
| D1 | meta JSON 审计列 | **保留**：LLM 排查时 run↔调用记录可互查 | 不加，依赖 qed_llm_calls 时间戳近似关联 |
| D2 | course_id/domain_name 互斥 | **应用层校验**（先例一致） | 加 CHECK 约束 |
| D3 | proposals 在 running 态存 NULL | **NULL，序列化时转 []** | 存 [] 占位 |
| D4 | created_by 审计列 | **保留**（五表惯例一致） | 省略 |
| D5 | 表名 | **qt_explore_runs** | qt_explore_history / qt_explorations |
