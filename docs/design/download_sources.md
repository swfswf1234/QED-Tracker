# 下载来源与资源契约

## 来源协议

教材来源实现 `search(query, limit)`、`resolve(candidate)` 和 `close()`。搜索结果统一为 `Candidate`：来源身份、题名、作者、语言、年份、版次、格式、页面 URL、下载 URL、可用性和外部标识。

已启用来源为 Internet Archive、Open Library、Google Books、LibGen、Anna's Archive 和 Z-Library。开放来源可返回只有元数据的结果；只有 `downloadable` 候选可进入下载器。HTML 来源变化只能影响对应适配器，不能中止其他来源。

论文只使用 arXiv 官方客户端，支持关键词、分类、作者和 ID。arXiv ID 同时用于文件名和外部标识。

## 选择与下载

- 普通搜索由用户通过结果序号显式选择；非交互环境必须传 `--pick` 或论文 `--download INDEX`。
- 冻结目录自动下载必须同时满足题名、作者、语言和版次；元数据缺失视为不严格匹配。
- 所有来源最终只返回 URL；通用下载器负责 Range、重试、PDF 结构、哈希与原子落盘。
- 同一 SHA-256 已登记时删除新产生的重复文件并复用既有资源记录。

## 资源 schema v1

单资源 JSON 包含 `resource_id`、`kind`、书目信息、`identifiers`、`source`、`file`、可选 `catalog_ref` 和 UTC 创建时间。`file` 至少包含相对路径、SHA-256、字节数、MIME 类型和页数。

JSONL 不是独立事实源，由单资源 JSON 按稳定顺序重建。已有 PDF 扫描只能接受数据根内部路径。
