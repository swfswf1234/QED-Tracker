# 项目状态快照

设计状态：Accepted
实现状态：Implemented
最后更新：2026-08-12
关联代码：无（状态快照，不映射具体模块）
关联测试：无
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)

## 用途

本文件是 QED-Tracker 开发状态的单一事实源入口：进场先读本表，30 秒掌握「项目现在到哪了」。
具体任务状态以[待办列表](../trackers/todo.md)为准，未来方向以[能力路线图](../trackers/roadmap.md)
为准；本表只保存「当前实现状态」快照。

## 服务状态

| 能力 | 端口/形态 | 状态 | 说明 |
| --- | --- | --- | --- |
| 8901 HTTP 服务（`/api/v1`） | 8901 | 已服务化 | FastAPI + 后台任务轮询（并发上限 2）；只读查询同步、轻量状态迁移同步；长操作走任务。 |
| MySQL 登记索引 | 共享 `qed` 库 `qt_resources` | 已实现 | JSON 事实源双写查询索引；无 `QED_DB_PASSWORD` 降级运行；review_note 留痕（QED-020）。 |
| CLI | `qed-tracker` | 已实现（未转客户端） | 命令树/退出码/机器输出；`serve` 入口；CLI 闭环命令（catalog evaluate / resources …）未实现，属 QED-010。 |
| 教材来源 | IA / Open Library / Google Books / libgen_li | 已实现 | libgen_li 发现专用（恒 metadata_only，人工下载后登记）；annas_archive/zlib 退役。 |
| arXiv 与论文发现 | arXiv + 百炼 | 已实现 | 检索计划 + 可审阅评分，不写资源事实、不自动下载。 |
| Axiom-Flow 交接 | HTTP（默认 8902） | 已实现 | 默认只上传，显式 `--parse` 才创建解析任务。 |

## 当前主线

- **主链路（QED-026，实现完成待人工验证）**：领域课程梳理 → 教材寻找 → 下载 → 人工验收
  （设计 Accepted：[main-line-curriculum.md](../design/main-line-curriculum.md)；架构见
  [main-line.md](main-line.md)）。courses/mainline 全命令已实现（提交链 948fa88~ea905b9，
  全量 221 passed + 3 skipped）；待人工闭环验证（配置 QWEN_API_KEY → mainline new →
  review → download → approve 移交根仓库，00/01/02 三门基础课）。
- **课程收集主线（QED-019）**：01 数学分析闭环——catalog 已定稿（01 共 14 目标，54 总），
  测试全绿；待 8901 重启（迁移 review_note）→ 存量清理 → evaluate 01 → 三态 → 下载/登记 →
  人工验收。
- **QED-014 全链路联调**：真实 8901 全链路（评估→确认→下载→验收/删除→登记→qed CLI/8903
  前端展示）待开始；QED-010（CLI 转 HTTP 客户端）与 QED-011（重复下载验证）随其后。
- **QED-024 套标记字段**：属 Plan 类别（方案确定后再进设计文档），既有 Draft 已归档至
  docs/history/baselines/catalog-set-field.md，待方案确定后实现
  （`set_no` 字段 + math-qe.json 54 目标补齐 + API 透出，回执根仓库 REQ-028）。
- **治理对齐（QED-022/023）**：守护契约范本对齐与 qt_* 表结构事实源确认，设计已建、待执行。

## 维护规则

- 服务实现状态、当前主线或能力归属变化时，更新本表并刷新「最后更新」日期。
- 本表不保存任务细节与未来规划（分别见 todo.md / roadmap.md）；与[系统总览](system-overview.md)
  的静态描述不一致时，以本表当前状态为准并回修系统总览。
