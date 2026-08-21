# 文档规范

状态：Current
最后更新：2026-08-12
治理对象：文档分类、写作、元数据、索引、命名、归档与删除
依据：QED-Engine 根仓库 `docs/standards/documentation.md` 治理模式，适配单仓库规模
关联测试：`tests/test_documentation.py`

## 目的与边界

本标准规定 QED-Tracker 每类文档保存什么事实、采用什么元数据，以及何时归档或删除。
具体任务状态查 [待办列表](../trackers/todo.md)，长期决策查 [ADR 索引](../adr/index.md)。

## 强制规则

### 文档分类与事实边界

| 位置 | 唯一职责 |
| --- | --- |
| 根 `README.md` | 面向用户的项目定位、安装、快速使用、数据位置与文档入口。 |
| 根 `AGENTS.md` | Agent 执行入口：项目目标、任务路由、强制约束与门禁。只指引，不保存正文事实。 |
| `docs/index.md` 与各目录 `index.md` | 只导航当前文件，不保存正文事实。 |
| `docs/architecture/` | 当前系统边界、模块拓扑和数据不变量。 |
| `docs/design/` | 当前契约与接口：下载/清单、论文发现、服务与外部接口（含 Axiom 消费面）、主链路、来源与评审、数据设计、治理。 |
| `docs/standards/` | 工程治理规则（文档规范、ADR 治理）。 |
| `docs/adr/` | 影响长期约束的决定、理由、后果和取代关系。 |
| `docs/guides/` | 可重复执行的用户操作与开发门禁。 |
| `docs/plans/` | 已批准且尚未关闭的实施计划。 |
| `docs/trackers/` | 全部未关闭任务、关闭台账与无状态能力路线图。 |
| `docs/history/` | 选择性保留的历史基线（旧系统、Math-QE）。 |

一个事实只设一个维护位置，其他文档使用链接。跨项目契约（端口、变量、数据布局）以 QED-Engine
根仓库 `docs/design/` 与 `docs/architecture/` 为准，本仓库文档只链接不复制。

### 写作、命名与索引

- 中文说明使用短句和明确主语；标识符、API 字段和外部协议名称保留英文。
- 文件名使用小写英文和连字符；活跃架构、设计、标准和指南使用稳定名称。
- 文档目录入口统一为小写 `index.md`；`docs/**/README.md` 禁止存在。
- 内部链接显式指向文件或 `index.md`，不依赖托管平台目录解析。
- Mermaid 图与说明在同一正文维护，不提交派生图片。

### 元数据

- 架构和设计声明设计状态、实现状态、最后更新、关联代码、关联测试和关联 ADR。
- 标准声明状态、最后更新、治理对象、依据和关联测试。
- ADR 元数据与状态按 [ADR 治理规范](adr-governance.md) 执行。
- 指南、索引和 tracker 至少声明 `状态` 与 `最后更新`。
- 架构/设计的设计状态只允许 `Draft`、`Proposed`、`Accepted`、`Rejected`、`Superseded`、
  `Historical`；实现状态只允许 `Not Started`、`In Progress`、`Implemented`、`Verified`、
  `Blocked`、`Completed`。

`Implemented` 表示实现和本地定向门禁完成；`Verified` 还要求适用全量与远端门禁通过；`Blocked`
必须声明证据、恢复条件和责任位置。

### 归档与删除

- Rejected/Superseded ADR 永久进入 `docs/history/adr/`。
- 关闭计划按根仓库[文档规范](../../../docs/standards/documentation.md#归档与删除)的归档判定执行。
- 被整体替换的起源文档进入 `docs/history/baselines/`。
- 失效指南默认删除，旧操作从 commit 或 tag 恢复。

## 执行与门禁

- `tests/test_documentation.py` 守护：文档入口集合、元数据、链接解析、代码/测试引用、
  Legacy 词禁令、CLI 命令与 parser 一致性、tracker ID 与活跃计划治理。
- 文档变更在提交前运行该测试与全量门禁（见[开发指南](../guides/development.md)）。
- 每次版本确认前按[版本末期文档整理规范](version-cleanup.md)执行文档整理轮。
- 涉及根仓库边界的文档变更，先确认根仓库规范，不越权修改其内容。

## 变更与取代

改变文档分类、事实归属、强制元数据、索引入口或归档条件时必须先新增 ADR。措辞、勘误、链接和
不改变语义的结构整理可直接修改。
