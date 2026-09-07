# ADR 0004：规范体系对齐根仓库治理模式

状态：Accepted
日期：2026-08-31
最后更新：2026-08-31
领域：工程治理
决策阶段：v0.1
取代：—
被取代：—

## 背景

QED-Tracker 现有 `docs/standards/` 共 5 份文档（documentation.md、adr-governance.md、
version-cleanup.md、local-dev.md、index.md），与根仓库 QED-Engine 已演进的规范体系存在差距：

1. 根仓库文档规范已改名 `doc-governance.md` 并扩写确认状态（暂定/已确认）、文档生命周期、
   归档 Retain/Delete 判定等治理机制；本仓库 `documentation.md` 尚未跟进。
2. 版本末期文档整理在本仓库单独成文（version-cleanup.md，[ADR 0002](0002-version-cleanup-governance.md)），
   根仓库已将其并入文档治理规范「版本与固定文档」。
3. 文档与代码双向追溯在根仓库为独立标准（code-map + DesignRef 文件头）；本仓库 `src/` 无
   DesignRef 文件头实践，追溯实际由 `docs/architecture/code-map.md` 与
   `tests/test_documentation.py` 承载，缺成文规则。
4. 本仓库无测试架构与门禁标准、无跨项目协作标准；而本项目跨项目任务频繁
   （QED-024/047/048/051 均含根仓库回执），测试门禁约定散落在 AGENTS.md 与开发指南。

## 决定

1. **`documentation.md` 改名 `doc-governance.md`**（对齐根仓库命名），并扩写：确认状态
   （暂定/已确认）与冲突优先级、文档生命周期、代码与文档追溯、版本末期文档整理节；
   文档分类表补登记 `docs/knowledge/`（QED-050 知识体系标准答案目录）。
2. **version-cleanup.md 并入 doc-governance.md「版本末期文档整理」节后删除**；长期任务
   QED-039 保留在 todo（修订 [ADR 0002](0002-version-cleanup-governance.md) 决定①的标准
   承载位置，机制本身不变）。
3. **代码与文档追溯不单独成文**：本仓库 `src/` 无 DesignRef 文件头实践，追溯规则作为
   doc-governance.md 一节（code-map 唯一事实源 + 模块增删同步 + 契约变化先设计后实现），
   不强制引入 src/ 文件头 DesignRef。
4. **新增标准 `testing.md`（测试架构与门禁）与 `cross-project-collaboration.md`
   （跨项目协作，需求接收方视角）**，按根仓库同名标准「三项目复用范本」适配裁剪。
5. **新建根 `CLAUDE.md` 薄指针**指向 AGENTS.md，不保存正文事实。
6. `local-dev.md` 完善本地/可移植配置边界声明；`adr-governance.md` 仅本地化微调。

## 后果

- standards/ 由 5 份变为 6 份（doc-governance、adr-governance、testing、
  cross-project-collaboration、local-dev + index），规则体系与根仓库对齐且适配单仓库规模。
- `tests/test_documentation.py` 白名单与 DesignRef 字符串同步更新；全库链接同轮清扫。
- 首批确认状态：doc-governance、adr-governance、local-dev 已确认；testing、
  cross-project-collaboration 于 2026-08-31 经用户确认转正为已确认。
  architecture/design 全量补登记确认状态列入 QED-039 版本末期轮待办，本次不铺开。
- 不移植 task-lifecycle.md（任务台账惯例已在 todo 6 列与计划治理测试中承载，暂不成文）。

## 关联

- 关联标准：[文档治理规范](../standards/doc-governance.md)、[ADR 治理](../standards/adr-governance.md)、
  [测试架构与门禁](../standards/testing.md)、[跨项目协作](../standards/cross-project-collaboration.md)、
  [本地开发环境](../standards/local-dev.md)
- 关联 ADR：[ADR 0002](0002-version-cleanup-governance.md)（版本末期整理机制并入文档治理规范）、
  [ADR 0003](0003-pending-design-location.md)（设计流转规则并入 doc-governance 生命周期）
- 关联测试：`tests/test_documentation.py`
- 固定文档落点（2026-08-31 落地审核补记）：决定①-⑥的落点即本批产物自身——
  [文档治理规范](../standards/doc-governance.md)、[测试架构与门禁](../standards/testing.md)、
  [跨项目协作规范](../standards/cross-project-collaboration.md)、根 `CLAUDE.md`，
  产物即落点，无额外合并项。
