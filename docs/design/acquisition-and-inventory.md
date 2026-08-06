# 下载与清单设计

设计状态：Accepted
实现状态：Implemented
最后更新：2026-07-30
关联代码：`src/qed_tracker/providers/`、`src/qed_tracker/application/`、`src/qed_tracker/downloader.py`、`src/qed_tracker/inventory.py`
关联测试：`tests/test_book_providers.py`、`tests/test_arxiv_provider.py`、`tests/test_download_inventory.py`、`tests/test_services.py`

## 来源协议

教材来源实现 `search(query, limit)`、`resolve(candidate)` 和 `close()`。搜索结果统一为 `Candidate`，包含来源身份、标题、作者、语言、年份、版次、格式、大小、页面 URL、下载 URL、可用性、外部标识和可选摘要。

内置教材来源为 Internet Archive、Open Library 和 Google Books。来源可以只返回元数据；只有 `availability=downloadable` 的候选能够进入下载器。单个来源的协议变化不得中断其他来源。

版权敏感来源（libgen / annas_archive / zlib 类）已硬编码退役（`RETIRED_PROVIDERS`），不纳入实现；来源的持续探索、评估矩阵与合规边界见[来源探索与评估设计](source-discovery.md)。

论文只使用 arXiv 客户端，支持关键词、分类、作者、arXiv ID 和 URL。arXiv ID 同时作为外部标识，并用于确定论文保存年份和文件名。

基于研究目标的检索规划与排序属于[论文智能发现设计](paper-discovery.md)。它复用本设计的 arXiv 候选、通用下载和 Inventory，不改变资源 schema。

## 选择与目录匹配

- `books get` 无 `--pick` 时只预览教材结果；只有显式提供序号才下载。
- 论文搜索可以用一个或多个 `--download INDEX` 显式选择结果；`papers get` 直接接受 ID 或 URL。
- 冻结目录自动下载必须同时满足标题、作者、语言和版次要求；缺少必需元数据视为不严格匹配。
- 目录运行默认只预览。只有显式 `--download` 才允许严格匹配项进入下载流程。

## 可靠下载

所有来源最终只提供候选和 URL，通用下载器统一负责：

1. 使用 `<target>.part` 保存本次未完成内容；每次重试都从头覆盖临时文件，不拼接未知远端版本。
2. 按配置的次数重试网络和文件错误。
3. 校验 `%PDF-` 文件头、可读取的 PDF 结构和至少一页内容。
4. 计算完整内容的 SHA-256、字节数和页数。
5. 只在全部检查通过后用原子替换生成正式文件；最终失败时移除临时文件。

资源服务把下载器已经计算的 SHA-256、大小和页数直接交给 Inventory，不重复解析 PDF。如果相同 SHA-256 已有有效记录，则复用既有记录并移除本次新产生的重复文件。

## 资源 schema v1

资源身份固定为 `sha256:<digest>`。单资源 JSON 写入 `.qed-tracker/resources/<sha256>.json`，字段如下：

| 字段 | 内容 |
| --- | --- |
| `resource_id`、`schema_version`、`kind`、`created_at` | 稳定身份、schema 版本、资源类型和 UTC 创建时间。 |
| `title`、`authors`、`language`、`year`、`identifiers` | 规范化书目信息和外部标识。 |
| `source` | 来源名、来源 ID、页面地址、下载地址和获取时间；本地扫描记录为 `provider=local`。 |
| `file` | 数据根相对路径、SHA-256、字节数、`application/pdf` 和页数。 |
| `catalog_ref` | 可选的目录 ID、目标 ID 和课程 ID。 |

资源 JSON 使用 UTF-8、稳定键排序和原子替换写入。单资源 JSON 是唯一清单事实源；0.5 不再生成 `manifest.jsonl`，已有文件不会被主动删除。

## 已有文件与完整性

`inventory scan` 递归查找用户明确指定的目录；所有路径必须解析到数据根内部。扫描只登记文件，不移动或删除原件。`inventory verify` 重新检查文件存在性、PDF 结构、SHA-256、大小和页数，并返回 `ok`、`missing`、`invalid` 或 `changed`。

## 失败语义

- 单个教材来源失败时记录来源名和错误摘要，并继续汇总其他来源。
- 没有候选或没有可下载候选时不创建文件。
- 非 PDF、损坏 PDF 或零页 PDF 永远不能成为正式资源。
- 批处理中的部分失败返回部分失败退出码，并保留已经成功登记的独立资源。
- 真实外部来源连通性不作为默认 CI 门禁；自动测试只使用固定响应和临时目录。
