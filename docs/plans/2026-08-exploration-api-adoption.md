# 探索 API 承接设计（根仓库 REQ-055/056，契约已冻结）

状态：Accepted
最后更新：2026-08-23
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
