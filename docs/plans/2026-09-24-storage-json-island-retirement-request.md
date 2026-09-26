# 存储链路治理请求包（根仓库 ARCH-032 / ADR 0018 承接讨论稿）

状态：待评审
任务类型：Plan（跨项目请求讨论稿；本文件不改代码、不改各任务契约）
最后更新：2026-09-24
需求方：QED-Engine 根仓库（ARCH-032 存储链路规范化轮，勘察证据见其计划壳「勘察证据」节）
目标项目：QED-Tracker
评审方：用户
执行方：QED-Tracker（按本仓 AGENTS.md 门禁执行）
关联设计：根仓库 `docs/standards/storage-conventions.md`（顶层白名单登记制、元数据 JSON 岛禁止）、`docs/design/dataset-conventions.md`（白名单节）
关联 ADR：根仓库 `docs/adr/0018-data-root-whitelist-and-meta-json-ban.md`；本仓数据库模型口径见 `docs/adr/0006-database-model-as-schema-rebuild.md`
关联 Tracker：根仓库 todo REQ-093；本仓 QED-071
归档判定：待关闭时按 [ADR 0009](../history/adr/0009-closed-plan-archival.md) 两态判定

## 目标与验收标准

根仓库 2026-09-24 存储链路全链路勘察发现三项与本仓数据治理相关的存量问题，按 ADR 0018
与新升格的存储标准须予处置。需求方（根仓库 agent）不修改本仓代码，仅登记本请求包；
逐项验收标准如下：

### R1 meta JSON 岛代码退役（接口/契约级）

- 现状：`src/qed_tracker/inventory.py:42-46` 构造并读写
  `<data_root>/qed-tracker/meta/resources/<sha256>.json` 与 `meta/transfers/axiom/
  <sha256>.json`（`_register_verified`、axiom 传输留痕）。该元数据岛已被根仓库 REQ-032
  判死（meta/ 退役、DB 为元数据唯一事实源），磁盘存量已删，但代码一旦 register 触发即
  重建，违反 ADR 0018「元数据 JSON 岛禁止」。
- **文档面同样残留 JSON 岛口径**（须与代码同轮收口，勘察实证）：
  `docs/architecture/system-overview.md:14,187`（「资源事实存放于 meta/resources/ 单资源
  JSON」——仍写作事实源）、`docs/architecture/database-private-tables.md:37`（「论文走
  arXiv 下载 + meta/resources/ JSON（kind=paper），MySQL 无索引」——论文记录无 DB 承载，
  与 `qt_books.kind=paper` 行口径互相矛盾，须一并定谳）、`docs/architecture/main-line.md:89`、
  `docs/design/download-pipeline.md:375`（资源 schema v1 落 `meta/resources/<sha256>.json`）。
- **隐含前置（时序约束「先迁列、后拆岛」，需求方 2026-09-24 全链路复扫新发现）**：内容哈希
  事实当前在岛侧——`qt_books` 无 sha256/size 列（`docs/architecture/database-private-tables.md:434`
  自证），完整性校验 `inventory.verify`（`inventory.py:182-196`）读的是 `meta/resources/<sha256>.json`。
  拆岛必须按序：① `qt_books` 经 Alembic 新增内容身份列（sha256、size；命名与本仓
  `sha256:<digest>` 口径一致，可对齐兄弟仓 `af_parse_jobs.source_sha256` 先例）；② 从 meta JSON
  存量与磁盘重算哈希双源回填并逐本对账；③ `ResourceInventory` 登记/校验/读取切到 DB；
  ④ 最后删除 `qed-tracker/meta/**` 写入路径。顺序颠倒会使哈希事实源在窗口期悬空、
  完整性校验静默失效。
- **承接前置（本仓守护）**：本讨论稿为 docs/ 新增文件，`tests/test_documentation.py:183`
  对全部文档做硬编码白名单等值断言——贵方承接执行时须先把本文件与 todo 引用同步进白名单
  （判例：历史 L-12「曾漏 integration-issues 致守护红」），需求方不代改测试代码。
- 验收：按上述「先迁列、后拆岛」①~④ 顺序执行；代码不再向 `qed-tracker/meta/**` 写入；
  `ResourceInventory` 的登记/留痕/校验语义落 DB（`qt_books` 新列 + `qt_sources` 现有列承接），
  相关测试同步；上述四处文档同步实况（含论文记录的 DB 承载定谳）。

### R2 下载 staging 残留清理（文案/操作级并入即可）

- 现状：`tmp/qed-tracker/downloads/` 存在 2026-08-28 的 50MB `.download` staging 残留
  （Apostol Calculus Vol.2），违反「任务结束清理」生命周期；staging 文件无超时回收机制。
- 验收：下载任务失败/取消路径清理 staging 有明确行为（或启动时清扫策略），并有测试覆盖；
  存量残留文件由用户确认后手工删除（数据根操作，不由 agent 自动执行）。

### R3 qt_books 下载错误列与起止时间戳（契约级、可延后）

- 现状：`fail_download` 只置 `status=failed` 不写原因（`db/knowledge_repository.py:874-876`），
  原因仅散落在 `qt_sources.note`；无下载开始/结束时间戳（只有 created_at/updated_at）。
  「任务→文件→失败原因」链路在书级断裂。
- 验收：`qt_books` 增下载错误摘要列与 started_at/finished_at（或等价语义），Alembic 迁移 +
  文档（`docs/architecture/database-shared-tables.md` 或私有表文档）+ 测试同步；属 v1.0
  排期外可候补，由用户裁决优先级。

## 边界与非目标

- 本请求包不要求改动 raw/parsed 文件布局与既有 sha256 幂等机制（勘察确认其为正面资产）。
- 需求方不在本仓产生代码改动与 git 操作；R1~R3 的执行、排期与门禁由本仓自行决定。
- 探索发起文档 `tmp/exploration/` 例外语义不变。
