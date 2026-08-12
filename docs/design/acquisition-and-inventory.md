# 下载与清单设计

设计状态：Accepted
实现状态：Implemented
最后更新：2026-08-12
关联代码：`src/qed_tracker/providers/`、`src/qed_tracker/application/`、`src/qed_tracker/downloader.py`、`src/qed_tracker/inventory.py`
关联测试：`tests/test_book_providers.py`、`tests/test_arxiv_provider.py`、`tests/test_download_inventory.py`、`tests/test_services.py`
关联 ADR：—

## 来源协议

教材来源实现 `search(query, limit)`、`resolve(candidate)` 和 `close()`。搜索结果统一为 `Candidate`，包含来源身份、标题、作者、语言、年份、版次、格式、大小、页面 URL、下载 URL、可用性、外部标识和可选摘要。

内置教材来源为 Internet Archive、Open Library、Google Books 和 **libgen_li**。来源可以只返回元数据；只有 `availability=downloadable` 的候选能够进入下载器。单个来源的协议变化不得中断其他来源。

**libgen_li 为「发现专用」来源**（2026-08-07 用户裁决恢复，见 [来源探索与评估设计](source-discovery.md) 边界约束）：只搜索与解析书目信息及下载方案（torrent / IPFS CID / ed2k 链接，写入 `Candidate.links`），候选恒为 `availability=metadata_only`，**永不自动写文件**。文件落地必须由人工下载后经登记端点（`POST /resources/{id}/register`）进入资源体系；登记端点执行 PDF 校验、SHA-256 计算与去重，与自动下载同一套通用逻辑。annas_archive / zlib 保持退役（`RETIRED_PROVIDERS`）。

论文只使用 arXiv 客户端，支持关键词、分类、作者、arXiv ID 和 URL。arXiv ID 同时作为外部标识，并用于确定论文保存年份和文件名。

基于研究目标的检索规划与排序属于[论文智能发现设计](paper-discovery.md)。它复用本设计的 arXiv 候选、通用下载和 Inventory，不改变资源 schema。

## 数学课程选书要求（2026-08-07 用户裁决，01 起执行）

面向全部数学课程（01–13）的教材与习题集采集原则，**贵精不贵多**：

1. **每门数学课程目标 2–4 套教程**。一套教程 = 教材 + 高质量配对的习题集；习题集不要求
   与教材严格一一对应，但必须是高质量配对（经典习题集即可）。
2. **先探索两门经典教程**作为核心；发现额外经典时允许加第三套；有对应的优秀英文版教程
   时**同步下载作为对照**（中英对照阅读）。超出 4 套的部分 **PASS（拒绝）**，避免同课程
   多版本冲突。
3. **翻译版优先**：优先选择经典教材的中文翻译版（便于人工评审与对照阅读）；翻译版不可得
   时按 archive.org 中文扫描件 → 英文原版顺序降级，不因链路困难降低对教材与习题集质量的要求。
4. **项目优先自动拉取**：候选走自动链路（archive 等）能下载即下载；**自动链路拉取不到时，
   提示人工下载并给出下载方案**（来源链接、torrent / IPFS / ed2k 等，见 `Candidate.links`），
   人工下载后经登记端点入资源体系，不阻塞课程闭环。
5. 分类口径：**教材（book）/ 习题集（exercise）/ 其他资料（supplement）**；配套习题答案等
   与教材同源文件归入 supplement，不重复下载为独立习题集。
6. 每门课程的定稿书单与下载来源记录在目录 `catalogs/math-qe.json` 与课程评估报告（evaluate
   任务 result）中，人工评审以 8903 前端为准。

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

资源身份固定为 `sha256:<digest>`。单资源 JSON 写入 `meta/resources/<sha256>.json`，字段如下：

| 字段 | 内容 |
| --- | --- |
| `resource_id`、`schema_version`、`kind`、`created_at` | 稳定身份、schema 版本、资源类型和 UTC 创建时间。`kind` 取值 `book`（教材）/ `exercise`（习题集）/ `supplement`（其他资料，如配套习题答案）/ `paper`。 |
| `title`、`authors`、`language`、`year`、`identifiers` | 规范化书目信息和外部标识。 |
| `source` | 来源名、来源 ID、页面地址、下载地址和获取时间；本地扫描记录为 `provider=local`；libgen 发现候选另含 `links`（下载方案：torrent / IPFS / ed2k）。 |
| `file` | 数据根相对路径、SHA-256、字节数、`application/pdf` 和页数。 |
| `catalog_ref` | 可选的目录 ID、目标 ID 和课程 ID。 |

人工评审建议（三态确认时的 `note`）保存在 MySQL `qt_resources.review_note`（QED-020，见
[人工评审优化设计](review-round-dedup.md)），单资源 JSON 事实源不包含评审备注。

资源 JSON 使用 UTF-8、稳定键排序和原子替换写入。单资源 JSON 是唯一清单事实源；0.5 不再生成 `manifest.jsonl`，已有文件不会被主动删除。

## 已有文件与完整性

`inventory scan` 递归查找用户明确指定的目录；所有路径必须解析到数据根内部。扫描只登记文件，不移动或删除原件。`inventory verify` 重新检查文件存在性、PDF 结构、SHA-256、大小和页数，并返回 `ok`、`missing`、`invalid` 或 `changed`。

## 失败语义

- 单个教材来源失败时记录来源名和错误摘要，并继续汇总其他来源。
- 没有候选或没有可下载候选时不创建文件。
- 非 PDF、损坏 PDF 或零页 PDF 永远不能成为正式资源。
- 批处理中的部分失败返回部分失败退出码，并保留已经成功登记的独立资源。
- 真实外部来源连通性不作为默认 CI 门禁；自动测试只使用固定响应和临时目录。
