# ADR 0008：设计文档域职责重划

状态：Accepted
日期：2026-09-07
最后更新：2026-09-07
需求方：用户（QED-Tracker 文档治理轮，Task C）
关联任务：QED-Tracker todo 本轮文档重整；承接 ADR 0003（目录流转）与 ADR 0007（按域拆分）先例

## 背景

design/ 目录经多轮演进后职责失义：

1. `tracker-service.md` 四职责混杂（8901 端点契约、Axiom 消费面、配置、书单与数据布局），
   端点表 16 条中 10 条已随 QED-030 从代码消失，任务模型与数据布局两节与实现脱节；
2. 下载链三处分立（book-download-registration、acquisition-and-inventory、tracker-service
   书单节），管线全貌分散；
3. 服务运行面散落两文（service-lifecycle、model-mode-config），高度互补；
4. 教程命名（tutorial-naming）与知识录入（knowledge-import）同域分立；
5. source-discovery 实为进行中的探索工作（QED-018 已关闭后延续），不是能力设计；
6. design/index.md 类别（接口契约/评审与来源/治理）随成员迁出已失义。

## 决定（2026-09-07 用户裁决，五项）

1. **tracker-service.md 拆散退役**：Axiom-Flow 消费面 → architecture/api.md「外部接口」节；
   配置与多项目约定 → 新建管理中心；math-qe 书单规格 → 下载管线；QED-030 退役内容
   （qt_resources 状态机、旧任务模型、数据布局）随归档消失。
2. **下载管线集中一篇**：book-download-registration.md 吸收 acquisition-and-inventory.md +
   tracker-service 书单规格 + catalog 冻结目录链，改名 `download-pipeline.md`
   （与 exploration-pipeline 对称）。
3. **新建 design/service-management.md（服务管理中心）**：service-lifecycle + model-mode-config
   合并 + 多项目约定导航节（只链接根仓库事实源，不复制正文）；两篇旧文归档。
4. **source-discovery.md 整篇移 plans/**（→ `plans/2026-09-source-discovery.md`，todo 登记
   QED-054）：设计契约部分并入 download-pipeline.md，本计划承载持续探索工作。此为
   design→plans 反向流转首例（与 ADR 0003 的 plans→design 正向流转正交）。
5. **tutorial-naming.md 并入 knowledge-import.md**：命名格式、mainline 命名路径、前端展示
   边界与决策登记作为「教程命名规范」节并入；textbook_ref 结构与 adopt 幂等以其新契约为准
   不重复迁移；旧文归档。

## design/ 类别变更

- **保留/调整后类别**：能力设计（main-line-curriculum、exploration-pipeline、
  knowledge-import、download-pipeline、paper-discovery）、服务与运行（service-management）、
  数据设计（database-private-tables、database-shared-tables，链接条目）。
- **解散三类**：接口契约（成员全部迁出）、评审与来源（source-discovery 移 plans）、
  治理（governance-contract-alignment 早已归档，空类）。
- 每篇设计文档在 design/index.md 登记一行「管/不管」职责边界；**design/index.md 是职责
  登记处**——后续 plans/ 文档归档晋升或新增设计文档，先查登记处确定唯一归属，禁止同类
  内容多文并存。

## 后果

- 白名单同步：REQUIRED_CURRENT_DOCS/DESIGN_DOCS 删 6 增 1（download-pipeline），plans 增 1，
  REQUIRED_HISTORY_DOCS 增 5（tests/test_documentation.py）。
- 5 篇文档归档至 history/baselines/（acquisition 用 2026-07- 前缀，按文档纪元命名），
  归档锚点以 2026-09-07 工作树状态冻结。
- 约 60 处入站引用改指（AGENTS、ADR 0001/0006、architecture 全套、guides、plans、
  design/index、src/tests 注释级）。
- QED-010（CLI 转 HTTP）的规划语境原挂在 tracker-service.md「CLI」节，现由 todo QED-010 行
  承接。
- 服务运行面事实源自本文起为 service-management.md；下载链事实源为 download-pipeline.md；
  端点与 Axiom 消费面契约为 architecture/api.md。
