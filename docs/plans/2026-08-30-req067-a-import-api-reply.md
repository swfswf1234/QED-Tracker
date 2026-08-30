# REQ-067-A 回执与评审（导入领域知识 API 契约）

状态：回执（Contract 已实现并有测试守护）
最后更新：2026-08-30
关联 Tracker：根仓库 docs/trackers/todo.md（REQ-067-A）；本仓库 QED-050（manual@v1 契约）
结论：**A 档可即日起开工**（导入端点已上线）；本回执含 4 项评审修正，供根仓库更新其
[2026-08-30-req067-import-api.md](../../../docs/plans/2026-08-30-req067-import-api.md)（注：该文件位于根仓库）。

---

## 1. 导入端点（现状即契约）

```
POST http://127.0.0.1:8901/api/v1/domains/import
Content-Type: application/json
```

body 两种形态：

| 形态 | 内容 | 适用 |
| --- | --- | --- |
| ① `{"domain": <manual@v1 全文对象>}` | 文件内容解析后包装 | **web 文件选择器（唯一可用形态）** |
| ② `{"file_path": "..."}` | 8901 本机可读路径 | 仅 CLI/本机操作；**web 禁用** |

## 2. JSON 校验规则（manual@v1，校验器事实源：`src/qed_tracker/application/knowledge_import.py`）

| 层级 | 规则 |
| --- | --- |
| 领域 | `domain`（slug，必填）；`name`（≤100 非空，创建后不可改）；`description`（≤1000 **非空**）；`level`/`scope`/`entry_requirements` 可选 |
| stages | 非空数组，值域 ⊆ `【基础|主干|分支|前沿】`，无重复 |
| classic_tracks | 0~4 项；每项 `name`（≤50）+`summary`（≤200）+`kind` ∈ `{main,branch}`；方向名不重复 |
| courses | **非空数组**；每门 `slug`（必填，即 course_id）+`name`（≤100）+`summary`（≤400）+`stage` ∈ stages；`track` 若填必须逐字取自主干（kind=main）方向名；`prerequisites` 仅可引用本批课程 slug、无自环、无循环；`aliases` 可选 |
| 其他 | `anchor_courses`、`extensions_planned` 可选（宽松校验） |

## 3. 语义、响应与错误码

- 领域+课程**幂等 upsert**（重复导入 = 维护字段更新），**不存在 409 冲突语义**；
- `domain.exploration_stage = 已完成`（人工探索定稿）；courses 保持既有 `exploration_stage`（默认未开始）；
- 响应：`{"domain_id": "...", "courses_created": N, "courses_updated": N, "exploration_stage": "已完成"}`

| HTTP | code | 场景 |
| --- | --- | --- |
| 201 | — | 导入成功 |
| 400 | INVALID_PARAMS | 校验失败（message 含字段级定位）/JSON 解析失败/文件不可读 |
| 422 | INVALID_PARAMS | body 缺 domain 与 file_path |

## 4. 评审修正（根仓库计划文档需改）

1. §1 请求体：从「body=JSON 全文」改为「body=`{"domain": ...}` 包装」；
2. §2 校验表按上表重写：现有提案（description/stages/courses 可选、slug 自动生成、无 prerequisites 规则）与 manual@v1 不符，会造成「前端校验通过 → 服务端 400」误导；前端步骤只做 `JSON.parse` + 非空检查即可，其余交 400 字段诊断；
3. §2 错误码：删除 409（幂等 upsert 无冲突语义）；
4. §3/§4（探索状态驱动、名称确认）：**移出本契约**，归 REQ-067 B8（独立设计 `2026-08-30-req067-b8-explore-orchestration.md`，本仓库 QED-051）；当前与该设计冲突的既有裁决为 REQ-064（2026-08-28 已修订留痕：8900 负责探索过程状态流转）——B8 将按新口径统一，**A 档实施期间 8900 直写逻辑不得改动**。

## 5. 附：8900 透传建议（根仓库侧）

web-ui 保持单网关：`backend TrackerClient` 增加 `import_domain()`，8900 新增
`POST /api/domains/import` 透传（body 原样转发 8901），避免前端直连 8901 CORS 面扩散。
