# 本地 LLM 模型对接与 LangChain 编排（local-llm-langchain）

状态：Draft（设计细化完成，待用户评审；2026-09-24 补 v1.0 交付口径裁决）
任务类型：Plan
最后更新：2026-09-24
需求方：用户（学习优化本地小模型；2026-09-21 补充裁决：LangChain 编排 + 声明式 pipeline/skill/MCP 配置）
目标项目：QED-Tracker
评审方：用户
关联设计：[服务管理中心设计](../design/service-management.md)（模型模式与密钥分置）、[论文发现设计](../design/paper-discovery.md)（LLM 顾问边界）、[探索管线设计](../design/exploration-pipeline.md)（prompt 模板与两轮审阅）
关联 Tracker：QED-067
归档判定：待关闭时按 [ADR 0009](../history/adr/0009-closed-plan-archival.md) 做 Retain/Delete 两态判定

## 目标与成功标准

v1.0 主线：QED-Tracker 以 **8900 网关（`qed-engine` 模式）** 接入 QED-Engine 本地文字模型
（qwen3.5 9B），prompt/pipeline 以 **LangChain（LCEL）** 编排，编排流程由**声明式配置**
（pipeline YAML + skill 资产 + MCP 工具白名单）定义。本任务是「学习优化本地小模型」的一环。

成功标准：

1. `qed-engine` 模式经 8900 网关调用本地 qwen3.5 9B 成功，调用记录落 `qed_llm_calls`
   （含 task/step 留痕，见「可观测与审计」）。
2. 至少一条示例链路（领域探索 agentic 链路，见「设计」）以 LangChain + 声明式配置跑通，
   默认测试全 mock（假模型 + fixture 检索结果）且门禁全绿。
3. pipeline / skill / MCP 三类配置的 schema、加载校验与注册语义成文（本计划即承载体），
   并同步进 `design/`（评审通过后按 [ADR 0003](../history/adr/0003-pending-design-location.md) 晋升）。
4. 模型文件、生命周期、网关归 QED-Engine；本仓只做接入与编排；「模型不直接下载、
   不写资源事实」强制约束不破。

## 交付口径与外部依赖裁决（2026-09-24，链条评审轮）

- **v1.0 口径**：本计划 067-1~5 **全量交付**（含 067-5 真实冒烟 + A/B 对照评审）是 v1.0
  三主线口径中主线①的交付定义；批次归属见 [v1.0 任务链条梳理](2026-09-24-v1-task-chain.md)。
- **REQ 时机**：067-1 冒烟若确认 8900 网关不支持 `task/step` 透传，须**在 A 批次内立即**
  向根仓库提 REQ（给根侧留排期窗口），不留到 067-5。
- **降级边界**：REQ 届期未回填时，067-5 真实链留痕可降级为仅 `prompt_template` 口径——
  **降级须用户裁决，不得静默砍项**。

## 现状

- 本仓 `src/qed_tracker/llm_client.py`：统一兼容层，`QED_API_SELECT` 路由——`local`/`api` =
  direct 直连 dashscope，`qed-engine` = HTTP 调 8900 `POST /api/v1/llm/text`（不接触密钥）。
  自身 `.env` 当前 `QED_API_SELECT=qed-engine`、`QED_MODEL=deepseek-v4-flash-0731`。
- QED-Engine 根 `docs/design/llm-gateway.md`：网关按根 `.env` `QED_API_SELECT`（api/local）路由；
  local 走 LM Studio（`QED_QWEN_URL=http://127.0.0.1:5001/v1`）。
  `docs/design/local-model-management.md`：`/models/qwen` 生命周期 + 根 `model/` 模型目录。
- **无 LangChain 依赖**（`pyproject.toml`）；prompt 为手写模板：`src/qed_tracker/prompt_lab/templates.py`
  （domain@v4 / courses@v8 / tutorials@v2）+ advisor（`providers/bailian.py`、`providers/book_advisor.py`、
  `main_line/advisor.py`）。
- 根仓库已有学习笔记 `docs/learning/langchain-notes.md`。

## 范围与非目标

- 范围：本仓模型接入（`qed-engine` 网关口径）、LangChain 编排层与声明式配置
  （pipeline/skill/MCP 白名单）、领域探索示例链路设计 + 试点实现。
- 非目标：模型权重/训练/量化、模型文件与生命周期管理（归 QED-Engine）；不改动
  `qed_llm_calls` 表结构；不替换现有 domain@v4/courses@v8 生产链路（新链路与旧链路并行
  A/B，替换与否由用户评审）；不引入 langchain 社区集成包（只依赖 `langchain-core`）。

## 前置条件

- QED-Engine 本地 qwen3.5 9B 服务与 8900 网关可用（根仓库侧）。
- 根 `.env` 模式与模型名确认。
- 网关 `POST /api/v1/llm/text` 如需按编排步骤落 `qed_llm_calls.task/step` 扩展列，
  涉及根仓库契约增量 → 按[跨项目协作规范](../standards/cross-project-collaboration.md)
  先提 REQ（工作项 1 内确认现有载荷字段后再定）。

## 设计：LangChain 编排层（本阶段方案，待评审）

### 分层与不变量

```
业务调用方（探索管线 / advisor / 新 orchestration 入口）
  ↓ 只依赖编排接口
编排层 orchestration/（新模块）
  ├─ 声明式配置加载：pipeline YAML → LCEL Runnable 链（RunnableSeq/RunnableLambda）
  ├─ LLM 步：PromptTemplate → LlmChatModel（BaseChatModel 适配）→ 结构化 OutputParser
  └─ 工具步：Tool 抽象 —— 仓内只读检索工具 / MCP 只读检索工具（白名单来自配置）
  ↓
llm_client.LlmClient（**不改**：direct/gateway 路由、密钥边界、预算、qed_llm_calls 审计行为）
```

- **编排层不绕过 `llm_client`**：`LlmChatModel` 是 `langchain_core.chat_models.BaseChatModel`
  薄适配，`_generate()` 内部调 `LlmClient.complete()`；因此 8900 网关/dashscope 直连、
  gateway 模式由网关统一写表的既有语义原样保留。
- **模型不落地事实**：编排链输出仍是**可审阅报告**（与探索管线同构的 report 结构），
  落库与状态推进继续走 apply-results / 两轮审阅（见[探索管线设计](../design/exploration-pipeline.md)）；
  工具步只读取证，下载与登记只能由确定性服务执行（AGENTS.md 强制约束）。
- 回滚不变量：编排层是新增旁路，旧链路逐字保留（见「回滚」）。

### 声明式配置三件套

1. **pipeline 配置（YAML，编排包内 `pipelines/` 目录）**——一条编排链的唯一流程事实源：

   ```yaml
   name: domain-exploration          # 链名
   version: 1                        # register() 拒低版本覆盖（沿 prompt_lab 语义）
   task: domain_explore              # 写 qed_llm_calls.task 留痕
   steps:
     - id: wiki_lookup              # step 标识（写 qed_llm_calls.step）
       kind: tool                   # tool | llm
       tool: wikipedia.search       # MCP/仓内工具名（须在工具白名单注册表）
       args_from: [domain_name]     # 输入绑定
     - id: domain_synthesis
       kind: llm
       template: domain-agentic@v1  # 引用 prompt_lab 模板编号（不复制文案）
       tools: [wikipedia.search, webfetch.university_page]  # 该 llm 步可用工具
       max_tokens: 16384
       validate: domain_report_v4   # 复用/扩展模板 validate
   edges: [[wiki_lookup, domain_synthesis]]
   ```

   加载器做 schema 校验（未知字段/未知工具名/未知模板编号 → 启动即失败），
   与 `prompt_lab.register()` 同一套「编号 + 版本」治理；每次 llm 步沿现有规则写
   `qed_llm_calls.prompt_template`。
2. **skill**——可审阅的「怎么做」资产包：`{pipeline 引用 + 模板编号 + priors 引用}` 注册表
   （`prompt_lab` 现有 templates/priors 不动，skill 只引用编号不复制正文）。评审 skill
   即评审这三者的组合，模型判断留痕仍只落 `qt_sources`/`qed_llm_calls`。
3. **MCP 配置**——外部工具服务器与**每链只读工具白名单**（`.env` 声明 MCP server，
   pipeline YAML 的 `tools` 字段收敛调用面）；默认空即纯 LLM 链。TLS/网络约束沿
   [测试门禁](../standards/testing.md)：默认测试不访问公网，工具层以 fixture mock，
   真实连通性由人工冒烟。

### 示例链路：领域探索（第一个 agentic pipeline）

用户给领域名 → 编排链产出「该领域的定义 + 更好的定义评估 + 课程编排」可审阅报告：

| 步骤 | kind | 内容 |
| --- | --- | --- |
| 1 `wiki_lookup` | tool | 维基百科：该领域条目是否存在 → 领域定义原文；扫描是否有**更优定义**（别名/相关条目） |
| 2 `university_lookup` | tool | 对 MIT / Stanford / 清华 逐一检索其公开课程页/OCW：该领域的定义表述 + 课程安排（课程名、顺序、先修） |
| 3 `domain_synthesis` | llm | 综合 1~2 步证据 + `domain@v4`/`courses@v8` 语义：输出领域定义、定义评估意见、课程编排建议（report 结构与现行领域探索报告兼容，仍走两轮审阅） |

与现行两步模板管线的关系：**并行试点、A/B 对照**（现行管线是生产链，不动）；
新模板按 prompt_lab 规则编号（`domain-agentic@v1`），验证有效后由用户评审是否替换。

### 可观测与审计

- LLM 步：direct 沿用 `LlmClient._record_call`；gateway 由 8900 网关写表——编排层把
  `task/step` 随调用透传（依赖前置条件的根仓库 REQ，若网关暂不支持则先只透传
  `prompt_template`，task/step 落痕记入联调遗留）。
- 工具步：每次调用在编排运行产物中留 trace（工具名、入参摘要、fixture/真实标记），
  与报告一并作为审阅材料；不新增表。

## 工作项（子任务 QED-067-1~5，均承载于本计划）

1. **067-1 网关端到端验证**：`qed-engine` 模式真实冒烟本地 qwen3.5 9B + `qed_llm_calls`
   落库核对；确认现有网关载荷支持的留痕字段，必要时向根仓库提 REQ。
2. **067-2 LangChain 依赖与适配层**：`langchain-core` 入 `pyproject`；`LlmChatModel` 适配
   + LCEL 最小链；测试用 fake chat model，不触网（TDD）。
3. **067-3 声明式配置加载器**：pipeline YAML schema、加载校验、`register()` 版本语义、
   skill 注册表；定向单测。
4. **067-4 领域探索示例链路（mock 全链）**：三步链路以 FakeChatModel + fixture 检索结果
   跑通，报告结构与两轮审阅载荷兼容。
5. **067-5 真实 MCP 只读工具接入 + 人工冒烟**：wikipedia/university 检索工具经 MCP 或
   仓内 provider 接入（只读白名单），真实冒烟记录按[操作指南](../guides/operations.md)
   登记；与 domain@v4 产物 A/B 对照报告供评审。

## 验证与验收

- 默认测试不访问公网/本地模型；用假顾问或 `httpx.MockTransport` + fake chat model +
  工具 fixture（见[测试门禁](../standards/testing.md)）。
- 真实冒烟记录（时间/模型/结果）按[操作指南](../guides/operations.md)要求登记。
- 全量门禁按[开发指南](../guides/development.md)执行；文档同步 code-map 新模块登记。

## 回滚

LangChain 为新增旁路（orchestration 模块 + 配置），保留原 `llm_client` 直调路径与现行
模板管线不动；回滚 = 停用编排入口，业务链路无感知。

## 关闭与归档

关闭时按 [ADR 0009](../history/adr/0009-closed-plan-archival.md) 做 Retain/Delete 两态判定；
设计确定后按 [ADR 0003](../history/adr/0003-pending-design-location.md) 晋升
`design/`（建议落点名 `orchestration-langchain.md`，先查 `design/index.md` 职责登记处）。
