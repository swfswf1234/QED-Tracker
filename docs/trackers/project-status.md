# 项目状态快照

设计状态：Accepted
实现状态：Implemented
最后更新：2026-09-11
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
| MySQL 登记索引 | 共享 `qed` 库五层模型 `qed_domain`/`qed_course`（共享）→ `qt_knowledge`/`qt_books`/`qt_sources`（私有） | 已实现 | 书库化重建（QED-050-D）+ 模型即 schema 重建式自愈（QED-053，ADR 0006：`db/schema.py` `ensure_schema`，Alembic 链已退役）；无 `QED_DB_PASSWORD` 降级运行。课程体系只读端点（QED-033 `/courses`）。 |
| CLI | `qed-tracker` | 已实现（已转 HTTP 客户端） | 命令树/退出码/机器输出；`serve`/`books`/`courses`/`domains`/`knowledge`/`mainline` 入口；主链路命令经 8901 提交+轮询（QED-010 已验收，2026-09-09，`migrate` 已随旧三表退役删除）。 |
| 教材来源 | IA / Open Library / Google Books / libgen_li | 已实现 | libgen_li 发现专用（恒 metadata_only，人工下载后登记）；annas_archive/zlib 退役。 |
| arXiv 与论文发现 | arXiv + 百炼 | 已实现 | 检索计划 + 可审阅评分，不写资源事实、不自动下载。 |
| Axiom-Flow 交接 | HTTP（默认 8902） | 已实现 | 默认只上传，显式 `--parse` 才创建解析任务。 |
| 模型调用模式 | local（直连 dashscope qwen）/ qed-engine（8900 网关） | 已实现 | QED-037：自身 `.env` + `llm_client.py` 兼容层 + service `--mode` + qed_llm_calls 调用记录。 |

## 当前主线

- **本期计划全链路验收通过（2026-09-11）**：主链路（QED-026）+ 教材探索与下载双轨（QED-050
  全子轮）+ 数据库重构（QED-053）+ CLI 转 HTTP 客户端（QED-010）+ 8901 全链路联调（QED-014）
  + 重复下载链路验证（QED-011）全部完成并验收关闭；下载状态机/落盘/ID 收口（QED-060/061/062）、
  探索契约对齐（QED-063/064/065，REQ-076/077/078）、遗留清单（QED-056/057）均已关闭。
  全量 `pytest tests -q` **482 passed + 1 skipped**，ruff clean。见[完成台账](completed.md)。
- **下一阶段主线（待立项）**：本地 LLM 模型替换 + 论文探索。
- **长期任务**：prompt 优化模块（QED-043）、来源探索与评估（QED-054，含 REQ-020①② 找得率基线
  持续采集与回执）；见[待办列表](todo.md)。

## 维护规则

- 服务实现状态、当前主线或能力归属变化时，更新本表并刷新「最后更新」日期。
- 本表不保存任务细节与未来规划（分别见 todo.md / roadmap.md）；与[系统总览](../architecture/system-overview.md)
  的静态描述不一致时，以本表当前状态为准并回修系统总览。
