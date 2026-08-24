# 探索 API 承接设计（根仓库 REQ-055/056，契约已冻结；含 REQ-059 增补）

状态：Accepted
最后更新：2026-08-24
关联代码：`src/qed_tracker/api/main.py`、`src/qed_tracker/db/models.py`（承接时落位）
关联测试：`tests/test_api.py`、`tests/test_knowledge_api.py`（扩展面）

## 背景

根仓库 ARCH-019 课程下载轮需要课程探索能力（LLM 检索最合适教程）与新建领域探索
（LLM 提议课程体系）。API 契约已在根仓库冻结（2026-08-23 用户评审），本仓库以共享表
唯一写方身份承接实现。契约唯一事实源：

- 根仓库 `docs/plans/2026-08-arch019-exploration-api.md`（冻结版，含全部端点定义、
  错误码、范例；本文档只登记承接范围与本地设计要点，不复制契约正文——跨项目契约
  以根仓库 docs 为准）

## 决定

1. **QED-040（承接 REQ-055·课程层）**：
   - 端点五枚：`POST /api/v1/courses/{course_id}/explore`（mode direct/text/doc，
     ref_doc_path 规范位置 `<数据根>/tmp/exploration/<课程名>探索.txt`）、
     `GET /api/v1/explore-runs/{run_id}`（轮询）、adopt/discard、
     `GET /api/v1/courses/{id}/explore-runs`（limit+offset 分页）。
   - 同课程已有 running 时幂等返回既有 run_id（响应附 `deduplicated: true`）。
   - adopt 服务端强校验：选中数 ≤ remaining_slots（409 CAPACITY_REACHED）、
     非 ready 态 409 RUN_STATE_CONFLICT。
   - 探索记录表为 qt_* 私有新表（表设计随实现细化，遵循 ADR 0009 命名空间）；
     采纳创建 draft `qt_knowledge` 行（textbook_ref/exercise_ref/intro 与 Proposal 对齐）。
2. **QED-041（承接 REQ-056·新建领域层 + 手工维护）**：
   - `POST /api/v1/curriculum-explore`：必填 `domain_name` + mode/ref 输入；
     LLM 提议 = create_domain 一条 + 若干 create_course（changes 结构见契约 §7.1）。
   - apply：勾选执行；冲突（领域重名 DOMAIN_NAME_CONFLICT、课程 id 已存在）拒绝该条
     并在 conflicts 标记原因，不静默覆盖、不回滚已成功条目；全成功 applied /
     有冲突 partially_applied。
   - 手工维护端点：POST /domains、POST /domains/{id}/courses、PATCH /courses/{id}、
     DELETE /courses/{id}（关联教程非终态时 409）、DELETE /domains/{id}（含课程 409）。
   - 字段校验细则（stages 枚举、sort_order、aliases）随实现设计文档细化，不阻塞。
3. **通用**：LLM 调用走本仓库自持配置（`.env API_KEY`），调用记录写 `qed_llm_calls`
   （service=qed_tracker）；8900 同路径纯透传由根仓库负责（REQ-054）；错误结构统一
   `{detail: {code, message}}`。

## 后果

- 正面：探索业务归本仓库接口类型③边界内；共享表写入权不外溢；前端经 8900 透传消费。
- 注意：新增端点与私有表须同步 `docs/architecture/api.md`、database-schema 文档与
  契约测试；统一数据根适配（REQ-055 附带项）与本组端点可同批落地。

## 取代

无（首次承接探索域；主链路 QED-026 的课程梳理 advisor 保持不动，探索为新并行入口）。

## 详规拆分与评审流程（2026-08-23 用户裁决）

实施前按三条线解耦详规，每线独立成文、**经用户评审确认后方可进入实现**；
确认前按 [ADR 0003](../adr/0003-pending-design-location.md) 以 Draft 形态随本计划承载于
`docs/plans/`，确定后迁入 `docs/design/`：

| 详规线 | 文档 | 覆盖范围 | 状态 |
| --- | --- | --- | --- |
| 数据库 | [探索运行表设计详规](2026-08-exploration-db-design.md) | qt_explore_runs 表结构、状态机、索引、迁移 0008 | Accepted（2026-08-23 用户确认） |
| API 本地实现 | [探索 API 本地实现详规](2026-08-exploration-api-design.md) | 端点落位、错误码映射、任务编排、幂等与孤儿兜底、adopt/apply 服务层校验、手工维护细则 | Draft 待评审 |
| LLM prompt/agent | [探索 LLM agent 设计详规](2026-08-exploration-advisor-design.md) | 课程层/领域层两 advisor：提示词、结构化输出契约、校验与修复、预算与调用记录 | Accepted（2026-08-24 用户裁决） |

评审顺序：数据库 → API → LLM agent（依赖关系决定）；上游契约（根仓库 §0~8 冻结版）
不因详规重开，详规只细化本仓库内部实现。

## REQ-059 增补（2026-08-24 需求方 QED-Engine 登记，待本仓库评审确认）

### 背景

QED-Engine 下载管理左树交互 v2 落地（全弹窗探索流 + 手工维护与探索解耦，2026-08-24
用户裁决）：树数据源切换为真实领域课程体系（GET /courses，QED-033 已上线），手工
「添加领域/新增课程/修改/删除」成为独立入口。消费侧已完成：8900 透传路由上线
（含本文档 §2.2 未列的 GET /domains、PATCH /domains/{id} 等），上游未实现端点按 404
优雅降级。以下增补经根仓库用户评审批准，登记至本仓库走评审流程。

### 范围增补（并入 QED-041）

| # | 增补项 | 类型 | 说明 |
| --- | --- | --- | --- |
| R1 | `GET /api/v1/domains` | 新端点 | 只读领域列表（`[{domain_id,name,description,stages,…}]`），树第一层备用数据源与管理视图基础 |
| R2 | `PATCH /api/v1/domains/{domain_id}` | 新端点 | 仅 `description`/`stages` 可改；`name` 锁死不入请求体；空 body 视为 no-op |
| R3 | 重探语义：apply 对「目标领域已存在」的 create_domain 条目跳过标记 | 行为变更 | 取代 DOMAIN_NAME_CONFLICT 冲突路径；详细行为定义见 [API 详规 §11](2026-08-exploration-api-design.md) |

### 字段口径差异（需求方请求，相对 §2.2 与 API 详规 §8 表）

- `POST /domains`：**domain_id 由服务端生成**，请求体 `{name, description?, stages?}`。
- `POST /domains/{id}/courses`：**course_id 由服务端生成**，请求体 `{name, stage?, sort_order?, note?}`。
- `PATCH /courses/{id}`：仅 `stage`/`sort_order`/`note` 可改（`name` 一并锁死，较决策点 A3 更严）。
- 删除防护错误码建议：`DOMAIN_NOT_EMPTY`（域下有课程行）、`COURSE_HAS_KNOWLEDGE`
  （课下有非终态知识行）——命名本仓库可调，回执根仓库备案即可。

### 验收标准增补（并入 QED-041 成功标准）

- 契约测试覆盖 R1/R2 正常流与 `404 DOMAIN_NOT_FOUND`；
- apply 重探分支：已存在领域 + create_domain/create_course 混合勾选 → create_domain 记入
  skipped（响应与 run 增加 `skipped: [{change_id, reason}]`，平行于 conflicts；结构如本仓库
  另有更优形态，回执时备案、前端随回执适配），create_course 正常落库，run→applied；
- 回执根仓库 REQ-059（提交号 + 测试输出）。
