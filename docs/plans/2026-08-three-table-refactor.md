# 三表重构实现计划（three-table-refactor）

状态：In Progress
最后更新：2026-08-13

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 双轨统一为三表——qt_selections（选课表，一条=一套书）→ qt_downloads（册级下载明细）→ qt_sources（渠道尝试），逐级一对多；存量一次性迁移合并（qt_resources + 主链路 JSON），旧存储退役只读；8901 新增三表端点（默认过滤 rejected/superseded，彻底隐藏语义数据层实现）；回执根仓库 REQ-029/030。

**Architecture:** 本计划承接 QED-028（数据库重构）+ QED-029（API 改造）。DB 层沿用现有 SQLAlchemy 2.0 ORM + Alembic 模式（`src/qed_tracker/db/`，迁移 0003 新增三表，qt_resources 保留只读）；一次性迁移脚本独立模块（幂等可重放，成功标志落 meta）；API 层在 `src/qed_tracker/api/main.py` 新增三表端点组（既有 /resources 端点过渡保留）。设计事实源：`docs/design/three-table-schema.md` + 根仓库 `docs/design/downloads-three-table-model.md`。

**Tech Stack:** Python 3.12、SQLAlchemy 2.0、Alembic、FastAPI、pytest（TDD）、ruff。

**状态与用户确认前置：** 设计文档 Draft 待用户审阅；「待用户确认项」三项（表2 是否需 candidate 态、主链路 JSON 迁移后旧文件处理、backup 转正语义）在实现前由用户拍板。

---

## 任务 1：三表 ORM 模型与状态枚举

**Files:**
- Edit: `src/qed_tracker/db/models.py`
- Edit: `tests/test_db_models.py`

新增 `SelectionStatus`（candidate/confirmed/backup/rejected/superseded）与 `DownloadStatus`
（candidate/downloading/downloaded/approved/rejected/failed）枚举；`QtSelection`/`QtDownload`/`QtSource`
三 ORM 模型（字段与约束见 `docs/design/three-table-schema.md` 三张 DDL；`qt_resources` 模型保留不动）。

- [ ] **Step 1: 写失败测试**
  - `tests/test_db_models.py` 新增：三模型字段/约束断言（selection_id PK、qt_downloads.selection_id FK、
    uq_qt_downloads_sha256 唯一、qt_sources.download_id FK）；枚举成员完整性；`to_dict` 序列化。
- [ ] **Step 2: 实现模型**
  - `models.py` 增 `SelectionStatus`/`DownloadStatus` 与三 ORM 类（表参数 InnoDB + utf8mb4）。
- [ ] **Step 3: 跑测试** `pytest tests/test_db_models.py -q` 全绿。

## 任务 2：Alembic 迁移 0003_three_table

**Files:**
- Create: `src/qed_tracker/migrations/versions/0003_three_table.py`
- Edit: `tests/test_db_mysql_smoke.py`（或迁移冒烟测试）

- [ ] **Step 1: 写失败测试**（迁移升级后三表存在 + 索引/唯一约束生效；qt_resources 仍在）
- [ ] **Step 2: 实现迁移**（revision `0003_three_table`，down_revision `0002_review_note`；
  建三表 + 索引；纯 ASCII；downgrade 删三表）
- [ ] **Step 3: 跑测试** 迁移升级/降级测试全绿。

## 任务 3：状态机合法性与彻底隐藏过滤

**Files:**
- Edit: `src/qed_tracker/db/repository.py`（或既有状态迁移服务）
- Edit: `tests/test_resources_api.py` / 新增定向测试

- [ ] **Step 1: 写失败测试**（非法迁移 409：confirmed→candidate、rejected→任意、superseded→任意、
  表2 approved/rejected→任意；表2 candidate→downloading 需任务发起、candidate→downloaded 跳级非法、
  downloading→downloaded 需 sha256+path 已登记、candidate→failed 不允许、failed→downloading 重试合法。
  彻底隐藏：列表/详情过滤 rejected/superseded/failed）
- [ ] **Step 2: 实现**（状态迁移校验 + 查询默认过滤）
- [ ] **Step 3: 跑测试** 全绿。

## 任务 4：一次性存量迁移（qt_resources + 主链路 JSON → 三表）

**Files:**
- Create: `src/qed_tracker/application/migrate_three_table.py`
- Create: `tests/test_migrate_three_table.py`

- [ ] **Step 1: 写失败测试**（fixture：迷你 qt_resources 各态 + 主链路 JSON 各态样本；
  映射断言见设计文档 §一次性迁移；幂等（跑两次结果一致）；rejected/not_found → 表1 rejected）
- [ ] **Step 2: 实现迁移**（幂等键 sha256/entry_id；成功标志 `meta/migrations/three_table.marker`；
  迁移前备份快照；主链路 JSON 导入确认后物理删除（用户裁决 2026-08-13）；qt_resources 退役只读）
- [ ] **Step 3: 跑测试** 全绿（含全量门禁）。

## 任务 5：8901 三表端点（API 改造）

**Files:**
- Edit: `src/qed_tracker/api/main.py`
- Edit: `tests/test_resources_api.py`（或新增 `tests/test_selections_api.py`）

- [ ] **Step 1: 写失败测试**（端点契约见根仓库 downloads-three-table-model.md §3.1：
  `GET /selections?course_id=&status=`、`GET /selections/{id}`、POST confirm/backup/reject/supersede、
  `GET /resources/{id}/downloads`、`POST /downloads`（新建表2 candidate 候选册，{selection_id, vol, file_hint}）、
  `POST /downloads/{id}/approve|reject`、`GET /downloads/{id}/sources`、
  `POST /downloads/{id}/register`；默认过滤断言；非法迁移 409；404 语义）
- [ ] **Step 2: 实现端点**（沿用现有 service/repository 模式；states 同步轻写、任务后台化不变）
- [ ] **Step 3: 跑测试** 全绿。

## 任务 6：文档同步与回执

**Files:**
- Edit: `docs/design/three-table-schema.md`（状态 Accepted；补充确认项结论）
- Edit: `docs/design/tracker-service.md`（链接新设计文档 + API 契约段）
- Edit: `docs/trackers/todo.md`（QED-028/029 证据）
- Edit: `docs/architecture/project-status.md`（主线同步）

- [ ] 回执根仓库 REQ-029/REQ-030（提交号 + 全量测试输出）；8901 重启实测三表端点冒烟
  （selections 列表/详情/三态/supersede、downloads approve/reject/sources/register、
  彻底隐藏验证）；未提交 git 前征询用户。

## 门禁（完成前运行）

- [ ] `pytest -q` 全绿（无公网访问）
- [ ] `ruff check src tests`
- [ ] 确认未读取/修改真实数据根（迁移脚本仅在用户显式执行时对真实库生效；测试用临时库）