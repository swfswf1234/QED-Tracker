# DeepTutor 机制调研（审阅稿）

状态：Draft
任务类型：调研（Plan 附属）
最后更新：2026-09-24
调研对象：`D:\coding\demo_program\DeepTutor`（外部开源项目，路径均相对该仓库根）
目标项目：QED-Tracker
关联设计：[下载管线设计](../design/download-pipeline.md)、[论文发现设计](../design/paper-discovery.md)、[探索管线设计](../design/exploration-pipeline.md)
关联任务：QED-067（编排/查询纪律/注册表形态）、QED-068（论文链路整合）、QED-069（下载链路评估）
归档判定：审阅后按用户裁决并入对应设计/计划或删除

## 调研范围

两部分：**I 检索与下载**（§1~3）、**II 知识路线整理与 LLM 编排**（§4，2026-09-21 补）。
本稿所有结论均以实际阅读源码为准，附文件路径佐证。

## 0. 全景

DeepTutor **不使用 LangChain**（仅 LlamaIndex 做可选 RAG，见其 `pyproject.toml`），
agent 编排为完全自研 agentic loop（OpenAI tool-calling + 文本 label 协议混合）。两大块：

- **I 检索与下载**：三条互不调用的独立链——检索（`deeptutor/tools/paper_search_tool.py` arXiv 元数据、
  `knowledge_frontier.py` LLM 派生查询、`web_fetch.py` 网页快照）；源文件下载
  （`tex_downloader.py` arXiv e-print TeX 源码，唯一真正的 arXiv 落盘通道）；
  入库（`reading/ingestion.py` URL 队列化摄取、`reading/store.py` 文件解析入库）。
- **II 知识路线与编排**：两条独立实现——`deeptutor/learning/` 掌握式学习路线
  （线性 module→knowledge point）与 `deeptutor/book/` 书引擎（概念图 + 先修边）；
  注册/编排形态见 `tools/builtin_specs.py`、`capabilities/`、`services/skill|mcp/`。

它没有我们五阶段链中的**匹配判定层**（不需要回答"这本书是不是要的那本"），也没有渠道/版权概念；
下载只面向"用户显式给了 URL/文件"。因此可借鉴的是**确定性零件与注册形态**，不是整条链。

## 1. 检索侧

### 1.1 arXiv 搜索工具（`tools/paper_search_tool.py`）

- 官方 `arxiv` 库客户端：`page_size=20, delay_seconds=3.0, num_retries=2`（L29~33），限速内置。
- 过量抓取再截断：`fetch_count = min(max_results*2, 30)`，先抓 2 倍量、过滤后取前 N（L72）。
- 阻塞请求包在 `asyncio.to_thread` + `wait_for(30s)`；**所有异常退化为空列表，绝不抛出**：
  超时→[]；HTTP 429→sleep(3) 单次重试再失败→[]；其他 HTTP 错误→[]（L84~110）。
- 后处理：`years_limit`（默认近 3 年）按发表年过滤；`arxiv_id` 取 `entry_id` 末段再
  `split("v")[0]` 剥版本（对含 `v` 的老式 ID 有隐患）；abstract 空白折叠；固定 8 字段输出。

### 1.2 查询派生与确定性 fallback（`tools/knowledge_frontier.py`）

「LLM 只出检索计划、确定性代码做清洗」的同构案例，与我们 LLM 顾问定位一致：

- LLM 要求返回 `{"queries": [...]}`（最多 3 条简短英文查询）；解析先正则抠第一个 JSON 数组
  （容忍周围散文）再 `json.loads`（`_parse_queries` L157~169）。
- 确定性清洗 `_clean_queries`：单行化、≤200 字符、≥2 词、大小写不敏感去重、截断至 3 条。
- LLM 失败/无有效查询 → 确定性模板 fallback：`[seed, "recent advances seed", "open challenges seed"]`
  （seed 取 focus 或首个文档名去后缀，L172~185）。
- 逐条查询执行，每条结果打 `source_query` 溯源；按 `(arxiv_id, title)` 小写去重；
  `query_plan.source: llm|fallback` 入 metadata 供审计。
- 产出是**只读报告**，末尾声明"推荐 ≠ 知识库内容，加入需人工动作"——发现与入库分离，与我们两轮审阅同型。

### 1.3 提示词查询纪律（`tools/prompting/hints/en/paper_search.yaml`）

对模型的硬纪律：**最多 3 个英文词**、不许整句、不许堆叠名词短语；
"**0 结果不许反复改写查询——换 web_search 或直接结束**"。

## 2. 下载侧

### 2.1 arXiv 源码下载（`tools/tex_downloader.py`）

- `https://arxiv.org/e-print/{id}`，普通 `requests.get(timeout=30)`；**无哈希、无大小上限、无限速**（反面）。
- 容器嗅探：先试 `tarfile.open` 再 `zipfile.ZipFile`，都不是则按单 tex 文件复制（L98~104）——
  e-print 确有 tar/zip/单文件三形态，嗅探顺序可借鉴。
- TarSlip 防护：逐 member 检查解包路径是否在目标目录内，越界跳过（L157~175）。
  缺陷：`os.path.commonprefix` 是字符串级而非路径级比较；**zip 分支完全无对应防护**（L177~180 直接 extractall）。
- 主 tex 三级启发：文件名 ∈ {main, paper, manuscript}.tex → 含 `\documentclass` → 最大 .tex。

### 2.2 网页抓取的安全面（`tools/web_fetch.py`）

设计前提写在 docstring：**"参数是模型决定的，不是人决定的"**，所以从严：

- 只收 http/https；`_is_disallowed_host` 对 IP 字面量 + DNS 解析出的**每一个**地址检查
  private/loopback/link-local/multicast/reserved/unspecified，DNS 失败也拒绝（fail-closed）。
- **手动逐跳跟随重定向**（≤5 跳），每一跳在连接**之前**重新校验 scheme+host；
  注释明确解释为何不用 `follow_redirects=True`（那样已连过中间主机才能检查）。
- `_bounded_read` 流式读取，超 4MB 立即停；正文截断 5 万字符带 `…[truncated]` 标记。
- 返回 `FetchOutcome(ok, markdown, url, title, truncated, error)`，错误是一行模型可读文案。
- HTML→文本双路：优先产品级 lxml 文章抽取，失败/精简安装退化为 regex 剥 tag。

## 3. 入库侧

### 3.1 URL 摄取（`reading/ingestion.py`）

- `normalize_url`（L609~627）：scheme/host 小写、path 补 `/`、丢 fragment；YouTube/Bilibili 归一为
  canonical 视频 URL（只留 id）。`url_material_id = sha256(normalize_url(url))[:16]`——
  **去重判定发生在抓取之前**。
- `queue_url` 只 upsert `status=QUEUED` 目录记录；异步 `process_url` 走
  QUEUED→PROCESSING(progress)→DONE/FAILED（error_code+detail 落库）；`retry` 按 kind 重放。
- 依赖注入：`ReadingIngestionService.__init__` 把 web_fetcher/loader/transcriber 全部可注入，
  默认注真实实现、测试传桩——与我们「默认测试零网络」门禁同一手法。

### 3.2 文件原子入库（`reading/store.py` `ingest()`，L221~359）

- `content_hash = sha256(bytes)[:16]` 直接作 material_id 与目录名：同字节天然幂等，
  重复 ingest 在每 id 文件锁下检查 manifest 完整性后直接返回。
- **staging→原子换入协议**：units/raw/outline 全写进带 uuid 后缀的 `.staging` 目录；
  **manifest 最后写**（注释：manifest 存在 = "此材料可用"的信号）；旧目录先 `os.replace`
  换出到 `.backup`，新目录换入失败则回滚 backup 再抛错——观察者永不见半写状态。
- 用户状态（批注/进度/书签）随重摄取迁移；EPUB 旧版升级若有批注直接抛冲突（旧 locator 不可安全映射）。
- 诚实性决策（L268~277 注释）：**PDF 拒绝从每页首行合成目录**——页首常是图注/页眉，
  当目录呈现是"主动误导"；PDF 要么用原生书签要么没有 outline。
- catalog 层（`reading/catalog_store.py`）material_id（标题/批注身份）与 content_id（共享字节）解耦，
  同一字节可有多个条目身份；SQLite `ON CONFLICT DO UPDATE` upsert。
- 搜索/去重 API：`POST /library/duplicate-check` 把 same_content（字节哈希）与
  same_name（同名不同内容→交人裁决）**分开报告**（`api/routers/reading.py`）。

## 4. 知识路线整理与编排（II，2026-09-21 补）

### 4.1 草稿→确认两阶段路线生成（对应我们 domain/courses 两步探索）

`learning/topic_generation.py`：

- **先 grounding 再生成**：每个来源先取 grounding——知识库走 `rag_search` top4 + 文档清单 inventory；
  单文件走**隔离子进程**抽文本（坏 PDF 不拖垮服务，L144~177），然后单次 LLM 出 JSON。
- **双模式校验 `materialize_modules()`**（L297~445）：草稿阶段 `strict=False`——坏条目丢弃并记入
  `discarded_modules`（含 index+reason）**返回给用户可见**；用户确认后落库阶段 `strict=True`——
  超限/坏条目**直接报错而非静默截断**。
- **coverage 报告**（`_coverage_report` L484 + prompts `materials` 逐字引用文档名 + `must_cover`
  重生成头）：程序化核对"路线是否覆盖了用户给的每份材料"。
- **上限随材料规模伸缩**：`module_limit_for(sources)`（L447），硬顶 `MAX_MODULE_LIMIT=20`
  防"路线退化为目录"。
- 数据模型（`learning/models.py`）：`LearningModule`（一句话 `objective` 作为后续 revise 的契约）、
  `KnowledgePoint` type 闭集（memory/concept/procedure/design）、pydantic `extra="ignore"` +
  `_missing_` 做旧中文枚举兼容——**无 schema 版本字段**，新字段靠默认值免迁移（与我们口径冲突，见不照搬）。

### 4.2 概念图 + LLM 自审 + 程序化兜底（`book/` 书引擎）

- 五阶段状态机（`book/models.py`：DRAFT→SPINE_READY→COMPILING→READY），逐 block 断点续编；
  `compiler.py::systemic_failure_reason` 区分"账号/配额坏了（全局熔断）"vs"这一页坏了（局部跳过）"。
- `book/agents/spine_synthesizer.py`：spine 生成 = **draft → critique → revise** 循环
  （L15~17、L114~170）——critique 是第二次 LLM 调用，输出结构化
  `{verdict, issues:[{category: coverage|ordering|granularity|redundancy|cycle, fix_hint}]}`；
  revise 消化批评后再进下一轮。
- **程序化兜底**：物化时 `_remove_cycles()`（DFS 找环删最弱 `depends_on` 边，L626~627）+
  `_topological_sort()` 重排章节——LLM 自审之后仍有确定性图校验把关。
- 溯源与省钱设计：`ExplorationReport` 多查询一次性并行检索后**持久化复用**，下游各阶段不再重查
  （`book/models.py` L384）；`Chapter.source_anchors` 锚定来源。

### 4.3 注册表与工具面白名单（对应我们 skill 注册表 + MCP 设计）

- **import-free 声明目录**：`tools/builtin_specs.py` 用 `BUILTIN_TOOL_SPECS` 元组声明全部内建工具
  （`name → "module:Class"` 字符串），注册表构建**不 import 工具模块**；懒加载时核对
  `tool.name != spec.name` 即抛"catalog drift"错误（L25~43）——声明与实现漂移守护。
- **LoopExtension 协议**（`capabilities/protocol.py`）：`is_active(context)` 门控 +
  `system_block / augment_kwargs / pre_loop` 钩子；`augment_kwargs` 由**服务端注入私有参数**
  （course_id、连接配置、预算），模型永远不供给身份/配置参数；`KnowledgeCapability` 子类
  `exclusive_tools=True` **整轮替换工具面**（白名单接管），普通能力只做加法。
- 工具面组合集中在 `agents/_shared/tool_composition.py`：一张「工具名→上下文条件」表驱动自动挂载；
  research 阶段用显式 `RESEARCH_BLOCK_TOOL_ALLOWLIST` 只读白名单（写类工具被排除）。
- **MCP**（`services/mcp/config.py` L49~96）：每 server `enabled_tools` 白名单（默认 `["*"]`）
  + blocklist + `tool_allowed()` 双名匹配；`manager.py` 把 MCP 工具标 `deferred`——
  schema 不进初始工具列表，经 `load_tools` 按需注入（渐进披露省 token）。
- **Skill 注册表**（`services/skill/service.py` 头部 docstring + L31~34）：`SKILL.md` +
  YAML frontmatter（`name/description/always/requires.{bins,env,sandbox}` 可用性门）；
  系统提示只放每 skill **一行 manifest**（`render_skills_manifest`），任务匹配时模型调
  `read_skill` 取全文；`read_skill` 载荷有硬顶防大文件灌爆上下文；user/builtin 双层目录；
  外部导入有扩展名白名单、体积上限、`.hub-lock.json` 溯源。

### 4.4 LLM 输出契约与容错

- prompt 全部 YAML colocated（`learning/prompts/{en,zh}.yaml`、`book/prompts/en/*.yaml`），
  `services/prompt/manager.py` 单例 + 语言 fallback 链（zh-tw→zh→en），**无版本号靠 git**。
- JSON 解析多级策略（`utils/json_parser.py`）：直接 loads → 提 markdown fence → 剥 `<think>` 块 →
  `raw_decode` 取**最长**可解码 JSON（防推理里的 schema 示例片段抢答）→ `json_repair` 兜底 → fallback。
- **全项目唯一重试规则**（`services/llm/structured_retry.py`）：reasoning 模型思考耗尽 max_tokens
  导致空 JSON 时，一次"调低 reasoning effort 重问"，`is_usable` 回调由调用方定义——
  对应我们两步探索的"空/截断 JSON"故障模式（曾以 max_tokens 下限缓解）。

### 4.5 多 agent 审阅流（与我们两轮审阅同构，作印证）

deep research 四相（`agents/research/pipeline.py` 头部）：Rephrase（仅 ask_user 工具、≤3 轮）→
Decompose 子题 → **OUTLINE 预览返回、用户确认后带 `confirmed_outline` 重跑同一管线** →
每子题独立 agentic block loop（APPEND 可动态扩队）→ 分节合成 + `CitationManager` 统一引文锚定。
subagent 委派外部 CLI agent 带**每轮 consult 预算**（剩余次数写进结果），完成后要求
"用自己的口吻总结、不得转述"。

## 5. 借鉴点 → QED-Tracker 落点对照

| # | DeepTutor 机制 | 我们的落点 | 建议级别 |
| --- | --- | --- | --- |
| 1 | LLM 查询计划：严格 JSON 解析→确定性清洗（≥2 词/去重/≤3 条）→失败模板 fallback→`source_query` 溯源 | `providers/bailian.py` / `book_advisor.py` 检索词变体产出后的校验层（QED-067 管线 config loader 的 validate 步骤同型） | 并入 QED-067 设计 |
| 2 | 提示纪律「0 结果不许反复改写；最多 3 个英文词」 | 顾问 prompt 模板规范（`prompt_lab/templates.py` 注释口径 + paper-discovery 设计文档） | 并入 QED-068 评审 |
| 3 | URL 规范化→哈希前置去重（抓取之前判重） | `providers/arxiv.py` 落地名/URL 键 + `downloader.py` 去重前置 | 登记 QED-069 候选 |
| 4 | duplicate-check 分报 same_content / same_name（歧义交人） | 下载提交前的重复检测响应口径（8901 任务提交面） | 登记 QED-069 候选 |
| 5 | web_fetch：逐跳重定向 SSRF 复检 + 流式硬顶 + 模型可读错误 | `downloader.py`（当前依赖 requests 默认 follow_redirects，无逐跳复检） | 小改进，登记 QED-070 台账评估 |
| 6 | e-print 容器嗅探顺序 + TarSlip 路径级检查（修正其 commonprefix 缺陷后采用） | `downloader.py` / 未来 TeX 源支持 | 存档观察（无 TeX 需求则不动） |
| 7 | staging→manifest-last→双 rename 回滚的原子入库协议 | `application/resources.py` 落盘登记路径（当前为写文件+DB 双轨，可对照检查半写窗口） | 存档观察，QED-069 评估 |
| 8 | PDF「拒绝合成目录」诚实性 + 首页文本校验升级（解析器签名进缓存键） | `downloader.verify_content()`（QED-066 已落软信号；升级方向记录） | 存档观察 |
| 9 | arXiv 过量抓取（2x，上限 30）+ years 过滤 + 429 单退避 | `providers/arxiv.py` 检索参数 | 并入 QED-068 评审 |
| 10 | 摄取服务全依赖注入（fetcher/loader 可注桩） | 我们测试已是同型做法（`httpx.MockTransport`） | 无需动作（印证） |
| 11 | 双模式校验：草稿 `strict=False` 丢弃+`discarded` 可见 / 确认 `strict=True` 报错不截断 | apply-results / confirm 阶段的 validate 分档（QED-067 pipeline YAML 的 `validate` 字段语义） | 并入 QED-067 设计 |
| 12 | coverage 报告：程序化核对产物是否覆盖输入材料清单 | courses 产出「名校教材不得遗漏」预检 + tutorials 审阅轮 | 并入 QED-067 设计 |
| 13 | 输出条数上限随材料规模伸缩（硬顶防退化为目录） | domain/courses 模板 max_tokens/条数按域规模调参 | 并入 QED-067 设计 |
| 14 | draft→critique→revise LLM 自审 + `_remove_cycles`/拓扑排序程序化兜底 | tutorials 产出后自动预检（引用完整性/重复/顺序） | 并入 QED-067 候选（成本敏感，可后置） |
| 15 | import-free 字符串注册表 + 装载时 name 漂移即抛错 | skill 注册表 / pipeline config loader 的声明-实现一致性守护（QED-067-3） | 并入 QED-067 设计 |
| 16 | `augment_kwargs` 服务端注入身份/配置/预算参数，模型不供给 | MCP 工具调用边界：参数由管线持有而非 LLM——与「模型不写资源事实」同型，显式写进设计约束 | 并入 QED-067 设计 |
| 17 | MCP 每 server `enabled_tools` 白名单 + `deferred` 渐进披露 | QED-067 MCP 配置形态（server 级白名单已有；deferred 可选） | 并入 QED-067 设计（白名单）/观察（deferred） |
| 18 | skill frontmatter `requires.{bins,env,sandbox}` 可用性门 + 一行 manifest + 按需 read 全文 + 载荷硬顶 | QED-067 skill 注册表字段设计 | 并入 QED-067 设计 |
| 19 | 唯一重试规则：空/截断 JSON 时降 reasoning effort 重问一次 | 两步探索截断故障的对症策略（现为 max_tokens 下限，可叠加） | 登记 QED-070 台账评估（依赖网关是否透传 reasoning 参数） |
| 20 | 阶段级只读工具白名单（research block allowlist）+「大纲预览→确认重跑同一管线」 | 与我们两轮审阅/按步收窄工具面同构 | 无需动作（印证设计成立） |

## 6. 不照搬清单

1. **浏览器/客户端预计算 content_id 供去重**：哈希来自调用方声明；我们必须以服务端字节哈希为唯一事实。
2. **knowledge_frontier「LLM 查询→直接搜」无匹配判定直通**：我们五阶段链必须保留 LLM 匹配判断 + 相似度软信号双闸。
3. **`tex_downloader.py` 下载细节**：无哈希/大小校验、zip 无 path traversal 防护、无限速节流——只取
   TarSlip 思路（并修正为路径级比较）与主 tex 三级启发，其余为反面样本。
4. **YouTube/Bilibili/ffmpeg 分块 STT 链**与教材 PDF 获取无关；PageIndex 是第三方 RAG 引擎适配，本项目不引。
5. **异常全退化为空列表**（1.1 的搜索错误策略）：我们任务链需要失败可见（`qt_tasks.error` / `explore_pending.error`），不能吞错返回空。
6. **自研 label 协议循环**（THINK/TOOL/APPEND/FINISH 文本协议 + 巨型 agent_loop + 大量 `getattr` 可选钩子）——正是我们 QED-067 要用 LangChain LCEL 替换的对象，钩子扩散导致语义难推理。
7. **additive 工具面默认**（能力在 chat 全量工具面上做加法）——我们每个 LCEL 步骤直接声明最小只读白名单，只取 `exclusive_tools` 整轮接管思路。
8. **mastery 的事件溯源 + 路径租约 + 每问交互状态机**（`learning/models.py`）——为多人实时会话设计，我们「一次生成→人审→入库」批处理用不上。
9. **无 schema 版本的 pydantic `extra="ignore"` 契约**——我们课程/教程 JSON 是长期重放与 diff 的入库契约，应保留显式版本口径（现 templates `@vN` 纪律不变）。

## 7. 审阅问题与裁决记录

1. ~~落点表 #1/#2/#9（检索侧）是否并入 QED-067/QED-068？~~ **已裁决（2026-09-21）**：
   并入 [QED-068 计划](2026-09-14-paper-pipeline-alignment.md)（068-1/068-2/068-3），
   fallback 语义与 `years_limit` 默认 3 已经用户确认。
2. 落点表 #3/#4/#5/#7（下载/入库侧）并入 QED-069 评估，还是仅存档观察？
   （#3/#5 已先行并入 QED-068-4 收口轮；#4/#7 待裁）
3. 落点表 #11~#18（知识路线/编排侧）是否按标注并入 QED-067 计划设计章节（尤其 #16 工具参数边界与 #18 skill frontmatter 字段）？#14/#19 是否后置？
4. 本稿关闭形态：审阅后删除（差异 Git 保留）、并入对应设计文档，还是保留为独立调研基线？
5. **链条登记（2026-09-24）**：三主线与 v1.0 交付口径已经链条评审确认，本稿遗留待裁项
   （#4/#7、#11~#18 归属，问题 2/3）集中收口于
   [v1.0 后续任务链条梳理](2026-09-24-v1-task-chain.md)批次 0/裁决表，须在该表 D 批次
   （069 细化）与 B 批次（067 设计章节定稿）前完成裁决；问题 4 留待各收尾轮按 ADR 0009 判定。
