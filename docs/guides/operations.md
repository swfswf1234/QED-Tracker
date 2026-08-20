# 日常操作

状态：Current
最后更新：2026-08-20

## 配置

安装开发版本并查看生效配置：

```powershell
python -m pip install -e ".[dev]"
qed-tracker config show
```

配置读取优先级：真实环境变量 → 本仓库 `.env`（自身配置）→ 根仓库 `.env`（兜底）→ 内置最小
默认值。本仓库 `.env` 模板（密钥可留空，由根仓库 `.env` 兜底；`API_KEY` 为**唯一密钥变量**
（逐厂商 key 已取消），`DASHSCOPE_API_KEY` 为兼容别名）：

```dotenv
# 模型模式：local=直连 dashscope qwen（默认）；qed-engine=经 8900 网关 /llm/text（不接触密钥）
QED_API_SELECT=local
API_KEY=
QED_LLM_GATEWAY_URL=http://127.0.0.1:8900
QED_MODEL=qwen-plus
QED_DB_HOST=127.0.0.1
QED_DB_PORT=3306
QED_DB_NAME=qed
QED_DB_USER=root
QED_DB_PASSWORD=
QED_TRACKER_PORT=8901
```

既有非密钥私有配置（`QED_AXIOM_URL`、`QED_TRACKER_URL`、`QED_PROXY`、`QED_TIMEOUT_SECONDS`、
`QED_RETRIES`、`QED_TLS_VERIFY`、`QED_SOURCES` 等）继续由自身 `.env` 承载。无任何 `.env` 时使用
内置最小默认值，启动时输出尾注提醒。数据根默认 `dataset/qed-tracker/`，可用全局 `--data-root`
覆盖。

TLS 校验默认开启。代理、超时、重试和 Axiom URL 由 `QED_*` 变量或内置默认值提供；密钥只经
`.env` 提供，不得写入任何本地文件。

## 工作台服务

```powershell
qed-tracker serve --port 8901
```

`serve` 启动工作台 API（默认 `127.0.0.1:8901`，即 `QED_TRACKER_PORT`）。独立启动时自动从
当前目录向上查找根 `.env` 并注入 `QED_*` 与供应商密钥（不覆盖已显式设置的环境变量）；
MySQL 迁移失败只警告、服务照常启动（任务会明确报错）。服务日志双通道输出：stderr 与仓库根
`logs/qed-tracker.log`（UTF-8，追加写；uvicorn 访问日志同通道），不再依赖外部重定向。
代理访问由 `QED_PROXY=http://127.0.0.1:7890`
提供，用于绕开对 archive.org、openlibrary.org 等来源的 DNS 污染与限流。

### 生命周期脚本（8900 控制中心接入）

仓库级启停入口统一为 `scripts/qed_tracker_service.py`（承接根仓库 REQ-017①，契约见
[服务生命周期设计](../design/service-lifecycle.md)），QED-Engine 8900 控制中心黑盒调用：

```powershell
python scripts/qed_tracker_service.py start              # 默认立即返回；--wait 可选等待健康
python scripts/qed_tracker_service.py start --wait 30    # 轮询 /api/v1/health 直到就绪
python scripts/qed_tracker_service.py start --mode qed-engine   # 指定模型模式（local=直连 / qed-engine=8900 网关）
python scripts/qed_tracker_service.py status             # running (pid N, mode X) / running (port probe) / stopped
python scripts/qed_tracker_service.py stop               # CTRL_BREAK 优雅停止 + taskkill 强杀兜底
python scripts/qed_tracker_service.py restart --wait --mode local   # 重启可换模式（重启后生效）
```

运行事实：PID 文件 `logs/qed-tracker.pid`，模式状态文件 `logs/qed-tracker-mode`，子进程
stdout/stderr 落 `logs/qed-tracker-serve.log`，应用级日志仍写 `logs/qed-tracker.log`。
`--mode` 不传时默认读自身 `.env` 的 `QED_API_SELECT`；模式持久化，重启可更改。退出码 `0`
成功/幂等、`1` 运行失败、`2` 参数错误。健康探测端口取 `QED_TRACKER_PORT`，默认 8901；
脚本不重复实现 8900 的过渡窗口/端口探测语义。

## 教材与习题集

```powershell
qed-tracker books get "Munkres Topology" --limit 10
qed-tracker books get "Munkres Topology" --pick 1
qed-tracker books get "Problems in Mathematical Analysis" --kind exercise --pick 2
qed-tracker books fetch-url https://example.org/book.pdf --title "Book Title"
```

`books get` 汇总启用来源，并将可下载结果排在只有元数据的结果之前。没有 `--pick` 时只预览；显式提供序号才下载，因此终端和脚本行为一致。只有元数据的结果不能下载。

内置来源固定为 Internet Archive、Open Library、Google Books 与 libgen_li（libgen_li 为发现
专用来源：只搜索与解析下载方案，永不自动写文件，人工下载后经登记端点入资源体系）。来源列表
可经 `QED_SOURCES` 环境变量覆盖；TOML 时代的来源配置已退役。

已知 PDF 地址可使用 `fetch-url`，但仍会经过统一的下载、校验、哈希和登记流程。单个来源失败会输出来源名和错误摘要，并继续处理其他来源。

## arXiv 论文

```powershell
qed-tracker papers search "Sobolev inequality" --category math.AP --limit 10
qed-tracker papers search --author "Terence Tao" --download 1
qed-tracker papers get 2401.00001 https://arxiv.org/abs/2402.00002
```

搜索可组合关键词、分类和作者。`--download INDEX` 可以重复指定；`papers get` 接受一个或多个 arXiv ID 或 URL。论文按年份写入 `papers/<year>/`。

## 论文智能发现

查看内置目标档案并生成只读推荐报告：

```powershell
qed-tracker papers profiles list
qed-tracker papers profiles show llm-engineering
qed-tracker papers recommend "可靠的 RAG 评测方法" --profile llm-engineering --top 5
qed-tracker papers selections list
qed-tracker papers selections show <selection-id>
```

推荐命令不会下载。确认报告中的推荐序号后，从同一快照显式下载：

```powershell
qed-tracker papers selections download <selection-id> --pick 1
qed-tracker papers selections download <selection-id> --pick 1 --pick 3
```

`--profile` 接受内置名称或自定义 JSON 路径；默认是 `llm-engineering`。可重复的 `--category` 只扩展本次允许分类。模型只根据 arXiv 标题、作者、分类、时间和摘要初筛，不能代替人工质量判断。

选择报告位于 `meta/selections/`。模型或 arXiv 失败会保存有限错误摘要，但不会写入 PDF；报告下载只能选择达到门槛的固定序号。完整契约见[论文智能发现设计](../design/paper-discovery.md)。

## 冻结目录

```powershell
qed-tracker catalog list
qed-tracker catalog show math-qe
qed-tracker catalog run math-qe --course 03
qed-tracker catalog run math-qe --course 03 --download --report topology.md
```

`catalog run` 默认只预览。只有 `--download` 会下载，并且仅接受完整元数据下的严格匹配；不确定结果留给人工复核。目录报告记录本次尝试，不替代资源清单。

## 清单与已有文件

```powershell
qed-tracker inventory scan E:/qed/dataset
qed-tracker inventory list --kind paper
qed-tracker inventory verify
```

`scan` 递归登记指定目录中的 PDF；路径必须位于数据根内。省略路径时扫描整个数据根。它不移动或删除文件。`verify` 重新检查文件结构、哈希、大小和页数。`meta/resources/` 中的单资源 JSON 是唯一清单事实源。

## 主链路：课程梳理与教材条目

主链路（领域课程梳理 → 教材寻找 → 下载 → 人工验收）是与 evaluate 平行的独立体系，面向课程
学习的主流程。课程体系迁移自包内静态数据（数学范本 14 门课程），教材条目存
`qt_knowledge`/`qt_books`（五要素：课程/版本评价建议/渠道记录/状态），需要 qed 库连接。

```powershell
qed-tracker courses list
qed-tracker courses show 01_math_analysis
qed-tracker mainline list --course 01_math_analysis
qed-tracker mainline new --course 01_math_analysis --title "数学分析原理" --author Rudin
qed-tracker mainline review <knowledge_id> --version 第8版
qed-tracker mainline download <knowledge_id>
qed-tracker mainline verify <knowledge_id> --book <book_id>
qed-tracker mainline approve <knowledge_id> --book <book_id>
qed-tracker mainline reject <knowledge_id> --reason <原因>
qed-tracker mainline channels
```

流程说明：

- `courses list/show` 查看课程体系（先修关系、阶段、关联目标）。
- `mainline new` 先参照顶尖大学（MIT/清华等）该课程指定教材，再按此探索候选；LLM 预填
  版本/评价/建议（需 `API_KEY`），输出 draft 条目供人工评审。评价权威性等级取
  高/中/低，仅供人工参考，不作为自动下载依据。
- `mainline review` 人工定稿（状态迁移 draft → confirmed，`--intro`/`--version` 补全版本要素）。
- `mainline download` 触发渠道下载（archive 等自动源）；无自动候选时输出人工下载指引
  （libgen 等发现专用来源），返回 3。
- `mainline verify` 校验已下载文件（PDF 结构/SHA-256/页数）。
- `mainline approve` 人工验收：通过后**复制**文件与登记同步**移交根仓库
  `dataset/qed-tracker/`**（正式落地，临时区副本保留留痕）；`related_targets` 回填待二次
  确认评估后人工执行（编辑 `qed_course.related_targets`）。多册书用 `--book` 逐个验收。
- `mainline reject` 验收不通过（`--reason` 必填，持久化留痕）。
- `mainline channels` 汇总渠道有效性（各来源成功/失败次数），供剔除无效渠道决策。

存量迁移（一次性，幂等可重放）：`qed-tracker migrate` 先执行课程种子
（`migrations/data/math.json` → `qed_domain`/`qed_course`），再梳理旧三表
（`qt_selections` → `qt_knowledge`、`qt_downloads` → `qt_books`）；旧表保留为
`qt_sources_legacy` 备份，确认无误后才用 `--drop-legacy` 删除。

已知限制（QED-027 待实现）：版本要素 CLI 闭环、人工下载 register 闭环、防总评高单本对比、
rejected 重试出口——见[主链路设计](../design/main-line-curriculum.md)「已知限制」。

## 交付给 Axiom-Flow

```powershell
qed-tracker axiom push sha256:<digest>
qed-tracker axiom push sha256:<digest> --parse
qed-tracker axiom push sha256:<digest> --parse --page-start 1 --page-end 20
```

默认 `push` 只执行健康检查和 PDF 上传。`--parse` 才会创建解析任务；页码参数必须与它一起使用。也可以传入数据根内的 PDF 路径，工具会先将文件登记为资源。

上传成功而解析提交失败时，Axiom 中的文档会保留，本地传输记录会保存错误；工具不会自动删除文档或重试解析任务。完整协议见[服务与外部接口设计](../design/tracker-service.md)「外部接口：Axiom-Flow 消费面」。

## 输出与失败

全局选项放在一级命令之前：

```powershell
qed-tracker --json papers search "elliptic curves" --limit 5
qed-tracker --data-root E:/qed/dataset inventory verify
```

退出码约定：`0` 成功，`2` 参数或配置冲突，`3` 没有可用候选，`4` 批处理或完整性检查部分失败，`5` 下载、文件或 Axiom 等运行错误。机器调用应同时检查退出码和 JSON 输出，不应只匹配人类可读文本。
