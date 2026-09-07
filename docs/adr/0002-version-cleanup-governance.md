# ADR 0002：版本末期文档整理长效机制

状态：Accepted
日期：2026-08-21
最后更新：2026-08-31
领域：工程治理
决策阶段：v0.1
取代：—
被取代：—

## 背景

QED-Engine 根仓库经 [ADR 0010](../../../docs/history/adr/v0.1/0010-documentation-versioning.md) 确立文档体系
三层结构（确定文档 architecture/ ／相对确定 design/ ／实时状态 trackers/），并声明版本末期
将本版本 ADR 决策合并进固定文档、`history/` 记录前版本（根仓库
[文档治理规范](../../../docs/standards/doc-governance.md)「版本与固定文档」「归档与删除」）。

QED-Tracker 的文档体系首轮对齐（QED-039）已完成固定化，但版本末期的周期整理没有固化流程：
每次升版本时需要人工回忆并逐项检查固定文档、design 三态、tracker 一致性，容易遗漏且无法
保证一致性。

## 决定

1. **新增标准版本末期文档整理规范**（登记时位于 `../standards/version-cleanup.md`；
   勘误：2026-08-31 按 [ADR 0004](0004-standards-governance-alignment.md) 并入
   [文档治理规范](../standards/doc-governance.md)「版本末期文档整理」节），固化每次版本确认前
   的文档整理轮：ADR 决策合并、固定文档更新、design/ 三态梳理、trackers 实时状态同步、
   链接与 metadata 校验、回执根仓库。
2. **QED-039 转为长期任务**：在 `docs/trackers/todo.md` 中长期保留（状态「进行中」），
   指向 version-cleanup.md 标准；每次版本末期执行一轮并更新成功标准，不再作为一次性任务关闭。
3. **对齐根仓库治理模式**：检查清单、三态规则与归档路径以根仓库 documentation.md 为上游，
   本仓库只保存适配子项目规模的副本，语义变化先经根仓库 ADR 评审。
4. 每轮执行的记录写入 `docs/design/docs-restructure-alignment.md`（或归档为历史），
   回执根仓库 REQ-002 / REQ-046。

   > 勘误（2026-08-31 落地审核补记）：docs-restructure-alignment.md 已归档至
   > `docs/history/baselines/`；每轮执行记录位置按
   > [文档治理规范](../standards/doc-governance.md)「版本末期文档整理」执行流程，
   > 登记在 QED-039 todo 证据列。

## 后果

- 版本末期文档整理成为可重复执行的受管流程，减少遗漏与不一致。
- 新增一份标准与一个持续 todo 条目，需要维护其内容与关联测试。
- standards 实质规则变更仍需新增 ADR（本 ADR 之外的变更）。
- 首轮执行由 QED-039 登记，后续每版本末期由用户确认升版本时触发。

## 关联

- 关联标准：[文档治理规范](../standards/doc-governance.md)（版本末期文档整理节）、
  [ADR 治理](../standards/adr-governance.md)、[ADR 0004](0004-standards-governance-alignment.md)
- 关联设计：[文档体系范本对齐](../history/baselines/docs-restructure-alignment.md)（Historical，2026-08-31 归档）
- 关联 ADR（根仓库）：[ADR 0010](../../../docs/history/adr/v0.1/0010-documentation-versioning.md)
- 固定文档落点（2026-08-31 落地审核补记）：决定①整理轮清单 →
  [文档治理规范](../standards/doc-governance.md)「版本末期文档整理」节；决定②QED-039
  长期任务 → [待办列表](../trackers/todo.md)；决定③上游对齐 →
  [文档治理规范](../standards/doc-governance.md)依据行与
  [规范索引](../standards/index.md)上游条款；决定④执行记录 →
  [文档治理规范](../standards/doc-governance.md)「版本末期文档整理」执行流程
  （QED-039 证据列）。
