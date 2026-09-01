# 项目状态快照

设计状态：Accepted
实现状态：Implemented
最后更新：2026-08-21
关联代码：无（状态快照，不映射具体模块）
关联测试：无
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)

## 用途

本文件是 QED-Tracker 开发状态的单一事实源入口：进场先读本表，30 秒掌握「项目现在到哪了」。
具体任务状态以[待办列表](todo.md)为准，未来方向以[能力路线图](roadmap.md)
为准；本表只保存「当前实现状态」快照。

## 服务状态

| 能力 | 端口/形态 | 状态 | 说明 |
| --- | --- | --- | --- |
| 8901 HTTP 服务（`/api/v1`） | 8901 | 已服务化 | FastAPI + 后台任务轮询（并发上限 2）；只读查询同步、轻量状态迁移同步；长操作走任务。 |
| MySQL 登记索引 | 共享 `qed` 库五层模型 `qed_domain`/`qed_course`（共享）→ `qt_knowledge`/`qt_books`/`qt_sources`（私有） | 已实现 | 知识层次重构（QED-031，Alembic 0006）：教程/书籍/渠道五层模型，qt_resources 与三表均已退役；无 `QED_DB_PASSWORD` 降级运行。课程体系只读端点（QED-033 `/courses`）。 |
| CLI | `qed-tracker` | 已实现（未转客户端） | 命令树/退出码/机器输出；`serve`/`courses`/`mainline`/`migrate` 入口；CLI 闭环命令（catalog evaluate / resources …）未实现，属 QED-010。 |
| 教材来源 | IA / Open Library / Google Books / libgen_li | 已实现 | libgen_li 发现专用（恒 metadata_only，人工下载后登记）；annas_archive/zlib 退役。 |
| arXiv 与论文发现 | arXiv + 百炼 | 已实现 | 检索计划 + 可审阅评分，不写资源事实、不自动下载。 |
| Axiom-Flow 交接 | HTTP（默认 8902） | 已实现 | 默认只上传，显式 `--parse` 才创建解析任务。 |
| 模型调用模式 | local（直连 dashscope qwen）/ qed-engine（8900 网关） | 改造中 | QED-037 执行中：自身 `.env` + `llm_client.py` 兼容层 + service `--mode` + qed_llm_calls 调用记录。 |

## 当前主线

- **主链路（QED-026，实现完成待人工闭环验证）**：领域课程梳理 → 教材寻找 → 下载 → 人工验收
  （设计 Accepted：[main-line-curriculum.md](../design/main-line-curriculum.md)；架构见
  [main-line.md](../architecture/main-line.md)）。courses/mainline 全命令已实现；待人工闭环验证
  （配置 API_KEY → mainline new → review → download → approve 移交根仓库，00/01/02 三门基础课）。
- **QED-036 教程命名规范（已完成，回执待写根仓库 REQ-041）**：`tutorial_name` 命名函数 +
  migrate 先查后建幂等 + mainline new `--set-no`/review `--title/--author` +
  textbook_ref 补 authors；存量 3 行已改规范名（教程1：数学分析原理（Rudin）等，证据
  docs/history/qed-036-tutorial-naming/）。
- **QED-037 模型模式与密钥分置（已完成，回执待写根仓库 REQ-043）**：自身 `.env` + config
  改读 + llm_client 双模式兼容层 + 三 advisor 接入 + service `--mode` + qed_llm_calls 调用
  记录（设计 Accepted/Implemented：[model-mode-config.md](../design/model-mode-config.md)）。
- **QED-038 密钥收敛（已完成，回执待写根仓库 ARCH-017）**：逐厂商 key 别名全部取消，
  `llm_api_key` 只读唯一 `API_KEY`。
- **课程收集主线（QED-019）**：01 数学分析闭环——catalog 已定稿（01 共 14 目标，54 总），
  12 册 approved 已移交根仓库；三态评估 → 下载/登记 → 人工验收。
- **QED-014 全链路联调**：真实 8901 全链路（评估→确认→下载→验收/删除→登记→qed CLI/8903
  前端展示）待开始；QED-010（CLI 转 HTTP 客户端）与 QED-011（重复下载验证）随其后。
- **QED-024 套标记字段**：代码层完成（`set_no` 字段 + catalog 解析 + 契约测试）+ 01 数学分析
  13 目标补齐（套一/套二/套三/en 与 note 一致）；其余 12 门课 41 目标待人工定套；
  API 已透出 `set_no`，回执根仓库 REQ-028 待完成。
- **治理对齐（QED-022）**：守护契约范本对齐已完成（8 个守护测试六字段 docstring + 守护面清单五类），回执根仓库 REQ-023 待写入。
- **文档体系长效机制（QED-039）**：首轮固定化已完成（architecture/ 固定 + api.md + database-schema
  升级 + project-status 移入 trackers/ + design 三态清理）；已建立
  [文档治理规范](../standards/doc-governance.md)「版本末期文档整理」节（ADR 0002 登记、
  ADR 0004 并入），每次版本确认前执行一轮。

## 维护规则

- 服务实现状态、当前主线或能力归属变化时，更新本表并刷新「最后更新」日期。
- 本表不保存任务细节与未来规划（分别见 todo.md / roadmap.md）；与[系统总览](../architecture/system-overview.md)
  的静态描述不一致时，以本表当前状态为准并回修系统总览。
