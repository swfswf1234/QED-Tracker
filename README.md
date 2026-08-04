# QED-Tracker

[![CI](https://github.com/swfswf1234/QED-Tracker/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/swfswf1234/QED-Tracker/actions/workflows/ci.yml)

QED-Tracker 是一个本地优先的 PDF 获取工具，聚焦教材、习题集和 arXiv 论文。它负责搜索、下载、PDF 校验、SHA-256 去重和本地资源清单，也能通过百炼根据研究目标规划 arXiv 检索并生成可审阅的论文推荐；需要进一步处理时，再将 PDF 显式交付给相邻项目 Axiom-Flow。

项目不运行常驻服务，也不维护数据库。包内冻结的 `math-qe` 目录保存 13 门课程的 44 个资源目标，但下载能力不依赖该目录。

## 安装

需要 Python 3.12 或更高版本：

```powershell
python -m pip install -e ".[dev]"
qed-tracker config init --data-root E:/qed/dataset
qed-tracker --help
```

本地配置默认写入仓库根目录下、不纳入版本控制的 `qed-tracker.local.toml`。仓库中的 `qed-tracker.example.toml` 是完整配置示例。

## 快速使用

```powershell
# 预览并显式选择教材或习题集
qed-tracker books get "Munkres Topology"
qed-tracker books get "Munkres Topology" --pick 1

# 搜索或按 ID 下载 arXiv 论文
qed-tracker papers search "Sobolev inequality" --category math.AP --limit 10
qed-tracker papers get 2401.00001

# 根据目标生成推荐报告；模型不会自动下载
qed-tracker papers recommend "可靠的 RAG 评测方法" --profile llm-engineering --top 5
qed-tracker papers selections download <selection-id> --pick 1

# 登记和校验数据根目录内已有的 PDF
qed-tracker inventory scan E:/qed/dataset
qed-tracker inventory verify

# 默认只上传；显式 --parse 才创建 Axiom 解析任务
qed-tracker axiom push sha256:<digest>
qed-tracker axiom push sha256:<digest> --parse --page-start 1 --page-end 20
```

全局选项必须放在一级命令之前，例如 `qed-tracker --json inventory list`。

## 数据位置

```text
<data-root>/
├── books/
│   ├── inbox/
│   └── math-qe/<course-id>/
├── papers/<year>/
└── .qed-tracker/
    ├── resources/<sha256>.json
    ├── paper-selections/<selection-id>.json
    └── transfers/axiom/<sha256>.json
```

`inventory scan` 只登记数据根目录内的 PDF，不移动或删除原文件。下载先写入 `.part`，通过 PDF 结构校验后才原子落盘并登记。

0.5 内置教材来源只保留 Internet Archive、Open Library 和 Google Books。旧配置中的 `libgen`、`annas_archive`、`zlib` 必须从 `[core].sources` 或 `QED_TRACKER_SOURCES` 删除；已下载资源不受影响。

## 与 Axiom-Flow 的边界

QED-Tracker 只负责取得并登记原始 PDF。Axiom-Flow 负责不可变导入、OCR/解析、质量审阅和知识发布。两者通过 Axiom-Flow HTTP API 交接，不共享 Python 包、数据库或数据目录。

论文推荐只使用 arXiv 元数据与摘要。百炼输出是可变的相关性初筛，不代表客观论文质量；推荐证据保存在独立选择报告中，不写入资源事实。

## 文档

- [文档索引](docs/index.md)
- [系统架构](docs/architecture/system-overview.md)
- [日常操作](docs/guides/operations.md)
- [开发指南](docs/guides/development.md)
- [后续规划](docs/trackers/roadmap.md)
