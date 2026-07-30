# Axiom-Flow 交接设计

设计状态：Accepted
实现状态：Implemented
最后更新：2026-07-30
外部契约：Axiom-Flow 0.3 HTTP API
关联代码：`src/qed_tracker/axiom.py`、`src/qed_tracker/cli.py`
关联测试：`tests/test_axiom.py`、`tests/test_cli_architecture.py`

## 边界

QED-Tracker 不导入 Axiom-Flow Python 包，不访问其 MySQL，也不写入其数据目录。交接只调用 HTTP API：

1. `GET /api/v1/health`
2. `POST /api/v1/documents`，multipart 字段名为 `file`，MIME 类型为 `application/pdf`
3. 仅在显式指定 `--parse` 时调用 `POST /api/v1/documents/{id}/parse-jobs`

QED-Tracker 在上传前必须找到已登记资源和实际 PDF。Axiom-Flow 按 PDF 内容哈希处理重复导入，并返回文档的 `id`、文件名、内容哈希、页数、状态和创建时间。

## 解析请求

默认 `axiom push` 只执行健康检查和上传，不创建解析任务。显式 `--parse` 后，客户端向解析端点发送 JSON；`page_start` 和 `page_end` 仅在用户提供时出现，页码从 1 开始且两端均包含。

CLI 要求页码参数与 `--parse` 同时使用。Axiom-Flow 继续负责页码上界、区间顺序、上传大小、任务幂等、预算和人工审阅规则，QED-Tracker 不复制或绕过这些约束。

## 传输记录

成功上传后，QED-Tracker 将结果写入 `.qed-tracker/transfers/axiom/<sha256>.json`，包含：

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
