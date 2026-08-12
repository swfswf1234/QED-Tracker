# Axiom-Flow API 接口文档（QED-Tracker 消费面）

设计状态：Accepted
实现状态：Implemented
最后更新：2026-08-12
外部契约：Axiom-Flow 0.3 `/api/v1` HTTP API（事实源：Axiom-Flow 仓库 api/main.py 与 api/schemas.py）
关联代码：`src/qed_tracker/axiom.py`、`src/qed_tracker/cli.py`
关联测试：`tests/test_axiom.py`、`tests/test_cli_architecture.py`
关联 ADR：—
交互对象：Axiom-Flow（API 提供方）、QED-Engine（跨项目契约，见 [service-contracts.md](../../../docs/design/service-contracts.md) 与 [dataset-conventions.md](../../../docs/design/dataset-conventions.md)）

> 本文是 **QED-Tracker 消费 Axiom-Flow API 的接口契约文档**：定义本仓库实际调用的端点、
> 请求/响应、错误语义与交互边界。**Axiom-Flow 全量 API 的事实源在其仓库**
> （api/main.py + docs/design/web-workbench.md，位于 Axiom-Flow 仓库），本文件只记录消费面契约，
> 不复制全量端点，避免双源漂移。跨项目事实（端口、dataset、qed 库）只链接根仓库契约。

## 端点契约（QED-Tracker 消费面）

QED-Tracker 客户端（`src/qed_tracker/axiom.py`）只消费以下 3 个端点。基准地址默认
`http://127.0.0.1:8902`（由 `QED_AXIOM_URL` 配置覆盖）。

### 1. GET /api/v1/health — 健康检查

| 项 | 内容 |
| --- | --- |
| 用途 | 上传前确认 Axiom-Flow 在线 |
| 请求 | 无 |
| 响应 200 | `{"status": "ok", "version": "0.3.0"}` |
| 调用处 | `AxiomClient.health()`（`axiom push` 第一步） |

### 2. POST /api/v1/documents — 上传 PDF

| 项 | 内容 |
| --- | --- |
| 用途 | 交付已登记 PDF（multipart） |
| 请求 | `file` 字段（multipart），MIME `application/pdf`；仅接受 `.pdf` 后缀 |
| 响应 201 | `DocumentResponse`：`{id, filename, content_hash, page_count, status, created_at}` |
| 错误 | 400（非 PDF / 无法导入）、413（超过大小限制，默认 `max_upload_bytes`）、422（校验失败） |
| 幂等 | Axiom-Flow 按 PDF 内容哈希处理重复导入（返回既有文档，不重复入库） |
| 调用处 | `AxiomClient.push()`；上传前必须已找到登记资源与实际 PDF |

### 3. POST /api/v1/documents/{document_id}/parse-jobs — 创建解析任务

| 项 | 内容 |
| --- | --- |
| 用途 | 显式创建解析任务（默认不调用，仅 `--parse` 时） |
| 请求体 | `{"page_start": 1, "page_end": null}`（可选；页码从 1 开始，两端均包含；仅用户提供时出现） |
| 响应 202 | `CommandResponse`：`{"job": {...}, "created": true\|false}` |
| 错误 | 404（文档不存在）、409（非法状态）、422（校验失败） |
| 边界 | 页码上界、任务幂等、预算与人工审阅规则由 Axiom-Flow 负责，QED-Tracker 不复制或绕过 |
| 调用处 | `AxiomClient.push(parse=True)`；CLI 要求页码参数与 `--parse` 同时使用 |

### 统一错误结构

所有错误响应：`{"error": {"code": "<code>", "message": "<摘要>", "details": {...}}}`。
本仓库客户端将失败包装为 `AxiomError`（带 HTTP 状态码与 ≤500 字响应摘要）。

## Axiom-Flow 全量 API 一览（事实源链接）

Axiom-Flow `/api/v1` 还提供文档查询、解析运行、页面/知识点审阅、工作簿、评测等 **30+ 端点**。
本仓库不使用，如需对接以 Axiom-Flow 侧为准：

- Axiom-Flow `docs/design/web-workbench.md`（`/api/v1` 契约与任务轮询语义）
- Axiom-Flow 源码 src/axiom_flow/api/main.py（端点实现，位于 Axiom-Flow 仓库，不在本仓库）
- Axiom-Flow 源码 src/axiom_flow/api/schemas.py（请求/响应模型，位于 Axiom-Flow 仓库，不在本仓库）

## 交互规范（与 Axiom-Flow / QED-Engine）

| 边界 | 约定 |
| --- | --- |
| 端口 | Axiom-Flow 默认 `8902`（根仓库 ADR 0002；保留 8000 兼容） |
| 数据边界 | QED-Tracker 不导入 Axiom-Flow Python 包、不访问其 MySQL（`af_*` 表）、不写入其数据目录；交接只走 HTTP API |
| dataset | Axiom-Flow 解析产物指向根仓库 `dataset/axiom-flow/parsed/`（Phase 3，ALN-003）；QED-Tracker 移交 PDF 见 [主链路设计](main-line-curriculum.md) |
| qed 库 | 共享实例、表命名空间隔离（`qt_*` / `af_*`），见 [数据库设计](database-schema-ownership.md) |
| 前端入口 | 8903 前端只连 8900 网关（ADR 0007），浏览器不直连 8902 |

## 传输记录（客户端行为事实）

成功上传后，本仓库将结果写入 `meta/transfers/axiom/<sha256>.json`，包含：

- `schema_version`、QED `resource_id` 和 Axiom 服务 URL；
- Axiom `document_id`、完整文档响应和 UTC 推送时间；
- 显式解析成功时的 `parse_command` 响应。

传输记录是下游交接状态，不得写入单资源 JSON，也不得改变 PDF 的 `resource_id`。

## 失败语义

- 健康检查、连接、上传、服务限制或解析提交失败均返回运行错误和有限长度的 HTTP 摘要。
- 上传失败时不写成功传输记录，也不修改本地资源事实。
- 上传成功而解析提交失败时，保留 Axiom 已导入文档，将 `parse_error` 写入传输记录，然后向 CLI 返回失败。
- 工具不自动删除已上传文档，也不自动重试可能产生费用的解析任务。
- 再次推送同一资源依赖 Axiom 的内容哈希幂等语义，本项目不通过共享状态实现下游去重。
