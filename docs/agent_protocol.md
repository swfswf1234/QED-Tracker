# QED-Tracker Agent Protocol

> Version: 2.0
> Status: Active

## 1. Reading Order

1. `README.md`：产品边界和用户命令。
2. `docs/trackers/todos.md`：当前工作与未来规划。
3. `docs/architecture.md`：包边界和数据流。
4. 与任务对应的 `docs/design/` 文档。
5. `docs/tests.md`：验证命令。
6. 只有追溯旧决策时才阅读历史 worklog 和知识库存快照。

不得根据已删除的 0.2 数据库/API 架构恢复功能。当前运行事实以代码、测试和 `.qed-tracker/resources/*.json` 为准。

## 2. Work Loop

- 修改前说明目标、影响面和数据风险；不得隐式扫描、移动或删除数据根内 PDF。
- 来源适配器只负责搜索与解析下载地址；文件写入、续传、校验、哈希和去重必须经过通用下载与清单服务。
- 默认测试不得访问公网。来源 HTML/API 变化通过固定 fixture 和显式人工探测处理。
- 修改公开 CLI、目录 schema、资源 schema 或 Axiom 契约时，同步更新设计文档和测试。
- 非平凡变更更新 tracker 和当天 worklog。

## 3. Runtime Rules

- Python 3.12；依赖和命令入口以 `pyproject.toml` 为准。
- 个人配置使用 `qed-tracker.local.toml` 或 `QED_TRACKER_*` 环境变量。
- TLS 校验默认开启；只有用户明确配置时才允许关闭。
- 批量目录下载只接受严格题名、作者、语言和版次匹配；不确定候选必须进入人工复核。
- Axiom 推送默认只导入 PDF；只有显式 `--parse` 才可创建可能产生模型费用的任务。

## 4. Git Policy

- `main` 保持稳定；日常开发进入 `dev`，发布候选依次进入 `release` 和 `main`。
- 大改动从 `dev` 派生 `feat/*`；`release` 修复随发布进入 `main` 后必须同步回 `dev`。
- 提交前运行定向测试、完整 Pytest、Ruff、安装/CLI 冒烟和 `git diff --check`。
- 不回滚无关用户变更。
