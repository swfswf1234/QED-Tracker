# Exploration Stage Enhancement（REQ-067-B10 + B12）

状态：Completed
任务类型：B
最后更新：2026-09-01
需求方：QED-Engine（根仓库 REQ-067-B10/B12）
目标项目：QED-Tracker
评审方：用户

## 背景

### REQ-067-B10：启动清理脏 exploration_stage

后端重启或任务崩溃后，`exploration_stage='探索中'` 残留未清理，导致前端轮询显示多个领域同时「探索中」。需在8901 lifespan startup 时清理。

### REQ-067-B12：新增「待确认」状态 + apply-results/re-explore 端点

探索完成后不直接写 `'已完成'`，改为写 `'待确认'`，前端显示「查看结果」按钮供用户审阅。新增两个端点用于用户确认应用或重新探索。

## 设计目标

1. 服务重启时自动清理脏的 `'探索中'` 状态
2. 探索完成后进入 `'待确认'` 状态，等待用户审阅
3. 支持用户确认应用或重新探索
4. 领域探索和课程探索都支持「待确认」状态

## 数据库变更

### 新增字段

两张表新增 `explore_pending` JSON 字段：

```sql
-- qed_domain
ALTER TABLE qed_domain ADD COLUMN explore_pending JSON NULL COMMENT '探索过程数据';

-- qed_course
ALTER TABLE qed_course ADD COLUMN explore_pending JSON NULL COMMENT '探索过程数据';
```

### 状态机更新

**领域探索状态机（6态）：**

```
未开始 → 已生成 → 探索中 → 待确认 → 已完成
                           ↓
                         失败
```

| exploration_stage | 含义 | explore_pending |
|---|---|---|
| 未开始 | 默认/新建领域 | null |
| 已生成 | 名称需确认 | `{kind: 'name_confirm', name_check: {...}}` |
| 探索中 | 后台任务运行中 | null |
| **待确认** | **探索完成，等待用户审阅** | **`{kind: 'review_results', courses: [...], domain_report: {...}}`** |
| 已完成 | 用户确认应用 | null |
| 失败 | 探索异常/服务重启 | `{kind: 'failed', error: '...'}` |

**课程探索状态机（6态）：**

```
未开始 → 已生成 → 探索中 → 待确认 → 已完成
                           ↓
                         失败
```

| exploration_stage | 含义 | explore_pending |
|---|---|---|
| 未开始 | 默认/新建课程 | null |
| 已生成 | 教材推荐完成 | `{kind: 'tutorials', tutorials: [...]}` |
| 探索中 | 后台任务运行中 | null |
| **待确认** | **探索完成，等待用户审阅** | **`{kind: 'review_results', tutorials: [...]}`** |
| 已完成 | 用户确认应用 | null |
| 失败 | 探索异常/服务重启 | `{kind: 'failed', error: '...'}` |

## API 变更

### 新增端点

#### `POST /domains/{domain_id}/apply-results`

用户确认探索结果应用。

**请求体：**
```json
{
  "selected_courses": ["course_slug_1", "course_slug_2"],
  "description": "可选，修改领域描述"
}
```

**逻辑：**
- 如果提供了 `description`，更新领域描述
- 将 `exploration_stage` 设为 `'已完成'`
- 清空 `explore_pending`
- 只保留 `selected_courses` 中的课程（删除未选中的）

**响应 200：**
```json
{
  "domain_id": "computer-science",
  "courses_kept": 5
}
```

**错误码：**
- 404：DOMAIN_NOT_FOUND
- 409：INVALID_TRANSITION（非'待确认'态）

#### `POST /domains/{domain_id}/re-explore`

用户修改描述后重新探索。

**请求体：**
```json
{
  "description": "新的领域描述",
  "mode": "direct"
}
```

**逻辑：**
- 更新领域描述（可选）
- 将 `exploration_stage` 设为 `'探索中'`
- 清空 `explore_pending`
- 提交 `domain_explore` 后台任务

**响应 202：**
```json
{
  "task_id": "abc123"
}
```

**错误码：**
- 404：DOMAIN_NOT_FOUND
- 409：INVALID_TRANSITION（非'待确认'态）

#### `POST /courses/{course_id}/apply-results`

用户确认课程探索结果应用。

**请求体：**
```json
{
  "selected_tutorials": ["set_no_1", "set_no_2"]
}
```

**逻辑：**
- 将 `exploration_stage` 设为 `'已完成'`
- 清空 `explore_pending`
- 只保留 `selected_tutorials` 中的教程（删除未选中的）

**响应 200：**
```json
{
  "course_id": "data_structures",
  "tutorials_kept": 2
}
```

**错误码：**
- 404：COURSE_NOT_FOUND
- 409：INVALID_TRANSITION（非'待确认'态）

#### `POST /courses/{course_id}/re-explore`

用户修改描述后重新探索课程。

**请求体：**
```json
{
  "description": "新的课程描述",
  "mode": "direct"
}
```

**逻辑：**
- 更新课程描述（可选）
- 将 `exploration_stage` 设为 `'探索中'`
- 清空 `explore_pending`
- 提交 `course_explore` 后台任务

**响应 202：**
```json
{
  "task_id": "def456"
}
```

**错误码：**
- 404：COURSE_NOT_FOUND
- 409：INVALID_TRANSITION（非'待确认'态）

### 行为变更（非端点修改）

**注意**：dry-run 端点保持同步执行、不写任何表的语义。`待确认` 状态由 8900 探索会话管理在调用 dry-run 后写入，而非 dry-run 端点自身写入。

**领域探索流程变更：**
1. 8900 调用 `POST /prompt-explores/dry-run`（同步，返回结果）
2. 8900 将结果写入 `explore_pending` 字段
3. 8900 将 `exploration_stage` 设为 `'待确认'`
4. 前端轮询显示「待确认」状态，用户可点击「查看结果」

**课程探索流程变更：**
1. 8900 调用 `POST /courses/{course_id}/prompt-explores/dry-run`（同步，返回结果）
2. 8900 将结果写入 `explore_pending` 字段
3. 8900 将 `exploration_stage` 设为 `'待确认'`
4. 前端轮询显示「待确认」状态，用户可点击「查看结果」

## 实现细节

### REQ-067-B10：启动清理脏 exploration_stage

**文件：** `src/qed_tracker/application/domain_explore.py`

```python
def cleanup_stale_exploring(repo: KnowledgeRepository) -> int:
    """启动时清理脏 exploration_stage='探索中'。返回重置的数量。"""
    stale_count = 0
    # 清理领域
    for domain in repo.list_domains():
        if domain.exploration_stage == "探索中":
            repo.update_domain(
                domain.domain_id,
                exploration_stage="失败",
                explore_pending={"kind": "failed", "error": "服务重启，探索任务中断"},
            )
            stale_count += 1
    # 清理课程
    for course in repo.list_courses():
        if course.exploration_stage == "探索中":
            repo.update_course(
                course.course_id,
                exploration_stage="失败",
                explore_pending={"kind": "failed", "error": "服务重启，探索任务中断"},
            )
            stale_count += 1
    return stale_count
```

**文件：** `src/qed_tracker/api/main.py`

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    # REQ-067 B10：启动时清理脏 exploration_stage='探索中'
    kn = _kn(app)
    stale = cleanup_stale_exploring(kn)
    if stale:
        logger.info("启动清理：%d 个探索状态已重置为失败", stale)
    yield
    manager.shutdown(wait=True)
    app.close()
```

### REQ-067-B12：新增「待确认」状态

**文件：** `src/qed_tracker/api/main.py`

新增四个端点（apply-results/re-explore × 2）。

**文件：** `src/qed_tracker/db/models.py`

新增 `explore_pending` 字段。

**文件：** `src/qed_tracker/db/knowledge_repository.py`

新增 `update_course` 方法支持 `explore_pending` 参数。

**文件：** `src/qed_tracker/migrations/versions/0014_add_explore_pending.py`

新增 Alembic 迁移。

## 测试计划

### 单元测试

1. `test_cleanup_stale_exploring`：测试启动清理功能
2. `test_domain_apply_results`：测试领域确认应用
3. `test_domain_re_explore`：测试领域重新探索
4. `test_course_apply_results`：测试课程确认应用
5. `test_course_re_explore`：测试课程重新探索

### 契约测试

1. 领域探索状态机 6 态流转
2. 课程探索状态机 6 态流转
3. 错误码对齐

### 集成测试

1. 领域探索完整流程：dry-run → 待确认 → 应用/重新探索
2. 课程探索完整流程：dry-run → 待确认 → 应用/重新探索
3. 服务重启清理验证

## 关联

- 根仓库 REQ-067-B10
- 根仓库 REQ-067-B12
- 根仓库 todo REQ-067 行
