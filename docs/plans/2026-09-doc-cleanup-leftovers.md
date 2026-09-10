# 文档清理遗留问题清单（2026-09-09）

状态：Active
任务类型：B（缺陷与裁决跟踪清单）
最后更新：2026-09-09
需求方：QED-Tracker 文档清理轮（QED-056）
评审方：用户

> 本清单承接 2026-09-09 文档清理轮（关闭 QED-026 / QED-050-D / QED-044 / QED-055，删除
> `2026-08-download-flow.md`、`2026-08-main-line-curriculum.md`、`2026-09-download-implementation.md`、
> `2026-08-db-api-docs-completion.md`、`2026-09-fix-import-stage-guard.md` 五份计划，Git 历史可追溯）
> 的全部未完事项。
>
> **2026-09-09 验收收口轮更新**：QED-050 / QED-050-E / QED-053 / QED-010 / QED-014 验收关闭；
> L-02/L-03/L-04 随 QED-014 验收通过关闭；L-05/L-06 注释级修复完成（QED-057 首批）；
> L-01/L-14 代码级修复归 QED-057，裁决项维持待用户。联调问题专项计划已归档至
> [历史基线](../history/baselines/2026-09-09-qed014-integration-issues.md)。

## 遗留清单（活跃）

| 编号 | 事项 | 证据 | 建议去向 | 优先级 |
| --- | --- | --- | --- | --- |
| L-01 | re-explore / run 路径 `mode` 默认值 `"web"` 为非法 mode：不带 mode 提交即失败（`_read_reference` 仅收 direct/text/doc）→ 写 error 载荷 | `api/main.py:800`、`:833`（2026-09-09 复核现行行号，`payload.get("mode", "web")` 两处）；[探索管线设计](../design/exploration-pipeline.md) Phase 2 待对齐表 | QED-057（默认改 `direct`，代码逻辑变更） | 高 |
| L-07 | 探索状态机「失败」态无写入点（错误路径写 待确认 + `explore_pending={kind:"error"}`）；lifespan 启动时对滞留 探索中/待确认 任务无清理 | [数据库共享表设计](../architecture/database-shared-tables.md) 实现口径注；`api/main.py` 错误路径 | 待用户裁决：补失败写入点/启动清理 or 维持现状（文档已如实登记） | 中 |
| L-08 | `qt_knowledge`→`qed_course` 真实 FK 缺失（ORM 物理外键仅 `qt_sources.book_id`，其余为逻辑外键；文档已按逻辑外键口径登记） | `db/models.py`；[数据库专用表设计](../architecture/database-private-tables.md) 头注 | 待用户裁决（是否补物理 FK 属 schema 决策） | 低 |
| L-09 | G1 confirm 端点覆写语义：缺省字段应 = 保留既有值，当前以脚本回显规避 | 原下载流程计划「已知事实与缺口」（Git 追溯） | QED-057 评估（原去向 QED-014 已关闭） | 中 |
| L-10 | G3 tmp/exploration 根契约冲突：根文档「用户资产不自动清理」vs 本仓库 tmp 可清理语义；副本已按用户指令删除 | 原下载流程计划（Git 追溯） | 待用户裁决：恢复副本 or 修订根文档 | 中 |
| L-11 | REQ-020① 收窄知会根仓库（口径已迁入 source-discovery 计划） | [来源探索与评估计划](2026-09-source-discovery.md) REQ-020 节 | 知会动作（待用户执行） | 低 |
| L-12 | `tests/test_documentation.py` REQUIRED_CURRENT_DOCS 为硬编码清单，新增计划文档需手工同步（曾漏 integration-issues 致守护红；本轮已补齐） | `tests/test_documentation.py` 文档白名单段 | 已裁决维持手工同步；如反复遗漏可考虑 glob 自动发现 | 低 |
| L-13 | REQ-020② 找得率基线：从 `qt_sources` 采集并回执根仓库（L-04 已于 2026-09-09 通过，具备采集条件） | [来源探索与评估计划](2026-09-source-discovery.md) REQ-020 节 | 随 QED-054 持续工作采集 | 中 |
| L-14 | HEAD（e1dd693）全量测试预存在失败：test_knowledge_repository 22 / test_knowledge_api 22 / test_knowledge_import 20 / test_book_fetch 10（含 8 error）/ test_cli_knowledge_import 3 / test_prompt_lab_api 2 / test_db_models 2（`test_enums_complete`、`test_qt_books_unique_constraints`）/ test_api 1（`test_concurrency_is_capped_at_two`，2026-09-09 HEAD 临时 worktree 复核证实）；根因示例 `create_knowledge() got an unexpected keyword argument 'domain_id'`（tests 调用旧签名） | `tests/test_book_fetch.py:105` 等；QED-050-D 收尾项「定向测试预存在失败修复」 | QED-057（签名对齐 + 契约测试更新） | 高 |

## 已关闭（2026-09-09 验收收口轮）

| 编号 | 事项 | 关闭方式 |
| --- | --- | --- |
| L-02 | QED-014 问题 2：LLM 调用记录（`qed_llm_calls`）联调环境落库验证 | 随 QED-014 验收通过（真实环境确认落库） |
| L-03 | QED-014 问题 8：前端 `DomainConfirmModal.tsx` 缺 `confirmDomainInfo` 调用 | QED-Engine 前端修复完成，随 QED-014 验收通过 |
| L-04 | 00/01/02 三门真实环境闭环验证（取书→机器验收→登记→前端展示） | 随 QED-014 验收通过 |
| L-05 | `QedCourse.stage` 模型注释与四档值域矛盾 | QED-057 注释级修复（2026-09-09）：模型 `comment=` 改 `基础/主干/分支/前沿`；存量表列注释随下次表重建自愈刷新 |
| L-06 | `main.py` 课程 dry-run docstring `tutorials@v1` 应为 `tutorials@v2` | QED-057 注释级修复（2026-09-09） |

## 备注

- 原下载流程计划 G 系列：G2（exploration_stage 回写）/ G7（qt_sources schema 漂移）/
  G8（8901 无自动下载执行器）已在 QED-050-D 重构中修复验证，不再登记；G4（auto-create
  粗糙）/ G5（file_keywords 注入不统一）为重构前实现不足记录，QED-050-D 取书链重写后
  未再复核原表述，如联调中发现按 L-04 收口（L-04 已通过，视为消解）。
- LLM 预填契约值域（mainline-prefill-v1）已迁入[主链路设计](../design/main-line-curriculum.md) §5，
  非遗留事项。
