# 日常操作

状态：Current
最后更新：2026-07-30

## 配置

安装开发版本并生成本地配置：

```powershell
python -m pip install -e ".[dev]"
qed-tracker config init --data-root E:/qed/dataset
qed-tracker config show
```

配置按“命令行、`QED_TRACKER_*` 环境变量、TOML、内置默认值”的顺序覆盖。可以用全局 `--config` 指定 TOML；未指定时依次查找 `QED_TRACKER_CONFIG`、当前目录的 `qed-tracker.local.toml` 和用户配置目录下的 `.qed-tracker/config.toml`。

TLS 校验默认开启。代理、超时、重试、来源列表、数据根和 Axiom URL 均可在 TOML 中配置；个人配置不得提交到仓库。

百炼论文推荐的模型、端点、超时、调用预算和输出上限位于 `[llm]`。密钥只能通过环境变量提供，不得写入 TOML：

```powershell
$env:QED_TRACKER_LLM_API_KEY = "<secret>"
```

## 教材与习题集

```powershell
qed-tracker books get "Munkres Topology" --limit 10
qed-tracker books get "Munkres Topology" --pick 1
qed-tracker books get "Problems in Mathematical Analysis" --kind exercise --pick 2
qed-tracker books fetch-url https://example.org/book.pdf --title "Book Title"
```

`books get` 汇总启用来源，并将可下载结果排在只有元数据的结果之前。没有 `--pick` 时只预览；显式提供序号才下载，因此终端和脚本行为一致。只有元数据的结果不能下载。

0.5 只内置 Internet Archive、Open Library 和 Google Books。升级后应从本地 TOML 或 `QED_TRACKER_SOURCES` 删除 `libgen`、`annas_archive` 和 `zlib`；工具会对遗留来源返回明确配置错误，不会自动修改个人配置。

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

选择报告位于 `.qed-tracker/paper-selections/`。模型或 arXiv 失败会保存有限错误摘要，但不会写入 PDF；报告下载只能选择达到门槛的固定序号。完整契约见[论文智能发现设计](../design/paper-discovery.md)。

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

`scan` 递归登记指定目录中的 PDF；路径必须位于数据根内。省略路径时扫描整个数据根。它不移动或删除文件。`verify` 重新检查文件结构、哈希、大小和页数。`.qed-tracker/resources/` 中的单资源 JSON 是唯一清单事实源。

## 交付给 Axiom-Flow

```powershell
qed-tracker axiom push sha256:<digest>
qed-tracker axiom push sha256:<digest> --parse
qed-tracker axiom push sha256:<digest> --parse --page-start 1 --page-end 20
```

默认 `push` 只执行健康检查和 PDF 上传。`--parse` 才会创建解析任务；页码参数必须与它一起使用。也可以传入数据根内的 PDF 路径，工具会先将文件登记为资源。

上传成功而解析提交失败时，Axiom 中的文档会保留，本地传输记录会保存错误；工具不会自动删除文档或重试解析任务。完整协议见[Axiom-Flow 交接设计](../design/axiom-handoff.md)。

## 输出与失败

全局选项放在一级命令之前：

```powershell
qed-tracker --json papers search "elliptic curves" --limit 5
qed-tracker --data-root E:/qed/dataset inventory verify
```

退出码约定：`0` 成功，`2` 参数或配置冲突，`3` 没有可用候选，`4` 批处理或完整性检查部分失败，`5` 下载、文件或 Axiom 等运行错误。机器调用应同时检查退出码和 JSON 输出，不应只匹配人类可读文本。
