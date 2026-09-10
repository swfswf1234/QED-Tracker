# 数据库共享表设计（qed_domain / qed_course / qed_llm_calls）

设计状态：Accepted
实现状态：Implemented
确认状态：已确认
最后更新：2026-09-09
需求方：QED-Engine
关联代码：`src/qed_tracker/db/models.py`、`src/qed_tracker/db/schema.py`（ensure_schema 自愈）、`src/qed_tracker/courses.py`
关联测试：`tests/test_db_models.py`、`tests/test_schema.py`、`tests/test_courses.py`
关联架构：[数据库专用表设计](database-private-tables.md)（`qt_*` 专用表族唯一事实源，含全库表清单与五层模型）
关联 ADR：[ADR 0005](../adr/0005-shared-tables-doc-location.md)（迁入 architecture/ 与归属裁决）、
[ADR 0006](../adr/0006-database-model-as-schema-rebuild.md)（模型即 schema + 重建式自愈）、
[ADR 0007](../adr/0007-database-docs-split-by-table-family.md)（按表族拆分与 DDL 展示统一）
文档归属与维护：QED-Tracker；登记同步点：QED-Engine 根仓库 `docs/design/database-design.md`
（共享表 schema 变更先经根仓库登记，见「Schema 变更流程」；QED-Engine 及其他子项目从本文档同步）

> **事实源声明（ADR 0007）**：本文件是 qed 库三张共享表（`qed_*`）的**设计文档唯一事实源**
> ——DDL、列语义、状态机契约、写权限与 Schema 变更流程均以本文件为准。实施事实源为 ORM
> 模型 `src/qed_tracker/db/models.py`（ADR 0006：模型即 schema，`ensure_schema` 启动自愈，
> 表/列中文注释事实源 = 模型 `comment=`）；本文 DDL 为设计展示，行尾 `--` 注释为设计注释，
> 与模型 `comment=` 解耦。**确认状态：已确认**——2026-09-09 经用户转正评审（QED-044 收口）。
> 项目专用表（`qt_*`）的契约见[数据库专用表设计](database-private-tables.md)，本文不重复。
> **实现口径注（2026-09-09 与代码核对）**：① `explore_pending` 错误载荷实际为
> `{kind:"error"}`（另含 `{kind:"name_confirmation"}`），设计期的 `{kind:"failed"}` 措辞退役；
> ② `exploration_stage` 的「失败」值当前无代码写入点（错误路径写 `待确认`+error 载荷），
> 保留为契约值；③ qed_course.stage 值域以本表 `基础/主干/分支/前沿` 为准（模型注释已
> 同步四档措辞，2026-09-09 遗留项 L-05 修复；存量表列注释随下次表重建自愈刷新）。

## 背景与目标

QED-Engine 由三个子项目组成（QED-Tracker、QED-Engine 后端、Axiom-Flow），共享同一个 MySQL 实例
（`qed` 库）。为避免跨项目写冲突，表命名空间严格隔离：

- `qed_*`：**共享表**，三项目可读，写权限归属单一项目（见各表说明）。
- `qt_*`：QED-Tracker 私有（见[数据库专用表设计](database-private-tables.md)）。
- `af_*`：Axiom-Flow 私有。

本文档覆盖三张共享表的设计：`qed_domain`（领域）、`qed_course`（课程）、`qed_llm_calls`
（LLM 调用审计）。前两张由 QED-Tracker 建表维护（ORM 模型声明 + `ensure_schema` 自愈，
ADR 0006），第三张由 QED-Engine 后端建表维护（`call_log.py` 幂等 `CREATE TABLE IF NOT EXISTS`）。

## ER 关系

```
qed_domain (1) ──< (N) qed_course        FK: qed_course.domain_id → qed_domain.domain_id
qed_course  (1) ──< (N) qt_knowledge     FK: qt_knowledge.course_id → qed_course.course_id（qt_* 侧）
qed_llm_calls 独立表，通过 prompt_template 字段关联 prompt_lab 模板编号
```

- `qed_domain` 与 `qed_course` 为 1:N 关系（一个领域包含多门课程）。
- `qed_course` 向下游 `qt_knowledge` 的外键延伸属专用表族，全库五层链路图见
  [数据库专用表设计](database-private-tables.md)「表族总览」。
- `qed_llm_calls` 与前两张表无外键关系，通过 `prompt_template`（格式 `{task}/{step}@v{n}`）
  关联 QED-Tracker 的 prompt_lab 模板注册表，记录每次 LLM 调用的完整输入输出。

---

## 表1：qed_domain（领域表）

一行 = 一个学科领域（当前仅 math，预留扩展）。

### DDL

```sql
CREATE TABLE qed_domain (
  domain_id          VARCHAR(32)   NOT NULL,           -- PK：math（学科标识，扩展预留）
  name               VARCHAR(100)  NOT NULL,           -- 显示名（数学）
  description        TEXT          NOT NULL,           -- 学科介绍
  level              VARCHAR(50)   NOT NULL DEFAULT '',-- 探索范围（本科-硕士）
  scope              TEXT          NOT NULL,           -- 学科知识（管线暂不输出，置空）
  exploration_stage  VARCHAR(20)   NOT NULL DEFAULT '未开始', -- 流程状态（6 态契约见下文）
  classic_tracks     JSON          NOT NULL,           -- 课程方向 [{name,summary,kind}] 0~4 项
  stages             JSON          NOT NULL,           -- 学习阶段顺序（无默认值，四档）
  path_results       JSON,                             -- 学习流程（notes/edges/graph_td）
  explore_pending    JSON,                             -- 探索待确认载荷（REQ-067-B12：审阅结果/失败原因）
  created_by         VARCHAR(16)   NOT NULL DEFAULT '',
  updated_by         VARCHAR(16)   NOT NULL DEFAULT '',
  created_at         DATETIME      NOT NULL,
  updated_at         DATETIME      NOT NULL,
  PRIMARY KEY (domain_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='领域表：按学科组织课程体系，一行一个学科，记录学科介绍、探索范围与学习阶段划分';
```

### 列说明

| # | 列名 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| 1 | `domain_id` | VARCHAR(32) PK | — | 领域标识，如 "math"。扩展预留，不使用自增 ID |
| 2 | `name` | VARCHAR(100) | — | 显示名，如 "数学" |
| 3 | `description` | TEXT | — | 学科介绍（LLM 生成，人工审） |
| 4 | `level` | VARCHAR(50) | `""` | 探索范围标签，如 "本科-硕士"。管线 domain@v4 输出 |
| 5 | `scope` | TEXT | `""` | 学科知识（领域边界描述）。当前管线不输出，先置空 |
| 6 | `exploration_stage` | VARCHAR(20) | `"未开始"` | 流程状态枚举（见下文） |
| 7 | `classic_tracks` | JSON | `[]` | 课程方向，JSON 数组 [{name, summary, kind}]，0~4 项。`kind`：`main`=主干方向 / `branch`=分支方向（2026-08-29 语义升级）。管线 domain@v4 输出 |
| 8 | `stages` | JSON | —（无默认值） | 学习阶段顺序列表，值为四档 `["基础","主干","分支","前沿"]`（2026-08-29 用户裁定；基础=入门基石；主干=方向主干；分支=方向细分/拓展；前沿=研究前沿/论文驱动）。之后可变更 |
| 9 | `path_results` | JSON | `null` | 学习流程，可空。领域探索管线输出（courses@v8 起由服务端按 prerequisites 推导），包含 notes/edges[{from,to}]/graph_td |
| 10 | `explore_pending` | JSON | `null` | 探索待确认载荷（REQ-067-B12）：`待确认` = `{kind:"review_results", stage, courses:[...], domain_report}` / `{kind:"name_confirmation", name_check}` / `{kind:"error", error}`；其余状态 NULL（领域第二轮课程结果现落 `raw/{id}/courses.json`，载荷为空） |
| 11-14 | audit | — | — | created_by/updated_by/created_at/updated_at |

### exploration_stage 状态机（6 态，REQ-067-B12 契约）

```
未开始 → 已生成 → 探索中 → 待确认 → 已完成
                        └──────────────→ 失败
（待确认 --re-explore--> 探索中；失败可由 8900 重新发起探索回到 探索中）
```

> **实现状态标注（2026-09-01）**：6 态状态机与 `explore_pending` 载荷为 REQ-067-B12
> **已实现**（ORM 模型、Repository、API 端点、测试；设计见
> [2026-08-31-req067-b10-b12-exploration-stage.md](../history/baselines/2026-08-31-req067-b10-b12-exploration-stage.md)）。
> 待确认→已完成（apply-results）与 待确认→探索中（re-explore）均可用；探索异步 run 的
> `domain_explore`/`course_explore` 后台 handler 已注册。

| 值 | 触发时机 | 写主体 | explore_pending |
|---|---|---|---|
| 未开始 | 手动创建 | 创建方（8900 直建或本仓库 API） | NULL |
| 已生成 | 领域探索**第一轮**（domain@v4 半场）报告就绪，等待用户确认（可修改） | **8901**（domain_explore_handler 只跑 domain@v4）；手动路径由本仓库 `POST /domains/import` 驱动 | NULL（领域第一轮） |
| 探索中 | 第一轮已确认，**第二轮**（courses@v8 半场）进行中 | **8901**（confirm-domain 后异步提交 domain_explore_courses 任务；re-explore 亦置此态） | NULL |
| 待确认 | 领域探索**第二轮**报告就绪，等待用户采纳；或课程探索单轮报告就绪（REQ-067-B12）；或探索任务失败落此态+error 载荷 | **8901**（domain_explore_courses_handler 完成置此态但不写载荷，结果落 `raw/{id}/courses.json`；手动导入路径经 confirm 双分支 / courses/import 直达此态；任务错误路径写 error 载荷） | 领域第二轮：NULL（结果在 courses.json）；课程：`{kind:"review_results", tutorials:[...]}`；错误：`{kind:"error", error}`；名称待确认：`{kind:"name_confirmation", name_check}` |
| 已完成 | 第二轮审阅采纳落库（本仓库 `POST /domains/{id}/apply-results`）或课程 apply-results | **本仓库 8901** | NULL（采纳时清空） |
| 失败 | **契约保留值，当前无代码写入点**（错误路径写 `待确认`+`{kind:"error"}`；设计期的「服务重启 lifespan 启动清理」未实现——遗留问题已登记） | （无） | （无） |

### 领域探索两轮审阅时序（2026-09-03 用户裁决）

领域探索（LLM 自动轨与手动轨一致）按「两步管线、两轮审阅」推进；**整条链路每个状态只走
一次**（线性），每轮语义与课程探索一致：生成 → 等待确认（可修改）→ 人工完成一轮 prompt
结果确认。`explore_pending` 载荷增 `stage` 标记区分轮次（`domain` = domain@v4 半场 /
`courses` = courses@v8 半场）：

```
第 1 轮（domain@v4 半场）：
  未开始 → 已生成（domain 报告生成，等待确认，可修改；写入 raw/{domain_id}/domains.json）
  → 用户修改+确认（POST /domains/{id}/confirm） → 探索中（异步提交 courses@v8 任务）
第 2 轮（courses@v8 半场）：
  探索中 → 待确认（courses 报告生成，写入 raw/{domain_id}/courses.json；等待确认，可修改）
  → 用户修改+确认（POST /domains/{id}/apply-results） → 已完成（领域探索结束）
```

- **已生成** = 第一轮报告就绪的待确认点；**探索中** = 第一轮已确认、第二轮进行中；
  **待确认** = 第二轮报告就绪的待确认点；**已完成** = 第二轮确认采纳，领域探索结束。
- 第 1 轮确认（已生成→探索中）由 `POST /domains/{id}/confirm` 驱动（读取 domains.json →
  upsert domain + 异步提交 courses@v8 任务）。**手动导入捷径（2026-09-09）**：domains.json
  已含 courses 时，confirm 跳过 courses@v8 直接把 courses 写入 courses.json 并置 `待确认`
  （两轮压缩为同步两步，`task_id=null`）。
- 第 2 轮确认（待确认→已完成）由 `POST /domains/{id}/apply-results` 驱动（选择保留的课程；
  采纳前先把 courses.json 幂等同步入 qed_course——courses@v8 与手动分支都只写 JSON 文件）。
- 课程探索为单步、单轮：`探索中 → 待确认`（报告就绪，等待确认，可修改）→ `确认 → 已完成`。
- dry-run 端点保持单次同步评估（只跑 domain@v4），不拆两轮。

### 字段语义补充

- **level vs stages**：level 是概括性标签（"本科-硕士"），stages 是具体阶段列表
  （["基础","主干","分支","前沿"]）。两者独立，level 由管线输出，stages 由人工或 LLM 确定。
- **classic_tracks vs stages**：classic_tracks 横向维度（分析学/代数学/…，kind=main 主干），
  stages 纵向维度（基础→主干→分支→前沿）。两个维度正交。
- **path_results**：包含 notes（文字说明）、edges（先修关系边列表）、graph_td（Mermaid 图
  语法）。可空——未探索时为 null。

### 写入权限

- **写**：QED-Tracker（ORM 模型声明 + `ensure_schema` 自愈建表维护 + API 端点 + CLI）。
- **读**：QED-Engine 后端（前端学习中心透传）、Axiom-Flow（只读）。

### 在本项目中的作用

- 课程体系的数据根：`GET /api/v1/courses` 与 `GET /api/v1/courses/{domain_id}`（QED-033
  只读透出）与 CLI `courses list/show` 的数据源；8900 后端经 `tracker_client.list_courses`
  透传给前端学习中心（根仓库 REQ-035）。
- 领域探索的流程载体：探索管线（domain@v4 → courses@v8）输出 level/classic_tracks/stages/
  path_results 落本表；exploration_stage 6 态驱动领域探索六步流程
  （见[知识录入设计](../design/knowledge-import.md)）。
- 领域 CRUD API（`POST/PATCH/DELETE /domains`）与手动导入（`POST /domains/import`）的落点。

---

## 表2：qed_course（课程表）

一行 = 一门课程。

### DDL

```sql
CREATE TABLE qed_course (
  course_id          VARCHAR(64)   NOT NULL,         -- PK：01_math_analysis（与 catalogs 对齐）
  domain_id          VARCHAR(32)   NOT NULL,         -- FK → qed_domain.domain_id；索引
  sort_order         INT           NOT NULL,         -- 学习顺序（原 courses[] 数组序，DAG 拓扑序）
  name               VARCHAR(200)  NOT NULL,         -- 规范名（数学分析）
  aliases            JSON          NOT NULL,         -- list[str]：别名（高等数学（工科称呼））
  track              VARCHAR(50)   NOT NULL DEFAULT '',-- 课程所属学术方向（管线 courses@v8 输出）
  stage              VARCHAR(32)   NOT NULL,         -- 所属阶段（qed_domain.stages 之一）
  prerequisites      JSON          NOT NULL,         -- list[str]：先修 course_id 数组（主知识链路 DAG）
  related_targets    JSON          NOT NULL,         -- list[str]：已通过验收的关联 catalog 目标（现为空，随验收回填）
  description        VARCHAR(1000) NOT NULL DEFAULT '',-- 课程介绍
  exploration_stage  VARCHAR(20)   NOT NULL DEFAULT '未开始', -- 流程状态（6 态契约同 qed_domain）
  explore_pending    JSON,                            -- 探索待确认载荷（REQ-067-B12：tutorials 审阅结果/失败原因）
  created_by         VARCHAR(16)   NOT NULL DEFAULT '',
  updated_by         VARCHAR(16)   NOT NULL DEFAULT '',
  created_at         DATETIME      NOT NULL,
  updated_at         DATETIME      NOT NULL,
  PRIMARY KEY (course_id),
  KEY ix_qed_course_domain_id (domain_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='课程表：登记一门课程，记录课程名称、所属阶段、先修关系与学习顺序';
```

### 列说明

| # | 列名 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| 1 | `course_id` | VARCHAR(64) PK | — | 课程标识，如 "01_math_analysis" |
| 2 | `domain_id` | VARCHAR(32) | — | 所属领域，FK → qed_domain.domain_id |
| 3 | `sort_order` | INT | 0 | 学习顺序（DAG 拓扑序） |
| 4 | `name` | VARCHAR(200) | — | 规范名，如 "数学分析" |
| 5 | `aliases` | JSON | `[]` | 别名列表，如 ["高等数学（工科称呼）"] |
| 6 | `track` | VARCHAR(50) | `""` | 课程所属学术方向，如 "分析学"。管线 courses@v8 输出 |
| 7 | `stage` | VARCHAR(32) | — | 所属学习阶段，值域来自 qed_domain.stages |
| 8 | `prerequisites` | JSON | `[]` | 先修 course_id 数组（主知识链路 DAG） |
| 9 | `related_targets` | JSON | `[]` | 已通过验收的关联 catalog 目标（随验收回填） |
| 10 | `description` | VARCHAR(1000) | `""` | 课程介绍（原 note 字段，2026-08-27 重命名） |
| 11 | `exploration_stage` | VARCHAR(20) | `"未开始"` | 流程状态枚举（6 态，同 qed_domain，见上文状态机） |
| 12 | `explore_pending` | JSON | `null` | 探索待确认载荷（REQ-067-B12）：`待确认` = `{kind:"review_results", tutorials:[...]}` / `{kind:"error", error}`；其余状态 NULL |
| 13-16 | audit | — | — | created_by/updated_by/created_at/updated_at |

### stage 字段说明

`stage` 的值域来自 `qed_domain.stages`（四档：`基础/主干/分支/前沿`，2026-08-29 用户裁定）。

探索管线输出的层级字段已于 2026-09-03（courses@v8 裁决）由 `tier` **对齐更名为 `stage`**：
管线报告与 explore_pending 载荷一律输出 `stage`，与 qed_course.stage 同名同值域，
落库不再需要 tier→stage 映射；path_results（Graph 分组用）随探索结果一并写入 qed_domain。

### exploration_stage 状态机（6 态，同 qed_domain）

`未开始 → 已生成 → 探索中 → 待确认 → 已完成`，`探索中/待确认 → 失败`。值域、explore_pending
载荷与实现状态标注见上文 qed_domain 状态机节。**课程探索为单步、单轮**：报告生成即进入
`待确认`（等待确认，可修改），确认后 `已完成`（语义与领域探索第二轮一致）。

| 阶段 | 触发条件 | 写主体 |
|---|---|---|
| 未开始 | 手动创建 | 创建方（8900 直建或本仓库 API） |
| 已生成 | 课程探索会话产出报告 | **8900**（写权限例外，见下） |
| 探索中 | 正式探索启动（异步场景） | **8900**（写权限例外）与 **8901**（re-explore 端点） |
| 待确认 | 课程探索（tutorials@v2）报告生成（course_explore handler 写 explore_pending 载荷） | **8900**（写权限例外）与 **8901**（后台 handler、错误路径 error 载荷） |
| 已完成 | 用户确认教材方案（`POST /courses/{id}/apply-results`） | **本仓库 8901** |
| 失败 | **契约保留值，当前无代码写入点**（错误路径写 `待确认`+`{kind:"error"}`） | （无） |

> 写主体口径（2026-08-28 澄清，根仓库 REQ-064⑤；2026-08-31 按 REQ-067-B12 修订）：**8900 负责
> 探索过程状态流转（探索中/已生成/待确认），本仓库负责验收终态（已完成）与失败清理
> （B10 启动清理）**。消解原「已生成 = dry-run 完成」与 api-design「dry-run 不写任何表」的
> 表述冲突——dry-run 端点不写表，状态由 8900 在探索会话管理中直写（依赖下方写权限例外）。

### 数据来源与配套规则

- **`courses/math.json` 退役**（2026-08-16 用户裁决）：本表为课程体系唯一事实源；CLI/8903
  改读表；`subject`/`stages` 迁入 qed_domain，`courses[]` 迁入本表（sort_order=数组序）。
- `related_targets` 规则延续主链路决策：只关联已通过二次确认评估（人工验收 approved）的课程目标。

### 写入权限

- **写**：QED-Tracker（ORM 模型声明 + `ensure_schema` 自愈建表维护 + API 端点 + CLI）。
- **读**：QED-Engine 后端（前端学习中心透传）、Axiom-Flow（只读）。

### 在本项目中的作用

- 下游专用表的外键锚点：`qt_knowledge.course_id`、书库与任务记录均以课程为归属
  （见[数据库专用表设计](database-private-tables.md)）。
- 课程探索的流程载体：探索管线（tutorials@v2）输出 stage/prerequisites 落本表；
  exploration_stage 6 态驱动课程探索单轮流程（`探索中 → 待确认 → 已完成`）。
- 课程 CRUD API（`POST /domains/{id}/courses`、`PATCH/DELETE /courses/{id}`）、采纳端点
  （`POST /courses/{id}/knowledge`）与探索审阅（apply-results/re-explore）的操作对象。

---

## 表3：qed_llm_calls（LLM 调用审计表）

一行 = 一次 LLM 调用（成功或失败）。记录完整的 prompt 输入、response 输出、耗时与审核态。
由 QED-Engine 后端 `call_log.py` 建表维护，三项目均可写入（通过 `service` 字段区分调用方）。

### DDL

> 表/列中文注释已随建表 DDL 全量落库（2026-08-28 注释补齐轮，`call_log.py` 的
> `CREATE_TABLE_SQL` 携带 COMMENT；存量表经 `ensure_comments()` 幂等校正）。下列 DDL
> 即真实建表语句：

```sql
CREATE TABLE IF NOT EXISTS qed_llm_calls (
  id                BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '行 ID（自增主键）',
  service           VARCHAR(32)   NOT NULL COMMENT '调用方标识：qed_engine/qed_tracker/axiom_flow',
  mode              VARCHAR(16)   NOT NULL COMMENT '调用模式：api（经 8900 网关）/ local（直连厂商）',
  provider          VARCHAR(32)   NOT NULL COMMENT '模型提供方：qwen/deepseek/glm/lmstudio/gateway',
  model             VARCHAR(64)   NOT NULL COMMENT '实际模型名（如 qwen-plus）',
  endpoint          VARCHAR(16)   NOT NULL COMMENT '调用类型：text/vision/embedding',
  prompt_template   VARCHAR(255)  COMMENT '模板编号（{task}/{step}@v{n}，如 domain-explore/domain@v2）',
  prompt            MEDIUMTEXT    COMMENT '完整 prompt（JSON 序列化的 messages 数组）',
  response          MEDIUMTEXT    COMMENT '模型原始响应文本',
  duration_ms       INT           COMMENT '调用耗时（毫秒）',
  status            VARCHAR(16)   NOT NULL COMMENT '调用结果：success/error',
  error             VARCHAR(500)  COMMENT '失败原因（截断至 500 字符）',
  created_at        DATETIME      NOT NULL COMMENT 'UTC 调用时间',
  task              VARCHAR(64)   COMMENT '任务标识（REQ-060 扩展，如 paper-plan、domain-explore）',
  step              VARCHAR(32)   COMMENT '步骤标识（REQ-060 扩展，如 plan、assess、domain）',
  review_status     VARCHAR(16)   DEFAULT 'unreviewed' COMMENT '审核态：unreviewed/passed/rejected（REQ-060 扩展）',
  review_note       VARCHAR(1000) DEFAULT '' COMMENT '审核备注（REQ-060 扩展）'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='LLM 调用审计表：一行 = 一次 LLM 调用（成功或失败），记录完整 prompt 输入、模型响应、耗时与审核态（三项目共用，service 区分调用方）';
```

> 本表由根仓库 `call_log.py` 建表维护，其 DDL（含列内 `COMMENT` 子句）不在 ADR 0007 展示
> 统一规范范围内，维持原样。

### 列说明

| # | 列名 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| 1 | `id` | BIGINT PK AUTO_INCREMENT | — | 行 ID |
| 2 | `service` | VARCHAR(32) | — | 调用方：`qed_engine` / `qed_tracker` / `axiom_flow` |
| 3 | `mode` | VARCHAR(16) | — | `api`（经 8900 网关）/ `local`（直连 dashscope） |
| 4 | `provider` | VARCHAR(32) | — | 提供方：`qwen` / `deepseek` / `glm` / `lmstudio` / `gateway` |
| 5 | `model` | VARCHAR(64) | — | 实际模型名，如 `qwen-plus` |
| 6 | `endpoint` | VARCHAR(16) | — | 调用类型：`text` / `vision` / `embedding` |
| 7 | `prompt_template` | VARCHAR(255) | NULL | 模板编号，格式 `{task}/{step}@v{n}`。如 `domain-explore/domain@v4` |
| 8 | `prompt` | MEDIUMTEXT | NULL | 完整 prompt（JSON 序列化的 messages 数组） |
| 9 | `response` | MEDIUMTEXT | NULL | 模型原始响应文本 |
| 10 | `duration_ms` | INT | NULL | 调用耗时（毫秒） |
| 11 | `status` | VARCHAR(16) | — | `success` / `error` |
| 12 | `error` | VARCHAR(500) | NULL | 失败原因（截断至 500 字符） |
| 13 | `created_at` | DATETIME | — | UTC 调用时间 |
| 14 | `task` | VARCHAR(64) | NULL | 任务标识（REQ-060 扩展），如 `paper-plan`、`domain-explore` |
| 15 | `step` | VARCHAR(32) | NULL | 步骤标识（REQ-060 扩展），如 `plan`、`assess`、`domain` |
| 16 | `review_status` | VARCHAR(16) | `unreviewed` | 审核态：`unreviewed` / `passed` / `rejected` |
| 17 | `review_note` | VARCHAR(1000) | `''` | 审核备注 |

### prompt_template 编号格式

```
{task}/{step}@v{version}
```

当前已注册的模板编号：

| 模板编号 | 所属管线 | 步骤说明 |
|---|---|---|
| `domain-explore/domain@v4` | 领域探索 | 名称校验 + 描述生成 + 方向（classic_tracks） |
| `domain-explore/courses@v8` | 领域探索 | 课程发现 + stage 层级 + prerequisites 先修（path@v5 已并入） |
| `course-explore/tutorials@v2` | 课程探索 | 教材推荐（ref 结构化、position 五档、intro 散文、parallel_ref） |

模板注册于 `src/qed_tracker/prompt_lab/templates.py`。

### 写入路径

| 写入方 | service 值 | 写入方式 | 写入列数 |
|---|---|---|---|
| QED-Tracker local 模式 | `qed_tracker` | `llm_client.py` → `_record_call()`（raw SQL INSERT） | 12 列（不含 task/step/review_*） |
| QED-Engine gateway 模式 | `qed_engine` | `call_log.py` → `record_call()`（pymysql INSERT） | 全部 17 列 |
| QED-Engine gateway 审核 | — | `call_log.py` → `review_call()`（UPDATE review_status/review_note） | 2 列 |

- QED-Tracker 的 `src/qed_tracker/llm_client.py` 在每次 LLM 调用后（无论成功失败）自动写入，
  写入失败静默降级（不阻塞业务流程）。
- QED-Engine gateway 为集中写入点，所有经 8900 网关的调用由其统一记录。

### 与其他表的关系

- **无外键关系**：qed_llm_calls 与 qed_domain/qed_course 无直接关联。
- **通过 prompt_template 关联模板**：模板编号指向 `src/qed_tracker/prompt_lab/templates.py`
  中的注册模板。
- **通过时间戳间接关联探索**：同一时间段内的 LLM 调用可通过 created_at 聚合为一次探索会话。

### 与 prompt_lab 的关联

QED-Tracker 的 prompt_lab 管线（DomainPipeline / CoursePipeline）在执行每步时，
将模板编号传给 `LlmClient.complete(prompt_template=...)`，最终写入 qed_llm_calls。
审核态（review_status/review_note）由 QED-Engine 前端控制台管理。

### 在本项目中的作用

- 本仓库所有 LLM 调用（探索 dry-run 评估、探索管线、取书 LLM 轨）的唯一审计痕迹：
  `llm_client.py` 自动落痕，写入失败不阻塞业务。
- dry-run 端点（领域/课程探索评估）**不写任何业务表**，唯一落点即本表——评估可追溯、
  不产生资源事实。
- 模板编号与耗时支撑 prompt_lab 模板优化（QED-043）与百炼调用审计。

---

## Schema 自愈与历史（ADR 0006：模型即 schema）

Alembic 迁移链已退役（ADR 0006）：`ensure_schema(engine)` 启动自愈取代 `alembic upgrade head`，
历史迁移链仅作 Git 历史追溯，不再作为实现依据。

- **统一自愈规则（含共享表）**：`Base.metadata` 声明表缺失 → `create_all` 补建；列集/主键
  与模型不一致 → DROP+CREATE 全表重建（统一规则，qed_domain / qed_course 随模型重建）；幂等。
- **qed_llm_calls 特判**：根仓库建表维护的共享审计表，本仓库 `ensure_schema` 仅在缺失时按
  权威 DDL（对齐根仓库 `call_log.py`）建表；已有表缺 REQ-060 扩展列（task/step/review_status/
  review_note）则 `ALTER ADD COLUMN` 补齐；**绝不 DROP 重建**（保护三项目审计历史）。
  兜底建表的 `prompt`/`response` 列以 SQLAlchemy `Text()`（TEXT）声明，与根仓库
  MEDIUMTEXT 展示略有宽度差异——生产表以根仓库 `call_log.py` 建表为准。
- **历史关键节点（仅追溯，非实现依据）**：0006 建 qed_domain/qed_course（math.json 种子迁入）；
  0011/0012 扩列与改名（level/scope/classic_tracks/path_results、track、description）；
  0013 DROP qt_explore_runs/qt_prompt_runs；0015 增 explore_pending（6 态状态机，REQ-067-B12）。
- **种子数据**：课程/领域种子不再经迁移写入；标准答案 JSON（`docs/knowledge/`）经确认流程
  导入（ADR 0006 决定 6），数据重建后可重放。

## 命名空间与写权限

### 命名空间

- `qed_*`：共享前缀。qed_domain / qed_course 所有权 QED-Tracker；qed_llm_calls 所有权
  QED-Engine 后端。
- `qt_*`：QED-Tracker 私有（见[数据库专用表设计](database-private-tables.md)）。
- `af_*`：Axiom-Flow 私有。

### 写权限

| 表 | 写方 | 约束 |
|---|---|---|
| qed_domain | QED-Tracker | 其他项目只读，**例外见下** |
| qed_course | QED-Tracker | 其他项目只读，**例外见下** |
| qed_llm_calls | 三项目均可写 | 通过 service 字段区分调用方 |

**8900 离线降级直写例外（2026-08-27 根仓库用户裁决 D2，REQ-064④；2026-08-28 修订留痕）**：
根仓库「服务独立性铁律」要求 8901 离线时 8903 下载管理仍可维护领域/课程并推进探索流程，
故允许 8900 在降级场景直写下列白名单列：

| 表 | 8900 离线直写允许列 | 仍然禁止列（探索产物，只归本仓库写） |
|---|---|---|
| qed_domain | description、stages、exploration_stage、explore_pending（REQ-067-B12） | level、scope、classic_tracks、path_results |
| qed_course | stage、sort_order、description、aliases、exploration_stage、explore_pending（REQ-067-B12） | track、related_targets |

## Schema 变更流程

共享表 schema 变更须先经根仓库登记（`docs/design/database-design.md`），再由写权限方实施。
本仓库侧实施方式为修改 ORM 模型 + `ensure_schema` 自愈（ADR 0006），`qed_*` 结构变化在重建
自愈完成后回执根仓库登记（ADR 0006 决定 7；根仓库 ADR 0003/0009 命名空间契约）。
