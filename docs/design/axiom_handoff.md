# Axiom-Flow 交接契约

## 边界

QED-Tracker 不导入 Axiom Python 包、不访问其 MySQL，也不写 Axiom 数据目录。交接只调用 Axiom-Flow 0.3 HTTP API：

1. `GET /api/v1/health`
2. `POST /api/v1/documents`，multipart 字段名为 `file`
3. 仅显式 `--parse` 时调用 `POST /api/v1/documents/{id}/parse-jobs`

Axiom 按 PDF 内容哈希保证重复上传返回同一文档。QED-Tracker 保存 `document_id`、服务 URL、时间和可选解析命令结果，但不把下游状态混入资源事实。

## 失败处理

- 健康检查、连接、上传、413 限制或解析任务失败均返回非零退出码和 HTTP 摘要。
- 上传成功而解析任务失败时，保留 Axiom 已导入文档，不自动删除或重试产生费用的任务。
- `page_start`/`page_end` 只随显式解析传递；默认 push 不产生模型调用。
- QED-Tracker 不绕过 Axiom 的文件大小、页码、预算、幂等或人工审阅规则。
