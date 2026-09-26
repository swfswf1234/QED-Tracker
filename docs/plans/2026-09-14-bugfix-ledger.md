# 缺陷修复台账（bugfix-ledger）

状态：In Progress
任务类型：Defect
最后更新：2026-09-24
需求方：用户
目标项目：QED-Tracker
评审方：用户
关联 Tracker：QED-070
归档判定：长期滚动台账，不随版本归档；条目闭环后保留记录

## 用途

集中登记后续发现的问题与 bug，跟踪现象、根因、修复与验证，避免缺陷散落在各计划中。
本台账是 v1.0 期间的滚动缺陷入口；高严重度或跨模块缺陷可另拆独立 `plans/` 文档，本台账登记指针。

## 台账

| ID | 发现日期 | 严重度 | 现象 | 根因 | 修复 | 验证 | 状态 | 关联 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BUG-003 | 2026-09-26 | 低 | Windows GBK 控制台下 `qed-tracker --json catalog show math-qe` 取不到目录：CLI 返回 `{"error": "'gbk' codec can't encode character '\u0151' ..."}` | `cli.py` 输出未做编码兜底（随控制台 code page），而冻结目录标题含 Latin 扩展字符（macron）；`PYTHONIOENCODING=utf-8` 下同一命令正常，说明是输出编码声明缺失而非数据损坏 | 未修复：发现于 QED-071 B 轮 CLI 冒烟，与拆岛无关；修复口径待裁（stdout 走 `errors="replace"` 还是显式强制 UTF-8） | 复现：GBK 控制台运行该命令 → error JSON；加 `PYTHONIOENCODING=utf-8` → 正常输出 | 待分析 | QED-071（B 轮冒烟证据）、`src/qed_tracker/cli.py` |

## 规则

- ID 使用 `BUG-<三位序号>`（如 `BUG-001`）。
- 严重度只允许 `高 / 中 / 低`；状态只允许 `待分析 / 修复中 / 待验证 / 已关闭`。
- 修复前先按系统化调试定位根因，**禁止猜测性修复**；`待验证` 必须补门禁输出证据。
- 跨项目缺陷按[跨项目协作规范](../standards/cross-project-collaboration.md)登记请求，不越权改对方仓库。
- 条目关闭后保留在本台账（长期滚动），不随版本归档。
- **v1.0 收口口径（2026-09-24 链条评审轮）**：v1.0 末期（任务链条 E 收口轮）所有条目须
  `已关闭` 或经用户裁决移交下期；台账本身继续滚动。
