# QED-071 存储链路治理实施计划（meta JSON 岛退役 + staging 生命周期）

状态：Current（2026-09-24 A 轮完成、B 轮待排期——执行与门禁证据见「A 轮收口记录」；**Q1~Q5 已于 2026-09-26 裁决 D10~D14**，见「进度与复核记录」）
任务类型：Plan（承接根仓库 ARCH-032 / ADR 0018 请求包 QED-071）
最后更新：2026-09-26
本轮范围：**A 轮 = 数据根（`QED_DATA_ROOT`）侧**；B 轮（数据库侧）本轮**只交付设计文档，不执行 DDL、不改 ORM 模型、不回填真实库**
关联 ADR：根仓库 [ADR 0018](../../../docs/adr/0018-data-root-whitelist-and-meta-json-ban.md)（顶层白名单 + JSON 岛禁止）；本仓 [ADR 0006](../adr/0006-database-model-as-schema-rebuild.md)（模型即 schema，重建式自愈）
关联设计：[下载管线设计](../design/download-pipeline.md)、[专用表设计](../architecture/database-private-tables.md)、[系统总览](../architecture/system-overview.md)、[主链路](../architecture/main-line.md)
关联 Tracker：QED-071；根仓库 todo REQ-093（回执）/ REQ-094（存量清理，仅提清单）
承接请求包：[存储链路治理请求包](2026-09-24-storage-json-island-retirement-request.md)
归档判定：待关闭时按 [ADR 0009](../history/adr/0009-closed-plan-archival.md) 两态判定

## 目标与成功标准

把「资源内容身份 + 去重索引 + 校验视图」从 `<data_root>/qed-tracker/meta/**` JSON 岛迁到 MySQL `qed` 库，
并补齐下载 staging 的清理生命周期。因裁决 D5（DB 部分先停在文档中），拆两轮：

| 轮次 | 交付 | 状态 |
| --- | --- | --- |
| A 轮 | 数据根侧：Axiom 传输留痕判废删除、staging 年龄清扫、岛相关死码/死配置清理、局部反岛守护、**B 轮设计文档定稿**、存量残留清理 | **A 轮完成（2026-09-24），B 轮待排期** |
| B 轮 | 数据库侧：`qt_books` 内容身份列手工迁移、磁盘重算回填对账、去重/校验/论文索引读 DB、`meta/resources/**` 停写、`qed-tracker/` 顶层区消失、全局反岛守护 | 后续轮，本轮只交付其设计契约 |

### A 轮成功标准（逐条可验证）

1. `qed-tracker/meta/transfers/**` 无代码写入路径；`record_axiom_transfer`、`transfers_dir` 全仓命中 0。
2. `tmp/qed-tracker/downloads/` 具备基于 mtime 年龄的清扫，挂在服务构造与取书任务入口；四项边界测试齐
   （阈值内保留 / 阈值外删除 / 非本仓命名模式不删 / 不越出 `tmp/qed-tracker/downloads/`）。
3. 死码与死配置清除：`Inventory.remove()`（无调用方）、`config.state_dir`（无代码引用）及其两处测试断言。
4. 局部反岛守护落地（A-W4）；**全局 `qed-tracker/` 断言留 B 轮**——A 轮资源岛仍在写，全局断言必红。
5. B 轮设计契约以「待实现」口径写入 `docs/architecture/database-private-tables.md`、
   `docs/design/download-pipeline.md`、`docs/architecture/system-overview.md`、`docs/architecture/main-line.md`，
   含 DDL 草案与红线顺序；`src/` 的 DB 层与真实库零改动。
6. `tests/test_documentation.py` 全绿；开发指南完整门禁通过；向根仓库发 REQ-093 **部分完成**回执。

### B 轮目标（本轮只登记，不执行）

1. `rg -c "qed-tracker/meta|meta/resources|meta/transfers"` 在 `src/`、`tests/`、`docs/`（当前层，`history/` 除外）
   命中 0，且 `<data_root>/qed-tracker/` 不再被任何代码路径构造——根仓 ADR 0018 顶层白名单只有 `raw/`、`tmp/`、
   `parsed/`、`backups/`，该顶层目录本身即野生区（勘误 M3）。
2. `qt_books` 具备内容身份列（`sha256`/`size_bytes`/`page_count`），存量书目经磁盘重算回填并出对账报告；
   迁移过程**不触发 `ensure_schema` 整表重建**。
3. 书侧 sha256 去重、`verify` 语义、论文去重索引全部读 DB；DB 不可用时**显式报错**，不静默降级。
4. `ResourceRecord`/资源 schema 的落点口径由「JSON 岛」改为「DB 列读视图」，CLI 契约同步。

## 范围与非目标

**A 轮范围内**：D3（Axiom 留痕判废）、R2（staging 生命周期）、岛相关死码清理、B 轮设计文档定稿。

**非目标（A 轮不做）**：

- 不停写 `meta/resources/**`：它当前是书侧 sha256 去重（`application/resources.py:104`）、论文去重索引
  （`application/papers.py:253-258`）、`inventory verify`（`cli.py:521-528`）三项的**唯一载体**。
  DB 列不存在时先停写 = 三重静默失效。这是 A/B 轮切分的唯一硬边界。
- 不执行 DDL、不改 `src/qed_tracker/db/models.py`、不回填真实库（B 轮，且需用户发令）。
- 不改论文记录契约（D2 后续裁定）；不做 R3（下载错误列与起止时间戳，候补）。
- 不改 `raw/`、`parsed/` 布局与既有 sha256 幂等落盘命名（请求包确认为正面资产）。
- 数据根存量删除、`tmp/参考书籍/` 迁移等 D 类操作只出清单，等用户执行或授权。

## 用户裁决记录（A 轮 2026-09-24：D1~D9；B 轮开工 2026-09-26：D10~D14）

| 编号 | 裁决 | 对本计划的影响 |
| --- | --- | --- |
| D1 | schema 演进走**一次性手工迁移**，迁移前备份进 `<data_root>/backups/` | 不引 Alembic、不改 ADR 0006；B-W1 按「备份 → ALTER → 改模型」硬顺序；根侧 `backups/` 台账登记义务随 B 轮产生 |
| D2 | 论文记录承载面**后续裁定** | B-W3 只做「岛读 → DB 读」的最小替换（`qt_selections.downloads` 派生），不新增论文 schema；拆岛不被此项阻塞 |
| D3 | Axiom 传输留痕**不需要** | A-W1 直接删 `axiom.py:72,75` 调用点与 `inventory.py:209-214`。已核实 `meta/transfers/**` 全仓**无读取方**（只有写入与测试断言），判废零功能损失 |
| D4 | 现在优先做优化 | （分支安排被 D9 取代）A 轮含 `docs/architecture/`、`docs/design/` 契约变更 |
| D5 | **本轮只做数据根侧，数据库部分停留在文档中** | A/B 轮拆分；B 轮只交付设计契约，执行与 DDL 推后 |
| D6（原 Q6） | 数据根存量残留**授权 agent 在本机执行**清理 | A-W6 由「只出清单」升级为「出清单 + 本机执行」；执行仍先展示逐项清单再动手，`tmp/参考书籍/`（用户资产）处置方式到时单独确认 |
| D7（原 Q7） | staging 清扫阈值 = `timeout × retries × 4`，绝对下限 6 小时 | A-W2 阈值定死并写进 `download-pipeline.md`；严格大于单次下载最长寿命，无需 in-flight 注册表 |
| D8（原 Q8） | 清扫只挂自动入口，**不加公开 CLI** | 无新命令，CLI 契约零变更 |
| D9（原分支裁决） | **A 轮直接在 `develop` 做**，不建 `feat/storage-json-island-retirement` | 取代 D4 的分支安排；A-W0 改动已在 develop 工作区，逐项提交 |
| D10（原 Q1） | `inventory verify/list` 的 `--json` 输出 **`resource_id` → `book_id`** | B-W2/B-W3 的 CLI 契约定死：输出 `book_id`；`api.md`/CLI 测试同步属公开 CLI 变更 |
| D11（原 Q2） | legacy catalog 路径（`run_catalog`/`find_by_catalog_target`/`catalog_ref`）**退役** | B-W3 删除该读路径而非改造，B 轮面积显著缩小；`catalogs/math-qe.json` 与冻结目录匹配（`matching.py`/`catalog.py`）**不在退役范围** |
| D12（原 Q3） | `ResourceRecord` **保留为内存 DTO** | 落点口径改「DB 列的读视图」，下游调用点最小改动；资源 schema v1 不删 |
| D13（原 Q4） | **不引入**「磁盘仅缺列时拒绝重建」加法列自愈 | 不改 ADR 0006、无需新 ADR；只登记纪律「私有表加列 = 手工迁移 + 备份」 |
| D14（原 Q5） | 论文承载面**不提前**到 B 轮，保持 D2 | B-W3 论文去重只做 `qt_selections.downloads` 派生最小替换；B 轮不被 D2 阻塞 |

## 前置条件

A 轮：

1. A-W0 文档承接（已完成）——`tests/test_documentation.py:22-66` 的 `REQUIRED_CURRENT_DOCS` 是全量等值断言
   （`:183-184`）；请求包与本计划两份文件此前均未入白名单，守护原为红，现已修。
2. 门禁绿基线并记录 pytest 通过数，用于 A 轮收口对账。（已完成：2026-09-24 基线 `conda run -n qed_env python -m pytest tests -q` = **496 passed, 1 skipped**）
3. ~~待裁 Q6、Q7 有答案~~ 已裁决（D6/D7/D8，2026-09-24）。

B 轮（开工前置，本轮只登记）：

1. 真实库基线证明：启动自愈返回 `(created, rebuilt) == (0, 0)`（`db/schema.py:138-170`）。
2. 用户确认可执行 D 类数据操作（`mysqldump` 备份 + ALTER）。
3. ~~Q1~Q5 定案（CLI 契约、legacy catalog 去留、`ResourceRecord` 去留、加法列自愈、论文承载面）~~
   **已定案（2026-09-26，D10~D14，全按建议默认）**——剩余硬门只余上文 1、2 两项。

### B 轮关键时序约束（防数据丢失；本轮写进设计文档并作为 B 轮开工硬门）

`ensure_schema` 对 `Base.metadata` 声明表的规则是：磁盘列名集合 ≠ 模型列名集合即 **DROP + CREATE 全表重建**
（`src/qed_tracker/db/schema.py:91-94` 判漂移，`:150-166` 执行；本仓无 Alembic，
[ADR 0006](../adr/0006-database-model-as-schema-rebuild.md) 决定 1/2）。`qt_books` 承载人工梳理的书目决策链
（`status`/`roles`/`priority`/`notes`），被 `qt_sources.book_id` 外键引用，并与
`parsed/<domain>/<course>/<book_id>/` 关联——**一旦被重建即不可从任何事实源重放**。

红线顺序：**先 ALTER 磁盘表，后改 ORM 模型**。任何反向操作（先提交模型改动、再补 DDL）都会在下次服务启动时
清空 `qt_books`。B-W1 的三个子步骤不得拆分到不同提交里跨顺序落地；改模型后须立刻验证 `rebuilt == 0`。

## A 轮工作项

### A-W0 文档承接（已完成，无行为变更）

- `tests/test_documentation.py` `REQUIRED_CURRENT_DOCS` 增加请求包与本计划两条。
- `docs/plans/index.md`「活跃计划」增加两条目；todo QED-071 行镜像裁决摘要与计划链接。
- 验证：`tests/test_documentation.py` 8 passed。

### A-W1 Axiom 传输留痕判废（D3）

- 删 `axiom.py:72,75` 两处 `inventory.record_axiom_transfer(...)` 调用、`inventory.py:209-214` 方法本体、
  `inventory.py:43` 的 `transfers_dir` 属性。
- 语义变更写进 `docs/design/download-pipeline.md`：Axiom 交付结果只作为 `push()` 返回值透出，不再落盘留痕；
  需审计时经 `qed_llm_calls`/`qt_tasks` 与 Axiom-Flow 侧记录反查（本仓不新建承载）。
- 测试：`tests/test_axiom.py:33,107` 由「断言 transfers JSON 内容」改为「断言返回值字段 + 断言不生成
  `qed-tracker/meta/transfers` 目录」。

### A-W2 staging 年龄清扫（R2）

根因比请求包更具体：`.download` 是 `stage_download` 的**成功产物名**（`application/resources.py:71`），
`DownloadManager` 只管 `.part`；失败/取消路径清理**已经存在**（`resources.py:83,111`、
`application/book_fetch.py:459`、`downloader.py:223,226`）。08-28 的 50MB 残留来自第三条路——候选被编排层
超时放弃后，**孤儿线程照样把 `.download` 写完，此时已无人 promote 或清理**（`resources.py:61` 的
`staging_tag` 注释即为此而加，日期与残留同日）。所以请求包「失败/取消路径清理」这条验收覆盖不到本 case，
残留必然复发。

- 新增纯函数 `sweep_downloads(directory: Path, *, max_age_seconds: int) -> list[Path]`，放 `inventory.py`
  （与 `downloads_tmp_dir` 同处，数据根路径语义集中），只匹配本仓命名模式 `*.download`、`*.download.part`。
- 阈值 = `settings.timeout_seconds × settings.retries × 4` 且绝对下限 6 小时（裁决 D7），保证严格大于单次
  下载最长寿命——因此**不需要**进程内 in-flight 注册表即安全（卡死由 httpx timeout 兜底）。
- 挂载点：`TrackerApplication.__init__`（`api/main.py:92` 附近，服务启动即清）+ 取书任务入口
  （`api/main.py:226` `_book_download_handler`、`:233` `_tutorial_fetch_handler`）。不另挂 CLI（裁决 D8）。
- 边界硬约束：只碰 `tmp/qed-tracker/downloads/`，不递归、不删目录、不碰 `tmp/exploration/` 与其他项目前缀；
  清扫失败（权限/占用）只告警不抛出，不得阻断取书任务。
- 测试：`os.utime` 伪造年龄覆盖四项边界 + 阈值计算本身。

### A-W3 岛相关死码与死配置清理

- 删 `Inventory.remove()`（`inventory.py:159-165`，全仓无调用方）。
- 删 `config.state_dir`（`config.py:64-66`，全仓无代码引用）与 `tests/test_config_catalog_matching.py:57,116`
  两处断言。
- 改 `inventory.py:1-6` 模块 docstring：明写「`meta/resources/` 岛为 B 轮退役对象，当前仍是内容身份唯一载体」，
  防止后续 agent 依 ADR 0018 误判其已退役。

### A-W4 局部反岛守护

- 契约测试并入 `tests/test_data_layout.py`（该文件已负责数据根布局断言）：
  ① `src/` 全仓不出现 `meta/transfers` 字符串；② 构造 `Inventory` 并跑完 A-W2 清扫后，
  `qed-tracker/meta/transfers/` 不生成、`tmp/qed-tracker/downloads/` 终态符合预期。
- **不做**「`<data_root>/qed-tracker/` 不存在」的全局断言（留 B 轮收口启用），也不做 A 轮成功标准 1 的全仓
  `rg` 零命中断言——资源岛仍在写。

### A-W5 B 轮设计文档定稿（本轮交付，不落代码）

- `docs/architecture/database-private-tables.md`：`qt_books` 三列目标契约与 DDL 草案（见 B-W1 表）、
  上述红线顺序、「B 轮前/后」两种口径标注、`:434`「无 sha256/size/page_count 列」改写为带轮次注记、
  `:37` 历史缺口加现状注记、`:422` 论文条目标注「实现未落地（D2 待裁）」。
  命名对齐兄弟仓 `af_parse_jobs.source_sha256` 与本仓 `sha256:<digest>` 口径。
- `docs/design/download-pipeline.md`：资源 schema v1（`:375-382`）落点由 `meta/resources/<sha256>.json` 改为
  「B 轮：`qt_books` 列 + `qt_sources` 现有列」；staging 生命周期契约（A-W2 阈值与清扫语义）本轮即写入实况。
- `docs/architecture/system-overview.md:14,187`、`docs/architecture/main-line.md:89`：同步岛口径（现写作
  「资源事实存放于 `meta/resources/` 单资源 JSON」）。
- B 轮读路径切换表（设计定稿，实现推后）：

| 现读岛位置 | B 轮落点 |
| --- | --- |
| `resources.py:104` sha256 去重 | `qt_books` 按 `sha256` 查行 + `file_path` 存在性判定；人工 `book_register`/`book_import`（`api/main.py:1203,1225`）本就不写岛、sha 只进 `qt_sources.note` 自由文本 → 切 DB 后两轨首次一致 |
| `papers.py:253-258` 论文去重 | `SelectionStore.downloaded_arxiv_ids()` 从 `qt_selections.downloads` 派生（字段已有 `arxiv_id`/`resource_id`/`status`，`papers.py:213-224`）；岛内 `kind=paper` 已随存量删除丢失，**去重当前实际已失效**，DB 派生严格优于现状 |
| `cli.py:521-528` `inventory verify` | DB 三列 vs 磁盘重算；输出 `resource_id` → `book_id`（**已裁 D10，2026-09-26**） |
| `inventory.py:123-128` 写盘、`:152-180` 读、`:198-207` `scan` | 删除；`raw_course_dir`/`raw_general_dir`/`downloads_tmp_dir` 与 `data_root` 访问器留原模块，`Inventory` 类退役不留兼容壳 |
| `books.py:123` `find_by_catalog_target`、`run_catalog`、`catalog_ref` | **退役（已裁 D11，2026-09-26）**：随 B-W3 删除，不改造为 `qt_knowledge` refs 派生 |

- 强制口径：DB 未配置/不可达时报错退出（沿用 `cli.py:221-227,930-933` 的 `db_configured` 门），**不得**回退读岛
  或静默跳过——请求包未覆盖的常态风险（勘误 M4）。
- 勘误记录（回执根仓时带上）：C1 本仓无 Alembic，加列即整表重建；C2 请求包所称 `qt_books.kind=paper` 不存在
  （类型由 `roles` 承载，`db/models.py:189`），且 `database-private-tables.md:37` 属「背景与动机」对已退役旧三表
  模型的历史描述，与 `:422` 当前契约不构成文档矛盾——真正问题是实现未按 `:422` 落地；C3 「双源回填」实为单源
  （岛存量已删）且论文去重索引随删除已静默失效；C4 请求包所称 `ResourceInventory` 实际类名为 `Inventory`。

### A-W6 数据根存量清单（出清单 + 本机执行，裁决 D6）——已执行 2026-09-24

实测 `<data_root>`（`D:\coding\QED-Engine\dataset`）终态（仅查 A-W6 指定路径，未全根扫描）：

| 清单项 | 实测 | 处置 |
| --- | --- | --- |
| 2026-08-28 50MB `.download` 残留 | 存在（50,139,897 bytes，Apostol Vol.2） | **已删除**（staging 可重下恢复） |
| `<data_root>/qed-tracker/meta/**` | **目录已不存在**（与勘误 C3「岛存量已删」一致） | 无需处置；B 轮前代码 register 仍可能重建 |
| `tmp/参考书籍/` | 不存在 | 无需处置 |
| `parsed/probe/`（`d3-20260922` 空目录） | 存在、空 | **已删除**（空目录） |
| 顶层白名单核验 | `backups/ parsed/ raw/ tmp/ + .gitkeep` | 符合根仓 ADR 0018 四目录白名单 |

本仓默认测试与 agent 不读写真实数据根（AGENTS 强制约束 + 完成检查 3），故 A 轮全部落盘
代码验证只走 `tmp_path`；本清单执行经用户 Q6 裁决显式授权。

### A-W7 收口与回执

- 定向测试：`test_axiom.py`、`test_data_layout.py`、`test_download_inventory.py`、`test_paper_application.py`、
  `test_services.py`、`test_book_api.py`、`test_knowledge_api.py`、`test_book_fetch.py`、
  `test_config_catalog_matching.py`、`test_documentation.py`。
- 根仓库 REQ-093 回执（根仓文件只读，改动交用户执行）：**部分完成**口径——D3 判废 + R2 生命周期 + B 轮设计契约
  已定稿；R1 资源半岛与 `qed-tracker/` 顶层区随 B 轮退役；附勘误 C1~C4 与遗漏 M3/M4（M1、M2 原文未落盘，见收口记录「勘误引用缺漏登记」）。
- REQ-094 存量清理：只交 A-W6 清单。

## B 轮工作项（本轮不执行，登记链条）

- **B-W1 内容身份列（手工迁移，D1）**：备份 `mysqldump --single-transaction qed qt_books` →
  `<data_root>/backups/YYYY-MM-DD-qed071-storage-island/qt_books.sql`（ADR 0018 例外区命名规则）→
  `ALTER TABLE qt_books ADD COLUMN sha256 VARCHAR(64) NULL, ADD COLUMN size_bytes BIGINT NULL,
  ADD COLUMN page_count INT NULL, ADD UNIQUE KEY uk_qt_books_sha256 (sha256);`（MySQL 唯一索引允许多 NULL，
  未下载书目不受影响）→ 才改 `db/models.py:174-207` → 立刻验证 `rebuilt == 0`。
  `page_count` **必须一并迁**：`inventory.py:194` 的校验是三项比较，缺一项即静默降级。
- **B-W2 回填与对账**：复用 `inspect_pdf`（`downloader.py:159-175`）对 `holding=owned` 且 `file_path` 非空的
  书目逐本重算写三列；对账报告三分类（回填成功 / 文件缺失 / 与 `qt_sources.note` 记录的 sha8 不符，后者人工裁）；
  落点为 CLI `qed-tracker inventory reconcile`（`--json` + 非 0 退出码沿用 `cli.py:520,528` 约定，属公开 CLI 变更）；
  论文与 `_general/` 内无法归属书目的文件只统计不回填（D2）。
- **B-W3 读路径切 DB**：按 A-W5 切换表执行。
- **B-W4 岛停写与 `Inventory` 退役**：删 JSON 写盘与岛读，`qed-tracker/` 顶层区消失，启用全局反岛守护与
  「全仓 `rg` 命中 0」验收。
- **B-W5 候补 R3**：`qt_books` 只加 `last_error` 一列，起止时间戳从 `qt_tasks` 派生为只读聚合
  （`qt_tasks.error`/`created_at`/`updated_at` 已在，`db/models.py:266-275`；每本书一个 `book_download` 任务），
  避开请求包设想的四列迁移。等 B-W1 把「加列 = 手工迁移 + 备份」的真实成本走通后再定排期。
- ~~待裁 Q4（B-W1 相关）：是否为私有表引入「磁盘仅缺列时拒绝重建并报错」的加法列自愈（照 `schema.py:39-44` 的
  `qed_llm_calls` 先例）。这会改 ADR 0006 的规则面，属实质变更需新 ADR；默认不做，只登记纪律。~~
  **已裁 D13（2026-09-26）：不做，不引新 ADR，只登记「私有表加列 = 手工迁移 + 备份」纪律。**

## 验证与验收

A 轮：

| 验收条目 | 验证方式 |
| --- | --- |
| D3 留痕判废（成功标准 1） | `rg` 全仓 `record_axiom_transfer`、`transfers_dir` 命中 0 + `test_axiom.py` 改后断言不生成 transfers 目录 |
| R2 生命周期（成功标准 2） | 四项边界测试 + 阈值计算测试；清扫只作用于 `tmp/qed-tracker/downloads/` |
| 死码清理（成功标准 3） | `rg` 全仓 `state_dir`、`Inventory.remove` 命中 0（`test_config_catalog_matching.py` 同步） |
| B 轮设计定稿（成功标准 5） | 四处文档口径同步 + `tests/test_documentation.py` 全绿 + 人工按请求包列出行号逐条勾 |
| 不越界 | 零 DDL、零 `db/models.py` 改动、零真实数据根读写（`git status` 与 diff 佐证） |
| 收口 | `docs/guides/development.md` 完整门禁 + 通过数对账 + REQ-093 部分完成回执 |

B 轮（登记，届时补全）：岛退役 `rg` 零命中 + `ensure_schema` `rebuilt == 0` 证据 + 对账报告三分类计数 +
读路径三条定向测试 + 完整 `test_schema.py`/`test_db_models.py`/CLI 契约测试。

## 回滚

- A 轮各项互不耦合，单提交回退即可。A-W2 最坏情况是误删在途 staging 文件——由「阈值严格大于单次下载最长
  寿命」规避，且 staging 内容全部可重下恢复，不触碰 `raw/` 成品。
- A-W1 删除的留痕无读取方，回滚只需恢复写盘；A-W3 死码删除无行为影响；A-W5 为纯文档。
- B 轮唯一不可逆风险是错误顺序触发 `qt_books` 重建，兜底 = B-W1 前的备份 dump
  （`mysql qed < backups/<YYYY-MM-DD-qed071-storage-island>/qt_books.sql`），恢复属 D 类操作需用户确认；
  B-W1 回退需 `ALTER TABLE ... DROP COLUMN` ×3 + 回滚模型提交（同样遵守「先改磁盘、后改模型」方向）。
- 分支：A 轮直接在 `develop` 逐项提交（裁决 D9，取代原 feat 分支安排）；`develop` 上只收 A 轮改动。

## 关闭与归档

A 轮收口只把 QED-071 标为「A 轮完成，B 轮待排期」，**不关闭任务**——R1 资源半岛未退役即不满足请求包验收。
本计划按 [ADR 0009](../history/adr/0009-closed-plan-archival.md) 判 **Retain**（含 B 轮设计契约，B 轮开工时直接
引用）。B 轮关闭时同轮做 REQ-093 终态回执与 todo 迁移 `completed.md`。

## 待裁问题

**2026-09-26 更新：Q1~Q5 已全部裁决（D10~D14，见「用户裁决记录」），B 轮无待裁项**；下表保留原始问题与裁决结果备查。

| 编号 | 问题 | 轮次 | 裁决结果（2026-09-26） |
| --- | --- | --- | --- |
| Q1 | `inventory verify/list` 的 `--json` 输出 `resource_id` → `book_id`（岛死后 `sha256:<digest>` 已无索引意义） | B | **已裁 D10：换为 `book_id`** |
| Q2 | legacy catalog 路径（`run_catalog`/`find_by_catalog_target`/`catalog_ref`）退役还是改造 | B | **已裁 D11：退役**（属已归档的 math-qe 流程，缩小 B 轮面积） |
| Q3 | `ResourceRecord` 与资源 schema v1：保留为内存 DTO 还是删除、CLI 直读 DB 行 | B | **已裁 D12：保留为 DTO**，文档改口径为「DB 列的读视图」 |
| Q4 | 是否为私有表引入「磁盘仅缺列时拒绝重建」加法列自愈（需新 ADR） | B | **已裁 D13：不做**，登记「加列 = 手工迁移 + 备份」纪律 |
| Q5 | 论文进 `qt_books`（D2）是否提前到 B 轮 | B | **已裁 D14：不提前**，保持 D2 |
| Q6 | ~~A-W6 存量清单处置方式~~ | A | **已裁决（D6）并执行完毕，见 A-W6** |
| Q7 | ~~A-W2 阈值口径~~ | A | **已裁决（D7）：timeout×retries×4 + 下限 6h** |
| Q8 | ~~清扫是否另挂公开 CLI~~ | A | **已裁决（D8）：只挂自动入口** |

## A 轮收口记录（2026-09-24）

- **门禁证据**（`conda run -n qed_env`，Windows 本机）：
  - 基线（开工前）：`pytest tests -q` = **496 passed, 1 skipped**。
  - 收口（全量）：`pytest tests -q` = **505 passed, 1 skipped, 10 warnings**（净增 9 个测试）。
  - `ruff check src tests scripts` = All checks passed；`git diff --check` = 0；
    `qed-tracker --version` = 0.5.0；`qed-tracker --json catalog list` = `["math-qe"]`。
  - `pytest tests/test_documentation.py` = **8 passed**。
- **成功标准逐条**：
  1. `rg "record_axiom_transfer|transfers_dir" src tests` → **零命中**；`test_axiom.py` 改为断言返回值字段 + 不生成留痕目录 ✅
  2. `sweep_downloads` + `staging_max_age_seconds` 落地，挂 `Application.__init__` 与两取书 handler；四项边界 + 阈值计算 + 服务构造清扫测试齐（`test_download_inventory.py` 6 个、`test_api.py` 1 个）✅
  3. `rg "state_dir|Inventory.remove" src tests` → **零命中**（含 `test_config_catalog_matching.py` 两处断言删除）✅
  4. A-W4 局部反岛守护落地（`test_data_layout.py` 两测试：src 零留痕字符串 + 构造/清扫终态）；全局 `qed-tracker/` 断言留 B 轮 ✅
  5. 四处 B 轮设计契约写入（database-private-tables「B 轮内容身份列契约」含 DDL 草案与红线顺序、download-pipeline 反岛预告 + staging 生命周期实况、system-overview 三处轮次注记、main-line 一处注记）；另同步 api.md 传输记录判废、code-map/service-management 死引用清除；`src/` DB 层与真实库**零改动**（`git status src/qed_tracker/db/` 空）✅
  6. 文档门禁 8 passed；完整门禁见上 ✅
  7. A-W6 存量清理已执行（见上表）✅
- **REQ-093 部分完成回执（草稿，交用户提交根仓库——根仓文件本仓只读）**：
  > QED-Tracker QED-071 A 轮完成：① D3 Axiom 传输留痕判废删除（`record_axiom_transfer`/`transfers_dir` 全仓零命中，审计经 qt_tasks/qed_llm_calls 与 Axiom 侧反查）；② R2 staging 年龄清扫生命周期落地（`sweep_downloads`，阈值 timeout×retries×4 下限 6h，挂服务构造 + 取书入口，含边界测试）；③ 数据根存量清理完毕（50MB `.download` 残留、`parsed/probe` 空目录已删，顶层已是 ADR 0018 四目录白名单）；④ R1 资源半岛与 `qed-tracker/` 顶层区**待 B 轮**（B 轮设计契约已定稿：`qt_books` 三列 DDL 草案 + 「先 ALTER 后改模型」红线顺序，本轮零 DDL、零模型改动）。勘误 C1~C4（无 Alembic 加列即整表重建 / `qt_books.kind=paper` 不存在 / 双源回填实为单源且论文去重索引已随存量删除失效 / `ResourceInventory` 实为 `Inventory`）与遗漏 M3（`qed-tracker/` 顶层目录本身即野生区）、M4（DB 不可用须显式报错、不得回退读岛）随本计划登记。R3 候补（B-W5：`qt_books` 只加 `last_error` 一列，时间戳从 qt_tasks 派生）。
- **勘误引用缺漏登记（收口时发现）**：`plans/index.md:50` 与本计划 A-W7 原文引用「遗漏 M1~M4」，
  但仅 M3（A-B 目标表行内）、M4（A-W5 强制口径行内）有定义，**M1、M2 的评审原文从未落盘**——
  已把回执引用收窄为「M3/M4」；M1、M2 定义待用户补录或从引用中裁掉（不阻塞 A 轮，B 轮回执前须定）。
- **REQ-094 存量清理回执**：A-W6 清单已执行完毕（见上表），无剩余存量项。

## 进度与复核记录（2026-09-26）

**一、A 轮复验（本机实测，非引用历史证据）**

- QED-071 定向测试（`test_axiom.py`、`test_data_layout.py`、`test_download_inventory.py`、
  `test_documentation.py`、`test_config_catalog_matching.py`、`test_api.py`）= **71 passed**。
- `rg "record_axiom_transfer|transfers_dir" src tests` → **零命中**；`rg "state_dir|Inventory.remove" src tests` → **零命中**。
- `git status src/qed_tracker/db/` 空 → 零 DDL、零 `db/models.py` 改动，A 轮未越界。
- A 轮成功标准 1~5 复验仍成立；A 轮改动（20+ 文件 + 2 份新计划）**尚未 git 提交**。

**二、全量门禁口径说明（避免误读）**

- 同日全量 `pytest tests -q` = **512 passed, 3 failed, 1 skipped**；3 个失败全在
  `tests/test_orchestration.py`，`ruff check` 的 1 个 error 在 `src/qed_tracker/orchestration/pipeline.py`
  ——均属 **QED-067 LangChain 编排**的在途未提交工作（`orchestration/`、`tests/test_orchestration.py`、
  `pyproject.toml`、`docs/plans/2026-09-14-local-llm-langchain.md`、`code-map.md` 中 orchestration 行），
  **与 QED-071 无关**；与 A 轮收口记录 505 passed 的差异即来自该批新增测试。
- 因此本任务的门禁举证以「QED-071 定向 71 passed + 上述 `rg` 零命中 + `db/` 零改动」为准；
  全量绿须待 QED-067 组修复后另行验证。

**三、Q1~Q5 裁决（2026-09-26，D10~D14，全按建议默认）**

D10 verify/list `--json` 换 `book_id`；D11 legacy catalog 退役；D12 `ResourceRecord` 保留为 DTO；
D13 不做加法列自愈（不引新 ADR）；D14 论文承载面不提前（保持 D2）。裁决已回写「用户裁决记录」表、
A-W5 读路径切换表、B 轮前置条件与「待裁问题」表。**B 轮自此无待裁项。**

**四、B 轮开工硬门（剩余 2 项）**

1. 真实库基线证明：启动自愈返回 `(created, rebuilt) == (0, 0)`（`db/schema.py:138-170`）。
2. 用户 D 类操作授权：`mysqldump` 备份 + `ALTER TABLE qt_books ...`（红线顺序不变：先改磁盘、后改模型）。

**五、A 轮尾巴（4 项未闭环）**

1. **分组提交**（2026-09-26 用户授权）：A 轮改动与 QED-067 在途改动混在同一 `develop` 工作区，
   须按单一目的拆两组提交；`docs/architecture/code-map.md` 单文件含两组改动（orchestration 行属 QED-067、
   inventory 行属 QED-071），须按 hunk 拆分暂存。QED-067 组当前 3 failed + 1 ruff error，**修绿后才可提交**。
2. REQ-093 **部分完成**回执草稿待用户提交根仓库（根仓文件本仓只读）。
3. 勘误 **M1/M2 定义未落盘**（收口记录已登记）：待用户补录或从引用中裁掉，B 轮回执前须定。
4. `docs/architecture/database-private-tables.md:300`「待裁 Q4」字样与 D13 不一致——属 A-W5 交付物的状态
   注记，按分级不动 `architecture/` 正文，登记为**待 B 轮文档轮同轮更新**（`plans/index.md` 本条同步已完成）。

