# 规范索引

状态：Current
最后更新：2026-08-04

本目录是 QED-Tracker 工程治理规则的唯一事实源。根 [AGENTS.md](../../AGENTS.md) 负责快速路由，
[文档规范](documentation.md) 负责文档事实边界，[ADR 治理](adr-governance.md) 负责决策登记。

| 标准 | 治理对象 | 自动门禁 |
| --- | --- | --- |
| [文档规范](documentation.md) | 文档分类、写作、元数据、索引、命名、归档与删除 | `tests/test_documentation.py` |
| [ADR 治理规范](adr-governance.md) | ADR 准入、编号、元数据、状态、取代与归档路径 | `tests/test_documentation.py`（链接与元数据守护） |

## 规则

- 标准声明状态、最后更新、治理对象和关联测试，并使用统一公共章节。
- 改变规范语义必须先新增 ADR（见 [ADR 索引](../adr/index.md)）。
- 治理模式以 QED-Engine 根仓库标准为上游参照（见根仓库
  [规范索引](../../../docs/standards/index.md)）；本目录只保存适配子项目的副本，语义变化先经
  根仓库 ADR 评审。
