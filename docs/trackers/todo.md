# 待办列表

状态：Current
最后更新：2026-08-31

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
| QED-026 | Plan | 进行中 | 主链路第一版（CLI 跑通 3 门基础课验证）：课程体系加载、教材条目五要素存储、LLM 预填评价、mainline new/review/download/verify/approve/reject/channels、验收后复制+登记同步移交根仓库 | 00/01/02 三门课程闭环；全量门禁全绿 | [2026-08-main-line-curriculum.md](../plans/2026-08-main-line-curriculum.md)、[2026-08-download-flow.md](../plans/2026-08-download-flow.md) |
| QED-050 | Plan | 进行中 | 教材探索与下载手动+自动双轨 + 知识体系梳理：方案 A 薄壳导入层复用现有能力；QED-043 语义升级；docs/knowledge/ 标准答案知识目录；手动探索（POST /domains/import）；手动下载（POST /books/{id}/import） | M1~M7 全部完成（prompt 模板升级、math.json 重整理、流程文档、导入链、下载链、文档同步） | [2026-08-knowledge-dual-flow.md](../plans/2026-08-knowledge-dual-flow.md) |
| QED-050-A | Plan | 待开始 | 领域探索管线优化（domain@v3 + courses@v5 + path@v5）：模板输出质量审核 + 真实冒烟验证 + 错误处理完备（400/404/409/502） | 模板审核通过；真实 LLM 冒烟输出可用；错误码全覆盖 | [2026-09-exploration-pipeline.md](../plans/2026-09-exploration-pipeline.md) |
| QED-050-B | Plan | 待开始 | 课程探索管线优化（tutorials@v1）：课程 dry-run 真实冒烟 + 与领域探索对称验证 | 课程 dry-run 真实 LLM 输出可用；与领域管线对称 | [2026-09-exploration-pipeline.md](../plans/2026-09-exploration-pipeline.md) |
| QED-050-C | Plan | 待开始 | 手动导入链路优化（领域 JSON + 课程 JSON + 书籍 PDF）：三种导入全链路测试 + schema 契约冻结 + slug/course_id 映射解决 | 三种导入全链路测试通过；schema 契约冻结；O1 待裁决关闭 | [2026-09-knowledge-import.md](../plans/2026-09-knowledge-import.md) |
| QED-050-D | Plan | 待开始 | 下载与登记链路优化（自动下载 + 手动导入 + 验收）：三门基础课下载闭环 + 渠道记录完备 + target_path 落盘验证 | 00/01/02 课程下载→验收→登记全链路通过；渠道记录完整 | [2026-09-download-registration.md](../plans/2026-09-download-registration.md) |
| QED-050-E | Plan | 待开始 | 数据生命周期验证（状态机全路径 + 清理策略）：知识/探索/书籍三条生命周期各状态路径测试 + 交叉点验证 + 清理策略端到端验证 | 全状态路径测试通过；交叉点联动验证；清理策略验证 | [2026-09-data-lifecycle.md](../plans/2026-09-data-lifecycle.md) |

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
| QED-046 | Defect | 暂停 | 迁移链 downgrade 缺陷（低优先级不阻塞）：`0008_exploration_runs.py` downgrade 引用不存在的索引，`alembic downgrade base` 全链走不通；全新库 upgrade head 路径已验证通过 | 低优先级，upgrade 正常，downgrade 不支持 |

---

## 长期任务

以下任务为持续进行的长期工作，不绑定具体 plans/ 文档：

| ID | 类型 | 状态 | 事项 | 说明 |
| --- | --- | --- | --- | --- |
| QED-043 | Plan | 进行中 | prompt 优化模块（领域/课程知识探索工作台）：领域管线 v2/v4/v4 已验证（13 门）；课程 tutorials@v1 实现完成 | 长期任务，持续优化 |
| QED-044 | Plan | 进行中 | 完整数据库设计文档与 API 设计文档：全部表族与 main.py 全部路由按五要素成文；architecture/database-schema.md 与 architecture/api.md 收敛更新 | 长期任务，前置门禁：QED-010/011/014/026 全部完成后才动笔正式稿 |

---

## 规则

- 任务按类型分类（Plan / Defect / Validation / Candidate），状态只允许 `待开始 / 进行中 / 已完成 / 阻塞`；阻塞必须声明证据、恢复条件和责任位置。
- 任务关闭时从本表移除并追加到[完成台账](completed.md)。
- **本期计划**任务按阶段分组，关联 plans/ 文档；**历史任务**标记暂停或低优先级；**长期任务**只列清单，不绑定 plans/ 文档。
