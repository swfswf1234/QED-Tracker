# ADR 0005：共享表文档迁入 architecture/（跨项目契约升格为架构固定文档）

状态：Accepted
日期：2026-08-31
最后更新：2026-08-31
领域：工程治理
决策阶段：v0.1
取代：—
被取代：—

## 背景

共享表（`qed_*`）的设计契约此前由 `docs/design/shared-tables.md` 承载（Accepted/Implemented），
是全库登记的跨项目同步点（根仓库 REQ-064 系列留痕、跨项目协作规范核对条款均引用）。
用户在 2026-08-31 的 architecture 文档域梳理中裁决数据库设计文档的定位：

1. 数据库设计文档分**共享表（`qed_*`）**与**项目专用表（`qt_*`）**两区；
2. 共享表单独成文，**由 QED-Tracker 管理**，QED-Engine 与其他子项目同步；
3. 该文档升格为架构固定文档，迁入 `docs/architecture/`。

共享表文档跨目录迁移属文档事实归属变更，按
[文档治理规范](../standards/doc-governance.md)「变更与取代」须先立本 ADR。

## 决定

1. **`docs/design/shared-tables.md` 迁入 `docs/architecture/shared-tables.md`**，成为架构
   固定文档：共享表跨项目契约（命名空间、逐表设计、写权限、状态机写主体、Schema 变更流程）
   的唯一事实源；`docs/design/` 不再保留副本。
2. **文档归属与维护方为 QED-Tracker**；根仓库 `docs/design/database-design.md` 作为登记
   同步点，由根仓库侧同步引用。「共享表 schema 变更须先经根仓库登记，再由写权限方实施
   迁移」的流程条款不变（见 [跨项目协作规范](../standards/cross-project-collaboration.md)）。
3. **`architecture/database-schema.md` 分区**：保持全库 DDL 事实源地位，章节重组为
   「共享表（`qed_*`）」与「项目专用表（`qt_*`）」两区，共享区与 shared-tables.md 互链
   （契约细节——写权限、状态机写主体、同步流程——以 shared-tables.md 为准）。

## 后果

- 好处：数据库设计文档在 architecture/ 一处收齐（用户设计的四项职责映射闭环）；
  共享表契约升格为架构层事实，与冲突优先级 `architecture/ > design/` 一致；
  同步方向（本仓库管理、他项目同步）成文。
- 成本：一次全库引用更新（设计/标准/计划/tracker/守护白名单约 15 处）+ 根仓库侧登记回执
  （`database-design.md` 与根仓库对 shared-tables 的引用路径）。
- 风险：根仓库未同步前出现旧路径引用——由 `tests/test_documentation.py` 白名单与
  `rg "design/shared-tables"` 清零检查兜底本仓库侧；根仓库侧以回执任务跟踪。

## 关联

- 关联标准：[文档治理规范](../standards/doc-governance.md)（文档分类表 architecture/ 行、
  冲突优先级）、[跨项目协作规范](../standards/cross-project-collaboration.md)（共享契约
  同步条款）
- 关联文档：[共享表设计](../architecture/shared-tables.md)、
  [数据库设计](../architecture/database-schema.md)
- 关联 ADR：[ADR 0004](0004-standards-governance-alignment.md)（规范体系对齐，本轮为其
  延续）、根仓库 ADR 0003/0009（共享表来源裁决，见 database-schema.md 关联）
- 承载任务：QED-052（architecture 文档域梳理轮，todo 登记）
- 固定文档落点：决定①②落点即迁移后的 [共享表设计](../architecture/shared-tables.md) 自身
  与 [跨项目协作规范](../standards/cross-project-collaboration.md)；决定③落点为
  [数据库设计](../architecture/database-schema.md) 分区结构。
