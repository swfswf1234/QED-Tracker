# 待办列表

状态：Current
最后更新：2026-08-05

| ID | 类型 | 状态 | 事项 | 成功标准 |
| --- | --- | --- | --- | --- |
| QED-008 | Plan | 待开始 | [跨项目] 服务化：8901 API（/api/v1）+ 后台任务与轮询（需求方：QED-Engine，设计：docs/design/tracker-service.md，ADR 0001；计划：../plans/2026-08-service-and-book-download.md） | `GET /health`、只读查询同步返回、写操作全部走任务；`meta/tasks/` 落盘；并发上限 2；同 sha256 幂等复用；API/客户端单元测试通过。 |
| QED-009 | Plan | 待开始 | [跨项目] 配置与数据迁移：直读根 .env `QED_*` 变量（含 QED_DB_*）、TOML 与 `QED_TRACKER_*` 退役、数据根默认 dataset/qed-tracker/（raw/meta/tmp 布局 + 文件名规则）（需求方：QED-Engine，设计：docs/design/tracker-service.md） | 无根 .env 时最小默认值 + 尾注提醒；新下载落在 raw/ 对应类型目录；存量数据不迁移。 |
| QED-010 | Plan | 待开始 | [跨项目] CLI 转 HTTP 客户端 + 基于真实 8901 服务的冒烟测试（需求方：QED-Engine，设计：docs/design/tracker-service.md） | `qed-tracker` 命令经 8901 完成任务；启动 → 建任务 → 轮询 → 校验文件落位全链路冒烟通过；`--no-wait` 输出 task_id。 |
| QED-011 | Validation | 待开始 | 重复下载链路验证（用户约定在 QED-008~010 冒烟后执行） | 同一资源二次下载返回既有资源记录，不产生重复文件，任务幂等。 |
| QED-012 | Plan | 待开始 | [跨项目] MySQL 资源登记与状态机：qed 库 `qt_resources` 表 + QED_DB_* 直读；JSON meta/resources/ 文件状态事实 + MySQL 查询索引双写；状态机 candidate→confirmed→downloading→downloaded→approved/rejected（+failed 可重试）；llm_evaluation/catalog_ref/留痕字段（需求方：QED-Engine REQ-013，设计：docs/design/tracker-service.md） | 登记表字段完整（来源/时间/书名/中英/作者/路径/sha256/状态/评估/留痕）；先落盘后登记、失败可重放；同 sha256 幂等；无密码时降级运行。 |
| QED-013 | Plan | 待开始 | [跨项目] 书单 math-qe-v2 与 LLM 筛选评估：参照 dataset/textbooks 索引整理 13 门课程（每课程教材组 + 习题集组，优先中文版经典教材中译本），qwen 辅助书目结构化与判断宁缺勿滥；按课程批量评估任务（搜索源 → LLM 评估 → 候选落库）（需求方：QED-Engine REQ-014，设计：docs/design/tracker-service.md） | 书单 JSON 落 catalogs/；`catalog evaluate`（按课程）产出 candidate 落库（含 llm_evaluation 可审阅报告，不写资源事实）；不可得中文书登记 pending_manual；扫描补书后转 confirmed 并回归确认链路。 |
| QED-015 | Plan | 待开始 | [跨项目] 下载任务与预览端点：`POST /tasks/books/download {resource_id}` 仅 confirmed 可触发（下载中→downloaded，回填 sha256/relative_path/page_count）；`GET /resources/{id}/file` PDF 预览流（downloaded/approved 可访问）（需求方：QED-Engine REQ-013/REQ-014，设计：docs/design/tracker-service.md） | 状态迁移合法校验（非 confirmed 触发返回 409）；同 sha256 幂等复用；预览流 Content-Type/长度正确；前端可 iframe 内嵌预览。 |
| QED-016 | Plan | 待开始 | [跨项目] 验收闭环与 CLI：`POST /resources/{id}/confirm`（candidate→confirmed）、`POST /resources/{id}/approve`（downloaded→approved）、`POST /resources/{id}/reject {reason}`（candidate 或 downloaded→rejected，reason 必填，后者硬删文件 + DB 留痕）；CLI 闭环命令 catalog evaluate / resources list|show|confirm|reject|approve / books download（需求方：QED-Engine REQ-011/REQ-013，设计：docs/design/tracker-service.md） | 状态机非法迁移返回 409；拒绝必填原因；已拒资源 DB 记录保留（reject_reason 非空）且同源候选不再推荐；CLI 无前端可走完整闭环。 |
| QED-014 | Validation | 待开始 | 联调冒烟与回执：真实 8901 全链路（评估→确认→下载→验收/删除→登记→qed CLI/8903 前端展示） | 8901 服务 + qed CLI + QED-Engine 下载工作台数据贯通；根仓库 todo REQ-004/REQ-011/REQ-013/REQ-014 收到回执。 |

`QED-005` 当前阻塞证据：环境中未设置 `QED_TRACKER_LLM_API_KEY` 或 `DASHSCOPE_API_KEY`。恢复条件是设置其中之一并允许受限网络调用；责任位置为本地人工验收。注：QED-009（配置统一，直读根 `.env` `QWEN_API_KEY`）落地后自动满足恢复条件，无需再设 `DASHSCOPE_API_KEY`。

| ID | 类型 | 状态 | 事项 | 成功标准 |
| --- | --- | --- | --- | --- |
| QED-005 | Validation | Blocked | 真实百炼与 arXiv 冒烟 | 配置模型密钥并获准联网后，预览推荐并从同一报告下载一篇临时 PDF。 |

规则：任务按类型分类（Plan / Defect / Validation / Candidate），状态只允许 `待开始 / 进行中 / 已完成 / 阻塞`；阻塞必须声明证据、恢复条件和责任位置。
