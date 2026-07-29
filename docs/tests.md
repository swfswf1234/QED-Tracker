# 测试指南

## 本地门禁

```powershell
python -m pip install -e ".[dev]"
python -m pytest tests -q
python -m ruff check src tests
python -m pip install .
qed-tracker --version
qed-tracker --json catalog list
git diff --check
```

默认测试完全离线：HTTP 使用 `httpx.MockTransport`，PDF 由 `pypdf` 在临时目录生成，禁止读取或修改 `E:/qed/dataset`。

## 覆盖范围

- TOML、环境变量和命令行配置优先级。
- 44 项冻结目录唯一性及严格匹配边界。
- 来源 HTML/API 归一化、metadata-only 标记和故障隔离。
- 完整下载、Range 续传、非 PDF 拒绝、结构校验、临时文件和原子落盘。
- SHA-256 登记、去重、扫描、核验和确定性 JSONL。
- CLI 命令树、退出码和无旧依赖架构约束。
- Axiom 健康检查、幂等上传、HTTP 错误、默认不解析和显式页码范围。

真实来源连通性属于人工操作验证，不应成为 CI 门禁；运行时失败必须保留来源名和错误摘要，其他来源继续执行。
