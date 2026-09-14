# QED-014 联调问题专项计划

状态：Historical（已归档）
最后更新：2026-09-09
任务类型：Validation
关联任务：QED-014（已验收关闭，见 [完成台账](../../trackers/completed.md)）
关联设计：[探索管线设计](../../design/exploration-pipeline.md)、[下载管线设计](../../design/download-pipeline.md)

> **归档说明（2026-09-09）**：QED-014 已于 2026-09-09 验收关闭（用户裁决，见完成台账），
> 本计划自 docs/plans/ 归档至 history/baselines/ 只读留档；问题 2/问题 8 对应遗留清单
> L-02/L-03，随验收通过。正文为归档时原文，仅修正相对链接与本行。

## 目的与边界

本文档记录 QED-014 跨项目联调过程中发现的问题、分析过程和解决方案。QED-014 要求真实 8901 全链路（评估→确认→下载→验收/删除→登记→qed CLI/8903 前端展示）冒烟测试通过。

**本文档只记录联调过程中发现的具体问题**，不重复设计文档已有的规范。问题解决后，解决方案同步到对应的设计文档或代码中。

## 问题登记表

| # | 问题 | 状态 | 发现时间 | 关联模块 | 解决方案 |
|---|------|------|----------|----------|----------|
| 1 | 领域知识导入链路区分逻辑不清晰 | 已分析 | 2026-09-08 | api/main.py | 见下方分析 |
| 2 | LLM 调用记录未写入数据库 | 待验证 | 2026-09-08 | llm_client.py | 待真实环境测试 |
| 3 | 5阶段领域探索模拟测试 | 已完成 | 2026-09-08 | tests/ | 测试文件已创建 |
| 4 | apply-results 未从 JSON 文件读取课程 | 已修复 | 2026-09-08 | api/main.py, db/knowledge_repository.py | 已添加 _sync_courses_from_json_to_db 同步函数 |
| 5 | LLM 超时失败（直连模式） | 已解决 | 2026-09-08 | .env | 切换到网关模式 |
| 6 | /courses/import 状态守卫过严 | 已修复 | 2026-09-09 | api/main.py:929 | 放宽状态检查为 "已生成" 或 "探索中" |
| 7 | 手动导入时 confirm 总是触发 LLM 探索 | 已修复 | 2026-09-09 | api/main.py:880-919 | 检查 domains.json 中是否已有课程，有则跳过 LLM |
| 8 | 前端"已导入"路径绕过 /confirm 端点 | 待修复 | 2026-09-09 | QED-Engine web-ui | 前端需先调 confirm-domain 再调 commit-import |

---

## 问题1：领域知识导入链路区分逻辑

### 问题描述

当导入领域知识（手动导入）时，会先写入 JSON，然后再次探索时是否有区分，究竟是继续走手动导入的链路还是直接 LLM 探索。

### 分析结果

领域探索存在两条链路，基于 `exploration_stage` 状态区分：

#### 手动导入链路

```
POST /domains/import（写入 JSON，状态→已生成）
  → POST /domains/{domain_id}/confirm（状态→探索中，触发 courses@v8）
    → courses@v8 后台任务完成（状态→待确认）
      → POST /domains/{domain_id}/apply-results（状态→已完成）
```

#### LLM 探索链路

```
POST /domains/{domain_id}/re-explore（状态→探索中，触发 domain_explore）
  → domain_explore 后台任务完成（状态→已生成，写入 JSON）
    → POST /domains/{domain_id}/confirm（状态→探索中，触发 courses@v8）
      → courses@v8 后台任务完成（状态→待确认）
        → POST /domains/{domain_id}/apply-results（状态→已完成）
```

#### 状态机区分逻辑

| 状态 | 可用操作 | 说明 |
|------|----------|------|
| 未开始 | 创建、导入 | 领域不存在，可创建或导入 |
| 已生成 | confirm、re-explore | 可继续手动链路（confirm）或切换到 LLM 探索（re-explore） |
| 探索中 | 等待 | 等待后台任务完成 |
| 待确认 | apply-results、re-explore | 可确认结果或重新探索 |
| 已完成 | 无 | 探索完成 |

### 结论

**区分逻辑是正确的**：手动导入和 LLM 探索通过 `exploration_stage` 状态机自然区分，无需额外标记。手动导入后，用户可以选择 confirm（继续手动链路）或 re-explore（切换到 LLM 探索）。

---

## 问题2：LLM 调用记录未写入数据库

### 问题描述

LLM 调用记录未写入 `qed_llm_calls` 表，无法追溯 LLM 调用历史。

### 分析过程

1. **LLM 记录写入条件**：`llm_client.py` 中 `_record_call` 方法检查 `self.engine` 参数，只有 `engine` 不为 None 时才写入数据库。

2. **engine 参数传递链**：
   - `api/main.py` 中 `_advisor_kwargs()` 传递 `engine=app._db_engine`
   - `Application.__init__` 中 `_db_engine` 的设置逻辑：
     - 如果 `knowledge_repository` 不为 None（测试环境），`_db_engine` 为 None
     - 如果 `knowledge_repository` 为 None 且 `settings.db_configured` 为 True，创建新的 engine

3. **可能原因**：
   - 测试环境中 `_db_engine` 为 None，不写入数据库
   - 真实环境中 LLM 调用本身可能没有成功（API_KEY 未配置、网络问题等）

### 解决方案

**待验证**：在真实环境中测试 LLM 调用，确认：
1. API_KEY 是否正确配置
2. 模型选择是否正确（`QED_API_SELECT`、`QED_MODEL`）
3. 网络连接是否正常
4. LLM 调用是否成功返回

**验证步骤**：
1. 启动 8901 服务：`conda run -n qed_env qed-tracker serve`
2. 检查 `.env` 配置：确保 `API_KEY`、`QED_API_SELECT`、`QED_MODEL` 正确
3. 执行领域探索：`POST /domains/{domain_id}/re-explore`
4. 检查 `qed_llm_calls` 表：确认是否有新的调用记录
5. 检查日志：观察 LLM 调用是否成功

---

## 问题3：5阶段领域探索模拟测试

### 问题描述

验证领域探索的完整状态机转换：未开始→已生成→探索中→待确认→已完成。

### 解决方案

已创建测试文件 `tests/test_computer_science_5stage.py`，包含：
1. `test_5stage_domain_import_and_confirm`：测试领域导入和确认的基本流程
2. `test_domain_import_validation`：测试领域导入校验
3. `test_confirm_requires_file`：测试确认领域需要文件存在

**测试结果**：3 个测试用例全部通过，验证了状态机逻辑的正确性。

---

## 下一步行动

### 立即执行

1. **真实环境 LLM 调用测试**
   - 启动 8901 服务
   - 配置正确的 API_KEY 和模型
   - 执行领域探索，验证 LLM 调用是否成功
   - 检查 `qed_llm_calls` 表是否有记录

2. **QED-014 联调测试**
   - 使用 computer-science.json 进行完整 5 阶段测试
   - 验证全链路：评估→确认→下载→验收→登记
   - 记录测试结果和发现的问题

### 后续优化

1. **LLM 调用超时优化**（如需要）
   - 根据真实环境测试结果，决定是否需要调整超时配置
   - 当前配置：`llm_timeout_seconds=300s`

2. **错误处理优化**（如需要）
   - 改进 LLM 调用失败时的错误信息
   - 添加更详细的日志记录

---

## 问题4：apply-results 未从 JSON 文件读取课程

### 问题描述

`POST /domains/{domain_id}/apply-results` 返回 `courses_kept=0`，但 courses@v8 后台任务成功找到了 14 门课程。

### 分析过程

1. **courses@v8 任务成功**：任务 ID `67911e2fe2ab` 状态为 `succeeded`，找到 14 门课程，写入 `courses.json` 文件，`exploration_stage` 更新为 `待确认`。

2. **apply-results 调用失败**：
   - 请求：`POST /domains/computer-science/apply-results`，`selected_courses` 包含 5 门课程 ID
   - 响应：`courses_kept=0`
   - `exploration_stage` 更新为 `已完成`

3. **根因分析**：
   - `domain_explore_courses_handler`（line 324）将课程写入 `courses.json` 文件
   - `apply_domain_results`（line 340-342）从数据库 `QedCourse` 表查询课程
   - **问题**：courses@v8 只写入 JSON 文件，不写入数据库，导致 `apply_domain_results` 查询不到课程

4. **相关代码**：
   - `api/main.py:324`：`write_domain_courses_file(app.settings.data_root, domain_id, courses_data)`
   - `db/knowledge_repository.py:340-342`：`session.scalars(select(QedCourse).where(QedCourse.domain_id == domain_id))`

### 解决方案

**方案A（推荐）**：修改 `apply_domain_results`，当 `exploration_stage == "待确认"` 时，先从 `courses.json` 文件读取课程，创建数据库记录，再执行删除逻辑。

**方案B**：修改 `domain_explore_courses_handler`，在写入 JSON 文件后，同步创建数据库课程记录。

**推荐方案A**，因为：
- 保持 JSON 文件作为探索结果的唯一事实源
- 避免 courses@v8 任务与数据库写入的耦合
- 与 GET /courses 端点的设计一致（line 522-534）

### 验证状态

已通过真实环境测试确认：
- courses@v8 任务成功（14 门课程）
- apply-results 返回 `courses_kept=0`
- 最终课程体系为空（courses=0）

---

## 问题5：LLM 超时失败（直连模式）

### 问题描述

首次使用 `QED_API_SELECT=local`（直连 dashscope）时，courses@v8 后台任务失败，错误：`Server disconnected without sending a response`。

### 分析过程

1. **LLM 连通性测试**：直接调用 dashscope API 正常（1.31s 简单对话，5.20s 长输出）
2. **失败原因**：8901 服务进程的网络环境与直接测试不同，可能未正确使用代理
3. **配置差异**：
   - 自身 `.env`：`QED_API_SELECT=local`，未设置 `QED_PROXY`
   - 根 `.env`：`QED_PROXY=http://127.0.0.1:7890`

### 解决方案

将 `QED_API_SELECT` 从 `local` 切换为 `qed-engine`（网关模式），通过 8900 网关调用 LLM，避免直连 dashscope 的网络问题。

### 验证状态

已通过真实环境测试确认：
- 切换到网关模式后，courses@v8 任务成功完成（14 门课程）
- 任务耗时约 90 秒（从 running 到 succeeded）

---

## 问题6：/courses/import 状态守卫过严（QED-055）

### 问题描述

手动导入六步流程步骤3调用 `POST /domains/{id}/courses/import` 时返回 409 INVALID_TRANSITION。

### 分析过程

1. **六步流程回顾**（见问题1分析）：
   - 步骤1：`POST /domains/import` → stage="已生成"
   - 步骤2：`POST /domains/{id}/confirm` → stage="探索中"，触发 courses@v8
   - 步骤3：`POST /domains/{id}/courses/import` → **409 错误**

2. **状态检查代码**（`main.py:929-931`）：
   ```python
   if domain.exploration_stage != "探索中":
       raise api_error(409, "INVALID_TRANSITION",
                       f"当前状态 {domain.exploration_stage}，需要 探索中")
   ```

3. **问题本质**：状态检查过于严格，只接受"探索中"，但手动导入流程中步骤1后 stage="已生成"

### 解决方案

**修改位置**：`src/qed_tracker/api/main.py:929`

```python
# 修改后：
if domain.exploration_stage not in ("已生成", "探索中"):
    raise api_error(409, "INVALID_TRANSITION",
                    f"当前状态 {domain.exploration_stage}，需要 已生成 或 探索中")
```

### 验证标准

1. 手动导入领域 JSON → stage="已生成" → 调 `/courses/import` → 返回 200 + 课程写入
2. LLM 探索路径 → stage="探索中" → 调 `/courses/import` → 仍正常工作
3. 全量测试通过

### 关联文档

- 详细修复方案：原 `docs/plans/2026-09-fix-import-stage-guard.md` 已随 2026-09-09 文档清理轮关闭删除（内容已并入本计划问题 6，差异由 Git 保留）
- 状态机分析：本计划问题1
- 知识录入设计：`docs/design/knowledge-import.md`（六步流程）

---

## 问题7：手动导入时 confirm 总是触发 LLM 探索

### 问题描述

手动导入领域 JSON（包含课程）后，调用 `POST /domains/{id}/confirm` 时总是触发 LLM 探索任务（courses@v8），覆盖用户手动提供的课程。

### 分析过程

1. **手动导入流程**：
   - `POST /domains/import`：写入 `domains.json`（包含领域+课程），stage="已生成"
   - `POST /domains/{id}/confirm`：**总是**提交 `domain_explore_courses` 任务

2. **问题代码**（`main.py:880-919`）：
   ```python
   # 异步提交 courses@v8 后台任务
   record = manager.submit("domain_explore_courses", {
       "domain_id": domain_id,
       "mode": "direct",
   })
   ```

3. **根因**：`domain_confirm` 函数没有检查 `domains.json` 中是否已有课程，总是触发 LLM 探索。

### 解决方案

修改 `domain_confirm` 函数，检查 `domains.json` 中是否已有课程：
- **有课程**：直接写入 `courses.json`，设置 stage="待确认"，不触发 LLM
- **无课程**：提交 `domain_explore_courses` 任务（LLM 探索）

```python
# 检查 domains.json 中是否已有课程
existing_courses = data.get("courses", [])

if existing_courses:
    # 手动导入：直接写入 courses.json，不触发 LLM
    courses_data = {
        "domain_id": domain_id,
        "courses": existing_courses,
        "path": data.get("path", {}),
    }
    write_domain_courses_file(app.settings.data_root, domain_id, courses_data)
    repo.update_domain(domain_id, exploration_stage="待确认")
    return {
        "domain_id": domain_id,
        "task_id": None,
        "exploration_stage": "待确认",
        "message": "领域已确认，课程已从导入文件同步",
    }
else:
    # LLM 探索：提交 courses@v8 任务
    record = manager.submit("domain_explore_courses", {...})
    return {"task_id": record.task_id, ...}
```

### 验证标准

1. **手动导入路径**：
   - `POST /domains/import`（包含 courses）
   - `POST /domains/{id}/confirm` → 返回 `task_id: null`，stage="待确认"
   - 课程正确写入 `courses.json`

2. **LLM 探索路径**：
   - `POST /domains/import`（不包含 courses）
   - `POST /domains/{id}/confirm` → 返回 `task_id`，stage="探索中"
   - LLM 生成课程写入 `courses.json`

### 关联文档

- 状态机分析：本计划问题1
- 知识录入设计：`docs/design/knowledge-import.md`（六步流程）

---

## 问题8：前端"已导入"路径绕过 /confirm 端点

### 问题描述

QED-Engine 前端的"已导入"路径直接调用 `commitImport()` → 8901 `/courses/import`，跳过了 `/confirm` 端点，导致：
1. `courses.json` 没有生成
2. 领域状态无法正确转换
3. 后续的 `apply-results` 无法执行

### 日志证据

| 端点 | 调用次数 | 结果 |
|------|----------|------|
| `POST /domains/math-advanced/confirm-domain` | **0** | 从未调用 |
| `POST /domains/math-advanced/confirm` | **0** | 从未调用 |
| `POST /domains/math-advanced/commit-import` | 多次 | 409 Conflict |
| `POST /domains/math-advanced/confirm-knowledge` | 7次 | 409 Conflict |

### 根因分析

**前端代码**（`D:\coding\QED-Engine\web-ui\src\components\DomainConfirmModal.tsx`）：

```typescript
// 第 129-139 行：已导入路径
if (imported) {
  try {
    await commitImport(domain.domain_id);  // 直接调用 commit-import
  } catch (commitErr) {
    message.warning(describeError(commitErr));
  }
  // 缺少：await confirmDomainInfo(domain.domain_id);
  return;
}
```

**问题**：`commitImport()` 调用 8900 的 `/commit-import` → 8901 的 `/courses/import`，但 `/courses/import` 要求领域状态为"已生成"或"探索中"。由于从未调用 `/confirm`，状态没有正确转换，导致 409 错误。

### 修复方案

**文件**：`D:\coding\QED-Engine\web-ui\src\components\DomainConfirmModal.tsx`

**修改位置**：第 129-139 行的 `if (imported)` 分支

**修改内容**：在调用 `commitImport` 之前先调用 `confirmDomainInfo`

```typescript
// 修改后：
if (imported) {
  // 先调 confirm-domain（与 AI 探索路径统一）
  const nameOverride = ep?.kind === 'import_courses' && ep.name_changed
    ? ep.imported_name
    : undefined;
  await confirmDomainInfo(domain.domain_id, nameOverride);
  
  // 再调 commitImport 提交课程
  try {
    await commitImport(domain.domain_id);
  } catch (commitErr) {
    message.warning(describeError(commitErr));
  }
  
  message.success('领域信息已保存，课程已确认');
  onClose();
  void fetchAll();
  return;
}
```

### 修复后的流程

1. `POST /domains/import` → domain 状态 = "已生成"
2. `POST /domains/{id}/confirm-domain`（8900）→ 8901 `POST /domains/{id}/confirm` → 域状态 = "待确认"（含 courses 时直接写 courses.json）
3. `POST /domains/{id}/commit-import`（8900）→ 8901 `POST /domains/{id}/courses/import` → 将 courses 写入数据库

### 关联文档

- 知识录入设计：`docs/design/knowledge-import.md`（六步流程）
- 前端组件：`D:\coding\QED-Engine\web-ui\src\components\DomainConfirmModal.tsx`

---

## 变更记录

| 日期 | 变更 | 说明 |
|------|------|------|
| 2026-09-08 | 初始创建 | 记录 QED-014 联调问题：导入链路区分、LLM 记录未写入、5阶段测试 |
| 2026-09-08 | 更新 | 新增问题4（apply-results 未从 JSON 读取课程）、问题5（LLM 超时失败）、真实环境测试结果 |
| 2026-09-08 | 修复 | 问题4已修复：添加 _sync_courses_from_json_to_db 同步函数，测试验证成功（courses_kept=12） |
| 2026-09-09 | 合并 | QED-055 合并到联调问题专项计划（问题6） |
| 2026-09-09 | 修复 | 问题7已修复：手动导入时 confirm 不再触发 LLM 探索 |
| 2026-09-09 | 分析 | 问题8已分析：前端"已导入"路径绕过 /confirm 端点，待前端修复 |
| 2026-09-09 | 修复 | 问题6已修复：放宽 /courses/import 状态守卫为 "已生成" 或 "探索中" |
