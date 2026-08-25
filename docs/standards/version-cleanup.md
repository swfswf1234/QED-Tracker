# 版本末期文档整理规范

状态：Current
最后更新：2026-08-21
治理对象：版本末期文档三态梳理、固定文档更新、tracker 一致性、回执
依据：QED-Engine 根仓库 `docs/standards/documentation.md`「版本与固定文档」「归档与删除」治理模式
关联 ADR：[ADR 0002](../adr/0002-version-cleanup-governance.md)
关联测试：`tests/test_documentation.py`

## 目的与边界

本标准规定 QED-Tracker 每次版本确认（升版本）前必须执行的文档整理轮：把本版本的 ADR 决策
合并进固定文档、清理 design/ 三态、同步实时状态，并验证文档体系完整。QED-039 是持续执行本
标准的长期任务。

子项目版本纪元与根仓库一致：当前为 v0.1；`docs/adr/index.md` 声明当前版本。

## 强制规则

### 触发条件

- **每次版本确认前**（`develop` 合入 `main`、用户确认升版本时）执行一轮。
- 版本之间文档变化未达整理规模时，由 QED-039 todo 条目记录待整理项，版本末期统一处理。

### 版本末期检查清单

1. **ADR 决策合并**：本版本新增 ADR 决策合并进 `architecture/` 或其他固定文档；
   `history/` 记录前版本；ADR 正文与编号保留（编号全局唯一、进入主分支后不复用）。
2. **固定文档更新**：API 接口文档（`architecture/api.md`）与数据库设计文档
   （`architecture/database-schema.md`）的变更设计先在 `plans/`（不确定文档）中进行，
   版本末期确认更新后落 `architecture/`，更新前旧版本进 `history/`。
3. **design/ 三态梳理**（对齐根仓库「归档与删除」）：
   - 设计内容已并入固定文档的标 Superseded 并删除（内容由固定文档承接）；
   - 已完成使命的存档文档移入 `docs/history/`（如 `history/baselines/`）；
   - 仍具契约价值且任务未完成或后续轮继续使用的保持原状并更新实现状态。
4. **trackers/ 实时状态同步**：`todo.md`（关闭项移除并追加 completed.md）、
   `project-status.md`（当前主线/服务状态刷新）、`roadmap.md` 无执行状态。
5. **链接与引用完整**：`tests/test_documentation.py` 守护全部通过（入口集合/元数据/链接/
   代码引用/CLI 一致性/tracker ID）。
6. **metadata 规范化**：架构/设计文档的设计状态与实现状态取值合法、最后更新刷新、
   关联代码/关联测试准确。

### 执行流程

1. 读取 `docs/architecture/code-map.md` 与 `docs/trackers/project-status.md`，掌握当前状态。
2. 按检查清单逐项整理；每次版本末期更新 `docs/design/docs-restructure-alignment.md` 的
   执行记录或归档为历史。
3. 运行 `tests/test_documentation.py` 定向门禁，再运行完整门禁（见
   [开发指南](../guides/development.md)）。
4. 回执根仓库 REQ-002 / REQ-046（提交号 + 门禁输出）。

## 变更与取代

改变触发条件、检查清单或执行流程属于 standards 实质规则变更，按
[ADR 治理规范](adr-governance.md) 先新增 ADR。措辞、勘误、链接和不改变语义的整理可直接修改。
