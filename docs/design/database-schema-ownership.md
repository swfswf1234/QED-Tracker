# 数据库设计确认：qt_* 表结构事实源（QED-023，承接根仓库 REQ-026）

设计状态：Accepted
实现状态：Not Started
最后更新：2026-08-10
关联代码：`src/qed_tracker/db/`（模型与迁移）
关联测试：`tests/test_resources_api.py` 等库相关测试
需求方：QED-Engine（根仓库 REQ-026；2026-08-09 用户裁决：数据库设计先在各子项目确认，
根仓库只做指引和规划）
执行方：QED-Tracker
接口面：qed 库 `qt_*` 表清单与结构（qt_resources 及后续新增表），Alembic 迁移
评审方：用户
验收标准：见下「成功标准」

## 背景

三项目共享 `qed` 库（根仓库 ADR 0003），表命名空间隔离：本仓库只使用 `qt_*` 前缀表。根仓库
`docs/design/database-design.md` 原承担各项目表结构的细节设计；2026-08-09 用户裁决：`qt_*`
表结构由本仓库确认并维护（既有 `docs/design/tracker-service.md` 已含 qt_resources 明细），
根仓库 database-design.md 按「指引与规划」收尾，回执后同步。

## 变更内容

1. **事实源声明**：`qt_*` 表清单与结构的事实源为本仓库 `docs/design/tracker-service.md` +
   `src/qed_tracker/db/` 迁移；新增表时先更新该设计文档再实现（先文档后实现）。
2. **回执**：确认后回执根仓库 REQ-026，根仓库 database-design.md 补登记 qt_* 表清单摘要并
   收尾为指引与规划。

## 成功标准

- 本仓库正式声明 `qt_*` 表结构事实源位置（本文件与 tracker-service.md 链接生效）。
- 根仓库 REQ-026 收到回执，根仓库 database-design.md 收尾完成。