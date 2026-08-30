# 共享表设计（qed_domain / qed_course / qed_llm_calls）

设计状态：Accepted
实现状态：Implemented
最后更新：2026-08-27
需求方：QED-Engine
关联代码：`src/qed_tracker/db/models.py`、`src/qed_tracker/migrations/`
关联架构：`docs/architecture/database-schema.md`（DDL 唯一事实源）
跨项目所有权：QED-Engine 根仓库 `docs/design/database-design.md`

## 背景与目标

QED-Engine 由三个子项目组成（QED-Tracker、QED-Engine 后端、Axiom-Flow），共享同一个 MySQL 实例
（`qed` 库）。为避免跨项目写冲突，表命名空间严格隔离：

- `qed_*`：**共享表**，三项目可读，写权限归属单一项目（见各表说明）。
- `qt_*`：QED-Tracker 私有。
- `af_*`：Axiom-Flow 私有。

本文档覆盖三张共享表的设计：`qed_domain`（领域）、`qed_course`（课程）、`qed_llm_calls`
（LLM 调用审计）。前两张由 QED-Tracker 建表维护（Alembic 迁移），第三张由 QED-Engine 后端
建表维护（`call_log.py` 幂等 `CREATE TABLE IF NOT EXISTS`）。

## ER 关系

```
qed_domain (1) ──< (N) qed_course        FK: qed_course.domain_id → qed_domain.domain_id
qed_course  (1) ──< (N) qt_knowledge     FK: qt_knowledge.course_id → qed_course.course_id
qed_llm_calls 独立表，通过 prompt_template 字段关联 prompt_lab 模板编号
```

- `qed_domain` 与 `qed_course` 为 1:N 关系（一个领域包含多门课程）。
- `qed_llm_calls` 与前两张表无外键关系，通过 `prompt_template`（格式 `{task}/{step}@v{n}`）
  关联 QED-Tracker 的 prompt_lab 模板注册表，记录每次 LLM 调用的完整输入输出。

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
  exploration_stage  VARCHAR(20)   NOT NULL DEFAULT '未开始', -- 流程状态
  classic_tracks     JSON          NOT NULL,           -- 课程方向 [{name,summary,kind}] 0~4 项
  stages             JSON          NOT NULL,           -- 学习阶段顺序（无默认值，四档）
  path_results       JSON,                            -- 学习流程（notes/edges/graph_td）
  created_by         VARCHAR(16)   NOT NULL DEFAULT '',
  updated_by         VARCHAR(16)   NOT NULL DEFAULT '',
  created_at         DATETIME      NOT NULL,
  updated_at         DATETIME      NOT NULL,
  PRIMARY KEY (domain_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 列说明

| # | 列名 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| 1 | `domain_id` | VARCHAR(32) PK | — | 领域标识，如 "math"。扩展预留，不使用自增 ID |
| 2 | `name` | VARCHAR(100) | — | 显示名，如 "数学" |
| 3 | `description` | TEXT | — | 学科介绍（LLM 生成，人工审） |
| 4 | `level` | VARCHAR(50) | `""` | 探索范围标签，如 "本科-硕士"。管线 domain@v2 输出 |
| 5 | `scope` | TEXT | `""` | 学科知识（领域边界描述）。当前管线不输出，先置空 |
| 6 | `exploration_stage` | VARCHAR(20) | `"未开始"` | 流程状态枚举（见下文） |
| 7 | `classic_tracks` | JSON | `[]` | 课程方向，JSON 数组 [{name, summary, kind}]，0~4 项。`kind`：`main`=主干方向 / `branch`=分支方向（2026-08-29 语义升级）。管线 domain@v3 输出 |
| 8 | `stages` | JSON | —（无默认值） | 学习阶段顺序列表，值为四档 `["基础","主干","分支","前沿"]`（2026-08-29 用户裁定；基础=入门基石；主干=方向主干；分支=方向细分/拓展；前沿=研究前沿/论文驱动）。之后可变更 |
| 9 | `path_results` | JSON | `null` | 学习流程，可空。管线 path@v4 输出，包含 notes/edges[{from,to}]/graph_td |
| 10-13 | audit | — | — | created_by/updated_by/created_at/updated_at |

### exploration_stage 状态机

```
未开始 → 已生成 → 探索中 → 已完成
```

| 值 | 触发时机 | 写主体 | 说明 |
|---|---|---|---|
| 未开始 | 手动创建 | 创建方（8900 直建或本仓库 API） | 初始状态 |
| 已生成 | dry-run 报告返回、待用户确认 | **8900**（写权限例外，见下） | 管线已跑，产出待审核；本仓库 dry-run 端点自身不写任何表 |
| 探索中 | 探索会话启动 | **8900**（同上） | 管线执行中 |
| 已完成 | apply 变更落库完成 | **8900** | 课程已写入 qed_course |

### 字段语义补充

- **level vs stages**：level 是概括性标签（"本科-硕士"），stages 是具体阶段列表
  （["基础","主干","分支","前沿"]）。两者独立，level 由管线输出，stages 由人工或 LLM 确定。
- **classic_tracks vs stages**：classic_tracks 横向维度（分析学/代数学/…，kind=main 主干），
  stages 纵向维度（基础→主干→分支→前沿）。两个维度正交。
- **path_results**：包含 notes（文字说明）、edges（先修关系边列表）、graph_td（Mermaid 图
  语法）。可空——未探索时为 null。

### 写入权限

- **写**：QED-Tracker（Alembic 迁移建表 + API 端点 + CLI）。
- **读**：QED-Engine 后端（前端学习中心透传）、Axiom-Flow（只读）。

---

## 表2：qed_course（课程表）

一行 = 一门课程。

### DDL

```sql
CREATE TABLE qed_course (
  course_id          VARCHAR(64)   NOT NULL,         -- PK：01_math_analysis
  domain_id          VARCHAR(32)   NOT NULL,         -- FK → qed_domain.domain_id；索引
  sort_order         INT           NOT NULL,         -- 学习顺序（DAG 拓扑序）
  name               VARCHAR(200)  NOT NULL,         -- 规范名（数学分析）
  aliases            JSON          NOT NULL,         -- list[str]：别名
  track              VARCHAR(50)   NOT NULL DEFAULT '',-- 课程所属学术方向
  stage              VARCHAR(32)   NOT NULL,         -- 所属阶段（qed_domain.stages 之一）
  prerequisites      JSON          NOT NULL,         -- list[str]：先修 course_id 数组
  related_targets    JSON          NOT NULL,         -- list[str]：已验收关联目标
  description        VARCHAR(1000) NOT NULL DEFAULT '',-- 课程介绍
  exploration_stage  VARCHAR(20)   NOT NULL DEFAULT '未开始', -- 流程状态
  created_by         VARCHAR(16)   NOT NULL DEFAULT '',
  updated_by         VARCHAR(16)   NOT NULL DEFAULT '',
  created_at         DATETIME      NOT NULL,
  updated_at         DATETIME      NOT NULL,
  PRIMARY KEY (course_id),
  KEY ix_qed_course_domain (domain_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 列说明

| # | 列名 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| 1 | `course_id` | VARCHAR(64) PK | — | 课程标识，如 "01_math_analysis" |
| 2 | `domain_id` | VARCHAR(32) | — | 所属领域，FK → qed_domain.domain_id |
| 3 | `sort_order` | INT | 0 | 学习顺序（DAG 拓扑序） |
| 4 | `name` | VARCHAR(200) | — | 规范名，如 "数学分析" |
| 5 | `aliases` | JSON | `[]` | 别名列表，如 ["高等数学（工科称呼）"] |
| 6 | `track` | VARCHAR(50) | `""` | 课程所属学术方向，如 "分析学"。管线 courses@v4 输出 |
| 7 | `stage` | VARCHAR(32) | — | 所属学习阶段，值域来自 qed_domain.stages |
| 8 | `prerequisites` | JSON | `[]` | 先修 course_id 数组（主知识链路 DAG） |
| 9 | `related_targets` | JSON | `[]` | 已通过验收的关联 catalog 目标（随验收回填） |
| 10 | `description` | VARCHAR(1000) | `""` | 课程介绍（原 note 字段，2026-08-27 重命名） |
| 11 | `exploration_stage` | VARCHAR(20) | `"未开始"` | 流程状态枚举（同 qed_domain） |
| 12-15 | audit | — | — | created_by/updated_by/created_at/updated_at |

### stage 字段说明

`stage` 的值域来自 `qed_domain.stages`（四档：`基础/主干/分支/前沿`，2026-08-29 用户裁定）。

pipeline path@v5 输出的 `tier` 与 `stage` 已**统一为同一概念**（值域同为四档，
2026-08-29 取代旧值域 基础/进阶/核心/冲刺）；tier 不落 qed_course 表，其结果已存
qed_domain.path_results（Graph 分组用）。

### exploration_stage 状态机

同 qed_domain：`未开始 → 已生成 → 探索中 → 已完成`

| 阶段 | 触发条件 | 写主体 |
|---|---|---|
| 未开始 | 手动创建 | 创建方（8900 直建或本仓库 API） |
| 已生成 | course-explore tutorials@v1 完成 | **8900**（写权限例外，见下） |
| 探索中 | 正式探索启动（异步场景） | **8900**（同上） |
| 已完成 | 教材采纳 + 验收完成 | **本仓库 8901**（knowledge complete 聚合时顺带回写，天然合规） |

> 写主体口径（2026-08-28 澄清，根仓库 REQ-064⑤）：**8900 负责探索过程状态流转
> （探索中/已生成/领域已完成），本仓库负责验收终态（课程已完成）**。消解原
> 「已生成 = dry-run 完成」与 api-design「dry-run 不写任何表」的表述冲突——
> dry-run 端点不写表，状态由 8900 在探索会话管理中直写（依赖下方写权限例外）。

### 写入权限

- **写**：QED-Tracker（Alembic 迁移 + API 端点 + CLI + migrate_knowledge 脚本）。
- **读**：QED-Engine 后端（前端学习中心透传）、Axiom-Flow（只读）。

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
  model             VARCHAR(64)   NOT NULL COMMENT '实际模型名（如 qwen-plus、qwen3.7-plus）',
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

### 列说明

| # | 列名 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| 1 | `id` | BIGINT PK AUTO_INCREMENT | — | 行 ID |
| 2 | `service` | VARCHAR(32) | — | 调用方：`qed_engine` / `qed_tracker` / `axiom_flow` |
| 3 | `mode` | VARCHAR(16) | — | `api`（经 8900 网关）/ `local`（直连 dashscope） |
| 4 | `provider` | VARCHAR(32) | — | 提供方：`qwen` / `deepseek` / `glm` / `lmstudio` / `gateway` |
| 5 | `model` | VARCHAR(64) | — | 实际模型名，如 `qwen-plus`、`qwen3.7-plus` |
| 6 | `endpoint` | VARCHAR(16) | — | 调用类型：`text` / `vision` / `embedding` |
| 7 | `prompt_template` | VARCHAR(255) | NULL | 模板编号，格式 `{task}/{step}@v{n}`。如 `domain-explore/domain@v2` |
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
| `domain-explore/domain@v2` | 领域探索 | 名称校验 + 描述生成 |
| `domain-explore/courses@v4` | 领域探索 | 课程发现 |
| `domain-explore/path@v4` | 领域探索 | 学习路径规划 |
| `course-explore/tutorials@v1` | 课程探索 | 教材推荐 |

模板注册于 `src/qed_tracker/prompt_lab/templates.py`。

### 写入路径

| 写入方 | service 值 | 写入方式 | 写入列数 |
|---|---|---|---|
| QED-Tracker local 模式 | `qed_tracker` | `llm_client.py` → `_record_call()`（raw SQL INSERT） | 12 列（不含 task/step/review_*） |
| QED-Engine gateway 模式 | `qed_engine` | `call_log.py` → `record_call()`（pymysql INSERT） | 全部 16 列 |
| QED-Engine gateway 审核 | — | `call_log.py` → `review_call()`（UPDATE review_status/review_note） | 2 列 |

- QED-Tracker 的 `llm_client.py` 在每次 LLM 调用后（无论成功失败）自动写入，写入失败静默降级
  （不阻塞业务流程）。
- QED-Engine gateway 为集中写入点，所有经 8900 网关的调用由其统一记录。

### 与其他表的关系

- **无外键关系**：qed_llm_calls 与 qed_domain/qed_course 无直接关联。
- **通过 prompt_template 关联模板**：模板编号指向 `prompt_lab/templates.py` 中的注册模板。
- **通过时间戳间接关联探索**：同一时间段内的 LLM 调用可通过 created_at 聚合为一次探索会话。

### 与 prompt_lab 的关联

QED-Tracker 的 prompt_lab 管线（DomainPipeline / CoursePipeline）在执行每步时，
将模板编号传给 `LlmClient.complete(prompt_template=...)`，最终写入 qed_llm_calls。
审核态（review_status/review_note）由 QED-Engine 前端控制台管理。

---

## 迁移史

| Migration | 内容 | 时间 |
|---|---|---|
| 0006 | 创建 qed_domain + qed_course（从 math.json 种子数据迁入） | 2026-08-16 |
| 0011 | qed_domain 新增 level/scope/exploration_stage/classic_tracks/path_results；description 扩容 TEXT；stages 去默认值 | 2026-08-27 |
| 0012 | qed_course 新增 track/exploration_stage；note 重命名 description | 2026-08-27 |
| 0013 | DROP TABLE qt_explore_runs + qt_prompt_runs（共享表重构，两表功能已由 qed_domain/qed_course + qed_llm_calls 替代） | 2026-08-27 |
| — | qed_llm_calls 由 QED-Engine 后端 `call_log.py` 幂等建表（不在 QED-Tracker 迁移范围内） | — |

## 约束与契约

### 命名空间

- `qed_*`：共享前缀。qed_domain / qed_course 所有权 QED-Tracker；qed_llm_calls 所有权
  QED-Engine 后端。
- `qt_*`：QED-Tracker 私有。
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
| qed_domain | description、stages、exploration_stage | level、scope、classic_tracks、path_results |
| qed_course | stage、sort_order、description、aliases、exploration_stage | track、related_targets |

### Schema 变更流程

共享表 schema 变更须先经根仓库登记（`docs/design/database-design.md`），再由写权限方实施迁移。
