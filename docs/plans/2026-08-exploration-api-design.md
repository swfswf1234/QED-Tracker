# 探索 API 本地实现详规（QED-040/041 · API 线）

状态：Draft（待用户评审）
最后更新：2026-08-23
关联计划：[承接设计与详规拆分](2026-08-exploration-api-adoption.md)、[数据库线详规](2026-08-exploration-db-design.md)（Accepted）
上游契约：根仓库 `docs/plans/2026-08-arch019-exploration-api.md` §0~8（冻结，本文不重写契约语义，只落本仓库实现细节）

## 背景与输入

本文档把冻结契约翻译为本仓库可实现的端点规格与内部编排，格式对齐
`docs/architecture/api.md` 的正式 API 文档要素（方法、参数、输入、输出、范例、错误码）。
每节末尾标注**稳定状况**：

- 【契约冻结】= 根仓库 §0~8 已冻结，不得改动；
- 【本地已定】= 本文档确定的实现细节；
- 【待评审】= 本文决策点，需用户裁决。

## 0. 通用约定（本地实现）

### 错误结构与错误码总表【契约冻结 + 本地已定】

```json
{ "detail": { "code": "CAPACITY_REACHED", "message": "该课程已有 4 个教程，达到上限" } }
```

- 新增辅助 `api_error(status, code, message)` 统一构造；仅探索域新端点使用。
- **既有端点字符串 detail 保持不动**（现有 8903 前端已消费，不破坏）。

错误码总表（沿用契约 §0，新增内部码见 §8/§9 决策点）：

| HTTP | code | 语义 | 稳定状况 |
| --- | --- | --- | --- |
| 400 | INVALID_PARAMS | 参数缺失/非法（含 ref_doc_path 不可读、ref_text 超长） | 契约冻结 |
| 404 | COURSE_NOT_FOUND / RUN_NOT_FOUND / DOMAIN_NOT_FOUND | 课程、运行记录或领域不存在 | 契约冻结 |
| 409 | CAPACITY_REACHED | 教程总数已达 4，拒绝新建探索或采纳 | 契约冻结 |
| 409 | COURSE_LOCKED | ≥2 套已完成审核，停止自动加入新教程 | 契约冻结 |
| 409 | RUN_STATE_CONFLICT | 运行态非法迁移 | 契约冻结 |
| 409 | DOMAIN_NAME_CONFLICT | 领域名冲突 | 契约冻结 |
| 503 | LLM_UNAVAILABLE | LLM 网关不可达或调用失败（可重试 = 新建 run） | 契约冻结 |
| 409 | COURSE_ALREADY_EXISTS | 手工加课时 course_id 已存在（扩展码） | 待评审 A2 |

### 教程计数口径【本地已定】

- `tutorial_count(course_id)` = qt_knowledge 中该课 `kind=tutorial` 且 status ∈
  {draft, confirmed, completed} 的行数；`remaining_slots = 4 − tutorial_count`。
- `completed_count(course_id)` = 同口径 status=completed 行数。
- rejected/superseded 不计入两者（与 UI 计划着色规则一致）。

### 服务端校验顺序【本地已定，待评审 A5】

explore 类 POST 的服务端校验序列：

```
400 INVALID_PARAMS（body 合法性先行）
→ 404 COURSE_NOT_FOUND / DOMAIN_NOT_FOUND
→ 409 CAPACITY_REACHED → 409 COURSE_LOCKED（仅课程层）
→ running 幂等查重 → 入队返回 202
```

### mode 输入校验【本地已定】

| mode | 必填附加 | 校验 |
| --- | --- | --- |
| direct | 无 | — |
| text | ref_text | 非空且 ≤10000 字符 |
| doc | ref_doc_path | 服务端 `Path.is_file()` 且可读；失败 400 INVALID_PARAMS |

- ref_doc_path 接受任意服务端可读绝对路径；规范位置
  `<QED_DATA_ROOT>/tmp/exploration/<对象名>探索.txt` 仅作界面默认提示（契约 §0），
  服务端不做数据根限制。
- mode 缺失或不在三值内 → 400 INVALID_PARAMS。

## 1. POST /api/v1/courses/{course_id}/explore —— 发起课程层探索

稳定状况：【契约冻结】端点语义与输出结构；【本地已定】handler 编排。

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| course_id | path | string | 是 | 课程标识（如 `01_math_analysis`） |
| mode | body | string | 是 | `direct` / `text` / `doc` |
| ref_text | body | string | mode=text | ≤10000 字符 |
| ref_doc_path | body | string | mode=doc | 服务端可读绝对路径 |

请求范例：

```json
{ "mode": "text", "ref_text": "优先美版经典教材的中译本，配套习题集成套推荐" }
```

**输出**（202 Accepted）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| run_id | string | 探索运行 ID（qt_explore_runs 主键） |
| task_id | string | 8901 内部任务 ID（TaskManager） |
| status | string | 恒 `running` |
| deduplicated | bool | 幂等命中时 true（同课程存在 running 运行，返回既有 run_id/task_id，不入队）；新建时缺省该键 |

响应范例（新建）：

```json
{ "run_id": "exp_9f31c2a4b6d7", "task_id": "tk_5b20a19c3e11", "status": "running" }
```

响应范例（幂等命中）：

```json
{ "run_id": "exp_9f31c2a4b6d7", "task_id": "tk_5b20a19c3e11", "status": "running", "deduplicated": true }
```

**编排**：先插 qt_explore_runs（running）拿 run_id，再以 task_type=`explore_course`
提交 TaskManager（params 含 run_id），回填 task_id。幂等查重在插表前执行。

## 2. GET /api/v1/explore-runs/{run_id} —— 运行详情（轮询）

稳定状况：【契约冻结】输出字段；【本地已定】孤儿兜底与序列化规则。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| run_id / scope / course_id | string | 标识三件套（curriculum scope 时 course_id 为 null、附 domain_name） |
| status | string | running / ready / adopted / discarded / failed / applied / partially_applied |
| params | object | `{mode, ref_text?, ref_doc_path?}` 快照 |
| proposals | array | ready 后非空；course=Proposal[] / curriculum=Change[]；其余态 `[]` |
| adopted_proposal_ids | array[string] | 已采纳 proposal_id / change_id |
| conflicts | array \| null | apply 后的冲突清单（仅 curriculum） |
| error | object\|null | failed 时 `{code, message}` |
| created_at / updated_at | datetime | ISO 8601 |

响应范例（ready 态节选）：

```json
{
  "run_id": "exp_9f31c2a4b6d7", "scope": "course", "course_id": "01_math_analysis",
  "status": "ready",
  "params": { "mode": "text", "ref_text": "优先美版经典教材…" },
  "proposals": [ { "proposal_id": "pp_a1b2c3d4e5f6", "set_name": "套一", "...": "..." } ],
  "adopted_proposal_ids": [], "conflicts": null, "error": null,
  "created_at": "2026-08-23T10:00:00", "updated_at": "2026-08-23T10:01:12"
}
```

**孤儿 running 兜底【本地已定】**：读取时若 status=running 且 task_id 非空，查
TaskManager——任务不存在（服务重启丢失）或状态 failed → 同步将 run 转 failed
（error code 分别为 `TASK_LOST` / `TASK_FAILED`，内部扩展码，仅出现在 run.error 字段，
不是 HTTP 错误响应）后返回。正常 succeeded 由 handler 在任务线程内即时转 ready，
此兜底只覆盖重启丢场景。

**proposal_id 规范化【本地已定】**：忽略 LLM 输出的任何 id 字段，服务端按序生成
`pp_<12hex>` 写回 proposals JSON 后再落库。

## 3. POST /api/v1/explore-runs/{run_id}/adopt —— 采纳所选

稳定状况：【契约冻结】校验与输出结构；【待评审 A1】原子性。

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| selected | body | array[string] | 是（≥1） | proposal_id 列表 |

请求范例：

```json
{ "selected": ["pp_a1b2c3d4e5f6"] }
```

**输出**（200）：

```json
{
  "adopted": [ { "knowledge_id": "kn_xxxx", "set_name": "套一" } ],
  "remaining_slots": 2,
  "run": { "run_id": "exp_9f31c2a4b6d7", "status": "adopted", "...": "..." }
}
```

**服务层流程【本地已定】**：
1. run 存在性（404 RUN_NOT_FOUND）→ 非 ready 409 RUN_STATE_CONFLICT；
2. selected 中含未知 proposal_id → 400 INVALID_PARAMS；
3. 重算 remaining_slots 强校验：`len(selected) > remaining_slots` → 409 CAPACITY_REACHED；
4. 单事务内逐 proposal 创建 draft qt_knowledge（domain/course 取自 run 与 qed_course，
   kind=tutorial，set_no 按 Proposal.set_no 映射"一/二/三/四"→"1/2/3/4"、en→"en"、空→""，
   name 复用 QED-036 `tutorial_name()`，textbook_ref/exercise_ref/intro 与 Proposal 对齐）
   并迁移 run→adopted。

## 4. POST /api/v1/explore-runs/{run_id}/discard —— 放弃本次

稳定状况：【契约冻结】幂等语义；【本地已定】实现映射到 repository.discard_run 守卫。

无请求体。ready→discarded；重复 discard 幂等成功（200 返回终态对象）；
其他非终态 409 RUN_STATE_CONFLICT。输出同 §2 运行对象。

## 5. GET /api/v1/courses/{course_id}/explore-runs —— 探索历史

稳定状况：【契约冻结】分页形态与摘要约定；【待评审 A6】摘要字段集。

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| course_id | path | string | 是 | 课程标识 |
| limit | query | int | 否 | 默认 20 |
| offset | query | int | 否 | 默认 0 |

**输出**（200）：按 created_at 倒序的摘要数组（不含 proposals 全量）：

```json
[
  {
    "run_id": "exp_9f31c2a4b6d7", "status": "adopted",
    "proposal_count": 3, "adopted_count": 1,
    "created_at": "2026-08-23T10:00:00", "updated_at": "2026-08-23T10:05:00"
  }
]
```

课程不存在时仍返回 200 空数组（历史视角宽容；创建入口才做 404 校验）【本地已定】。

## 6. POST /api/v1/curriculum-explore —— 发起新建领域探索

稳定状况：【契约冻结】语义；【本地已定】编排同 §1（task_type=`explore_curriculum`）。

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| domain_name | body | string | 是 | 非空 ≤100 字符；应用时重名 409 DOMAIN_NAME_CONFLICT |
| mode / ref_text / ref_doc_path | body | — | 同 §1 | 推荐 doc 模式指向规范位置探索文档 |

请求范例：

```json
{ "domain_name": "高等数学", "mode": "doc", "ref_doc_path": "D:/coding/QED-Engine/dataset/tmp/exploration/高等数学探索.txt" }
```

**输出**（202）：同 §1 结构（scope=`curriculum`）。上限类 409 不适用。

## 7. GET /api/v1/curriculum-runs/{run_id} 与 apply

稳定状况：【契约冻结】changes 结构与应用语义。

- GET 输出同 §2（proposals 承载 Change[]，change_id 服务端按序规范化 `ch_NN`，
  忽略 LLM 输出 id）。
- `POST /curriculum-runs/{run_id}/apply`：输入 `{ "selected": ["ch_01"] }`；
  逐条执行 create_domain → create_course（共享表写入，ADR 0009 唯一写方）；
  冲突条目记入 conflicts 不覆盖不回滚；全部成功 run→applied，有冲突 run→partially_applied。

```json
{
  "applied": [ { "change_id": "ch_01", "entity": "domain", "target_id": "advanced_math" } ],
  "conflicts": [ { "change_id": "ch_02", "reason": "课程 id 已存在：cs_ai" } ],
  "run": { "run_id": "exp_...", "status": "partially_applied", "...": "..." }
}
```

冲突判定：create_domain 目标 domain_id 或 name 已存在；create_course 目标 course_id
已存在。target_id 生成规则（LLM 提议 slug 还是服务端生成）属 LLM 详规线。

## 8. 手工维护五端点

稳定状况：【契约冻结】方法/路径/防护语义；【待评审 A2/A3/A4】细则。

| 方法/路径 | 输入要点 | 成功输出 | 错误 |
| --- | --- | --- | --- |
| POST /api/v1/domains | domain_id/name/description/stages 必填；stages 为字符串数组 | 领域对象 to_dict | 409 DOMAIN_NAME_CONFLICT（id 或 name 已存在）；400 字段非法 |
| POST /api/v1/domains/{domain_id}/courses | course_id/name/stage/sort_order 必填；prerequisites/aliases/note 可选 | 课程对象 to_dict | 404 DOMAIN_NOT_FOUND；409 COURSE_ALREADY_EXISTS（A2）；400 stage 不在领域 stages 列表内 |
| PATCH /api/v1/courses/{course_id} | 部分字段：name/stage/sort_order/prerequisites/aliases/note（A3：domain_id/course_id 不可改） | 更新后课程对象 | 404 COURSE_NOT_FOUND；400 同上 |
| DELETE /api/v1/courses/{course_id} | 无 body | `{ "deleted": "<course_id>" }` | 404；409 关联教程非终态行存在（A4：终态 rejected/superseded 行保留审计、不阻塞） |
| DELETE /api/v1/domains/{domain_id} | 无 body | `{ "deleted": "<domain_id>" }` | 404；409 含任何课程行 |

stage 校验基准【本地已定】：取值必须 ∈ 所属领域 qed_domain.stages 列表
（math 现为四值：本科基础/本科进阶/研究生基础/QE冲刺），不做全局硬编码枚举，
新领域可携带自有 stages。

## 9. 任务编排骨架【本地已定】

- create_app 构造 TaskManager 时合并内置 handler：
  `{**extra_handlers, "explore_course": ..., "explore_curriculum": ...}`
  （闭包引用 Application，advisor 为 None 时 handler 直接 finish_failed
  error={code:"LLM_UNAVAILABLE"}——未配置密钥降级不阻塞服务启动）。
- 并发上限沿用 2；LLM 调用异常统一 finish_failed(error={code:"LLM_UNAVAILABLE"})。
- 进度中间档本轮不做（契约 §2 冻结决定），progress 固定 5→100 两跳。

## 10. 测试策略【本地已定】

- TestClient + SQLite create_all 注入（test_knowledge_api.py 夹具模式）；
  advisor 经 Application(advisor=...) 注入 fake（既有注入点，零网络）。
- 用例矩阵：§1~§8 全端点正常流；三类 409；幂等 deduplicated；adopt 强校验与未知 id；
  discard 幂等；孤儿 running 双分支兜底；apply applied/partially_applied 双分支；
  手工端点两类 409 + stage 校验；错误结构 detail.code/message 断言。

## 决策点汇总（请逐条确认）

| # | 决策点 | 推荐 | 备选 |
| --- | --- | --- | --- |
| A1 | adopt 原子性 | **单事务**（知识行 + run 迁移同一 session，中途失败全回滚） | 逐个提交，部分成功 |
| A2 | 手工加课冲突码 | **新增 COURSE_ALREADY_EXISTS**（回执根仓库备案） | 复用 DOMAIN_NAME_CONFLICT 语义混用 |
| A3 | PATCH 可改字段 | **排除 domain_id/course_id**（归属不变更，移动课程另行设计） | 允许迁移 domain |
| A4 | 删课对终态知识行 | **保留审计行不阻塞**（仅 draft/confirmed/completed 阻塞） | 连终态一并拒绝或清理 |
| A5 | 校验顺序 | **400 先于 404**（body 合法性先行，防脏数据入库） | 404 先行（资源定位优先） |
| A6 | 历史摘要字段 | **run_id/status/proposal_count/adopted_count/created_at/updated_at** | 附 params 摘要（体积增大） |
