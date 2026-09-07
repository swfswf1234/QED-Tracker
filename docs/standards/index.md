# 规范索引

状态：Current
确认状态：已确认
最后更新：2026-08-31

本目录是 QED-Tracker 工程治理规则的唯一事实源。根 [AGENTS.md](../../AGENTS.md) 负责快速路由，
[文档治理规范](doc-governance.md) 负责文档事实边界与生命周期，[ADR 治理](adr-governance.md)
负责决策登记。指南负责可重复操作步骤，ADR 保存决定与理由——这些位置不得复制标准正文。

| 标准 | 确认状态 | 治理对象 | 权威产物 | 自动门禁 |
| --- | --- | --- | --- | --- |
| [文档治理规范](doc-governance.md) | 已确认 | 文档分类边界、确认状态、生命周期、代码与文档追溯、版本末期整理、归档与删除 | code-map、todo/plans 台账、ADR index | `tests/test_documentation.py` |
| [ADR 治理规范](adr-governance.md) | 已确认 | ADR 准入、编号、元数据、状态、取代与归档路径 | `docs/adr/index.md` | `tests/test_documentation.py`（链接与元数据守护） |
| [测试架构与门禁](testing.md) | 已确认 | 测试隔离边界、门禁组成、治理契约测试编写规范 | 守护面清单（testing.md 内） | `tests/test_documentation.py` |
| [跨项目协作规范](cross-project-collaboration.md) | 已确认 | 需求承接、评审、执行、验收回执与诊断纪律 | 双方 todo 与回执记录 | 无（流程治理） |
| [本地开发环境](local-dev.md) | 已确认 | 本地机器标识、环境依赖、构建命令与开发约定 | 本文档自包含 | 无 |

## 规则

- 标准声明状态、确认状态、最后更新、治理对象、依据和关联测试，并使用统一公共章节。
- 改变规范语义必须先新增 ADR（见 [ADR 索引](../adr/index.md)）。
- 治理模式以 QED-Engine 根仓库标准为上游参照（见根仓库
  [规范索引](../../../docs/standards/index.md)）；本目录只保存适配子项目的副本，语义变化先经
  根仓库 ADR 评审。
