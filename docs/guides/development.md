# 开发指南

状态：Current
最后更新：2026-08-12

## 当前事实来源

按以下顺序定位信息：

1. [README](../../README.md)：产品边界和首次使用。
2. [文档索引](../index.md)：当前架构、设计、指南和路线图入口。
3. [待办列表](../trackers/todo.md)：当前计划、缺陷和外部验收阻塞。
4. 代码、测试和包内目录数据：最终运行事实。

历史资料只用于追溯，不得作为当前实现依据。公共 CLI、配置、目录 schema、资源 schema 或 Axiom 契约发生变化时，必须同步更新当前文档和测试。

## 安装与依赖

Python 版本和依赖以 `pyproject.toml` 为唯一事实源：

```powershell
python -m pip install -e ".[dev]"
```

配置直读根仓库 `.env` 的 `QED_*` 变量，无根 `.env` 时使用内置最小默认值。

## 分支与提交

- `release` 用于日常开发，较大改动从它派生 `feat/*`。
- 发布候选从 `release` 合入 `main`。
- `main` 上的修复发布后必须同步回 `release`。
- 提交保持单一目的，不回滚无关用户改动；过程由 Git 记录，不新增逐日 worklog。

## 实现约束

- 来源适配器只搜索和解析下载地址，文件写入、重试、校验、哈希及去重必须经过通用服务。
- 默认测试不得访问公网。来源协议变化使用固定 fixture 覆盖，真实连通性由人工检查。
- 测试只能使用临时目录，禁止读取或修改实际数据根。
- 不得隐式扫描、移动或删除数据根内的 PDF。
- TLS 校验默认开启，只能由用户显式配置关闭。
- 批量目录下载必须保持严格匹配；不确定候选不得自动落盘。
- Axiom 上传默认不解析，只有显式 `--parse` 才能创建可能产生费用的任务。
- 论文推荐测试必须使用假顾问或 `httpx.MockTransport`，CI 不读取模型密钥、不访问 arXiv，也不把模型评分写入资源事实。
- 主链路（`courses`/`mainline`）：教材条目独立存储于 `meta/main-line/`（与资源清单解耦）；
  LLM 预填只生成可审阅评价，不写资源事实；下载/校验/哈希仍走通用服务；验收（approve）采用
  **复制 + 登记同步**移交根仓库 `dataset/qed-tracker/`，不移动临时区文件；主链路测试必须使用
  假顾问或 `httpx.MockTransport`，不访问公网、不读取真实数据根。

## 验证门禁

安装开发依赖后运行：

```powershell
python -m pytest tests -q
python -m ruff check src tests
qed-tracker --version
qed-tracker --json catalog list
git diff --check
git diff --cached --check
```

测试覆盖配置优先级、目录唯一性和匹配边界、来源归一化、可靠下载、资源登记与校验、论文推荐与报告重放、CLI 命令树和退出码，以及 Axiom 的上传与可选解析。真实来源和模型在线可用性不作为 CI 门禁；人工检查应记录运行时间、来源、模型、结果和错误摘要。

wheel 打包验证由 GitHub Actions 执行（本地不构建，避免产生 build/、dist/、egg-info 等产物）。

GitHub Actions 在 `release` 和 `main` 上执行相同的 Python 3.12 测试、Ruff、wheel、CLI 冒烟与 diff 门禁；任一分支失败都必须停止后续晋级。
