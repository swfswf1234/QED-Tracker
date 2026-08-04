# 待办列表

状态：Current
最后更新：2026-08-04

| ID | 类型 | 状态 | 事项 | 成功标准 |
| --- | --- | --- | --- | --- |
| QED-005 | Validation | Blocked | 真实百炼与 arXiv 冒烟 | 配置模型密钥并获准联网后，预览推荐并从同一报告下载一篇临时 PDF。 |

`QED-005` 当前阻塞证据：环境中未设置 `QED_TRACKER_LLM_API_KEY` 或 `DASHSCOPE_API_KEY`。恢复条件是设置其中之一并允许受限网络调用；责任位置为本地人工验收。

| ID | 类型 | 状态 | 事项 | 成功标准 |
| --- | --- | --- | --- | --- |
| QED-008 | Plan | 待开始 | [跨项目] 服务化：8901 API（/api/v1）+ 后台任务与轮询（需求方：QED-Engine，设计：docs/design/tracker-service.md，ADR 0001） | `GET /health`、只读查询同步返回、写操作全部走任务；`meta/tasks/` 落盘；并发上限 2；同 sha256 幂等复用；API/客户端单元测试通过。 |
| QED-009 | Plan | 待开始 | [跨项目] 配置与数据迁移：直读根 .env `QED_*` 变量、TOML 与 `QED_TRACKER_*` 退役、数据根默认 dataset/qed-tracker/（raw/meta/tmp 布局 + 文件名规则）（需求方：QED-Engine，设计：docs/design/tracker-service.md） | 无根 .env 时最小默认值 + 尾注提醒；新下载落在 raw/ 对应类型目录；存量数据不迁移。 |
| QED-010 | Plan | 待开始 | [跨项目] CLI 转 HTTP 客户端 + 基于真实 8901 服务的冒烟测试（需求方：QED-Engine，设计：docs/design/tracker-service.md） | `qed-tracker` 命令经 8901 完成任务；启动 → 建任务 → 轮询 → 校验文件落位全链路冒烟通过；`--no-wait` 输出 task_id。 |
| QED-011 | Validation | 待开始 | 重复下载链路验证（用户约定在 QED-008~010 冒烟后执行） | 同一资源二次下载返回既有资源记录，不产生重复文件，任务幂等。 |

规则：任务按类型分类（Plan / Defect / Validation / Candidate），状态只允许 `待开始 / 进行中 / 已完成 / 阻塞`；阻塞必须声明证据、恢复条件和责任位置。
