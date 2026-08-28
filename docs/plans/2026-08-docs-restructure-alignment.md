# QED-039 文档体系范本对齐 实施计划

**Goal:** 按 QED-Engine 根仓库 ADR 0010 对齐 QED-Tracker 文档体系三层结构：architecture/（确定文档）→ design/（相对确定）→ trackers/（实时状态）

**Architecture:** architecture/ 固定化（5 确定文档）+ 新增 api.md + database-schema.md 升级 + project-status.md 移出 + design/ 三态清理 + adr/index 版本声明 + 契约测试同步

**Tech Stack:** Markdown 文档、Python pytest 测试

---

## 文件变更总览

| 操作 | 文件 |
|------|------|
| 移动 | `docs/design/database-schema.md` → `docs/architecture/database-schema.md` |
| 移动 | `docs/architecture/project-status.md` → `docs/trackers/project-status.md` |
| 移动 | `docs/design/three-table-schema.md` → `docs/history/three-table-schema.md` |
| 移动 | `docs/design/database-schema-ownership.md` → `docs/history/database-schema-ownership.md` |
| 新建 | `docs/architecture/api.md` |
| 修改 | `docs/adr/index.md`（加版本声明 v0.1.0） |
| 修改 | `docs/architecture/index.md`（更新文档列表） |
| 修改 | `docs/design/index.md`（移除三态文档、更新 database-schema 引用） |
| 修改 | `docs/index.md`（更新 trackers 描述） |
| 修改 | `docs/trackers/index.md`（新增 project-status 入口） |
| 修改 | `docs/architecture/code-map.md`（更新 DesignRef 路径） |
| 修改 | `docs/architecture/system-overview.md`（更新数据库文档引用） |
| 修改 | `AGENTS.md`（更新任务路由表） |
| 修改 | `tests/test_documentation.py`（Step 2 单独更新） |

---

## Step 1：文档结构物理移动与创建

### Task 1.1: 移动 database-schema.md 到 architecture/

- [ ] **Step 1: 执行移动**

```powershell
Move-Item -LiteralPath "docs\design\database-schema.md" -Destination "docs\architecture\database-schema.md"
```

- [ ] **Step 2: 更新文档内元数据**

将文件顶部元数据中的 `设计状态：Accepted` 改为 `设计状态：Accepted`（不变），但需确认文件内无 `design/` 自引用路径。检查并更新文件内所有 `../architecture/` 相对路径为同级引用。

- [ ] **Step 3: 验证移动后文件存在**

```powershell
Test-Path -LiteralPath "docs\architecture\database-schema.md"
```

Expected: True

### Task 1.2: 移动 project-status.md 到 trackers/

- [ ] **Step 1: 执行移动**

```powershell
Move-Item -LiteralPath "docs\architecture\project-status.md" -Destination "docs\trackers\project-status.md"
```

- [ ] **Step 2: 更新文档内元数据**

文件内关联 ADR 路径从 `../adr/0001-tracker-service-architecture.md` 改为 `../adr/0001-tracker-service-architecture.md`（相对路径不变，因为 trackers/ 和 architecture/ 同级）。确认文件内链接均可解析。

- [ ] **Step 3: 验证**

```powershell
Test-Path -LiteralPath "docs\trackers\project-status.md"
```

Expected: True

### Task 1.3: 移动 three-table-schema.md 到 history/

- [ ] **Step 1: 确认目标目录存在**

```powershell
Test-Path -LiteralPath "docs\history"
```

Expected: True

- [ ] **Step 2: 执行移动**

```powershell
Move-Item -LiteralPath "docs\design\three-table-schema.md" -Destination "docs\history\three-table-schema.md"
```

- [ ] **Step 3: 更新文件内关联测试路径**

原文件关联测试包含 `tests/test_db_three_table_smoke.py`，保持不变（只读留档）。

- [ ] **Step 4: 验证**

```powershell
Test-Path -LiteralPath "docs\history\three-table-schema.md"
```

Expected: True

### Task 1.4: 移动 database-schema-ownership.md 到 history/

- [ ] **Step 1: 执行移动**

```powershell
Move-Item -LiteralPath "docs\design\database-schema-ownership.md" -Destination "docs\history\database-schema-ownership.md"
```

- [ ] **Step 2: 验证**

```powershell
Test-Path -LiteralPath "docs\history\database-schema-ownership.md"
```

Expected: True

### Task 1.5: 新建 architecture/api.md

- [ ] **Step 1: 创建文件，写入8901 API接口文档**

文件路径：`docs/architecture/api.md`

文件内容应包含：
- 文档元数据（设计状态：Accepted，实现状态：Implemented，最后更新，关联代码，关联测试，关联 ADR）
- 四类端点分类说明：
  - ① 服务生命周期与健康：`GET /api/v1/health`
  - ② 数据查询：`GET /api/v1/courses`、`GET /api/v1/courses/{domain_id}`、`GET /api/v1/knowledge`、`GET /api/v1/knowledge/{knowledge_id}`、`GET /api/v1/books/{book_id}/sources`、`GET /api/v1/catalogs`、`GET /api/v1/catalogs/{catalog_id}`
  - ③ 资源生命周期操作：`POST /api/v1/knowledge/{id}/confirm`、`POST /api/v1/knowledge/{id}/complete`、`POST /api/v1/knowledge/{id}/reject`、`POST /api/v1/knowledge/{id}/supersede`、`POST /api/v1/books`、`POST /api/v1/books/{id}/sources`、`POST /api/v1/books/{id}/register`、`POST /api/v1/tasks`、`GET /api/v1/tasks/{task_id}`
  - ④ LLM 检索课程教程·选书业务：`GET /api/v1/books/search`、`GET /api/v1/papers/search`
- 每个端点包含：方法、路径、参数说明、返回值概要、错误码
- 参考 `src/qed_tracker/api/main.py` 中的实际路由定义

- [ ] **Step 2: 验证文件创建**

```powershell
Test-Path -LiteralPath "docs\architecture\api.md"
```

Expected: True

### Task 1.6: 更新 adr/index.md 版本声明

- [ ] **Step 1: 在文件顶部元数据后添加版本声明**

在 `最后更新：2026-08-04` 行之后，添加：

```markdown
当前版本：v0.1.0
```

- [ ] **Step 2: 验证文件内容**

```powershell
Select-String -LiteralPath "docs\adr\index.md" -Pattern "v0.1.0"
```

Expected: 匹配到1行

---

## Step 2：索引与交叉引用更新

### Task 2.1: 更新 architecture/index.md

- [ ] **Step 1: 更新文档列表**

修改 `docs/architecture/index.md`：
- 移除 `project-status.md` 行
- 将 `database-schema.md` 从 design/ 引用改为 architecture/ 内部引用
- 新增 `api.md` 行（8901 API 接口文档）

更新后的"当前文档"表格应为：

```markdown
| 文档 | 设计状态 | 实现状态 | 内容 |
| --- | --- | --- | --- |
| [系统总览](../architecture/system-overview.md) | Accepted | Implemented | 职责边界、运行拓扑、模块职责、数据布局、系统不变量与架构符合度 |
| [代码与设计映射表](../architecture/code-map.md) | Accepted | Implemented | 受管代码、DesignRef 与测试的映射唯一事实源 |
| [主链路架构](../architecture/main-line.md) | Accepted | Implemented | 领域课程梳理 → 教材寻找 → 下载 → 人工验收的主链路体系（与 evaluate 平行） |
| [8901 API 接口文档](../architecture/api.md) | Accepted | Implemented | FastAPI 8901 端点分类（生命周期/数据查询/资源操作/LLM 业务）与契约 |
| [数据库设计](../architecture/database-schema.md) | Accepted | Plan | qed 库 qed_*/qt_* 表族唯一事实源（领域/课程/知识行/书行/渠道五层模型） |
```

- [ ] **Step 2: 更新文件顶部描述**

将"本目录保存当前系统结构、运行拓扑、数据不变量、代码与设计的映射关系以及项目状态快照。"改为"本目录保存当前系统结构、运行拓扑、数据不变量、代码与设计的映射关系。"（移除"项目状态快照"）

- [ ] **Step 3: 更新底部引用**

将 `具体来源协议和持久化字段属于[下载与清单设计](../design/acquisition-and-inventory.md)` 保持不变。

### Task 2.2: 更新 design/index.md

- [ ] **Step 1: 移除三态文档条目**

从"数据设计"部分移除：
- `database-schema-ownership.md` 相关说明（第45-46行）
- `three-table-schema.md` 相关说明（第46行）

将数据设计部分更新为：

```markdown
## 数据设计

- [数据库设计](../architecture/database-schema.md)（Accepted，2026-08-16 用户裁决知识层次重构）：qed 库
  `qed_*`（共享）与 `qt_*`（QED-Tracker 私有）表族**唯一事实源文档**——领域/课程/知识行/
  书行/渠道五层模型（qed_domain → qed_course → qt_knowledge → qt_books → qt_sources）、
  状态机、文件命名（物理名/展示名）、存量迁移与共享表所有权。
```

- [ ] **Step 2: 更新 database-schema.md 引用路径**

所有 `database-schema.md` 引用从 `design/database-schema.md` 改为 `../architecture/database-schema.md`。

### Task 2.3: 更新 docs/index.md

- [ ] **Step 1: 更新 trackers 描述**

将 trackers 行的内容从"有状态待办、完成台账与无状态路线图"改为"有状态待办、完成台账、项目状态快照与无状态路线图"。

### Task 2.4: 更新 trackers/index.md

- [ ] **Step 1: 新增 project-status 入口**

在现有条目后新增：

```markdown
- [项目状态快照](../trackers/project-status.md)：QED-Tracker 当前实现状态与当前主线。
```

### Task 2.5: 更新 architecture/code-map.md

- [ ] **Step 1: 更新 DesignRef 路径**

将所有 `docs/design/database-schema.md` 替换为 `docs/architecture/database-schema.md`（涉及行：18, 40, 43, 44, 50, 69, 70, 71）。

将所有 `docs/design/three-table-schema.md` 替换为 `docs/history/three-table-schema.md`（涉及行：47, 48, 49, 68, 72）。

### Task 2.6: 更新 architecture/system-overview.md

- [ ] **Step 1: 更新数据库文档引用**

将"MySQL `qed` 库三表（`qt_selections`/`qt_downloads`/`qt_sources`）作为册级明细登记索引"中的三表引用更新为五层模型描述，并将数据库设计引用从 `design/database-schema.md` 改为 `database-schema.md`（同目录）。

### Task 2.7: 更新 AGENTS.md

- [ ] **Step 1: 更新任务路由表**

将"服务与 API"行的"当前文档"列从 `docs/design/tracker-service.md` 改为 `docs/design/tracker-service.md`、`docs/architecture/api.md`。

将"配置、目录和 CLI"行的"当前文档"列中 database-schema 引用确认指向正确路径。

### Task 2.8: 更新 docs/design/docs-restructure-alignment.md

- [ ] **Step 1: 更新实现状态**

将文件顶部 `实现状态：Not Started` 改为 `实现状态：Implemented`。

将 `设计状态：Proposed` 改为 `设计状态：Accepted`。

---

## Step 3：契约测试同步（独立提交）

### Task 3.1: 更新 tests/test_documentation.py

- [ ] **Step 1: 更新 REQUIRED_CURRENT_DOCS 集合**

```python
REQUIRED_CURRENT_DOCS = {
    Path("README.md"),
    Path("AGENTS.md"),
    Path("docs/index.md"),
    Path("docs/trackers/roadmap.md"),
    Path("docs/trackers/project-status.md"),       # 从 architecture/ 移入
    Path("docs/architecture/index.md"),
    Path("docs/architecture/system-overview.md"),
    Path("docs/architecture/code-map.md"),
    Path("docs/architecture/main-line.md"),
    Path("docs/architecture/api.md"),              # 新增
    Path("docs/architecture/database-schema.md"),  # 从 design/ 移入
    Path("docs/design/index.md"),
    Path("docs/design/acquisition-and-inventory.md"),
    Path("docs/design/paper-discovery.md"),
    Path("docs/design/source-discovery.md"),
    Path("docs/design/review-round-dedup.md"),
    Path("docs/design/tracker-service.md"),
    Path("docs/design/governance-contract-alignment.md"),
    Path("docs/design/main-line-curriculum.md"),
    Path("docs/design/service-lifecycle.md"),
    Path("docs/design/service-lifecycle-encoding-fix.md"),
    Path("docs/design/tutorial-naming.md"),
    Path("docs/design/model-mode-config.md"),
    Path("docs/standards/index.md"),
    Path("docs/standards/documentation.md"),
    Path("docs/standards/adr-governance.md"),
    Path("docs/adr/index.md"),
    Path("docs/adr/0001-tracker-service-architecture.md"),
    Path("docs/guides/index.md"),
    Path("docs/guides/operations.md"),
    Path("docs/guides/development.md"),
    Path("docs/plans/index.md"),
    Path("docs/plans/2026-08-main-line-curriculum.md"),
    Path("docs/trackers/index.md"),
    Path("docs/trackers/todo.md"),
    Path("docs/trackers/completed.md"),
}
```

- [ ] **Step 2: 更新 REQUIRED_HISTORY_DOCS 集合**

```python
REQUIRED_HISTORY_DOCS = {
    Path("docs/history/index.md"),
    Path("docs/plans/index.md"),
    Path("docs/trackers/index.md"),
    Path("docs/history/baselines/pre-acquisition-cli.md"),
    Path("docs/history/baselines/math-qe-2026-05.md"),
    Path("docs/history/baselines/catalog-set-field.md"),
    Path("docs/history/baselines/2026-08-service-and-book-download.md"),
    Path("docs/history/qed-030-retire-qt_resources/index.md"),
    Path("docs/history/qed-036-tutorial-naming/index.md"),
    Path("docs/history/three-table-schema.md"),             # 从 design/ 移入
    Path("docs/history/database-schema-ownership.md"),     # 从 design/ 移入
}
```

- [ ] **Step 3: 更新 DESIGN_DOCS 集合**

```python
DESIGN_DOCS = {
    Path("docs/architecture/system-overview.md"),
    Path("docs/architecture/main-line.md"),
    Path("docs/architecture/database-schema.md"),  # 从 design/ 移入
    Path("docs/design/acquisition-and-inventory.md"),
    Path("docs/design/paper-discovery.md"),
    Path("docs/design/source-discovery.md"),
    Path("docs/design/review-round-dedup.md"),
    Path("docs/design/tracker-service.md"),
    Path("docs/design/governance-contract-alignment.md"),
    Path("docs/design/main-line-curriculum.md"),
    Path("docs/design/service-lifecycle.md"),
    Path("docs/design/service-lifecycle-encoding-fix.md"),
    Path("docs/design/tutorial-naming.md"),
    Path("docs/design/model-mode-config.md"),
}
```

- [ ] **Step 4: 运行测试验证全绿**

```powershell
python -m pytest tests/test_documentation.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: 运行全量门禁**

```powershell
python -m pytest tests -q
ruff check src tests
```

Expected: pytest 全绿 + ruff 无报错

---

## 执行顺序与提交策略

1. **提交 1**：Step 1（Task 1.1-1.6）— 文档结构物理移动与创建
2. **提交 2**：Step 2（Task 2.1-2.8）— 索引与交叉引用更新
3. **提交 3**：Step 3（Task 3.1）— 契约测试同步

每个提交后运行 `ruff check src tests` 确认无回归。
