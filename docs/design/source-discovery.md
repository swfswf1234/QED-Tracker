# 来源探索与评估

设计状态：Accepted
实现状态：In Progress
最后更新：2026-08-07
关联代码：`src/qed_tracker/providers/books.py`、`tests/test_book_providers.py`
关联测试：`tests/test_book_providers.py`

## 项目目标（正式）

**发现合适的下载路径、淘汰不合适的下载路径**是本项目的一个持续目标：教材与习题集来源
不固定，随连通性、协议与版权状态变化，需要持续探索、实测、评估并维护来源清单。评估结论
统一记录在本文档「来源评估矩阵」中，避免凭印象决策或重复踩坑。

## 边界约束

- 版权敏感来源默认不纳入自动下载。**2026-08-07 用户明确裁决**（数学课程选书要求
  「2-4 套高质量教程，翻译版优先」，而 archive 中文覆盖窄、翻译版实测 0 命中）：
  **libgen（libgen.li）从「硬编码退役」恢复为「书目发现 + 人工下载指引」专用来源**——
  LibgenProvider 只搜索与解析书目信息（标题/作者/ISBN/出版社/大小/格式）及下载方案
  （torrent / IPFS CID / ed2k 链接），`availability=metadata_only`，**永不自动写文件**；
  文件落地必须由人工下载后经登记端点（PDF 校验 + SHA-256 去重，走通用服务）进入资源体系。
  annas_archive / zlib 保持退役。此变更为长期裁决，配套代码 `RETIRED_PROVIDERS` 同步移除 libgen。
- 只探索开放/合规来源：公共领域馆藏、开放教材库、出版社/机构官方站点、作者自发布等；
  libgen 仅作发现补充，不改变「来源适配器只搜索和解析下载地址；文件写入、重试、校验、
  哈希与去重必须经过通用下载器」的约束。
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
| libgen_li（libgen.li） | 经代理 200（libgen.rs/st 域不可达；libgen.li 可达） | **高**：中文翻译版全覆盖实测命中（菲赫金哥尔茨《微积分学教程》3 卷、卓里奇、陶哲轩《实分析》中译、谢惠民《习题课讲义》上下、裴礼文、Apostol 中译、Rudin 中译 2003 等） | 高：ISBN/出版社/年份/语言/页数/大小/格式完整；edition 页含 md5 + IPFS CID | 无 HTTP 直链：仅 torrent / IPFS 网关（cloudflare-ipfs.com、gateway.ipfs.io、pinata 实测均不可达）/ TOR / ed2k | **保留（发现专用 + 人工下载指引）**：2026-08-07 用户裁决恢复，只搜索与解析下载方案，人工下载后登记 |

### 已淘汰记录

| 来源 | 淘汰原因 | 日期 |
| --- | --- | --- |
| annas_archive / zlib | 版权敏感，0.5 硬编码退役；annas-archive.li 搜索页有反爬挑战页、z-lib 域名多为出售/不可用，维持退役 | 2026-08-06 补记，2026-08-07 复测维持 |
| libgen | 0.5 曾硬编码退役（版权敏感）；**2026-08-07 用户裁决恢复为「书目发现 + 人工下载指引」专用来源**（见边界约束），不再视为淘汰 | 2026-08-06 补记 / 2026-08-07 裁决变更 |

## 可达链路总结与评估（2026-08-06 第二轮实测）

按「搜索 → 解析 → 下载」三环节评估链路可行性（对象：13 门课程教材/习题集，中文为主）：

| 链路 | 搜索 | 解析 | 下载 | 评估 |
| --- | --- | --- | --- | --- |
| archive.org（英文书） | 可行：全字段查询，英文书名命中率高（Baby Rudin / LADR 实测命中） | 可行：`/metadata/{id}` 取最大公开 PDF | 可行：`/download/{id}/` 直下，552 页 33.5MB 实测成功 | **可行（主力）**，英文教材闭环已验证 |
| archive.org（中文书） | 受限：CJK 已改 `title:"首词" AND 其余词` 精确短语策略；覆盖有限——陈纪修《数学分析新讲》、现代数学基础丛书、概率论与数理统计中文版实测命中，其余多数中文教材 0 命中 | 同英文 | 同英文（待本轮实测确认） | **可行但覆盖窄**：能命中即可下载；未命中只能 pending_manual |
| open_library | 中文书名 0 命中；英文可作 archive 补充 | 仅 `ia` 字段可解析下载，否则 METADATA_ONLY | 依赖 archive item | **不可用于中文**，英文补充 |
| google_books | 中文书目全但持续 429 限流（多轮实测均被限） | 仅 `accessInfo.pdf.downloadLink` 可下载，中文书极少有 | 低 | **本轮不可用**（限流），等配额恢复后复测 |
| project_gutenberg | 主站可达，无稳定 JSON API | — | — | 仅英文公共领域，13 门课程收益低，暂不落地 |
| open_textbook_library / libretexts | 可达，无公开 JSON API，英文为主 | — | — | 补充记录，按需深入 |
| pressbooks.directory | 403 反爬 | — | — | 不可用 |
| sciencep（科学文库） | TLS 证书验证失败（本地根证书） | — | — | 待评估（证书问题解决后重测） |
| libgen.li（发现专用） | 可行：中文 query 直接全字段搜索（无需 CJK 特殊策略），命中率极高 | 可行：edition 页解析 md5 / IPFS CID / torrent / ed2k 链接 | **不可自动**：无 HTTP 直链；IPFS 网关（cloudflare-ipfs.com / gateway.ipfs.io / pinata）实测均不可达；torrent / TOR / ed2k 需人工 | **发现可行（中文翻译版唯一全覆盖源），下载需人工**：候选带下载方案链接，人工下载后经登记端点入资源体系 |

**结论**：中文翻译版自动下载链路依然只有 archive.org（命中即可下载，覆盖窄）；
**libgen.li 是中文翻译版书目的全覆盖发现源**（2026-08-07 用户裁决恢复为发现专用），
但文件下载必须人工（torrent / IPFS / 浏览器），人工下载的文件经登记端点（PDF 校验 +
SHA-256 去重）进入资源体系。01 数学分析闭环据此定稿：套一 Rudin 中译 + 吉米多维奇
（本地已有）、套二 菲赫金哥尔茨《微积分学教程》3 卷 + 谢惠民《习题课讲义》上下
（libgen 发现 → 人工下载）、套三 陈纪修《数学分析》上下（archive 自动下载）+ 习题
答案（supplement）、英文对照 Rudin EN（已有）+ Pólya（archive 可选）。

## 待探索清单

按价值排序，逐项实测后更新矩阵：

1. **libgen.li 人工下载通道**：候选下载方案的可行人工通道（torrent 客户端、IPFS 桌面节点、
   镜像站），产出「人工下载指引」配套文档；不改变「不自动写文件」边界。
2. **archive.org 中文扫描件专项**：以「中文教材标题 + 作者」直接搜 archive 中文条目
   （archive 收录大量中文教材扫描本，是最现实的合规中文来源），评估匹配精度与下载质量。
3. **Project Gutenberg**：公共领域数学经典（无现代教材，补充用）。
4. **Open Textbook Library / LibreTexts / Pressbooks 系**：开放教材库，英文为主，
   现代教材但覆盖数学经典有限。
5. **科学文库（科学出版社）**：中文科技图书官方平台，部分免费阅读/下载，评估可下载范围。
6. **出版社/机构官方站点**：高教社、人教社等，评估是否有合法样章/整书下载。
7. 其他实测中发现的候选源。

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
- 2026-08-06（第二轮实测，01 数学分析闭环前置）：13 门课程清库后按课程评估（01/02/06 已跑，
  中文 target 多数 pending_manual，英文候选 backup）；**google_books 持续 429**（每轮评估
  均被限流，本轮中文搜索绕过）；archive.org 出现连接被拒（10061，网络层阻断，恢复后继续
  中文链路实测）；「可达链路总结与评估」章节落盘（archive 中文为唯一可用中文下载链路，
  待吉米多维奇 `title:"数学分析习题集"` 与陈纪修 resolve/下载实测回填）。
- 2026-08-07（第三轮实测，数学课程选书要求落地）：**libgen.li 实测**——连通性（代理 200，
  libgen.rs/st 域不可达、zlib.sk 为域名出售页、annas-archive.li 有反爬挑战页）；中文翻译版
  书目全覆盖（菲赫金哥尔茨《微积分学教程》3 卷 / 卓里奇 / 陶哲轩《实分析》中译 / 谢惠民
  《习题课讲义》上下 / 裴礼文 / Apostol 中译 / Rudin 中译均命中，含 ISBN/出版社/年份/大小/
  格式完整元数据）；edition 页可解析 md5 + IPFS CID + torrent + ed2k；**无 HTTP 直链**，
  IPFS 网关（cloudflare-ipfs.com / gateway.ipfs.io / pinata）实测均不可达 → 结论入矩阵
  「保留（发现专用 + 人工下载指引）」。用户裁决：libgen 从退役恢复为发现专用（边界约束
  更新），`RETIRED_PROVIDERS` 同步移除 libgen；01 数学分析定稿两套 + 陈纪修 + 英文对照
  （见「可达链路总结与评估」结论）。
