# 来源探索与评估

设计状态：Accepted
实现状态：Ongoing
最后更新：2026-08-06
关联代码：`src/qed_tracker/providers/books.py`、`tests/test_book_providers.py`
关联测试：`tests/test_book_providers.py`

## 项目目标（正式）

**发现合适的下载路径、淘汰不合适的下载路径**是本项目的一个持续目标：教材与习题集来源
不固定，随连通性、协议与版权状态变化，需要持续探索、实测、评估并维护来源清单。评估结论
统一记录在本文档「来源评估矩阵」中，避免凭印象决策或重复踩坑。

## 边界约束

- 版权敏感来源（libgen / annas_archive / zlib 类）**不纳入探索与实现**；0.5 起已硬编码
  退役（`RETIRED_PROVIDERS` + 测试强制拒绝），原因补记：版权侵权风险、来源可用性依赖镜像
  站且不稳定，不符合开放来源立场。此约束为长期裁决，变更需用户明确决策。
- 只探索开放/合规来源：公共领域馆藏、开放教材库、出版社/机构官方站点、作者自发布等。
- 默认测试不得访问公网；连通性实测在人工联调轮进行（经 `QED_PROXY` 代理）。
- 新来源实现必须遵守来源协议（`search(query, limit)` / `resolve(candidate)` / `close()`），
  只搜索和解析下载地址；文件写入、重试、校验、哈希与去重必须经过通用下载器。

## 来源评估矩阵

每源记录：连通性（直连/代理）、中文覆盖、候选质量（元数据完整性与匹配精度）、
下载成功率、结论。结论取值：**保留（主力）**、**保留（补充）**、**受限**、**移除**。

| 来源 | 连通性 | 中文覆盖 | 候选质量 | 下载成功率 | 结论 |
| --- | --- | --- | --- | --- | --- |
| internet_archive | 直连 DNS 污染（解析到 Meta 网段 69.63.184.142，Python 挂起）；经 `QED_PROXY` 正常 | 有中文扫描件（陈纪修《数学分析新讲》math_analysis_chenjixiu、现代数学基础丛书、概率论与数理统计中文版等），但 13 门课程中文教材覆盖有限（点集拓扑学/高等代数/实变/泛函/常微/数理方程 实测 0 命中）；**中文（CJK）query 已改 title 精确短语 + AND 组合**（全字段 OR 拆词只返回 ChinaXiv 噪音） | 高：title/creator 元数据完整，strict 匹配可达 score=1.0；中文命中需按「书名 + 作者」组合查询 | 高：resolve 经 `/metadata/{id}` 取最大公开 PDF，552 页 33.5MB 实测成功 | 保留（主力） |
| open_library | 同 archive 的 DNS 污染；经代理正常 | 低（中文书名 0 命中实测） | 中：`ia` 字段命中才可下载，否则 METADATA_ONLY | 中 | 保留（补充） |
| google_books | 直连正常（googleapis 未被污染） | 中（中文书目多，但 PDF downloadLink 极少） | 中：仅 `accessInfo.pdf.downloadLink` 可下载，大部分仅元数据 | 低（429 Too Many Requests 限流频繁） | 受限（依赖限流恢复） |
| project_gutenberg | 主站直连 200（www.gutenberg.org）；第三方聚合 API gutendex.com 直连/代理均超时 | 无（英文公共领域） | 公共领域英文经典（数学现代教材基本无版权覆盖）；官方无稳定 JSON API（RDF dump / HTML 页） | — | 补充（英文公共领域，暂不落地 provider：无 API 且对 13 门课程收益低） |
| open_textbook_library | 直连 200（open.umn.edu） | 无 | 开放教材（英文为主，数学经典覆盖有限）；无公开 JSON API | — | 补充（记录连通性，按需深入） |
| libretexts | 代理 200 | 无 | 开放教材（英文为主）；无公开 JSON API | — | 补充（记录连通性，按需深入） |
| pressbooks.directory | 直连 403（反爬限制） | — | — | — | 不可用 |
| sciencep（科学文库） | 直连/代理 TLS 证书验证失败（本地根证书） | 高（官方中文科技图书平台） | 部分免费阅读/下载 | — | 待评估（证书问题解决后重测） |

### 已淘汰记录

| 来源 | 淘汰原因 | 日期 |
| --- | --- | --- |
| libgen / annas_archive / zlib | 版权敏感，0.5 硬编码退役（见边界约束） | 2026-08-06 补记 |

## 待探索清单

按价值排序，逐项实测后更新矩阵：

1. **archive.org 中文扫描件专项**：以「中文教材标题 + 作者」直接搜 archive 中文条目
   （archive 收录大量中文教材扫描本，是最现实的合规中文来源），评估匹配精度与下载质量。
2. **Project Gutenberg**：公共领域数学经典（无现代教材，补充用）。
3. **Open Textbook Library / LibreTexts / Pressbooks 系**：开放教材库，英文为主，
   现代教材但覆盖数学经典有限。
4. **科学文库（科学出版社）**：中文科技图书官方平台，部分免费阅读/下载，评估可下载范围。
5. **出版社/机构官方站点**：高教社、人教社等，评估是否有合法样章/整书下载。
6. 其他实测中发现的候选源。

## 评估流程

1. 候选源列入「待探索清单」。
2. 联调轮实测（经 `QED_PROXY`）：连通性、中文候选数、元数据完整度、一次真实下载成功率。
3. 结论写入矩阵；「保留」类来源实现 provider（TDD：固定 fixture 测试，不依赖公网），
   注册进 `PROVIDER_TYPES`；「受限/移除」类来源记录原因，不落地代码。
4. 单个来源协议变化只影响该来源（来源隔离铁律），不得中断其他来源。

## 执行记录

- 2026-08-06：三源初评写入矩阵；archive 多词查询修复（`title:(a b c)` → 全字段查询）；
  03-munkres 真实下载闭环成功（Topology 2nd edition，552 页）。
- 2026-08-06（QED-018 首轮实测）：archive.org 中文扫描件专项——实测 10 个中文教材 query：
  多数 0 命中（点集拓扑学/高等代数/实变/泛函/常微/数理方程/抽象代数），少量真实命中
  （陈纪修《数学分析新讲》、现代数学基础丛书 3 册、概率论与数理统计中文版）；全字段 OR
  拆词查询对中文只返回 ChinaXiv 预印本噪音，**落地 CJK 查询策略**（首词 title 精确短语 +
  其余词 AND，`tests/test_book_providers.py` 守护），真实命中 math_analysis_chenjixiu；open_library 中文 0 命中；Gutenberg 主站可达
  （gutendex API 不可达）、Open Textbook Library/LibreTexts 可达、科学文库 TLS 证书失败、
  Pressbooks 403——结论均已入矩阵；本轮**不新增 provider**（候选源无稳定 JSON API 且对
  13 门课程目录收益有限，CJK 查询改进为实际落地项）。
