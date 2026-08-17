# QED-Tracker

QED-Tracker 是一个本地优先的 PDF 获取组件，聚焦教材、习题集和 arXiv 论文。它负责发现、下载、PDF 校验、SHA-256 去重和本地资源清单，也能通过百炼根据研究目标规划 arXiv 检索并生成可审阅的论文推荐；需要进一步处理时，再将 PDF 显式交付给相邻项目 Axiom-Flow。

项目以 8901 HTTP 服务（`/api/v1`）运行，写操作（下载、评估、推荐）经后台任务执行并以任务状态轮询暴露；资源事实以单资源 JSON 存于数据根，MySQL `qt_resources` 为查询/展示索引（无密码时降级运行）。包内冻结的 `math-qe` 目录保存 13 门课程的教材与习题集目标，但下载能力不依赖该目录。

## 安装

需要 Python 3.12 或更高版本：

```powershell
python -m pip install -e ".[dev]"
qed-tracker config show
qed-tracker --help
```

配置直读根仓库 `.env` 的 `QED_*` 变量（`QWEN_API_KEY`、`QED_MODEL`、`QED_DB_*` 等），
本地 TOML 与 `QED_TRACKER_*` 环境变量已退役；无根 `.env` 时使用内置最小默认值并输出尾注提醒。

## 快速使用

```powershell
# 启动 8901 API 服务（后台任务 + MySQL 登记索引；写操作经任务轮询）
qed-tracker serve

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

# 主链路：课程梳理与教材条目（课程学习主流程，与 evaluate 平行；需要 qed 库连接）
qed-tracker courses list
qed-tracker courses show 01_math_analysis
qed-tracker mainline new --course 01_math_analysis --title "数学分析原理" --author Rudin
qed-tracker mainline review <knowledge_id>
qed-tracker mainline download <knowledge_id>
# 验收通过 → 复制移交根仓库 dataset/qed-tracker/
qed-tracker mainline approve <knowledge_id>
# 一次性存量迁移（math.json + 旧三表 → 五表；幂等可重放，--drop-legacy 才删旧表）
qed-tracker migrate

# 默认只上传；显式 --parse 才创建 Axiom 解析任务
qed-tracker axiom push sha256:<digest>
qed-tracker axiom push sha256:<digest> --parse --page-start 1 --page-end 20
```

全局选项必须放在一级命令之前，例如 `qed-tracker --json inventory list`。

## 数据位置

```text
<data-root>/
├── raw/
│   ├── books/{inbox,math-qe/<course-id>}/   # 教材
│   ├── exercises/inbox/                     # 习题集
│   └── papers/<year>/                       # 论文
├── meta/
│   ├── resources/<sha256>.json              # 单资源事实源
│   ├── main-line/<course_id>/<entry_id>.json # 主链路教材条目（五要素，独立于资源清单）
│   ├── selections/<selection-id>.json       # 论文选择报告
│   ├── transfers/axiom/<sha256>.json        # Axiom 传输记录
│   └── tasks/<task-id>.json                 # 后台任务状态
└── tmp/downloads/<task-id>.part             # 下载临时区
```

默认数据根为 `dataset/qed-tracker/`。`inventory scan` 只登记数据根目录内的 PDF，不移动或删除
原文件。下载先写入 `.part`，通过 PDF 结构校验后才原子落盘并登记（随后双写 MySQL 查询索引）。

内置教材来源为 Internet Archive、Open Library、Google Books 与 libgen_li（libgen_li 仅发现与
提供人工下载方案，不自动写文件）；不依赖旧配置。

## 与 Axiom-Flow 的边界

QED-Tracker 只负责取得并登记原始 PDF。Axiom-Flow 负责不可变导入、OCR/解析、质量审阅和知识发布。两者通过 Axiom-Flow HTTP API 交接，不共享 Python 包、数据库或数据目录。

论文推荐只使用 arXiv 元数据与摘要。百炼输出是可变的相关性初筛，不代表客观论文质量；推荐证据保存在独立选择报告中，不写入资源事实。

## 文档

- [文档索引](docs/index.md)
- [系统架构](docs/architecture/system-overview.md)
- [日常操作](docs/guides/operations.md)
- [开发指南](docs/guides/development.md)
- [后续规划](docs/trackers/roadmap.md)
