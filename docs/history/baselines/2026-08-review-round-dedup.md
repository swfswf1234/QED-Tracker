# 人工评审优化：同源去重 + review_note（QED-020）

归档状态：已归档（2026-09-07 自 docs/design/ 移入 history/baselines/）
归档说明：
- 范围：evaluate 同源去重与 file_hint 例外、review_note 字段与 confirm/backup/reject
  三端点 note 参数、陈纪修存量重复清理（一次性动作）。
- 失效原因：承载表 qt_resources 与 catalog_evaluate 任务已随 QED-030 删除；
  review_note 由 `qt_downloads.review_note` 承接，教材候选生成由目录运行/下载路径承接。
- 不可变锚点：正文自 Git commit 1c2ede541dd0c3d00b7eebdea713661994f29ee1 冻结
  （此后仅允许补 Historical 声明、反向关系或修复链接）。
- 当前事实入口：[数据库专用表设计](../../architecture/database-private-tables.md)（qt_* 表族唯一事实源）。
设计状态：Historical（2026-09-07 归档）
实现状态：Completed（QED-020 实现完成并关闭；机制随 QED-030 退役，承接见下）
确认状态：已确认
最后更新：2026-09-07
关联代码：`src/qed_tracker/db/models.py`、`src/qed_tracker/db/knowledge_repository.py`、`src/qed_tracker/api/main.py`
关联测试：`tests/test_knowledge_repository.py`、`tests/test_knowledge_api.py`、`tests/test_download_inventory.py`
关联 ADR：—
需求方：QED-Engine（REQ-018；QED-020 已完成，见[完成台账](../../trackers/completed.md)）
执行方：QED-Tracker
接口面：三表端点（confirm/backup/reject 可带 note；qt_downloads.review_note）
评审方：用户
验收标准：见下「成功标准」

## 背景

1. **重复书问题**：catalog 目标 `01-chenjixiu`（教材）与 `01-chenjixiu-exercises`
   （习题集）都命中 archive 同一条目 `math_analysis_chenjixiu`（课本及答案合订），
   评估时登记成两条资源（book confirmed + exercise candidate），下载两本不合理。
2. **人工评审建议**：人工评估（确定/备选/否定）时希望能填一句建议落库存储，
   供后续参考与展示。
3. **存量重复**：已存在的陈纪修 exercise candidate 与教材 confirmed 同源，需清理。

## 变更内容

### 1. evaluate 同源去重

> 已退役（QED-030）：`catalog_evaluate.py` 任务与 `db/repository.py` 已删除。
> 教材候选现在由目录运行/下载路径生成：套归属按 `CatalogTarget.note`（QED-024），
> 下载与三表登记由 `BookService.download` → `record_book_download` 承接。

evaluate 任务（删前语义，位于已删的 `application/catalog_evaluate.py`）：

- 单次 `evaluate()` 调用内维护 `seen_provider_ids: dict[str, str]`（provider_id → 首次目标 id）；
- 严格匹配命中候选后，若 `candidate.provider_id` 已在本次任务中登记过且
  **目标无 `file_hint`**，不重复 `upsert_candidate`，报告追加
  `skipped: {target_id, reason: "同来源已由首次目标覆盖（<首次目标 id>）"}`；
- **file_hint 例外（2026-08-07 用户裁决）**：同一条目含多个独立 PDF（如 archive
  `math_analysis_chenjixiu` 的上/下册 + 习题答案）时，带 `file_hint` 的目标不受
  同源去重限制，按文件名关键词分别收录，各自 resolve 选对应文件（QED-019 机制）；
- 未命中来源的分支（pending_manual/not_found）不受影响；
- 跨任务去重不做（已有 `find_rejected_same_source` / `find_by_ref` 跳过逻辑保持）。

### 2. review_note 字段与接口

> 承接（QED-028/030）：review_note 现属三表 `qt_downloads.review_note`，
> 表1/表2 的 confirm/backup/reject 带 note 由 `knowledge_repository` 与
> `/api/v1/selections|downloads` 端点实现（`backup_selection(note=...)` 等）。

- `src/qed_tracker/db/models.py`：`ResourceRow` 增加
  `review_note: Mapped[str] = mapped_column(String(1000), nullable=False, default="")`；
- Alembic 迁移（qt_resources 增列，default ""；该列随 0005 drop）；
- 已删的 `db/repository.py`：`confirm` / `mark_backup` / `reject` 接受
  `note: str = ""` 参数并写入 `review_note`（追加覆盖，单值字段）；
- `src/qed_tracker/api/main.py`：confirm/backup/reject 三端点接收可选
  `payload.note`（confirm/backup 当前无 body，改为可选 `_EMPTY_BODY`）；
- `_row_dict` / 资源查询返回 `review_note` 字段。

### 3. 存量清理

- 陈纪修 exercise candidate（`cand_c8977caa0b358ebd71dd0bd585341dd3`，archive
  `math_analysis_chenjixiu`）与教材 confirmed 同源：经 `POST /resources/{id}/reject`
  `{reason: "与教材同源重复（archive math_analysis_chenjixiu 课本及答案合订），人工裁决清理", note: "教材已确认，习题集目标由教材覆盖"}`；
- candidate→rejected 为合法迁移，无文件硬删（candidate 无文件），DB 留痕保留。

## 成功标准

- QED-Tracker 门禁全绿：`pytest tests -q` + `ruff check src tests` +
  `python -m pip wheel . --no-deps --no-build-isolation` + CLI 冒烟；
- 定向测试：同源去重（同 provider_id 两目标只落一条 + skipped 报告）、
  review_note 接口（confirm/backup/reject 带 note 落库、/resources 返回）；
- 8901 重启后实测：陈纪修 candidate 清理完成、资源列表无重复；
- 回执 QED-Engine REQ-018：提交号 + 测试输出。

## 关联测试

- `tests/test_knowledge_repository.py`（状态机 note 参数）
- `tests/test_knowledge_api.py`（note 接口契约）
- `tests/test_download_inventory.py`（如有 schema 影响）
