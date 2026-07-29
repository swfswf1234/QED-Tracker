# QED-Tracker 0.3

QED-Tracker 是一个本地优先的 PDF 获取工具，只负责两类输入：教材/习题集和 arXiv 论文。下载文件经过 PDF 校验、SHA-256 去重并登记为 JSON 资源；需要解析时，再显式推送给相邻的 Axiom-Flow。

项目不再提供数据库、Web API、GitHub/RSS 跟踪或官方文档镜像。数学 QE 规划已经完成，其 13 门课程和 44 个资源目标作为冻结目录随包保留，不再与下载核心耦合。

## 安装

需要 Python 3.12：

```powershell
python -m pip install -e ".[dev]"
qed-tracker config init --data-root E:/qed/dataset
qed-tracker --help
```

本地配置默认写入 `qed-tracker.local.toml`，该文件不会提交。也可以复制 `qed-tracker.example.toml`，或用 `QED_TRACKER_*` 环境变量覆盖配置。

## 常用命令

```powershell
# 教材与习题集
qed-tracker books search "Munkres Topology"
qed-tracker books get "Munkres Topology" --pick 1
qed-tracker books fetch-url https://example.org/book.pdf --title "Book Title"

# arXiv 论文
qed-tracker papers search "Sobolev inequality" --category math.AP --limit 10
qed-tracker papers search --category math.CA --download 1
qed-tracker papers get 2401.00001 https://arxiv.org/abs/2402.00002

# 冻结目录：默认只预览；--download 只下载严格匹配项
qed-tracker catalog list
qed-tracker catalog show math-qe
qed-tracker catalog run math-qe --course 03 --download --report topology.md

# 原地登记和校验已有 PDF
qed-tracker inventory scan E:/qed/dataset
qed-tracker inventory verify
qed-tracker inventory export

# 显式交付给 Axiom-Flow；默认只导入 PDF
qed-tracker axiom push sha256:<digest>
qed-tracker axiom push sha256:<digest> --parse --page-start 1 --page-end 20
```

全局 `--json` 必须写在一级命令前，例如 `qed-tracker --json inventory list`。

退出码约定：`0` 成功，`2` 参数或配置冲突，`3` 没有可用候选，`4` 批处理或完整性检查部分失败，`5` 下载、文件或 Axiom 等运行错误。

## 数据布局

```text
<data-root>/
├── books/
│   ├── inbox/
│   └── math-qe/<course-id>/
├── papers/<year>/
└── .qed-tracker/
    ├── resources/<sha256>.json
    ├── manifest.jsonl
    └── transfers/axiom/<sha256>.json
```

现有 PDF 可在原目录登记；`inventory scan` 不移动或删除文件。正式资源只有在 PDF 结构校验通过后才会写入清单，下载过程先写 `.part`，成功后原子落盘。

## 与 Axiom-Flow 的边界

QED-Tracker 负责发现、下载、校验和来源记录。Axiom-Flow 负责不可变导入、OCR/解析、质量审阅和知识发布。两者只通过 Axiom-Flow HTTP API 交接 PDF，不共享数据库；`--parse` 是唯一由本工具创建解析任务的入口。

详细设计见 [系统架构](docs/architecture.md)、[下载来源](docs/design/download_sources.md)、[Axiom 交接](docs/design/axiom_handoff.md)和[测试指南](docs/tests.md)。
