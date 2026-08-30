# 领域探索状态接管（REQ-067 B8）设计稿

状态：Draft（待评审）
任务类型：B
最后更新：2026-08-30
关联 Tracker：[todo.md](../trackers/todo.md)（QED-051）
关联设计/计划：
- 根仓库 [2026-08-29-req067-downloads-optimization.md](../../../docs/plans/2026-08-29-req067-downloads-optimization.md)（REQ-067 §B2/B6/B7/B8）
- 根仓库 [2026-08-30-req067-import-api.md](../../../docs/plans/2026-08-30-req067-import-api.md)（REQ-067-A ③④）
- 本仓库回执 [2026-08-30-req067-a-import-api-reply.md](2026-08-30-req067-a-import-api-reply.md)
- 本仓库 [2026-08-prompt-optimization.md](2026-08-prompt-optimization.md)（QED-043：prompt_lab v3 三步管线，本稿即其「Phase B 正式流程」领域侧落地）
- 本仓库 [2026-08-engine-exploration-alignment.md](2026-08-engine-exploration-alignment.md)（QED-047/048：REQ-064 写主体口径，本稿修订其领域侧）

> 归档判定：设计经用户评审后并入 `docs/design/shared-tables.md`（写主体口径修订）与
> `docs/architecture/api.md`（端点契约），计划壳归档 `docs/history/plans/2026-08/`。

---

## 1. 背景与问题

REQ-067 B8 要求：领域探索的状态流转由 QED-Tracker 驱动——前端提交探索请求后
`exploration_stage` 立即置「探索中」，完成后由 QED-Tracker 更新为「已完成 / 已生成 / 失败」；
名称确认（B7）也由 QED-Tracker 提供确认端点。

**现状事实**（均以运行代码为准）：

1. 8901 的领域探索只有 `POST /api/v1/prompt-explores/dry-run`（main.py:887）：同步执行、
   **不写任何表**（engine 置 None，qed_llm_calls 也不落库）、报告直接返回；
2. 8900 的 `explore_sessions.py`（backend）是当前编排方：内存态会话 + 后台线程调 8901
   dry-run 获取报告 + `shared_tables.set_domain_stage` 直写/经 PATCH 写 `exploration_stage`
   （探索中/已生成/已完成）——即「8900 负责探索过程状态流转」（REQ-064 2026-08-28 裁决）；
3. 8901 的 `update_domain`（knowledge_repository.py:207）name 不可变；
   `PATCH /domains/{id}` 支持 exploration_stage 直写（A3，无状态机校验）；
4. 导入端点（QED-050）幂等 upsert 并置 `exploration_stage=已完成`；
5. 历史教训：`qt_explore_runs` 会话表（QED-040/041 时代）已于迁移 0013 删除、旧探索端点
   全部下线——**本次不重建会话表**，探索任务走现有 TaskManager（meta/tasks）留痕。

**冲突**：REQ-067-A 提案「QED-Tracker 接管状态流转」与 REQ-064 裁决「8900 负责过程状态」
 方向相反。经用户裁决（2026-08-30）：**采用新口径**（B8），本设计稿即该裁决的落地设计；
 涉及 REQ-064 留痕的修订在 §7。

## 2. 目标与范围

### 目标

- 领域探索（启动→执行→落库→名称确认→终态）全链路由 8901 驱动；
- `exploration_stage` 五态（未开始/探索中/已生成/已完成/失败）写主体=QED-Tracker；
- 前端无需感知 session，轮询 `/courses` 取状态即可（REQ-067 B2/B8 数据流）。

### 范围（IN）

| 项 | 内容 |
| --- | --- |
| 新端点 | `POST /domains/{id}/explore`（202）、`POST /domains/{id}/confirm-name`（202） |
| 任务 | `domain_explore` handler（TaskManager，与 book_download 同队列，并发上限 2 不变） |
| 存储 | qed_domain 新增 `explore_pending JSON NULL`（迁移 0015） |
| 状态机 | 五态合法迁移与 409 防护（探索中幂等拒重） |
| apply | 全量自动落库（领域字段 + 课程 upsert，见 §6） |
| 文档 | shared-tables.md 写主体口径修订、api.md 端点表、database-schema.md 状态机/列 |
| 契约 | 项目内 A 档回执（§8 回执清单含前端/8900 变更） |

### 范围（OUT，明示不做）

- **课程探索**（tutorials）：保持 REQ-064 现状（8900 会话 + dry-run + adopt + 课程级 stage）；
  REQ-067 §B8 前端数据流中课程域行为不变；
- 报告落库/浏览：探索报告仅透传即时路径（见 §6 例外），不新增报告表；C5 已定 ExploreFlowModal
  课程外视图清理为根仓库侧工作；
- 会话级「放弃/超时」：8900 的 10min 确认超时语义取消——DB 持久态无超时（用户随时可重探/重导）；
- 探索失败自动重试：任务失败后由（前端/用户）再次 POST explore 触发；
- 离线降级（8901 离线时 8900 直写）：随 §7 契约修订**删除领域侧例外**（8901 离线则无探索可执行）。

## 3. 状态机（五态）

```
未开始 ──POST explore──▶ 探索中 ──成功·无待确认──▶ 已完成
  ▲                        │  │
  │                        │  └─ 成功·待名称确认──▶ 已生成 ──POST confirm-name──▶ 探索中
  │                        │                                        （重跑 confirm_name_override）
  │                        └─ 管线异常/校验失败──▶ 失败 ◀──人工 PATCH 复位──┘
  └────────────（失败/完成/已生成均可再次 POST explore，即 B2 初始/重探）──────────┘
```

| 当前态 | 触发 | 目标态 | 非法 |
| --- | --- | --- | --- |
| 未开始/失败/已完成/已生成 | POST explore | 探索中 | 探索中（409 DOMAIN_EXPLORING） |
| 探索中 | POST confirm-name | —— | 409 INVALID_TRANSITION |
| 已生成 | POST confirm-name | 探索中 | 其余 409 INVALID_TRANSITION |
| 探索中 | 管线完成 | 已完成/已生成/失败 | — |

- 「失败」不自动回退；用户可从失败态直接重探（POST explore），或人工 PATCH 复位未开始。
- `explore_pending` 语义：`{"kind": "name_confirm", "name_check": {...}}`（待确认）
  或 `{"kind": "failed", "error": "..."}`（失败诊断）；其他状态置 NULL。
- 探索中前置检查：同领域已有 `domain_explore` 任务处于 running/queued 时 409。

## 4. 端点契约

### POST /api/v1/domains/{domain_id}/explore（202）

```
body（可选）: {"mode": "direct"|"text"|"doc", "ref_text": "?", "ref_doc_path": "?",
               "scope_hint": "?"}
```

- 领域不存在 → 404 DOMAIN_NOT_FOUND；mode 非法 → 422；ref_doc_path 不可读 → 400；
  状态=探索中 → 409 DOMAIN_EXPLORING。
- 语义：**同步置** `exploration_stage=探索中`（前端秒级感知）→ 提交 `domain_explore` 任务，
  返回 `{"task_id": "..."}`。
- 重探（已完成/已生成/失败态再 POST）即重新探索：先清 explore_pending 再置探索中。

### POST /api/v1/domains/{domain_id}/confirm-name（202）

```
body（必填）: {"decision": "accept"|"custom"|"retain", "name": "?"}
```

- 状态≠已生成 → 409 INVALID_TRANSITION；decision 非法 → 422；
  **accept：name 可省略**（缺省采用 `explore_pending.name_check.suggested_name`；若提供则校验
  ≤100、非空）；**custom：必须提供 name**（≤100、非空）；**retain：忽略 name**（用现领域名）。
  （对齐 QED-Engine B7 只发 `{decision}` 的契约——其采纳建议按钮不传 name。）
- 语义：置 `exploration_stage=探索中` + explore_pending=NULL → 提交 `domain_explore`
  任务（`confirm_name_override=最终名`，对齐 8900 现状 confirm_name 重跑语义，pipeline
  步骤 2/3 仅在此重跑后才执行）→ 成功 apply 后置已完成。

### GET /api/v1/domains、GET /api/v1/courses

- `_domain_view_flat` / `_domain_view` 增透出 `explore_pending`（前端 B7 名称确认区数据源）。
- 既有字段（exploration_stage/level/classic_tracks/path_results）不变。

### 状态写入方

仅三个内部写点：explore 端点（置探索中）、confirm-name 端点（置探索中）、
`domain_explore` 任务（终态）。`PATCH /domains/{id}` 保留 exploration_stage 直写能力
（人工修正逃生舱，文档注明），但不再是规范路径。

## 5. domain_explore 任务设计

- handler 签名对齐 `_book_download_handler`：`(params, progress) -> dict`；
- 组装管线：`DomainPipeline(engine=app._db_engine, **_advisor_kwargs())`——**engine 必须传
  真库引擎**（dry-run 传 None 是为了不写表；任务侧 qed_llm_calls 落库是审计必需
  （REQ-060 共享表），失败降级已由 llm_client 兜底）；
- 流程：`pipeline.explore(domain.name, scope_hint, mode, ref_text, ref_doc_path,
  confirm_name_override)`：
  - `NameConfirmationRequired`（初始探索且未 override）→ 置 **已生成** +
    explore_pending=`{"kind": "name_confirm", "name_check": ...}`，任务 result
    `{"outcome": "confirmation_required"}`，任务状态 succeeded；
  - 成功且无 override → 直接 apply（§6）→ 置 **已完成**，explore_pending=NULL；
  - 成功且有 override → 若最终名 ≠ 现名：`repo.update_domain(name=...)`（仅此路径放开
    name；PATCH 端点仍不可改名）→ apply → 置 **已完成**；
  - 失败（LLM 不可用/预算耗尽/校验失败/跨步不一致）→ 置 **失败** +
    explore_pending=`{"kind": "failed", "error": "..."}`，任务 failed（error 落盘）；
- 预算隔离：每次任务 `_advisor_kwargs()` 新建实例（budget 隔离，与 dry-run 同帧）。

## 6. apply 语义（全量自动落库，与 import 同构）

用户已裁决：探索完成后**全量自动落库**（无人工勾选步骤，与 REQ-067 §B2 无勾选环一致）。

- 领域：`create_domain` 幂等 + `update_domain` 维护 `description/level/scope/stages/
  classic_tracks/path_results`（探索产物四列本仓库是唯一写方——REQ-064 已确认）；
  stages 取报告四档（基础/主干/分支/前沿与 domains 契约一致）；
  path_results 写 `{"edges": [...], "graph_td": "..."}`（由报告 path 段）；
- 课程：按报告 courses 逐门幂等 upsert——slug 复用（course_id=slug，契约同 import），
  `sort_order=index`、`stage`、`track`、`aliases`、`prerequisites`、`description=summary`；
- **修正修复规则**：repo.update_course 不覆盖 name（name 由 QED-Tracker 探索改名路径
  domain 级独占）；课程只维护探索产物列。
- 探索报告与领域行差异：不落库报告全文（OUT 已排除）；若后续需要重放，任务 result 中
  附带完整报告，可由 GET /tasks/{id} 查得（临时性，非持久契约）。

## 7. 共享表契约修订（QED-048 遗留口径的领域侧更新）

- shared-tables.md 状态机表（qed_domain 行）：
  - 探索中/已生成/已完成（领域）/失败 写主体：**8900 → 8901**（REQ-067 B8 留痕）；
  - 写权限例外表（8900 离线直写）：删除 **qed_domain** 行（description/stages/
    exploration_stage），**qed_course 行保留**（课程探索仍由 8900 驱动，REQ-064 不变）；
- database-schema.md：qed_domain 加 `explore_pending JSON NULL`（迁移 0015）；
  状态机枚举补「失败」；api.md：五层端点节补 explore/confirm-name 契约；
- 回执根仓库 REQ-064（修订说明）与 REQ-067-A ③④（新口径）。

## 8. 回执清单（给 QED-Engine / 前端）

| 消费方 | 变更 |
| --- | --- |
| 8900 | 领域探索会话（target=domain）退役：`explore_sessions` 领域分支改透传 8901
  `POST /domains/{id}/explore`、`confirm-name`（或前端直连 8901，CORS 已放行 8903）；
  `set_domain_stage` 领域调用删除；课程分支不动 |
| web-ui | B2 触发改 `startCurriculum` silent → 新端点；B7 确认区读
  `explore_pending.name_check`（suggested_name/valid/reasons）；B6 状态读 /courses 不变；失败态
  显示与重试入口按 8901 契约（失败/已完成/已生成均可重探） |
| 8900 直写例外 | 领域例外删除（§7），离线降级仅剩课程行 |

## 9. 测试计划（默认测试不得联网）

1. `tests/test_explore_ownership.py`（新）：状态机迁移合法性（409 四断言）、explore/
   confirm-name 端点契约（202/404/409/422/400）、失败态落盘（注入假管线抛异常）；
2. 任务 handler：假管线工厂注入（fake DomainPipeline 替身，仿 dry-run 测试注入模式），
   验证「探索中→已完成/已生成/失败」三终端与 explore_pending 内容、name 改名路径；
3. `tests/test_db_models.py`：explore_pending JSON 列 + update_domain(name=...)；
4. `tests/test_documentation.py`：白名单同步（新增文档/引用）；
5. 回归：test_api（PATCH/import 不变）、test_prompt_lab（dry-run 不变）、
   test_knowledge_import（manual@v1 不变）全绿。

## 10. 风险与开放项

| 项 | 说明 |
| --- | --- |
| LLM 重跑 | 名称确认后重跑三步（与 8900 现状 confirm_name 语义一致），成本不变；后续可优化
  为「仅重跑 steps2/3」（pipeline 拆分，不进本档） |
| 任务与状态一致性 | 任务跑挂（进程重启）残留「探索中」→ 用户可再次 POST explore（前置检查宽松
  为仅查同任务 id running 时 409？——**开放项**：进程重启后任务表状态不可见（内存），
  端点只查 DB 状态则无 409；接受「重启后重探即重来」语义，人工 PATCH 复位为逃生舱） |
| 前端轮询 | 探索为任务级异步（分钟级），轮询节奏沿用 B2（3~5s）；无 SSE/WebSocket（OUT） |
| 与 QED-043 | prompt_lab 模板版本（v3）不在本档改动；仅「谁执行」变化 |
