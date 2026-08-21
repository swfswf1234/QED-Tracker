# 文档体系范本对齐设计（docs-restructure-alignment）

设计状态：Accepted
实现状态：Implemented
最后更新：2026-08-21
需求方：QED-Engine 根仓库（REQ-002 文档治理，依据 ADR 0010 文档体系分层与版本治理）
关联 ADR：`docs/adr/0001-tracker-service-architecture.md`

## 背景

QED-Engine 根仓库于 2026-08-20 通过 ADR 0010 确立文档体系三层结构：**确定文档（architecture/）
／相对确定（design/）／实时状态（trackers/）**，并以 QED-Engine 为范本调整 Axiom-Flow、
QED-Tracker 两个子项目的文档体系。用户裁决：子项目调整由本仓库执行（根仓库只建设计文档与
todo 登记）。

本仓库现状：`architecture/` 有 system-overview.md（服务架构）、code-map.md、main-line.md、
**project-status.md（实时状态，需移入 trackers/）**；`guides/` 已有 operations.md +
development.md；数据库定义 `database-schema.md` 位于 `design/`（qed_*/qt_* 唯一事实源）。

## 目标

1. `architecture/` 只放确定文档：system-overview.md（服务架构文档）+ main-line.md（主链路
   架构）+ **新增 8901 API 接口文档**（api.md）+ **database-schema.md 升级为固定数据库文档**
   （移入 architecture/ 或标注固定状态）+ code-map.md；**project-status.md 移入 trackers/**。
2. API 接口文档按 QED-Engine 长期任务「API 接口开发」分类（REQ-046）落位，QED-Tracker 四类：
   ① 自身服务生命周期（启停/重启/健康检测）；② 数据查询（五层数据库知识，传递给
   QED-Engine）；③ 资源生命周期操作（状态迁移、创建、登记、任务提交）；④ LLM 业务接口
   （检索课程对应教程、选择书目等）。
3. `adr/index.md` 声明当前版本（本仓库沿用自身纪元）。
4. `design/` 三态梳理：已完成使命的文档（如 three-table-schema / database-schema-ownership
   等）标 Superseded / 移入 history。
5. 契约测试同步更新（architecture 目录集合、design 目录集合、trackers 集合、guides 集合等）。

## 范围与非目标

- 范围内：文档结构调整、索引与链接更新、本仓库契约测试同步（代码）。
- 非目标：不改动任何功能代码；不迁移数据；不提交 git（由本仓库自身执行提交）。

## 验证与回执

- 门禁：`pytest tests -q` + `ruff check src tests` + 文档守护 `tests/test_documentation.py` 全绿。
- 回执根仓库 REQ-002 / REQ-046（提交号 + 门禁输出）。

## 执行人

本仓库（QED-Tracker）按 todo 登记执行；执行前先由用户评审本设计。
