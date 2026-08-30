# 下载流程现状分析与优化方向

状态：Current  
最后更新：2026-08-28  
关联任务：QED-026（主链路收尾）、QED-043（prompt 优化）、REQ-020（榜单数据收集）、REQ-032（meta/退役）

## 一、三条下载链路当前逻辑

### 链路一：catalog run（冻结目录严格匹配）

触发方式：`BookService.run_catalog(targets)` → 由 `catalog run` CLI 命令调用。

```
targets（冻结目录 math-qe.json）
  → BookProvider.search(query, limit=10, original_title=)
    → 4 来源适配器按顺序尝试：
      InternetArchive（CJK 短语特判：繁→简→日→韩）
      OpenLibrary（→InternetArchive 映射下载）
      GoogleBooks（pdf downloadLink 稀有，仅 meta）
      Libgen（li 仅发现，人工下载）
    → 每条候选 match_candidate 评分（title + original_title + authors + file_hint 加权）
      → strict 优先（0.7 以上）；无 strict 时选最高分
  → DownloadManager.download(final_url, url_for_info=meta_url)
    → retries=3、退避 min(2^n, 4) 秒
    → PDF 魔数校验 + 页数最小阈值
    → .part 原子落盘 → sha256 计算
  → ResourceService.register(staging_path, md5, sha256, catalog_target=None, domain_id, course_id)
    → staging 目录暂存 → md5 校验（archive 声明时）
    → sha256 去重（已有同文件 → 复用路径，不重复下载）
    → raw/<domain>/<course>/ 或 raw/_general/ 落盘
    → Inventory JSON 登记
  → attempts 报告（成功/失败/跳过计数）
```

成功条件：至少一个 catalog target 的首选候选下载成功 + PDF 校验通过 + sha256 唯一。

### 链路二：mainline CLI（知识行 → 书行 → 下载 → 校验 → 移交）

触发方式：`mainline download <course_id>` → `mainline verify <course_id>` → `mainline approve <course_id>`。

**download 阶段：**
```
qt_knowledge WHERE status=confirmed（非 hidden）
  → 自动查找/创建 qt_books 行（candidate/decided/failed）：
    若无书行 → 以 knowledge.name 为 title 粗糙创建（无 authors/version/ref）
  → BookProvider.search(query=f"{knowledge.name} {book.kind}", limit=3)
    → 无 original_title（不使用 decision 引用）
    → 无 file_hint 注入
    → 无 match_candidate 评分
    → 取第一个 downloadable 候选
  → resolve 选择文件（file_keywords 优先 → size 最大）
  → DownloadManager.download
  → add_source 记录渠道
  → complete_download（status=downloaded）或 fail_download（status=failed）
```

**verify 阶段：**
```
status=downloaded 的书行
  → inspect_pdf（魔数+页数）
  → 若 PDF 异常 → reject_download（status=rejected，reason 记录）
  → 若通过 → verify_book（status=verified）
```

**approve 阶段：**
```
status=verified 的书行
  → inspect_pdf 二次确认
  → 复制到 raw/<domain>/<course>/（硬链接或复制）
  → complete_knowledge 聚合：
    所有非 hidden 书行全 verified → knowledge.status = completed
    （注：设计声称 completion 回写 qed_course.exploration_stage=已完成，但代码未实现此回写）
```

成功条件：knowledge 达到 completed 状态。

### 链路三：8901 books API（人工登记）

触发方式：`POST /books` + `POST /books/{id}/sources` + `POST /books/{id}/register`。

```
POST /books → 创建 candidate 书行（手动指定 title/authors/roles/version）
POST /books/{id}/sources → add_source 登录渠道（channel + source_url + quality 等）
POST /books/{id}/register → register（downloaded→register 直转：记录相对路径、md5、sha256、page_count）
  或 decide→start→download→register 完整流程
  或 decide→fail→retry→download→register
POST /books/{id}/verify → verify_book（downloaded→verified）
POST /books/{id}/complete → complete_book（verified→completed）
POST /books/{id}/reject → reject（有 reason）
```

成功条件：书行达到 completed 状态。

### 链路四：8901 books fetch API（自动取书执行器，方案 A 2026-08-28）

触发方式：`POST /books/{id}/fetch` → `book_download` 后台任务（TaskManager 线程池，并发上限 2）。

```
POST /books/{id}/fetch（202 → task_id）
  → 状态校验（仅 candidate/decided/failed；candidate 自动 decide；downloading 409 提示先 cancel）
  → start（downloading）
  → 检索词 = 书行 title + authors（非 knowledge.name 展示名）
  → BookService.search(query, limit=8)（每次任务独立 BookService，结束 close）
  → 按序逐候选（downloadable 优先）：
      每候选总预算 QED_FETCH_ATTEMPT_TIMEOUT（默认 600s，工作线程 + future.result 看门狗）；
      staging 文件名带唯一 tag（孤儿线程不与后续候选写同名 .download/.part）
    成功 → add_source(channel, ok=True) + complete_download（→ downloaded）
    失败/超时 → add_source(channel, ok=False, note=原因) → 下一候选
  → 全部失败 → add_source(download, ok=False) + fail_download（→ failed）
      任务 error 附逐候选摘要 + 人工下载指引（metadata_only 候选链接清单）
```

成功条件：任务 succeeded + 书行 downloaded（verify 仍人工）。
配套端点：`POST /books/{id}/cancel`（downloading → decided 复位，仅 downloading 可取消）。
渠道留痕（qt_sources）同时产出 REQ-020② 找得率数据。

## 二、状态机事实

### BookStatus（九态，2026-08-28 修正：原记录漏 downloading）

```
candidate → decided → downloading → downloaded → verified → completed
    ↓           ↓           ↓            ↓
  rejected    rejected    failed      rejected/superseded
    ↑           ↑          ↓
    └── retry ──┘    decided（cancel 复位，仅 downloading）
```

- candidate：初始态，待决定是否下载
- decided：已决定下载，等待执行
- downloading：下载中（fetch 任务执行期；cancel 可复位回 decided）
- downloaded：文件已下载，待校验
- verified：校验通过，待确认/移交
- completed：已确认/移交
- failed：下载失败（可重试）
- rejected：校验拒绝（不可重试，reason 必填）
- superseded：被新版本替代（hidden）

### KnowledgeStatus（五态）

```
draft → confirmed → completed
  ↓         ↓
rejected  superseded
```

- draft：A2 采纳后初始态
- confirmed：探索定稿（预填决定引用 + 简介）
- completed：所有非 hidden 书行全 verified 聚合触发
- rejected：拒绝（reason 必填，by 必填）
- superseded：被替代（hidden）

complete 聚合条件：`visible_books > 0 AND all_visible_books.status == verified`。无书行或全 hidden 时不允许 complete。

### 聚合回写（设计 vs 代码）

共享表设计声称"knowledge complete 时回写 qed_course.exploration_stage=已完成"——**代码未实现**。当前 `complete_knowledge` 仅设置 knowledge 行状态，不触碰 qed_course。课程 exploration_stage 回写留待后续轮（或下载流程优化时一并修复）。

## 三、下载器与清单层事实

### DownloadManager（`src/qed_tracker/downloader.py`）

- 重试：最多 3 次（含首次），退避 min(2^n, 4) 秒
- PDF 校验：魔数 `%PDF` + 页数最小阈值（可配置）
- 落盘：.part 临时文件 → 成功后原子 rename
- 哈希：sha256 全文计算（用于去重与登记）
- TLS：默认开启，可由用户显式关闭
- Proxy：HTTP_PROXY/HTTPS_PROXY 环境变量支持

### ResourceService（`src/qed_tracker/application/resources.py`）

- staging：`tmp/qed-tracker/downloads/` 临时存放
- md5 校验：仅当 archive 声明时执行（非全文哈希）
- 去重：sha256 匹配已有记录 → 复用路径，不重复下载
- 落盘路径：`raw/<domain>/<course>/` 或 `raw/_general/`（无 domain/course 时）
- Inventory JSON 登记：`meta/resources/` 下单文件 JSON

### Inventory（`src/qed_tracker/inventory.py`）

- 事实源：`meta/resources/` JSON（每资源一个文件）
- 路径约束：所有文件必须在数据根内
- 去重键：sha256
- 查询：`find_by_catalog_target` 用于 catalog run 去重

### 来源适配器（`src/qed_tracker/providers/`）

| 适配器 | 搜索 | 下载 | 特性 |
|---|---|---|---|
| InternetArchive | 全文搜索 | ✅ 直接下载 | CJK 短语特判（繁→简→日→韩）；resolve 选文件：file_keywords 优先 → size 最大 |
| OpenLibrary | title/author 搜索 | → IA 映射 | 重定向到 IA 下载 |
| GoogleBooks | title 搜索 | ❌ 仅 meta | pdf downloadLink 稀有 |
| Libgen | title/author 搜索 | ❌ 仅发现 | links 指引人工下载；register 登记闭环 |

### resolve 选文件规则（InternetArchive）

1. 按 `file_keywords` 匹配（注入到 provider 层，目前仅 catalog 链路注入）
2. 无 keywords 匹配时按文件大小降序
3. 多卷册：无自动分卷处理（需人工干预或 catalog target 精确匹配）

## 四、成功率/准确率优化点分析

### 4.1 成功率瓶颈

| 瓶颈 | 当前行为 | 优化方向 |
|---|---|---|
| **query 构造** | mainline 用 `knowledge.name`（教程N：书名（作者））直搜 | 改用 decision 引用 title/original_title/authors 构造中英文双 query |
| **候选选择** | mainline 取第一个 downloadable，无评分无回退 | 引入 match_candidate 评分 + 候选队列逐个回退 |
| **渠道顺序** | 四来源固定顺序，无健康统计 | qt_sources 渠道记录 → 动态调整优先级 / 降级不可用渠道 |
| **resolve 选文件** | file_keywords 仅 catalog 链路注入；mainline 无 | 统一注入 file_keywords；多卷册自动分卷处理 |
| **重试策略** | 固定 3 次重试 | 基于渠道失败模式区分：网络错误→重试；404/封禁→切换渠道 |

### 4.2 准确率瓶颈

| 瓶颈 | 当前行为 | 优化方向 |
|---|---|---|
| **md5 校验** | 仅 IA 提供 md5 声明 | 全渠道 md5 声明对比；无声明时跳过而非失败 |
| **书名一致性** | 下载后不验证书名/作者 | inspect_pdf 提取首页文本 → fuzzy match 决定引用 |
| **页数/体积** | 仅最小页数阈值 | 增加最大页数/体积 sanity（防止错误文件） |
| **书行↔资源关联** | 依赖 Inventory JSON 的 catalog_target 字段 | qt_books.relative_path 直接关联（已有字段，mainline 链路使用） |

### 4.3 人工兜底路径

- Libgen 链路：搜索返回链接列表 → 用户手动下载 → `POST /books/{id}/register` 登记
- 所有链路失败后：用户可手动下载 PDF → `mainline register` 或 API register

## 五、验收标准提案（供裁决）

### 5.1 单本验收

| 检查项 | 口径 | 判定 |
|---|---|---|
| PDF 结构完整 | 魔数 `%PDF` + 页数 > 0 | 必须通过 |
| 指纹一致 | sha256 登记值与文件实际值一致 | 必须通过 |
| 来源留痕 | qt_sources 至少一条记录（channel + source_url） | 必须通过 |
| 书名匹配 | 决定引用 title/original_title 与 PDF 首页文本 fuzzy match ≥ 阈值 T | 建议通过（可配置阈值） |
| 不重复下载 | sha256 去重命中即复用，不创建新文件 | 必须通过 |

### 5.2 批量验收

| 指标 | 口径 | 目标（建议） |
|---|---|---|
| catalog 一次通过率 | catalog run 首次执行成功下载的 target 占比 | ≥ 80%（三基石课冻结目录） |
| mainline 首选候选成功率 | mainline download 首个候选即成功的占比 | ≥ 60%（当前约 30%~40%，优化后目标） |
| 渠道命中率 | 各渠道（IA/OL/GB/Libgen）搜索返回有效候选的占比 | 分渠道统计，IA 目标 ≥ 70% |
| 失败可重试率 | failed 后 retry 成功的占比 | ≥ 50% |

### 5.3 非功能验收

| 检查项 | 口径 |
|---|---|
| 零公网测试守护 | 默认测试不得访问公网；来源协议变化用固定 fixture 覆盖 |
| 冻结目录严格匹配 | catalog run 只处理冻结目录内 target；不确定候选不自动落盘 |
| TLS 默认开启 | 只能由用户显式配置关闭 |
| 数据根约束 | 所有下载文件必须在 QED_DATA_ROOT 内 |

## 六、REQ-020 承接声明

### REQ-020 ② 找得率榜单（承接）

根仓库 REQ-020② 要求"各来源渠道命中率/下载成功率实测统计，回填 QED-Tracker source-discovery 矩阵"。

**本次承接方式：**

1. **口径定义**：本节 5.2 的"渠道命中率"即为 REQ-020② 的"找得率"口径——各渠道搜索返回有效候选的占比
2. **数据源**：`qt_sources` 表的渠道尝试记录（每次 search/download 一条 source 行）
3. **执行时机**：下载流程优化执行轮（Phase 4 下载三门课时）产出基线数据
4. **回执方式**：基线数据产出后回执根仓库，标注"口径已定义、基线已采集"

**不单独建界面**：产出为统计数字，随下载流程文档一并交付。

### REQ-020 ① 权威性榜单（收窄建议）

根仓库 REQ-020① 要求"各教材/版本在数学社区权威性排序，服务第一轮评估选书"。

**当前状态：**
- 三基石课权威性已由 golden 范本（`docs/guides/course-tutorials-math-golden.json`）+ priors（`src/qed_tracker/prompt_lab/priors.py`）承载
- 其余 9 门进阶课 + 扩展课随 golden 扩展逐步沉淀
- LLM 探索管线（tutorials@v1/v2）自动产出经典地位 intro

**建议：** 收窄为"随课程扩展沉淀"，不单独立项。知会根仓库调整范围。

## 七、REQ-032 双轨登记

根仓库 REQ-032 要求"meta/ JSON 退役，元数据默认存数据库"。

**当前双轨状态：**

| 数据 | 事实源 | 用途 |
|---|---|---|
| `meta/resources/*.json` | Inventory JSON | catalog run / books-get 链路去重与登记 |
| `qt_books` + `qt_sources` | MySQL | mainline 三表链路登记 |
| `meta/selections/*.json` | Inventory JSON | 论文选择报告（paper discovery） |
| `meta/transfers/axiom/*.json` | Inventory JSON | Axiom 上传记录 |
| `meta/tasks/*.json` | Inventory JSON | 任务记录 |

**本次不推进退役：**
- 当前双轨在下载链路分析前可共存
- 下载流程优化轮可先利用 qt_sources 渠道记录产出找得率数据
- 退役作为独立架构重构轮（或并入 QED-011 重复下载验证后）

**登记事项：** 下载流程文档已记录双轨事实，后续重构时可追溯。

## 八、已知事实与缺口

| 编号 | 事项 | 性质 | 处置 |
|---|---|---|---|
| G1 | confirm 端点覆写陷阱 | 实现缺陷 | 本轮脚本回显规避；后续修端点语义（缺省=保留既有值） |
| G2 | course exploration_stage 回写缺口 | 设计-实现差距 | complete_knowledge 不回写 qed_course.exploration_stage；后续修复 |
| G3 | tmp/exploration 根契约冲突 | 治理冲突 | 根文档定义"用户资产不自动清理"；按用户指令已删除（正本在 QED-Tracker/tmp/）；待用户裁决：恢复副本 or 修订根文档 |
| G4 | mainline 书行 auto-create 粗糙 | 实现不足 | 用 knowledge.name 为 title、无 authors/version/ref；API fetch 链路已改为按书行 title+authors 检索（2026-08-28），CLI 链路待对齐 |
| G5 | file_keywords 注入不统一 | 实现不足 | 仅 catalog 链路注入；mainline/fetch 无；后续统一 |
| G6 | 知识行 8 条（含 CS 测试数据 1 条） | 预存数据 | 非本轮创建，不影响 math 播种；后续可清理 |
| G7 | qt_sources schema 漂移（旧 download_id 结构） | 已修复 | 2026-08-28 迁移 0014：旧表改名 qt_sources_legacy 留档后按 ORM DDL 重建；此前 add_source/list_sources 全部 500（Unknown column 'book_id'） |
| G8 | 8901 无自动下载执行器（点击下载后无后续动作） | 已修复 | 2026-08-28 方案 A：`book_download` 后台任务 + `POST /books/{id}/fetch`（见链路四）；每候选 600s 预算看门狗 |

## 九、开放问题

1. **confirm 端点语义修复**：是否本轮一并修复（缺省字段=保留既有值）？还是保持脚本回显规避，修复留给后续轮？
2. **course exploration_stage 回写**：是否在下载流程优化时一并修复 complete_knowledge → qed_course.exploration_stage 回写？
3. **REQ-020 ① 收窄知会**：是否由你直接告知根仓库维护者，还是本轮文档登记后统一处理？
4. **REQ-032 退役时机**：是否在下载流程优化后立即推进，还是保持待开始？
5. **tmp/exploration 根契约**：恢复副本到 dataset 侧 or 修订根文档？需要你裁决。
