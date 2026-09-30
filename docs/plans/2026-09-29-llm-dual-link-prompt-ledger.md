# LLM 双链路口径与 prompt 资产台账（llm-dual-link-prompt-ledger）

状态：Draft（2026-09-29 用户改判后新建，待用户评审；评审通过后第 3、4 节的口径晋升进 `docs/design/`）
复核口径：第 2、5 节于 2026-09-29 **按工作树实况二次复核**（同日并行会话曾落地 QED-072 W-8 步骤 4 把论文模型面删净，随即又整体撤回，见 2.4）；本文件登记实况，不登记 072 计划的应然描述。
任务类型：Plan
最后更新：2026-09-29
需求方：用户（2026-09-29 裁决：当前阶段用本地模型做优化，API 链路（含百炼）作**备用与对比**，
两条链路都保持可用；**v1.0 及之前版本默认只使用本地模型**）
目标项目：QED-Tracker
评审方：用户
关联 Tracker：QED-074（本计划）；取代 [QED-072](2026-09-28-bailian-retire-local-only.md) 的
D-1/D-3「完全屏蔽百炼、通路唯一」与 D-7「论文两条内联 prompt 直接删除」；
关联 QED-073（探索链本地化）、QED-067（本地模型 + 编排）、QED-068（论文链路）
关联设计：[论文发现设计](../design/paper-discovery.md)、[服务管理中心设计](../design/service-management.md)、
[主线路径设计](../design/main-line-curriculum.md)、[探索链设计](../design/exploration-pipeline.md)、
[共享表架构](../architecture/database-shared-tables.md)（`qed_llm_calls` 留痕面）、
[模块映射](../architecture/code-map.md)
关联 ADR：[ADR 0003 暂定设计落点](../history/adr/0003-pending-design-location.md)、
[ADR 0009 关闭计划归档](../history/adr/0009-closed-plan-archival.md)
归档判定：待关闭时按 ADR 0009 做 Retain/Delete 两态判定（预期 Retain：本文件是 prompt 资产
台账与双链路对比口径的事实源）

## 1. 目标与成功标准

把「LLM 从哪来」与「LLM 说什么」两件事一次理清：

1. **口径纠正**：QED-072 的立案前提是「百炼退役 + 本地独占 + 通路唯一」，与用户 2026-09-29
   的实际规划不符。本计划把它改判为「**默认本地、双链路可用**」，并逐条列出受影响的成功标准、
   工作项与待裁项，避免「文档说删净、代码要留备用」的裂口。
2. **台账成立**：全仓每一条 LLM prompt（含注册表条目、内联 prompt、修复重试骨架、编排实验
   模板）都有唯一一行记录：编号 → 定义位置 → 调用点 → 上游入口 → 可达链路 → 处置。台账与
   `tests/test_prompt_template_ids.py` 的守护断言一一对齐，新增调用点若漏登记直接红。
3. **对比可用**：给出「同 payload 双跑」的对比取证方法（本地 vs API 两侧的契约一次通过率、
   repair 次数、耗时、正文规模、判定一致性），并确认两侧留痕可比对（`service/mode/provider/model`
   列即区分键）；对比所需的最小改造（若有）列成工作项，不在本计划内偷跑实现。
4. **默认不变**：`v1.0 及之前` 的默认配置、默认测试与文档示例都指向本地链路；API 链路只在显式
   切换时生效，且不得成为任何默认路径的依赖。

### 非目标

- 不改根仓库任何文件（网关载荷字段、registry 模型参数等只提请求，交用户执行）。
- 不在本计划内做 prompt 文案优化（属 QED-073）与真实抓取（属 067-5）。
- 不引入第二只本地模型，也不新增云端供应商；「API 链路」＝现有 dashscope 兼容直连分支。
- 不动数据根；默认测试零公网。

## 2. 现状勘察（逐 file:line，2026-09-29 复核）

### 2.1 通路：单点双分支，选择权在 `api_select`

| 事实 | 位置 | 说明 |
| --- | --- | --- |
| 全仓 LLM 字节只经一个出口 | `llm_client.py:104` `LlmClient.complete(messages, *, prompt_template="")` | 四处 advisor + 两条 pipeline + 编排适配层都汇聚到这里 |
| 分支判据 | `llm_client.py:98` `is_gateway = api_select == "qed-engine"` | 其余值（`local`/`api`）走直连 |
| 直连分支 | `llm_client.py:115` `_direct_complete` → `POST {base_url}/chat/completions` | `base_url` 默认 dashscope 兼容端点（`:31`），`temperature: 0` 硬编码（`:130`），Bearer `API_KEY` |
| 网关分支 | `llm_client.py:169` `_gateway_complete` → `POST {gateway_url}/api/v1/llm/text` | 载荷只有 `prompt/system/max_tokens/prompt_template` 四字段 |
| 直连侧留痕 | `llm_client.py:205` `_record_call`（`mode="api" provider="qwen"`），仅当注入了 `engine` 时写 | 网关侧由 8900 代写（`mode=local provider=lmstudio`） |
| 网关载荷压平 | `llm_client.py:170-171` | `system`=首条 system，`prompt`=**最后一条** user；多轮/修复上下文在网关侧只剩最后一轮 |
| 后端选择配置 | `config.py:53` `api_select`（`QED_API_SELECT`，默认 `local`）、`:54` `llm_gateway_url`、`:48` `llm_model`、`:49` `llm_base_url`、`:50` `llm_timeout_seconds`、`:51` `llm_call_budget`、`:52` `llm_max_tokens` | 根 `.env` 现值：`QED_API_SELECT=qed-engine`、`QED_MODEL=deepseek-v4-flash-0731`；`QED_LLM_BASE_URL`/`QED_LLM_GATEWAY_URL` 未设 → 取默认（直连即指向 dashscope） |
| 直连前置 | `providers/bailian.py:194`、`providers/book_advisor.py:158`、`main_line/advisor.py:104` | 三处同一条件式 `if not is_gateway and not configured: raise`——**网关模式免 `API_KEY`，只有直连模式要求**；这正是「备用链路」的既有闸门，改判后**保留**，DL-1 默认本地不受它约束 |

结论：**双链路能力在代码里从来没有被拆掉**，QED-072 的 W-4「direct 分支移除」是尚未执行的计划项，
因此口径改判不需要回滚代码，只需要改计划与文档，并把「默认值」这件事写死。2026-09-29 的「删除落地又撤回」事件（2.4）从反面印证了这一点：被删的从来不是**通路**，而是**通路上的一只 advisor 实现**——删之即断链（`papers recommend` 当场抛错、10 处文档引用转红），而恢复只能靠回滚，配置层无路可达。
所以 DL-2 的保护对象是 advisor 实现，不只是 `llm_client.py` 的分支。

### 2.2 prompt 定义：注册表 6 条（两文件），游离面 5 个编号

注册表（`register()` 拒低版本覆盖，`template_id = f"{task}/{step}@v{version}"`）当前 **6 条，分居两文件**：`prompt_lab/templates.py` 三条探索链（`:201/:323/:520`，注册 `:365-366`、`:566`）+
`prompt_lab/advisor_templates.py`（**未进 git 索引的新文件**）三条顾问链（`:48/:98/:164`，注册 `:174-176`）。
顾问三条是 QED-072 W-8 步骤 3 从 advisor **手抄迁入**的产物，版本号未动，因此历史留痕仍可按 `prompt_template` 比对；消费形态已是注册表驱动的 `template.messages(payload)` +
`template.validator(payload)`（`book_advisor.py:101/:139`、`main_line/advisor.py:85`），即 072 W-8「校验工厂」的目标形态部分落地。

游离面：2 条论文 prompt 仍内联在 `providers/bailian.py`、3 个 agentic 编号在编排实验层。守护测试
`tests/test_prompt_template_ids.py:137-143` 用 5 条豁免把游离面显式化，`:168-177` 钉死注册表清单，`:180-183` 反向禁止豁免清单留失效条目。

### 2.3 与 QED-072 假设不符的三处实测事实

1. **`max_tokens` 对探索链不可配**：`prompt_lab/pipeline.py:69` 与 `:261` 把值钳到 `≥16384`，
   覆盖 `settings.llm_max_tokens=4096`。本地窗口若为 16384，则该下限＝整窗，任何 prompt 正文都
   挤不进；这是 QED-073 的冲突项，也是双链路对比时必须先固定的变量。
2. **repair 复用同一 `prompt_template`**：四处修复重试（`bailian.py:186`、`book_advisor.py:151`、
   `main_line/advisor.py:97`、`explore_advisor.py:119`）都用失败调用原编号，留痕上分不出首试与修复。
3. **dry-run 在直连侧不写留痕**：`api/main.py:1421/:1460` 传 `engine=None`，而 CLI 与路由文档都
   宣称「唯一痕迹是 `qed_llm_calls`」——只有 `qed-engine` 模式成立。对比取证必须知道这一点。

### 2.4 删除已落地又撤回：一次实况演练（2026-09-29，工作树证据）

本次改判（DL-2）落地前，并行会话已经把 QED-072 W-8 **步骤 4**（Q72-f 的 A 形态：类、两条 prompt、
测试一并删净）执行过一次，随后整体撤回。两侧证据都可复核：

| 时点 | 实况 | 证据 |
| --- | --- | --- |
| 删除窗口内 | `providers/bailian.py`、`tests/test_bailian_advisor.py` 消失；`recommend()` 入口抛「论文推荐暂无可用模型面（QED-072 W-8 删除 paper-plan prompt，待 QED-068 S3 重建）」 | 本会话内的第一次工作树读取：`git status` 列 ` D` 两文件 + `application/papers.py:119` 抛错文本（撤回后该行已不存在） |
| 删除窗口内 | `tests/test_documentation.py::test_current_code_and_test_references_resolve` **红**：`AGENTS.md`、`architecture/code-map.md`、`architecture/system-overview.md`、`design/paper-discovery.md`、`design/service-management.md` 共 **10 处**引用已删文件 | 该轮 pytest 输出（10 条 `-> src/...bailian.py` / `-> tests/test_bailian_advisor.py`） |
| 撤回后 | `providers/bailian.py` 与 `llm_client.py` 回到 HEAD 状态（`git diff` 空）；`recommend()` 抛错消失；上述文档测试转绿 | `git status` 不再列这两文件 + 复跑 `test_documentation.py` |
| 撤回后 | 守护测试豁免清单回到 5 条，且论文两条的去向注记**已改写为指向本计划**：「QED-074 W-2 迁入注册表（2026-09-29 改判：D-7 的删除裁决作废，空窗取消）」 | `tests/test_prompt_template_ids.py:138-139` |

三条取自该窗口的实况结论（比任何推演都贵）：

1. **「先禁用后删除」的红线在 advisor 层同样适用**：删除一旦落地，文档同步面（10 处引用，跨 5 个文件）
   立刻把门禁拖红——这正是 072 成功标准 5 要防的裂口，而且它发生在**代码收口之前**，只能靠回滚止损。
2. **`llm_client.py` 的改动随撤回一并归零**（该文件现为 HEAD 状态，`git diff` 空）：网关侧截断检测   从未落地，BUG-001 仍开放——W-3/W-5 的取证不得假设它已修。
3. **论文链路的模型面从未真正失去**：现在 `bailian.py` 在册、`papers recommend` 可用，本计划对 W-8 步骤 4
   的改判因此是「**取消即将发生的删除**」而非「重建」——工作量与风险都比 072 原计划低一档。

对向记录（避免单边叙述）：072 计划的「W-8 交付记录」节与步骤表（`:148`、`:241-242`、`:280-284`、`:317`）登记的是同一起事件，其归因与本节一致（步骤 4 按形态 A 落地 → 文档测试红 → 提交前全量回退），并把「迁入注册表」的落地明确移交本计划 W-2；两侧口径以本文件的 DL 守则与 072 的取证数据互为补，不重复登记。

工作面提示：仓库根现有 **10 个并行会话的未跟踪手稿**（`_w8_before.json`、`_w8_after.json`、`_w8_dump.py`、
`_w8_step3a.py`、`_w8_step3b.py`、`_w8_step4.py`、`_w8_revert4.py`、`_w8_plan.py`、`_w8_d7fix.py`、
`_w8_codemap.py`，仍在增长）。它们不在 `logs/` 面内、也未 gitignore，且直接污染完成门禁：`ruff check .` 因它们报 **18 处**（`UP020` × 17 + `I001` × 1，全部在 `_w8_*.py`，`src/`/`tests/`/`docs/` 零命中）。
本计划**只登记不触碰**（清理归其作者，见 Q74-f）。

## 3. 双链路口径（本计划的裁决面）

| 编号 | 守则 | 理由 | 落点 |
| --- | --- | --- | --- |
| DL-1 | **默认本地**：v1.0 及之前版本，默认配置、默认测试、文档示例、任务处理器一律按 `qed-engine` → 8900 → `qwen/qwen3.5-9b`；未显式切换不得触碰云端 | 用户 2026-09-29 裁决「v1.0 及之前默认都只用本地模型」；百炼额度已耗尽是账户侧事实 | 现 `.env` 已满足（`QED_API_SELECT=qed-engine`）；文档示例见 W-1 |
| DL-2 | **备用链路可用**：直连分支（dashscope 兼容端点 + `API_KEY`）保留为可显式启用的备用与对比通路，删除动作全部撤销 | 用户规划「两个链路都可用」；代码现状即满足 | QED-072 W-4 改判（见第 4 节） |
| DL-3 | **切换只经配置**：`QED_API_SELECT=local|api` 切直连，`=qed-engine` 切本地；不在业务代码里写死分支、不加 feature flag | 分支判据已在唯一出口 `llm_client.py:98`，加第二处即破坏单点纪律 | 无需改造；`config.py:53` |
| DL-4 | **两侧留痕即对比键**：`qed_llm_calls` 的 `service/mode/provider/model` 天然区分两链路（本地 `qed_engine/local/lmstudio/qwen3.5-9b`，直连 `qed_tracker/api/qwen/<QED_MODEL>`），对比取证只按同 `prompt_template` + 不同 `mode` 取行 | 网关载荷无 `task/step`，`prompt_template` 是唯一可靠关联键 | `db/schema.py:47-75`；对比脚本见 W-3 |
| DL-5 | **判定不落事实**：无论哪条链路，模型只产出检索计划与可审阅评估，判断只落 `qt_sources` 留痕与 `qed_llm_calls`，下载与登记仍由确定性服务执行 | `AGENTS.md` 强制约束，与模型来源无关，改判不放宽 | 保持不变 |
| DL-6 | **对比不得进默认路径**：任何「双跑对比」只在人工冒烟脚本/探针里发生，默认测试必须 `httpx.MockTransport` 零公网 | `AGENTS.md`「默认测试不得访问公网」 | W-3 交付形态约束 |

### 3.1 对 `AGENTS.md` 强制约束句的处理（需用户裁定）

现句为「**百炼**只生成检索计划…」（把供应商写死）。改判后这条约束的对象是「模型链路」而非
「百炼」。建议改为「**模型（本地或 API）只生成检索计划与可审阅评估…**」，其余分句原样保留。
该文件属项目入口约束，改法见 Q74-a。

## 4. QED-072 影响面（逐条改判，不静默覆盖）

| 072 条目 | 原文口径 | 改判后 |
| --- | --- | --- |
| 需求方 / D-1 / D-3 | 「完全屏蔽百炼」「后续淘汰」 | 撤销：百炼所在直连分支保留为备用与对比通路 |
| 成功标准 1「通路唯一」 | `LlmClient` 不存在可用直连分支、`API_KEY` 退出 LLM 面 | 改为「**默认唯一 + 备用可用**」：默认路径唯一走网关；直连分支保留且仅显式配置可达 |
| 成功标准 4「唯一留痕形态」 | `service=qed_engine mode=local` 为唯一形态 | 改为「两形态并存且可区分」（DL-4），对比取证按 `mode` 分行 |
| 成功标准 5 / W-5 命名面 | `Bailian*` 类名随「百炼退役」改名 | 命名不再由退役驱动；`Bailian*` 前缀在双链路下具误导性 → 降级为「中性命名（`PaperModelAdvisor` 等）」的可选项（Q72-c 保留但重述） |
| W-4 | direct 分支「先禁用后删除」 | 改为「保持分支可用 + 默认值钉在本地 + 补齐网关侧截断检测（BUG-001）」；删除动作取消 |
| W-8 步骤 4 | `bailian.py` 论文两条 prompt **不搬迁、直接删除**，`papers recommend` 留空窗（Q72-f） | 改为「**迁入注册表**」，空窗期取消；068-2/S3 的重写从「从零写」改为「在册改写」，Q72-f 随之作废。**实况：删除曾落地一次并已撤回（2.4），改判落在未删状态上，无需重建** |
| W-8 步骤 5 | agentic 三条纳入注册表 | 不变；但纳入后要标注其**仅本地链路**属性（编排预检硬要求 `qed-engine`，`scripts/qed067_gateway_smoke.py:70-79`） |
| Q72-b | 删除节奏一步删净 vs 先禁用 | 作废（不删） |
| Q72-d | 27B 在本地链路的位置 | 不变，仍待裁 |
| Q72-e | `task/step` 透传根侧 REQ | **优先级上升**：双链路对比要靠 `prompt_template` + `mode` 拼顺序，`task/step` 若能透传可显著简化对比脚本 |

改判登记动作：QED-072 计划头部追加「口径改判（2026-09-29）」行并指向本文件，todo 的 QED-072 行
同步镜像——由本计划 W-0 执行，已在本轮完成。

## 5. prompt 资产台账（全量，2026-09-29 复核）

### 5.1 注册表条目（`prompt_lab/`，6 条）

| 编号 | 定义位置 | 调用点 | 上游入口 | 可达链路 | 链位 |
| --- | --- | --- | --- | --- | --- |
| `domain-explore/domain@v4` | `templates.py:200`（注册 `:365`） | `prompt_lab/pipeline.py:238` `DomainPipeline._run` | CLI `domains explore`（`cli.py:152`）；`POST /api/v1/prompt-explores/dry-run`（`api/main.py:1408`）；任务 `domain_explore`（`:264`，入口 `POST /api/v1/domains/{id}/re-explore`） | 双 | 主链路（课程梳理） |
| `domain-explore/courses@v8` | `templates.py:322`（`:366`） | `pipeline.py:304` | 同上第二步；任务 `domain_explore_courses`（`:310`，入口 `POST /api/v1/domains/{id}/confirm`） | 双 | 主链路 |
| `course-explore/tutorials@v2` | `templates.py:519`（`:566`） | `pipeline.py:304`（`CoursePipeline`，`:266`） | `POST /api/v1/courses/{id}/re-explore`（`:925`）、任务 `course_explore`（`:358`）、courses dry-run（`:1444`） | 双 | 主链路（教材探索） |
| `book-query/variants@v1` | `advisor_templates.py:47`（`:174`） | `providers/book_advisor.py:101` | `application/book_fetch.py:451`（硬编码查询用尽且 `QED_BOOK_LLM_QUERY=1`）→ `POST /api/v1/books/{id}/fetch`、`POST /api/v1/knowledge/{id}/fetch`、CLI `books fetch` / `mainline download` | 双 | 主链路（取书） |
| `book-confirm/assess@v1` | `advisor_templates.py:97`（`:175`） | `providers/book_advisor.py:139` | `application/book_fetch.py:437`（`QED_BOOK_LLM_CONFIRM=1`；异常降级为全 `uncertain`） | 双 | 主链路 |
| `mainline-prefill/prefill@v1` | `advisor_templates.py:163`（`:176`） | `main_line/advisor.py:85` | CLI `mainline new --course --title --author`（`cli.py:188` → `:1199`）；**无 HTTP 路由** | 双 | 主链路（教材预填） |

> 注：`advisor_templates.py` 与注册表迁移是 QED-072 W-8 步骤 2/3 已由并行会话落地的现状
> （`book-eval/assess@v1` 与 `models.BookAssessment` 已删）。本台账按工作树实况登记，不重述其过程。

### 5.2 未入册（守护豁免中，5 个编号）

| 编号 | 定义位置 | 调用点 | 上游入口 | 可达链路 | 改判后处置 |
| --- | --- | --- | --- | --- | --- |
| `paper-plan/plan@v1` | `providers/bailian.py:29`，system 文案 `:85-86`，user 载荷 `:90-93` | `bailian.py:118` | `application/papers.py:150` ← CLI `papers recommend`（`cli.py:301`）；**8901 走不到**（`api/main.py:131` 的 `PaperService(advisor=None)`） | 双 | **迁入注册表**（原「删除」作废） |
| `paper-plan/assess@v1` | `bailian.py:30`，system/user `:143`/`:147-150`（摘要截 `[:4000]`、每批 10 篇） | `bailian.py:175` | `application/papers.py:163` | 双 | 同上 |
| `domain-explore/domain-agentic@v1` | `orchestration/pipeline.py:59`，`_SYSTEM_PROMPT` 内联 `:28` | 同文件 `run_domain_phase`（`:49-57` human 模板） | 仅 `scripts/qed067_gateway_smoke.py`；**无 CLI/HTTP** | **仅本地**（预检 `:70-79` 硬要求 `qed-engine`） | 入册并标注「实验链 / 仅本地」 |
| `domain-explore/courses-agentic@v1` | `orchestration/pipeline.py:110` | `run_courses_phase`（`:100-108`） | 同上 | 仅本地 | 同上 |
| `domain-agentic@v1` | `orchestration/pipelines/domain-exploration.yaml`（裸编号缺 task 前缀） | `orchestration/runner.py:198-202` 推导 | 同上 | 仅本地 | 入册同时修 yaml 编号（Q67-c 已记） |

### 5.3 骨架与注入面（不是模板编号，但决定模型看到什么）

| 项 | 位置 | 事实 |
| --- | --- | --- |
| 修复重试 prompt 手抄 4 份 | `bailian.py:182-186`、`book_advisor.py:147-151`、`main_line/advisor.py:93-97`、`explore_advisor.py:63` + `:115-119` | 同一文案「修复给定响应，使其成为符合原契约的严格 JSON。只输出 JSON。」；`原契约[:6000]` + `待修复响应[:8000]`；**复用原编号**（DL 留痕盲点）；异常类型三家不一致（`BailianError`/`ValueError`/`ExploreAdvisorError`） |
| priors 注入 | `prompt_lab/priors.py:13` `DOMAIN_PRIORS`、`:53` `PRIOR_KEYS_BY_STEP`、`:72` 注入点（`pipeline.py:95/:119/:213/:286`） | 用户先验直接进入 user turn；QED-073 本轮实测**故意不注入**以取得裸基线 |
| 不可信文本入模上限 | `explore_advisor.py:26` `REF_TEXT_LIMIT=8000`；`bailian.py:135` `abstract[:4000]`；`orchestration/evidence.py:52` `max_tokens=4300` | 三处各自为政，无双链路差异 |
| system turn 内插业务数据 | `main_line/advisor.py:82-89`（迁移后见 `advisor_templates.py:163`） | 全仓唯一把 caller 数据拼进 **system** 的位置，注入边界最弱，双链路同样暴露 |
| 探索链 `max_tokens` 硬下限 | `pipeline.py:69`、`:261` `max(..., 16384)` | 覆盖配置；对比实验前必须先固定 |

### 5.4 死码与文档漂移（台账附带，归 W-4 处理）

- `api/main.py:136-148` 建的 `Application.advisor` 无任何调用点（只在 `:153` 关闭）——「模型面存在」
  的假象来源之一。
- `templates.py:120` 声称 `list_templates()` 供 `/prompt-templates` 与 CLI `templates` 使用，两个入口
  均已不在代码里（现仅测试使用）。
- `config.py:181-190` 降级提示仍写「catalog evaluate 跳过评估」，`catalog` 只剩 `list`/`show`。
- `explore_advisor.py:62` 注释举例 `course-explore/tutorials@v1`，注册表已是 `@v2`。

## 6. 对比取证口径（本地 vs API）

同一 payload 双跑，只在人工冒烟脚本里发生（DL-6）。固定量：`prompt_template`、payload 文件、
`max_tokens`（两侧同值；探索链需先解 5.3 的硬下限）。记录量：

| 维度 | 取法 |
| --- | --- |
| 契约一次通过率 | 首试即通过 / 触发 repair / 抛错，按 `prompt_template` + `mode` 分组（repair 复用同编号，需靠 `id` 顺序或响应内 `calls` 计数区分） |
| 耗时 | 客户端计时（本地实测 20~103 秒/次，冷启动会撞到网关 300 秒上限——本轮实测 `qed073/domain-evidence@v2` 三条即 3 次 `ReadTimeout`，热身后 20.6 秒成功，留痕 `id=47`） |
| 正文规模与截断 | `response` 字符数 + `finish_reason`（网关侧截断检测未落地，BUG-001 仍开放） |
| 判定一致性 | 结构化字段逐条对比（论文三项分、书籍 verdict、`name_check.valid`、`classic_tracks` 命中候选清单率） |
| 成本 | API 侧按账户额度（百炼 `qwen-plus` 已耗尽；`QED_MODEL` 现为 `deepseek-v4-flash-0731`，**额度未实测**，属账户侧事实，见 Q74-d） |

## 7. 工作项

| 编号 | 工作项 | 产出 | 状态 |
| --- | --- | --- | --- |
| W-0 | 现状勘察 + QED-072 改判登记（本文件第 2、4 节；072 计划头部与 todo 镜像同步） | 本台账 + 072 改判行 + todo 双行 | **完成（2026-09-29）** |
| W-1 | 默认口径成文：`design/paper-discovery.md`「百炼边界」改写为「模型链路边界（默认本地 + API 备用）」；`service-management.md`、`main-line-curriculum.md`、`exploration-pipeline.md`、`code-map.md` 同步；`AGENTS.md` 强制约束句按 Q74-a 裁定后改写 | 文档同步清单逐条落地 | 待 W-1 评审通过后执行 |
| W-2 | 论文两条 prompt 迁入注册表（QED-072 W-8 步骤 4 由「删论文模型面」改为本项；删除动作已取消，无需回滚）：按 `advisor_templates.py` 既有形态在册，advisor 改注册表消费；豁免清单随之减两条（`:138-139`）、钉清单随之加两条（`:170-177`） | `advisor_templates.py` 在册 + `test_prompt_template_ids.py` 与 `test_bailian_advisor.py` 绿 | 待用户「开始执行」 |
| W-3 | 对比冒烟脚本落地：`scripts/` 下人工脚本做同 payload 双跑 + 留痕回读表（默认测试不参与） | 脚本 + 一次真实双跑报告（附留痕 `id` 区间） | 待执行 |
| W-4 | 死码与漂移清扫：5.4 四条（`Application.advisor`、`list_templates` 注释、`catalog evaluate` 提示、`tutorials@v1` 注释） | 清扫提交 + `test_documentation.py` 绿 | 待执行 |
| W-5 | 留痕盲点改造请求：repair 编号复用与 `task/step` 透传（根侧 REQ，P-4 优先级上升） | 根仓 REQ 文本，交用户执行 | 待执行 |

### 7.1 W-0 交付记录（2026-09-29，本轮）

- 交付物：本文件（含 2.4 实况登记与 DL-1~DL-6 口径）+ `docs/plans/index.md` 条目 + `docs/trackers/todo.md` QED-074 行（状态 `待开始`，计划本体 Draft 待评审）与 QED-072/QED-068 行的改判镜像 + `tests/test_documentation.py` 当前文档白名单 +1。全程零代码改动、零真实模型调用（W-0 无需留痕）。072 计划头部的改判行由并行会话（072 窗口）自行登记，本窗口不重复写入。
- 门禁实况：`pytest tests -q` → **555 passed / 1 failed / 1 skipped**；唯一红项 `tests/test_orchestration.py::test_evidence_packer_trims_deterministically_and_records_budget_omissions` 属并行会话未跟踪 WIP（`src/qed_tracker/orchestration/` 与其测试文件同为 `??`），不由本计划修复。
- `ruff check .` → 18 处全部在仓库根 `_w8_*.py` 手稿（见上方工作面提示），`src/`、`tests/` 零命中。
- 台账复核：第 5 节引用的每个 file:line 均在 2026-09-29 工作树上重取（`bailian.py` 撤回后行号回到 HEAD 口径：`:29/:30/:118/:175/:186/:194`）。

## 8. 验证与验收

- **留痕强制**：任何真实模型调用（含对比双跑）都要在 `qed_llm_calls` 留行并按 `prompt_template`
  回读；无留痕＝未发生。交付必须附 `id` 区间与回读 URL。
- 默认测试零公网：W-2/W-4 的测试改动全部用 `httpx.MockTransport`；直连侧新增用例不得打真实端点。
- 台账完整性可机器证明：第 5 节每一行都能被 `tests/test_prompt_template_ids.py` 的扫描面覆盖
  （`src/**/*.py` + pipeline `*.yaml`），且豁免清单条目数与 5.2 行数一致（当前 5，其中论文 2 条的去向注记已指向 W-2）。
- 默认不变性验收：清空显式切换后，`.env` 与工作树默认路径必须落在 `qed-engine`；任何默认路径
  出现直连即为不合格。
- 完成门禁：`ruff check .` + `pytest tests -q` 全绿（并行会话既有红须举证归因）；
  `tests/test_documentation.py` 绿（本计划已镜像进 todo 与 plans 索引）。
- 真实数据根零读写；未获明确要求不提交 git。

## 9. 待裁项

| 编号 | 问题 | 选项与代价 |
| --- | --- | --- |
| Q74-a | `AGENTS.md`「百炼只生成检索计划…」强制约束句是否改写为「模型（本地或 API）…」 | 改写＝口径与代码一致；不改＝入口约束继续点名一个已降级的供应商 |
| Q74-b | 论文两条 prompt 迁入注册表时的版本号：保持 `@v1`（留痕连续）还是 `@v2`（承认新形态） | 保持＝历史留痕可直接比对，但 068-2/S3 的重写点变模糊；`@v2`＝干净切代，但需同时改 068 与豁免清单表述 |
| Q74-c | `Bailian*` 类与文件名是否改中性名（Q72-c 的重述） | 改名＝牵动 `cli.py`/`api/main.py`/测试文件名/多处文档同步面；不改＝双链路下类名与实际通路不符 |
| Q74-d | API 备用链路的可用凭证：百炼 `qwen-plus` 额度已耗尽，现 `QED_MODEL=deepseek-v4-flash-0731` 是否即为备用面主力 | 实测＝一次真实小调用（须用户同意走云端）；不实测＝W-3 对比脚本只能在本地侧空跑 |
| Q74-e | 探索链 `max_tokens≥16384` 硬下限在对比前如何处理 | 放开为配置项＝改动产线行为（需 QED-073 一并裁）；对比期临时旁路＝只影响冒烟脚本、少改产线 |
| Q74-f | 并行会话工作面：W-2 由谁执行（本计划 vs 072 W-8 步骤 4 的改造版），以及仓库根 7 个 `_w8_*.py/json` 手稿的清理归属 | 本计划执行＝口径统一在「默认本地 + API 备用」，但与对方在同一批文件（`advisor_templates.py`、`test_prompt_template_ids.py`）上必然冲突；交对方＝我只出验收判据，前提是其步骤 4 语义已按 2.4 改判；手稿一律不代删（属对方 WIP） |

## 10. 回滚

- 本计划 W-0 只动文档（新增本文件 + 072 计划改判行 + todo/索引/文档测试登记），逐文件可逆。
- W-1/W-2 落地后如需回滚：文档按提交逆序还原；注册表迁移保留原编号即历史留痕可比，删除动作已取消，
  不存在「删净后无法恢复」的窗口。

## 11. 关闭与归档

按 `qed-closeout`：todo 移 `completed.md`，本计划按 ADR 0009 做 Retain/Delete 判定
（预期 **Retain**：台账是后续任何新增 LLM 调用点的登记基准，删除即失去唯一事实源）。
