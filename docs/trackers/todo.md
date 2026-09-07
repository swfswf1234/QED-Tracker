# 待办列表

状态：Current
最后更新：2026-09-07

## 本期计划（全链路跑通）

### 核心目标
1. 跑通全链路（探索→评估→下载→验收）
2. 完善文档评估逻辑链路
3. 完善文档下载链路
4. QED-014 验证最终效果

### 任务清单


#### 阶段二：主链路完善

| ID | 类型 | 状态 | 事项 | 成功标准 | 关联计划 |
| --- | --- | --- | --- | --- | --- |
| QED-026 | Plan | 进行中 | 主链路第一版（CLI 跑通 3 门基础课验证）：课程体系加载、教材条目五要素存储、LLM 预填评价、mainline new/review/download/verify/channels（approve/reject 已随 QED-050-D 删除，取书经 8901 五阶段链，登记 owned 即完成） | 00/01/02 三门课程闭环；全量门禁全绿 | [2026-08-main-line-curriculum.md](../plans/2026-08-main-line-curriculum.md)、[2026-08-download-flow.md](../plans/2026-08-download-flow.md) |
| QED-050 | Plan | 进行中 | 教材探索与下载手动+自动双轨 + 知识体系梳理：方案 A 薄壳导入层复用现有能力；QED-043 语义升级；docs/knowledge/ 标准答案知识目录；手动探索（POST /domains/import）；手动下载（POST /books/{id}/import） | M1~M7 全部完成（prompt 模板升级、math.json 重整理、流程文档、导入链、下载链、文档同步） | [2026-08-knowledge-dual-flow.md](../history/baselines/2026-08-knowledge-dual-flow.md) |
| QED-050-D | Plan | 进行中 | 下载与登记链路优化（自动下载 + 手动导入 + 验收）：三门基础课下载闭环 + 渠道记录完备 + target_path 落盘验证。2026-09-04 设计确认晋升[下载管线设计](../design/download-pipeline.md)（五阶段下载链 + 九项裁决），实现按[下载登记实现计划](../plans/2026-09-download-implementation.md)分阶段执行；2026-09-06 Phases 0~6 实现完成（0018 书库化重建 + original_title、QED_BOOK_* 8 键 + accept_pdf 验收门、LLM 顾问扩展与渠道 enrich、五阶段编排与 mark_owned 登记服务、API 35 路由重接 + 并发 409 防护、CLI mainline/books 重接 + migrate 退役、文档同步 + 门禁全绿）；2026-09-07 CLI 手动上传人工闭环验证（qed_test 库）：domains import math-advanced（12 门）→ knowledge import 01/02/11（11 套 confirmed、21 书行）→ books import 手动导入 17 本（数学分析 11 / 高等代数 3 / 概率论 3，渠道 local_import 18 条全 ok）→ mainline verify 逐套复核全 ok；未导入：01ma-b02/b03（Apostol 两卷，用户暂缓）、02la-b06（普罗斯库烈柯夫习题集，目录无 PDF）、11pb-b05（Casella & Berger，目录无 PDF）；01 json 增行 b16 谢惠民下册/b17 Rudin 英文习题答案/b18 Fitzpatrick（parallel_ref）并校验通过；既有失败不阻塞：正本守护 test_knowledge_docs_courses_conform_to_contract 因 template.json 与正本同目录被误扫、test_validate_course_rejects 用 tutorials@v1 旧数据；2026-09-07 qed_test 清库后纯 8901 API 链重放冒烟完成（POST /domains/import 12 门 → /courses/{id}/knowledge 采纳 11 套/21 书行 → /knowledge/{id}/confirm 11/11 → /books/{id}/import 17 本 owned → verify 17/17 ok；同 sha 幂等复用与 local_import 渠道留痕验证；回执已登记根仓库 ARCH-019）；剩余：00/01/02 三门真实环境闭环验证 | 00/01/02 课程下载→验收→登记全链路通过；渠道记录完整 | [2026-09-download-implementation.md](../plans/2026-09-download-implementation.md) |
| QED-050-E | Plan | 待开始 | 数据生命周期验证（状态机全路径 + 清理策略）：知识/探索/书籍三条生命周期各状态路径测试 + 交叉点验证 + 清理策略端到端验证 | 全状态路径测试通过；交叉点联动验证；清理策略验证 | [2026-09-data-lifecycle.md](../plans/2026-09-data-lifecycle.md) |
| QED-053 | Plan | 进行中 | v0.1 数据库重构（[ADR 0006](../adr/0006-database-model-as-schema-rebuild.md)）：模型即 schema + 重建式自愈，Alembic 链退役。实施：[2026-09-db-schema-rework.md](../plans/2026-09-db-schema-rework.md)。阶段一（代码+文档）进行中；确认时写 JSON 为阶段二 | 全量门禁全绿；qed_test 库冒烟通过（ensure_schema 缺表补建/不一致重建/幂等/qed_llm_calls 增量自愈）；真实 qed 库经人工确认后更新 | [2026-09-db-schema-rework.md](../plans/2026-09-db-schema-rework.md) |

#### 阶段三：验证与回执

| ID | 类型 | 状态 | 事项 | 成功标准 | 关联计划 |
| --- | --- | --- | --- | --- | --- |
| QED-010 | Plan | 待开始 | [跨项目] CLI 转 HTTP 客户端 + 基于真实 8901 服务的冒烟测试（需求方：QED-Engine） | `qed-tracker` 命令经 8901 完成任务；启动 → 建任务 → 轮询 → 校验文件落位全链路冒烟通过；`--no-wait` 输出 task_id；论文链路真实冒烟 | [2026-08-engine-exploration-alignment.md](../history/baselines/2026-08-engine-exploration-alignment.md) |
| QED-011 | Validation | 待开始 | 重复下载链路验证（用户约定在 QED-008~010 冒烟后执行） | 同一资源二次下载返回既有资源记录，不产生重复文件，任务幂等 | — |
| QED-014 | Validation | 待开始 | [跨项目] 联调冒烟与回执：真实 8901 全链路（评估→确认→下载→验收/删除→登记→qed CLI/8903 前端展示）（**最终验证**） | 8901 服务 + qed CLI + QED-Engine 下载工作台数据贯通；根仓库 todo REQ-004/REQ-011/REQ-013/REQ-014/REQ-026 收到回执 | — |

---

## 历史任务（待清理）

以下任务与本期计划关联度低，标记为低优先级或暂停：

| ID | 类型 | 状态 | 事项 | 说明 |
| --- | --- | --- | --- | --- |
| QED-042 | Plan | 暂停 | main.py 超长重构（低优先级）：src/qed_tracker/api/main.py 当前 950+ 行，端点定义/校验逻辑/helper 函数混杂。按业务域拆分为独立路由模块，保留 main.py 仅做 app 工厂注册。无行为变更，纯结构重构 | 无行为变更，纯结构优化，不影响全链路跑通 |
| QED-045 | Plan | 暂停 | 探索管线模型选型治理占位（低优先级）：评估是否需要 per-step/per-task 模型覆盖能力，供未来主链路用推理型 + 探索用轻量的混跑场景；当前单线路策略下无需求，仅防范围丢失占位 | 低优先级，当前无需求 |
| QED-046 | Defect | 暂停 | 迁移链 downgrade 缺陷（低优先级不阻塞）：`0008_exploration_runs.py` downgrade 引用不存在的索引，`alembic downgrade base` 全链走不通；全新库 upgrade head 路径已验证通过。**已随 ADR 0006 失效**（Alembic 链退役，迁移目录删除，问题随链消失），保留历史记录 | 低优先级，upgrade 正常，downgrade 不支持；ADR 0006 后随链退役 |

---

## 长期任务

以下任务为持续进行的长期工作，不绑定具体 plans/ 文档：

| ID | 类型 | 状态 | 事项 | 说明 |
| --- | --- | --- | --- | --- |
| QED-043 | Plan | 进行中 | prompt 优化模块（领域/课程知识探索工作台）：领域管线 v2/v4/v8 已验证（13 门）；课程 tutorials@v2 实现完成 | 长期任务，持续优化 |
| QED-044 | Plan | 进行中 | 完整数据库设计文档与 API 设计文档：主线 30 条路由五组六要素 + 非主线 7 条附录一览成文（architecture/api.md）；数据库文档按表族拆分两文（[ADR 0007](../adr/0007-database-docs-split-by-table-family.md)：architecture/database-private-tables.md / architecture/database-shared-tables.md）（[实施计划](../plans/2026-08-db-api-docs-completion.md)） | 正式稿已成文（2026-09-07）；转正评审与根仓库同步回执待办 |
| QED-054 | Plan | 进行中 | 来源探索与评估（持续工作）：来源评估矩阵维护、渠道连通性/中文覆盖/候选质量实测、待探索清单推进；libgen_li 保持发现专用（metadata_only，永不自动落盘），annas_archive/zlib 保持退役 | 评估结论持续更新进计划矩阵；新来源按来源协议接入经通用下载器 | [2026-09-source-discovery.md](../plans/2026-09-source-discovery.md) |

---

## 规则

- 任务按类型分类（Plan / Defect / Validation / Candidate），状态只允许 `待开始 / 进行中 / 已完成 / 阻塞`；阻塞必须声明证据、恢复条件和责任位置。
- 任务关闭时从本表移除并追加到[完成台账](completed.md)。
- **本期计划**任务按阶段分组，关联 plans/ 文档；**历史任务**标记暂停或低优先级；**长期任务**只列清单，不绑定 plans/ 文档。
