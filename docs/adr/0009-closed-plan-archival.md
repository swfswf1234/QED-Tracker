# ADR 0009：关闭计划默认归档 docs/history/

状态：Accepted
日期：2026-09-11
最后更新：2026-09-11
需求方：用户（QED-Tracker 本期收尾轮，2026-09-11）
关联任务：QED-063/064/065、QED-011、QED-056/QED-057 收尾；承接 ADR 0003（目录流转）、ADR 0008（设计文档域重划）

## 背景

[文档治理规范](../standards/doc-governance.md)「归档与删除」的「关闭计划两态判定」现行默认规则为：
仅当记录已执行数据操作、迁移/发布里程碑、事故复盘或不可替代外部证据时 **Retain**（归档
`history/`），其余 **Delete**（删除，不保留计划壳）。

实际执行中，关闭计划正文（决策依据、执行记录、验收证据）删除后只能从 Git 历史恢复，人工
查阅成本高、审计链路断裂。用户 2026-09-11 裁决：关闭计划默认归档，不再默认删除。

## 决定（2026-09-11 用户裁决）

1. **关闭计划默认 Retain**：`docs/plans/` 计划关闭时，正文移入 `docs/history/baselines/`
   （保留原文件名），不删除；`plans/index.md` 与 `docs/history/index.md` 同步登记去处。
2. **Delete 仅限两种情形**：计划内容已完全并入固定文档且无独立查阅价值、或用户明确指示删除。
3. **白名单同步**：移入 `history/` 的文件从 `tests/test_documentation.py` 的
   `REQUIRED_CURRENT_DOCS` 移至 `REQUIRED_HISTORY_DOCS`；`docs/plans/*.md` 活跃集仍受
   todo 引用守护（`test_tracker_ids_and_active_plan_are_governed`）。
4. **与既有流转正交**：plans→design 的评审晋升仍按 ADR 0003；关闭归档走本 ADR，不改动晋升路径。

## 后果

- [文档治理规范](../standards/doc-governance.md)「归档与删除」节更新：关闭计划默认由 Delete
  改为 Retain（归档 `history/baselines/`），Delete 收窄为上述两情形。
- 本期关闭的 `2026-09-11-exploration-contract-alignment.md`（QED-063/064/065）与
  `2026-09-doc-cleanup-leftovers.md`（QED-056/057）按本 ADR 归档 `history/baselines/`。
- 后续所有关闭计划遵循此规范；归档正文保持当时结论，仅允许补 Historical 声明与修复链接。
