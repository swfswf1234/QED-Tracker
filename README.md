# QED-Tracker

QED-Tracker 是一个本地优先的 PDF 获取组件，聚焦教材、习题集和 arXiv 论文。它负责发现、下载、PDF 校验、SHA-256 去重和本地资源清单，也能通过百炼根据研究目标规划 arXiv 检索并生成可审阅的论文推荐；需要进一步处理时，再将 PDF 显式交付给相邻项目 Axiom-Flow。

项目以 8901 HTTP 服务（`/api/v1`）运行，写操作（下载、评估、推荐）经后台任务执行并以任务状态轮询暴露；资源事实以单资源 JSON 存于数据根，MySQL 五层登记索引（`qed_domain`/`qed_course` 共享 + `qt_knowledge`/`qt_books`/`qt_sources` 私有）为查询/展示索引（无密码时降级运行）。包内冻结的 `math-qe` 目录保存 13 门课程的教材与习题集目标，但下载能力不依赖该目录。

## 安装

需要 Python 3.12 或更高版本：

```powershell
python -m pip install -e ".[dev]"
qed-tracker config show
qed-tracker --help
```

配置读取优先级：真实环境变量 → 本仓库 `.env`（`QED_API_SELECT=local` 默认、`API_KEY`、
`QED_LLM_GATEWAY_URL`、`QED_MODEL`、`QED_DB_*`、`QED_TRACKER_PORT`）→ 根仓库 `.env`（兜底）→
内置最小默认值。密钥为唯一变量 `API_KEY`（QED-038：逐厂商 key 别名已取消，无回退）；模型调用
默认 `local` 模式直连 dashscope qwen，可切 `qed-engine` 经 8900 网关 `/llm/text`。本地 TOML 与
`QED_TRACKER_*` 环境变量已退役。

## 快速使用

```powershell
# 启动 8901 API 服务（后台任务 + MySQL 登记索引；写操作经任务轮询）
qed-tracker serve

# 或使用仓库生命周期脚本（start/stop/restart/status，8900 控制中心黑盒调用）
python scripts/qed_tracker_service.py start --wait
python scripts/qed_tracker_service.py status
python scripts/qed_tracker_service.py stop
# 预览并显式选择教材或习题集
qed-tracker books get "Munkres Topology"
qed-tracker books get "Munkres Topology" --pick 1

# 搜索或按 ID 下载 arXiv 论文
qed-tracker papers search "Sobolev inequality" --category math.AP --limit 10
qed-tracker papers get 2401.00001

# 根据目标生成推荐报告；模型不会自动下载
qed-tracker papers recommend "可靠的 RAG 评测方法" --profile llm-engineering --top 5
qed-tracker papers selections download <selection-id> --pick 1

# 查看与校验 DB 书目（qt_books 内容身份三列 vs 磁盘重算）
qed-tracker inventory list
qed-tracker inventory verify
# 磁盘重算回填/对账三列（QED-071 B 轮，需数据库）
qed-tracker inventory reconcile

# 主链路：课程梳理与教材条目（课程学习主流程，与 evaluate 平行；需要 qed 库连接）
qed-tracker courses list
qed-tracker courses show math_analysis
qed-tracker mainline new --course math_analysis --title "数学分析原理" --author Rudin
qed-tracker mainline review <knowledge_id>
# 教程级取书：经 8901 五阶段链（检索→确认→下载→机器验收→登记 owned）
qed-tracker mainline download <knowledge_id>
# 只读复核（重算 sha/页数比对）
qed-tracker mainline verify <knowledge_id>
# 渠道有效性汇总
qed-tracker mainline channels

# 手动知识导入（标准答案 → 系统；需要 8901 服务在线）
qed-tracker domains import docs/knowledge/math-advanced.json
qed-tracker knowledge import docs/knowledge/math-advanced/math_analysis.json
# 手动下载导入（外部 PDF → 校验 → 拷入数据根 raw/ → mark_owned 登记 owned）
qed-tracker books import <book_id> "C:/downloads/textbook.pdf" --target "raw/math-advanced/math_analysis/斯图尔特微积分.pdf"

# 默认只上传；显式 --parse 才创建 Axiom 解析任务（仅接受 book_id，需 holding=owned 且文件在位）
qed-tracker axiom push <book_id>
qed-tracker axiom push <book_id> --parse --page-start 1 --page-end 20
```

全局选项必须放在一级命令之前，例如 `qed-tracker --json inventory list`。

## 数据位置

数据根为共享树 `<QED_DATA_ROOT>`（默认根仓库 `dataset/`，ARCH-019；根仓 ADR 0018 顶层白名单
`raw/ parsed/ tmp/ backups/`）：

```text
<data-root>/
├── raw/<domain-id>/<course-id>/             # 教材/习题成品（唯一被外部读取区）
│   └── _general/                            # 领域通用桶：手动下载、论文 papers/<year>/
└── tmp/qed-tracker/downloads/               # 下载中间态 *.download / *.download.part（终态不保留）
```

内容身份（sha256/size_bytes/page_count）只存 MySQL `qt_books` 三列（QED-071 B 轮，
`qed-tracker/meta/resources/` 资源 JSON 岛已退役，不再落盘）；后台任务与选择报告同样在
MySQL（`qt_tasks`/`qt_selections`）。本地 PDF 转正走 `books import <book_id> <file>`，
批量回填/对账走 `inventory reconcile`（不再有原地批量扫描登记命令，也不隐式扫描用户 PDF）。
自动取书先写入中间态，通过机器验收（PDF 结构/页数/大小硬门槛）后才原子落盘 `raw/`
并经 `mark_owned` 登记（同一提交写内容身份三列）。

内置教材来源为 Internet Archive、Open Library、Google Books 与 libgen_li（libgen_li 仅发现与
提供人工下载方案，不自动写文件）；不依赖旧配置。

## 与 Axiom-Flow 的边界

QED-Tracker 只负责取得并登记原始 PDF。Axiom-Flow 负责不可变导入、OCR/解析、质量审阅和知识发布。两者通过 Axiom-Flow HTTP API 交接，不共享 Python 包、数据库或数据目录。

论文推荐只使用 arXiv 元数据与摘要。百炼输出是可变的相关性初筛，不代表客观论文质量；推荐证据保存在独立选择报告中，不写入资源事实。

## 文档

- [文档索引](docs/index.md)
- [系统架构](docs/architecture/system-overview.md)
- [操作指南](docs/guides/operations.md)
- [开发指南](docs/guides/development.md)
- [后续规划](docs/trackers/roadmap.md)
