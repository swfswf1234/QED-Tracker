# 完整数据库设计文档与 API 设计文档（QED-044）

状态：Active（正式稿动笔被门禁阻塞：QED-010/011/014/026 全部完成前只维护不重构；2026-08-26 用户裁决立项）
最后更新：2026-09-01
关联任务：todo [QED-044（长期任务）](../trackers/todo.md)；承接 [QED-039](../trackers/todo.md) 待优化项之「API 文档内容完善」
首批子集：[prompt 优化模块设计](2026-08-prompt-optimization.md) Phase 3/4（三公共表 qed_llm_calls/qed_domain/qed_course + 相关 API 的 design/ 正式确认文档）
执行依据：[文档治理规范](../standards/doc-governance.md)「版本末期文档整理」节（版本内修复事实准确性，版本末期门禁通过后正式稿升级）

## 1. 目标

把两份 architecture 固定文档升级为**完整版**，全部内容遵守既定流向：

```
plans 骨架（本文件）→ design/ 分域确认文档（正式格式）→ architecture 收敛更新
```

| 目标文档 | 现状 | 差距 |
| --- | --- | --- |
| `architecture/database-schema.md`（唯一事实源） | 五层模型 DDL 齐全 | 缺 ER 关系总览、逐表字段字典、迁移史（0001~0013）、qed_llm_calls 所有权边界章节 |
| `architecture/api.md` | 五类端点简介+返回要点 | 未达五要素标准（接口/简介/**输入/输出/范例**）；路由数量与 `main.py` 实现有漂移风险 |

## 2. 范围清单（立项盘点以实现为准，本清单为快照）

### 数据库侧

- **共享表**：qed_domain / qed_course（所有权 QED-Tracker，其他项目只读）；qed_llm_calls
  （**根仓库所有**，本仓仅经 `llm_client._record_call` 写入 direct 调用记录；扩展列
  task/step/review_status/review_note 属 REQ-060 契约，文档须写明双向边界）
- **私有表**：qt_knowledge / qt_books / qt_sources
- **退役表处置**：qt_selections / qt_downloads（drop）、qt_sources_legacy（`migrate --drop-legacy` 删除）
- 补齐项：ER 关系图（五层主链 + 两张探索运行表旁路）、字段字典（含中文注释来源
  `migrations/data/table_comments.json`）、索引清单、迁移史时间线

### API 侧

- `src/qed_tracker/api/main.py` 全部路由按五要素成文（2026-09-01 盘点：**46 个路由装饰器**，
  分八类：服务健康 / 领域与课程管理 / 教程状态机 / 书籍生命周期与渠道 / 任务管理 /
  LLM 候选检索 / 目录 / 探索与采纳）
- 每端点五要素：**接口**（方法+路径+参数位置）、**简介**（语义+消费方）、**输入**
  （body/query/path schema）、**输出**（响应 schema + 错误码）、**范例**（请求/响应 JSON）

## 3. 依赖门禁（为何等 QED-010/011/014/026）

| 任务 | 对文档的影响 |
| --- | --- |
| QED-010 CLI→HTTP 客户端 + 真实冒烟 | CLI 形态与 API 消费面最终定型 |
| QED-011 重复下载链路验证 | 幂等语义的 API 行为澄清 |
| QED-014 全链路联调回执 | 跨项目契约最终确认（REQ 回执收口） |
| QED-026 主链路第一版闭环 | mainline 端点族行为稳定 |

提前写正式稿必然返工；门禁未过期间发现的文档失真仍按「当前事实源必须准确」即时修复
（如 2026-08-26 补录 qt_prompt_runs）。

## 4. 关系声明

- **承接 QED-039**：其待优化项「API 文档内容完善」由本任务吸收（todo 行已标注）；其余待优化项不变。
- **首批子集 = QED-043 Phase 3/4**：三公共表 + 相关 API 的 design/ 正式确认文档先落，
  作为格式模板验证后再铺开到全量范围。
- **完成时**：design/ 分域文档收敛进 architecture 两份固定文档，`test_documentation.py`
  全绿；本计划关闭并按规范归档。

## 5. 当前状态盘点（2026-09-01）

按 doc-governance.md「版本末期文档整理」规范，版本内只修复事实准确性，正式稿升级留待门禁通过后。

### 架构文档事实准确性

| 文档 | 维度 | 实际 | 文档 | 差距 | 处理 |
|---|---|---|---|---|---|
| `architecture/api.md` | 路由总数 | 46 条 | 42 条 | 4 条 REQ-067-B12 端点标记"未实现"但已实现 | 版本内修复 |
| `architecture/api.md` | 端点分组 | 八类 | 八类 | 结构正确，总数需更新 | 版本内修复 |
| `architecture/database-schema.md` | 活跃表 | 5 张 | 5 张 | ✅ DDL 准确 | 无需操作 |
| `architecture/database-schema.md` | 迁移链 | 0001-0015 | 只提到 0014 | 0015（add_explore_pending）缺失 | 版本内补入 |

### api-design.md Draft 状态

| 维度 | 实际 | Draft | 差距 |
|---|---|---|---|
| 端点数 | 46 条 | 19 条 | 严重过时，缺整个 book lifecycle 组（15 端点） |
| 最后更新 | 2026-09-01 | 2026-08-28 | 落后 4 天，本期变更未同步 |
| 处理 | 本期变更已登记在变更记录 | — | 版本末期正式稿时统一补齐 |

### 门禁状态

| 门禁 | 状态 | 对正式稿的影响 |
|---|---|---|
| QED-010 CLI→HTTP + 冒烟 | 待开始 | CLI 消费面未定型 |
| QED-011 重复下载验证 | 待开始 | 幂等语义未澄清 |
| QED-014 全链路联调 | 待开始 | 跨项目契约未确认 |
| QED-026 主链路第一版 | 进行中 | mainline 端点族行为未稳定 |

**结论**：正式稿升级仍被门禁阻塞；版本内只做事实准确性修复。

### 执行策略

- **版本内**（当前）：修复 api.md 路由数 42→46 + 标记 4 端点已实现 + 迁移 0015 补入
- **版本末期**（门禁通过后）：api.md + database-schema.md 按五要素标准重写 → 设计状态 Accepted
- **plans 晋升**：`2026-08-api-design.md`（Draft）中的端点清单作为正式稿素材，版本末期同步到 architecture/

## 6. 开放问题

- design/ 分域文档的拆分粒度（按表族/按业务域 vs 单一大文档）——待首批子集落地后由用户裁决。
- API 范例是否从契约测试断言值生成（防手写漂移）——执行时评估。

## 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-08-26 | 初始创建 | 用户裁决立项，门禁阻塞策略确立 |
| 2026-09-01 | 事实准确性盘点 | 路由数 44→46（REQ-067-B12 四端点已实现）；迁移 0015 缺失；database-schema.md DDL 准确；api-design.md Draft 严重过时（19 vs 46）；执行策略更新为「版本内修事实 + 版本末期写正式稿」 |
