# QED-Tracker 服务接口设计（tracker-service）

设计状态：Draft
实现状态：Not Started
最后更新：2026-08-04
需求方：QED-Engine
关联代码：src/qed_tracker/api/（服务化轮新增，尚未实现）
关联测试：服务化轮新增 API（TestClient）与客户端（MockTransport）测试、8901 真实服务冒烟测试
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)

## 背景

QED-Engine 按 [ADR 0002](../../../docs/adr/0002-frontend-and-port-centralization.md) 统一全局
端口段：QED-Tracker 服务端口 8901。统一 CLI 与前端需要经 HTTP 调用本项目的搜索、下载、校验、
登记与 Axiom 推送能力；长操作（大 PDF 下载、百炼推荐）不能阻塞请求，须以后台任务 + 状态轮询
暴露。跨项目契约见根仓库[服务契约](../../../docs/design/service-contracts.md)与
[dataset 目录约定](../../../docs/design/dataset-conventions.md)。

## 所需变更

### 服务（src/qed_tracker/api/，端口 8901，前缀 `/api/v1`）

| 方法/路径 | 行为 |
| --- | --- |
| `GET /health` | 存活检查 |
| `GET /books/search?q=&source=&limit=` | 同步：教材候选搜索 |
| `GET /papers/search?q=&category=&author=&limit=` | 同步：arXiv 候选搜索 |
| `GET /resources?kind=`、`GET /resources/{sha256}` | 同步：资源清单查询（前端展示） |
| `GET /selections`、`GET /selections/{id}` | 同步：论文选择报告 |
| `GET /catalogs`、`GET /catalogs/{id}` | 同步：冻结目录与目标 |
| `POST /tasks/books/download` | 后台任务：教材/习题下载 |
| `POST /tasks/papers/download` | 后台任务：论文下载 |
| `POST /tasks/recommend` | 后台任务：百炼论文推荐 |
| `POST /tasks/catalog/run` | 后台任务：冻结目录批处理 |
| `POST /tasks/scan` | 后台任务：数据根扫描登记 |
| `POST /tasks/axiom/push` | 后台任务：Axiom 上传（默认不解析） |
| `GET /tasks`、`GET /tasks/{id}` | 任务列表与状态轮询 |

任务模型（落盘 `meta/tasks/<task-id>.json`）：`{task_id, type, status, progress, created_at,
updated_at, params, result, error}`；`result` 含 `resource_id`、`relative_path`、
`selection_id` 等，供前端"任务 → 文件"跳转。并发上限 2；同 sha256 幂等复用。

### 配置（`config.py`）

- 直读根 `.env` 的 `QED_*` 变量：`QWEN_API_KEY`（百炼）、`QED_MODEL`、`QED_AXIOM_URL`
  （默认 `http://127.0.0.1:8902`）、`QED_TRACKER_PORT`（默认 8901）。
- 本地 TOML 与 `QED_TRACKER_*` 环境变量退役；无配置时内置最小默认值 + 启动尾注提醒。
- 根 `.env` 由统一 CLI `qed` 启动服务时注入；独立启动无 `.env` 时降级运行。

### 数据布局（数据根默认 `dataset/qed-tracker/`）

```text
dataset/qed-tracker/
├── raw/books/{inbox,math-qe/<course-id>}/        # 教材
├── raw/exercises/inbox/                          # 习题集（kind=exercise 独立）
├── raw/papers/<year>/                            # 论文
├── meta/{resources,selections,transfers,tasks}/  # JSON 状态
└── tmp/downloads/<task-id>.part                  # 下载临时区（原子落盘后清理）
```

文件名规则：`<slug>_<sha256前8>.pdf`（论文为 `<arxiv-id>_<sha256前8>.pdf`）。
存量数据不迁移；`.qed-tracker/` 状态目录迁移到 `meta/`。

### CLI（`cli.py`）

转 HTTP 客户端：默认等待任务完成；`--no-wait` 输出 `task_id`；`--json` 保留。独立脚本入口
`qed-tracker` 在统一 CLI `qed` 承接后退役（见根仓库计划 Phase 1/2）。

## 接口/契约影响

- Axiom-Flow 地址默认改为 `http://127.0.0.1:8902`（现状 8000）。
- `QED_TRACKER_LLM_API_KEY` / `DASHSCOPE_API_KEY` 读取路径退役，改读 `QWEN_API_KEY`。
- 资源 schema 不变（`file.relative_path` 相对数据根）；目录结构变化（`books/` → `raw/books/`）
  属内部布局，资源 JSON 记录随新路径生成。

## 验证方式

1. 单元：API 端点（TestClient，mock 应用层）与客户端（httpx MockTransport）离线测试。
2. 冒烟：真实启动 8901 服务 → 创建下载任务 → 轮询 → 校验 PDF 落位
   `dataset/qed-tracker/raw/books/inbox/` 且资源登记、任务记录完整。
3. 重复下载链路：同一资源二次下载返回既有记录（sha256 幂等），不产生重复文件。
4. 降级：无根 `.env` 时服务与 CLI 正常启动并输出尾注提醒。

## 回执条件

- 本设计转 Accepted 且 Phase 2 实现通过 QED-Tracker 全量门禁（`pytest tests -q`、ruff、
  `tests/test_documentation.py`、8901 冒烟）。
- 根仓库 `docs/trackers/todo.md` 收到完成回执，链接本文件与 QED-Tracker 任务 ID。
