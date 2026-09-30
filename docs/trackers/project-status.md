# 项目状态快照

设计状态：Accepted
实现状态：Implemented
最后更新：2026-09-30
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
| MySQL 登记索引 | 共享 `qed` 库五层模型 `qed_domain`/`qed_course`（共享）→ `qt_knowledge`/`qt_books`/`qt_sources`（私有） | 已实现 | 书库化重建（QED-050-D）+ 模型即 schema 重建式自愈（QED-053，ADR 0006：`db/schema.py` `ensure_schema`，Alembic 链已退役）；无 `QED_DB_PASSWORD` 降级运行。课程体系只读端点（QED-033 `/courses`）；`qt_books` 内容身份三列（sha256/size_bytes/page_count）为书侧唯一事实源，`meta/resources/` 资源 JSON 岛与 `Inventory` 类已退役（QED-071 B 轮）。 |
| CLI | `qed-tracker` | 已实现（已转 HTTP 客户端） | 命令树/退出码/机器输出；`serve`/`books`/`courses`/`domains`/`knowledge`/`mainline`/`inventory`/`axiom` 入口；主链路命令经 8901 提交+轮询（QED-010 已验收，2026-09-09，`migrate` 已随旧三表退役删除）。QED-071 B 轮 CLI 变更：`catalog run` 退役（D11）、`inventory scan` 删除 + `list` 改 DB 书目视图（D16）、`inventory verify/reconcile` 与 `axiom push <book_id>` 读 `qt_books` 且无 DB 时退出码 2（D15/M4）。 |
| 教材来源 | IA / Open Library / Google Books / libgen_li | 已实现 | libgen_li 发现专用（恒 metadata_only，人工下载后登记）；annas_archive/zlib 退役。 |
| arXiv 与论文发现 | arXiv + 百炼 | 已实现 | 检索计划 + 可审阅评分，不写资源事实、不自动下载。 |
| Axiom-Flow 交接 | HTTP（默认 8902） | 已实现 | 默认只上传，显式 `--parse` 才创建解析任务；`axiom push` 只接受 `book_id` 且磁盘内容与 `qt_books` 记录不一致时拒绝上传（QED-071 D15）。 |
| 模型调用模式 | local（直连 dashscope qwen）/ qed-engine（8900 网关） | 已实现 | QED-037：自身 `.env` + `llm_client.py` 兼容层 + service `--mode` + qed_llm_calls 调用记录。 |

## 当前主线

- **本期计划全链路验收通过（2026-09-11）**：主链路（QED-026）+ 教材探索与下载双轨（QED-050
  全子轮）+ 数据库重构（QED-053）+ CLI 转 HTTP 客户端（QED-010）+ 8901 全链路联调（QED-014）
  + 重复下载链路验证（QED-011）全部完成并验收关闭；下载状态机/落盘/ID 收口（QED-060/061/062）、
  探索契约对齐（QED-063/064/065，REQ-076/077/078）、遗留清单（QED-056/057）均已关闭。
- **服务稳定性优化关闭（2026-09-14，QED-066）**：服务重启后 orphaned running/queued 任务
  恢复为 failed（dedup 解除）+ `verify_content` 下载后内容校验（首页文本 vs 登记标题，软信号
  写入 qt_sources.note）；REQ-017② 进度上报评估结论已登记（后端就绪、缺口在前端）。
  全量 `pytest tests -q` **496 passed + 1 skipped**，ruff clean。见[完成台账](completed.md)。
- **v1.0 本期主线立项并定口径（2026-09-14 立项，2026-09-24 链条评审）**：三主线 =
  ① 本地模型接入与编排（QED-067）、② 论文探索与下载（QED-068，详细方案已裁）、
  ③ 下载链路评估与质量闭环（QED-069/070）；**v1.0 口径 = 三主线全部交付 + 根侧
  ARCH-024 三线优化收口**，批次顺序（0 裁决轮 → A~E）与各线交付口径见
  [v1.0 后续任务链条梳理](../plans/2026-09-24-v1-task-chain.md)；各任务尚未排期实施。
- **存储链路治理 QED-071 关闭（2026-09-26）**：A 轮（数据根侧，2026-09-24）+ B 轮
  （元数据库侧）交付：`qt_books` 内容身份三列手工迁移落 `qed_test` + 磁盘重算回填 17/17
  （`inventory reconcile`）、去重/校验/交付读路径切 DB（M4：无 DB 显式报错，不静默回退岛）、
  `meta/resources/` 资源岛退役停写 + `Inventory` 类删除 + 全局反岛守护。实现中勘正 **D17**：
  `uk_qt_books_sha256` 唯一键与「同内容多书 N:1 共用」语义冲突，放宽为普通索引
  `ix_qt_books_sha256`。**生产 `qed` 库未动**：上线新模型前须先执行完整 ALTER
  （三列 + 普通索引，红线顺序「先 ALTER 后改模型」）。REQ-093 终态回执待交根仓，
  M1/M2 定义从未落盘，待用户补录或裁掉（未移交 QED-070）。六项人工/治理面遗留登记在[完成台账](completed.md) QED-071 行；执行计划与根仓请求包已按 ADR 0009 Retain 归档至 [历史基线](../history/baselines/2026-09-24-storage-json-island-retirement.md)。
- **todo 任务管理治理轮关闭（2026-09-30，QED-075）**：todo 三层分工成文（本期计划 / 普通任务轮 / 长期任务），v1.0 表逐行重审后冻结、成功标准一经评审确立不得改写（过程更新只进 plans/，守护测试机器核验）；QED-070 缺陷台账移入普通任务轮滚动承载；三类产物落位规范成文（[ADR 0011](../adr/0011-artifact-placement-hygiene.md)：`logs/` 仅服务运行产物、`tmp/` 开发临时区、重要过程数据归 `QED_DATA_ROOT`）并完成 logs/tmp 存量清扫。见[完成台账](completed.md)。
- **长期任务**：prompt 优化模块（QED-043）、来源探索与评估（QED-054，含 REQ-020①② 找得率基线
  持续采集与回执）；见[待办列表](todo.md)。

## 维护规则

- 服务实现状态、当前主线或能力归属变化时，更新本表并刷新「最后更新」日期。
- 本表不保存任务细节与未来规划（分别见 todo.md / roadmap.md）；与[系统总览](../architecture/system-overview.md)
  的静态描述不一致时，以本表当前状态为准并回修系统总览。
