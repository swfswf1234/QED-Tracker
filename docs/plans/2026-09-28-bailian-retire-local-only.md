# 百炼退役与本地链路独占（bailian-retire-local-only）

状态：Accepted（2026-09-28 用户裁决立项；取证工作项 W-0 已完成，W-1~W-7 实现未开始；2026-09-29 追加 W-8 prompt 集中注册表收口：**步骤 1~3 已交付**，步骤 4 当日按 Q72-f 形态 A 落地后**已回退**——D-7 的该项被 QED-074 草案改判，论文模型面空窗取消）
任务类型：Plan
最后更新：2026-09-29
需求方：用户（2026-09-28 裁决：百炼额度已耗尽，论文评分/书籍确认后续不得再到 `qwen-plus`；
现在完全屏蔽百炼，本轮只考虑走通本地链路；本地 qwen3.5 9B 可用预算放宽至 19000）
目标项目：QED-Tracker（跨项目依赖：QED-Engine 根仓库两项，见「前置条件」）
评审方：用户
关联 Tracker：QED-072；本计划 D-1/D-3「完全屏蔽百炼、通路唯一」与 D-7「论文两条内联 prompt 直接删除」
已被 [QED-074 双链路口径与 prompt 资产台账](2026-09-29-llm-dual-link-prompt-ledger.md)（Draft，待用户评审）
取代；改判不触及 W-8 步骤 1~3 与其余三答（死码删除、agentic 纳入、072 承载）
关联设计：[论文发现设计](../design/paper-discovery.md)（「百炼边界」节须改写）、
[服务管理中心设计](../design/service-management.md)（模型模式与密钥分置）、
[主线路径设计](../design/main-line-curriculum.md)（教材预填顾问）、
[私有表架构](../architecture/database-private-tables.md) 与
[共享表架构](../architecture/database-shared-tables.md)（`qed_llm_calls` 留痕面）
关联 ADR：[ADR 0003 暂定设计落点](../history/adr/0003-pending-design-location.md)、
[ADR 0009 关闭计划归档](../history/adr/0009-closed-plan-archival.md)
归档判定：待关闭时按 ADR 0009 做 Retain/Delete 两态判定

## 目标与成功标准

把 QED-Tracker 的**全部** LLM 调用收敛到唯一通路：`qed-engine` 模式 → 8900 网关 → 本地
`qwen/qwen3.5-9b`，并淘汰百炼（dashscope 直连）这条第二通路。本任务是 067「本地模型」主线的
口径修正：从「本地模型与百炼并行 A/B」改为「本地模型独占，百炼退役」。

成功标准：

1. **通路唯一**：`LlmClient` 不再存在直连 dashscope 的可用分支，`API_KEY` 不再是本仓 LLM
   调用的前置条件；四处 advisor（论文/书籍/主线/探索）全部经 8900 网关调用本地模型。
2. **契约不破**：百炼原有六处结构化校验（论文 `plan`/`assess`、书籍 `assess`/`confirm`、
   主线 `prefill`、检索词变体）在本地 9B 上逐条实测通过或明确降级口径；「模型只生成检索计划
   与可审阅评估，不直接下载、不写资源事实」的强制约束保持不变。
3. **预算成文**：以本地模型真实窗口替换 `v0.1` 沿用的 8196 预算表，给出输入/输出/余量三段
   口径与每条链的 `max_tokens` 取值，并写清「低于 1024 必吐空正文」的硬下限纪律。
4. **留痕可检验**：每次调用在 `qed_llm_calls` 留一行，`prompt_template` 可按运行顺序回读，
   `service=qed_engine mode=local model=qwen/qwen3.5-9b` 成为唯一留痕形态。
5. **文档与代码同步**：`AGENTS.md`「百炼只生成检索计划…」强制约束、`docs/design/` 三处
   百炼描述、`code-map.md`、类与文件名、测试名全部随口径变更更新（不留「文档说百炼、代码走本地」
   的裂口）。

## 用户裁决记录（2026-09-28）

| 裁决 | 原文要点 | 对本计划的影响 |
| --- | --- | --- |
| D-1 | 不走百炼链路，后续淘汰 | 百炼由「并行对照」降为「待删除」 |
| D-2 | 论文评分/书籍确认后续不应到 `qwen-plus`（已经没有额度了） | 067/068 中一切依赖云端 qwen 的路径视为不可用 |
| D-3 | 现在完全屏蔽百炼 | 本仓 LLM 通路收敛为网关单一分支 |
| D-4 | 只看本地链路进行，本轮只考虑走通本地链路 | 本轮范围＝本地链路，不扩到真实抓取/编排链优化 |
| D-5 | 9B 模型可以用 19000 预算 | 8196 旧预算表作废，新预算表以 19000 为输入（待 W-2 实测确认） |
| D-6 | 百炼链路与 LangChain 编排要区分开，避免被 LangChain 带偏 | 本计划只管传输与模型来源；编排链（067-2~5）另议 |
| D-7（2026-09-29） | prompt 收口四问四答：并入 072 承载（W-8）；论文两条内联 prompt **不搬迁、直接删除**；`book-eval/assess@v1` 死码删除；orchestration 的 agentic 三条一并纳入注册表 | 见「W-8 prompt 集中注册表收口」节 |

## 取证结论（W-0，2026-09-28 实测）

全部数据来自当日真实调用，留痕行 `id=31~37`，可用
`GET http://127.0.0.1:8900/api/v1/llm/calls?start=2026-09-28&prompt_template=<模板>` 回读复核。
探针脚本与原始输出留在 `logs/`（`q67_probe_answer.py`、`q67_oncall_9000.py`、
`q67_bailian_contract_on_local.py`，均在 gitignore 面内）。〔2026-09-30 ADR 0011：探针与原始输出落位改 `tmp/`，本节历史文件按 QED-075 W-6 清单处置〕

### 1. 通路：本地槽位可由网关代起

`POST /api/v1/models/qwen/start` 派发即返回，14 秒后槽位 `ready=true`
（`source=local`、`model=qwen/qwen3.5-9b`、`base_url=http://127.0.0.1:5001/v1`）。
在此之前 5001 端口无任何监听、槽位 `ready=false`（`reason=ConnectError`）——即「模型没起来」
是本机 LM Studio server 未运行，不是网关或本仓配置问题。`lms` CLI 在 PATH
（`C:/Users/86182/.lmstudio/bin/lms`），所以网关的半托管启动链可用。

### 2. 输出预算是本地链路的第一号卡点，不是模型能力

同一道极简题（「请用一句中文回答：1+1 等于几？」），四档 `max_tokens`：

| `max_tokens` | 留痕 id | 正文 |
| --- | --- | --- |
| 64 | 31 | 0 字符（`success=true`，空正文穿透＝BUG-001） |
| 256 | 32 | 0 字符 |
| 1024 | 33 | `1+1 等于 2。`（9 字符） |
| 2048 | 34 | `1+1 等于 2。` |
| 9000 | 35 | 5055 字符完整教材梳理，自然收尾非截断，86.0 秒 |

判定：9B 的思考 token 与正文共用 `max_tokens`，**预算 ≤256 时正文必空**；1024 是实测硬下限，
正常任务需千位以上。耗时由实际生成长度决定（9000 预算 86 秒 ≈ 2048 预算 81 秒），
因此**把预算往大给几乎无额外代价**——这是新预算表能与旧表彻底分道的事实基础。

### 3. 百炼论文契约在本地 9B 上一次通过，零修复

用真实 `BailianPaperAdvisor`（`api_select="qed-engine"`、`max_tokens=9000`）+ 真实
`_structured()` 校验与 repair 分支跑固定候选（6 篇，不访问公网）：

| 契约 | 模板 | 留痕 id | 输入字符 | 输出字符 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 检索计划 | `paper-plan/plan@v1` | 36 | 549 | 1122 | 一次通过，4 条检索、`category` 全落在 `math.NA`/`cs.MA` 白名单 |
| 论文评分 | `paper-plan/assess@v1` | 37 | 2719 | 991 | 一次通过，6 篇 ID 全覆盖不重复、三项分皆 0–5 整数、`risks` 为字符串数组 |

`advisor_calls` 与 `response_sha256` 数量一致（1/1、2/2），证明 repair 分支未被触发。
判断质量亦可审阅：PDE 综述给 `goal_fit=2` 并注明「超出二年级范围」，Chebyshev 插值课堂研究与学生
版 Jacobi/Gauss-Seidel 指南给 5/5/5，有机合成那篇三项全 0 且主动指出「不在允许的数学计算类目录中」。
输出为裸 JSON，无 Markdown 围栏。

### 4. 留痕形态在本地链路上的得与失

网关代写后：`service=qed_engine`、`mode=local`、`provider=lmstudio`、`model=qwen/qwen3.5-9b`、
`endpoint=text`，列表接口即含完整 `prompt`/`response`（无需详情端点）。
**`task`/`step` 仍为 `NULL`**（载荷无该字段），且本仓 direct 分支自写的
`service=qed_tracker mode=api` 行随百炼退役一并消失，`usage` 也不再回填（gateway 分支置空）。

## 范围

- `src/qed_tracker/llm_client.py`：通路收敛与网关分支补齐（截断检测、留痕口径）。
- 四处 advisor 的模型来源与预算参数：`providers/bailian.py`、`providers/book_advisor.py`、
  `main_line/advisor.py`、`providers/explore_advisor.py` 及其构造点
  （`api/main.py`、`cli.py`）。
- 预算表重算与成文（本计划承载，评审后迁 `design/`；运维与能力说明另立 `guides/`，见 W-6）。
- `docs/design/paper-discovery.md`「百炼边界」等三处描述、`code-map.md`、`AGENTS.md` 强制约束句。
- 命名与测试面：`Bailian*` 类名/文件名/测试名的去留（W-5）。
- prompt 资产收口：内联 prompt 迁入 `prompt_lab/templates.py`、死码删除、三份手抄骨架合一、孤儿 prompt 守护测试（W-8）。

## 非目标

- 不做真实 Wikipedia/三校官方页抓取（属 067-5），不改 MCP 工具白名单。
- 不优化 LangChain 编排链本身的 prompt/步骤（按 D-6 与本计划解耦）。
- 不动根仓库任何文件；根侧改动只提请求，由用户执行。
- 本轮不引入第二只本地模型（27B 与 9B 的取舍另议，见 Q72-d）。

## 前置条件

| 编号 | 条件 | 归属 | 现状 |
| --- | --- | --- | --- |
| P-1 | 本地模型服务在跑（LM Studio server，5001） | 机器侧/用户 | 2026-09-28 经网关代起可用；重启后需再起 |
| P-2 | 网关文字槽位 `source=local` | 根侧运行态 | 已满足 |
| P-3 | 9B 实际上下文窗口（19000 还是 registry 写的 16384） | 根侧参数 + 实测 | **未确认**，见 W-2 |
| P-4 | 网关载荷是否支持 `task/step`（REQ 提案） | 根侧 | 不支持，表侧列已存在，只差写入侧 |
| P-5 | 网关载荷是否支持按调用点名模型 | 根侧 | 不支持（`LlmTextRequest` 仅 4 字段）；本地独占后此需求降级为不需要 |

## 工作项

| 编号 | 工作项 | 产出 | 状态 |
| --- | --- | --- | --- |
| W-0 | 本地链路通路 + 预算阶梯 + 论文两契约取证 | 本计划「取证结论」节 | **完成（2026-09-28）** |
| W-1 | 书籍契约与主线预填实测：`book-advisor` 的 0–100 `score`+`verdict`、`confirm` 二值判定、`main_line/advisor` 的 `prefill`（含越界指令抗性，摘要不可信纪律不破） | 逐契约通过/失败表 + 留痕 id | 待开始 |
| W-2 | 窗口边界实测：逐级放大输入（含真实批量规模：10 篇 × `abstract[:4000]`）定位溢出报错点，确认 16384/19000 | 窗口真值 + 输入上限 | 待开始 |
| W-3 | 预算表重设计：以 W-2 真值给出 `输入上限 + 输出预算 + 余量 = 窗口` 的可行组合，逐链给 `max_tokens`，并写入「≥1024」硬下限 | 新预算表（替换 8196 旧表） | 待开始 |
| W-4 | 通路收敛改造清单（**2026-09-29 QED-074 改判**：direct 分支删除与 `API_KEY` 退出 LLM 面**取消**，两分支保留可用；保留项：默认钉本地 + 网关侧补 `finish_reason`/截断检测（BUG-001 收口）） | 改造清单 + 影响面 | 待开始 |
| W-5 | 命名与文档同步面清点：`Bailian*` → 本地命名的改名范围、`AGENTS.md` 强制约束句改写、三处 `design/` 描述、`code-map.md`、测试文件名 | 同步清单（供评审） | 待开始 |
| W-6 | `docs/guides/` 新增本地模型能力与运维说明（用户点名：优化手段、模型能力、pipeline 设计） | 指南文档（W-0~W-3 数据齐备后写） | 待开始 |
| W-7 | 根侧请求提交：`task/step` 透传 REQ（P-4）；registry `context` 参数与 19000 口径对齐 | 根仓 REQ 文本，交用户执行 | 待开始 |
| W-8 | prompt 集中注册表收口（D-7 裁决）：内联 prompt 入册、`book-eval` 与论文模型面删除、骨架合一、孤儿守护测试、七处文档同步 | 注册表唯一事实源 + 守护测试绿 | **进行中（步骤 1~3 已交付 2026-09-29；步骤 4 落地后当日回退，改由 QED-074 W-2 承接「迁入注册表」，待用户「开始执行」；步骤 5~7 未开始）** |

## 验证与验收

- **留痕强制（用户 2026-09-28 重申）**：本任务**每一步**真实模型调用都必须在 `qed_llm_calls`
  留下一行并可按 `prompt_template` 回读；无留痕的调用视为未发生，不得作为验收证据。
  自 W-1 起统一使用 `qed072/<step>@v{n}` 命名（W-0 混合前缀见下方索引），每份工作项交付时
  必须附本次运行的留痕 `id` 区间与回读 URL。
- 默认测试零公网：所有新增测试用 `httpx.MockTransport` 假网关，真实调用只走人工冒烟脚本。
- 每份工作项验收都要留可复核证据：留痕行 `id` + `prompt_template` + 正文字符数。
- 契约通过的定义＝通过**现有真实校验代码**（含越界分类、ID 全覆盖、整数分域、`risks` 类型），
  不接受「看起来是 JSON」。
- 完成门禁：`ruff check .` + `pytest tests -q` 全绿（并发会话造成的既有红须举证归因），
  `tests/test_documentation.py` 绿（本计划已镜像进 todo）。
- 真实数据根零读写。

### W-0 留痕索引（2026-09-28，全部可回读）

| 留痕 id | `prompt_template` | 内容 | 结果 |
| --- | --- | --- | --- |
| 31 | `qed067/answer-probe@v64` | 极简题，`max_tokens=64` | `success=true`，正文 0 字符（BUG-001 实证） |
| 32 | `qed067/answer-probe@v256` | 极简题，256 | 正文 0 字符 |
| 33 | `qed067/answer-probe@v1024` | 极简题，1024 | 正文 9 字符 |
| 34 | `qed067/answer-probe@v2048` | 极简题，2048 | 正文 9 字符 |
| 35 | `qed067/onecall-9000@v1` | 自由长文，9000 | 正文 5055 字符，自然收尾，86.0 秒 |
| 36 | `paper-plan/plan@v1` | 真实 advisor 检索计划 | 校验一次通过，正文 1122 字符，59.0 秒 |
| 37 | `paper-plan/assess@v1` | 真实 advisor 6 篇评分 | 校验一次通过，正文 991 字符，92.5 秒 |

回读方式（列表接口即含完整 `prompt`/`response`/`task`/`step`）：
`GET http://127.0.0.1:8900/api/v1/llm/calls?start=2026-09-28&prompt_template=<模板>`。
七行共同形态：`service=qed_engine`、`mode=local`、`provider=lmstudio`、
`model=qwen/qwen3.5-9b`、`endpoint=text`、`task=NULL`、`step=NULL`。


## W-8 prompt 集中注册表收口（2026-09-29 用户裁决登记；步骤 1~3 已交付，步骤 4 改判取消）

**裁决（2026-09-29 四问四答）**：本轮 prompt 收口并入本任务承载（W-8，不新开 todo 任务）；
`providers/bailian.py` 的两条论文内联 prompt **不搬迁、直接删除**；死码 `book-eval/assess@v1`
连同 `models.BookAssessment` **删除**；并行会话 `src/qed_tracker/orchestration/` 的三条 agentic
模板 id **一并纳入注册表**（用户明确授权改动其未跟踪文件）。

**同日改判登记（2026-09-29，QED-074 草案）**：四答中「论文两条内联 prompt 直接删除」一项**作废**，
改为迁入注册表（`paper-plan/plan@v1` 在册、S3 改写为 `@v2`，空窗取消），落地由 QED-074 的 W-2 承接、
**待用户「开始执行」**；本窗口曾按 Q72-f 形态 A 删净 `providers/bailian.py` 与其测试，已在提交前全量回退。
其余三答（并入 072 承载、`book-eval` 死码删除、agentic 三条纳入）不受影响。

### 现状清点（2026-09-29，逐 file:line 佐证）

注册表三条（`prompt_lab/templates.py`，`register()` 拒低版本覆盖）：`domain-explore/domain@v4`、
`domain-explore/courses@v8`、`course-explore/tutorials@v2`。

内联未入册六条，分属三个 advisor：

| 位置 | 模板 id | 入口 | 处置 |
| --- | --- | --- | --- |
| `providers/bailian.py:83-94` | `paper-plan/plan@v1` | 仅 CLI `papers recommend`（`api/main.py:131` 的 PaperService `advisor=None`，8901 走不到） | **迁入注册表**（QED-074 W-2 待执行；原 D-7「删除 + 068-2 从零写 `plan@v2`」作废，改为在册改写） |
| `providers/bailian.py:140-151` | `paper-plan/assess@v1` | 同上 | **迁入注册表**（同上，在册改写为 `assess@v2`） |
| `providers/book_advisor.py:100-113` | `book-eval/assess@v1` | **src 零调用者**，仅 `test_prompt_template_ids.py:86` 自喂 | **删除** + `models.BookAssessment`（`models.py:120`） |
| `providers/book_advisor.py:160-173` | `book-query/variants@v1` | `application/book_fetch.py:451` | 迁入注册表 |
| `providers/book_advisor.py:223-236` | `book-confirm/assess@v1` | `application/book_fetch.py:437` | 迁入注册表 |
| `main_line/advisor.py:78-101` | `mainline-prefill/prefill@v1` | `cli.py:1199` | 迁入注册表 |

并行会话（未跟踪 `src/qed_tracker/orchestration/`）三条：`domain-explore/domain-agentic@v1`、
`domain-explore/courses-agentic@v1`（`pipeline.py:59/110`，`_SYSTEM_PROMPT` 内联在同文件 `:28`）、
`domain-explore/domain_synthesis@v1`（`runner.py` 侧，`test_orchestration.py:517/648` 断言）。

另有三处并存骨架：`bailian.py:177-204`、`book_advisor.py:261-288`、`main_line/advisor.py:134-158`
各抄一份 `_structured`/`_complete`（严格 JSON 校验 + 一次修复重试 + 预算 + sha256 留痕），
`providers/explore_advisor.py:104-138` 是第四份也是唯一抽干净的；三处异常类型不一致
（`BailianError` / `ValueError` / `ExploreAdvisorError`）。

### 目标形态

`prompt_lab/templates.py` 成为**全部** LLM prompt 的唯一事实源（口径从「探索类 prompt 的唯一集中处」
扩到「全部调用点」，`design/exploration-pipeline.md:104` 同步改写）：

1. **校验工厂**（合并形态甲，用户已裁）：`PromptTemplate` 增可选
   `validate_for: Callable[[dict], Callable[[object], Any]]`——注册表同时拥有文案与输出契约；
   依赖运行时上下文的校验（`allowed_categories` 白名单、期望 `provider_id` 全集）由 payload 派生，
   advisor 退化为「组 payload → `template.messages(payload)` + `template.validate_for(payload)`
   → `_structured`」。
2. **骨架合一**：三份手抄 `_structured`/`_complete` 改为复用 `ExploreAdvisorBase`，异常类型随之
   统一；各链 `contract_version` 透出保持原值，不伪造新契约。
3. **孤儿 prompt 守护测试**（本工作项的验收实体）：扫描 `src/qed_tracker/**` 内全部
   `prompt_template=` / `*_template_id = "..."` 字面量，断言每个 id 都能在注册表解析到条目，
   并钉死条目清单。此后「新增 LLM 调用点忘记登记」直接红，「文档说集中在注册表」才成立。

### 交付顺序（每步一提交，全绿才下一步）

1. `templates.py` 加 `validate_for` + 孤儿守护测试（先把未登记面显式化）。
2. 删 `book-eval/assess@v1`、`BookAssessment` 与 `test_prompt_template_ids.py` 的 book-eval 断言。
3. 迁 `book-query/variants@v1`、`book-confirm/assess@v1`、`mainline-prefill/prefill@v1` 入注册表
   ——**文案零改动、版本号不动**，`qed_llm_calls.prompt_template` 历史留痕仍可比对。
4. ~~删 `bailian.py` 论文模型面（两条 prompt 及其 `plan`/`assess`）~~ **取消（2026-09-29 QED-074 改判）**：
   两条 prompt 改为迁入注册表，空窗取消、Q72-f 随之作废；本步落地移交 QED-074 W-2（待「开始执行」）。
5. 纳入 agentic 三条；只搬文案与模板编号，**不合并并行会话的未提交逻辑改动**，以其自带
   `test_orchestration.py` 转绿为准；同期若对方在改同一文件则以对方为准、本步回退。
6. 文档同步面：`design/exploration-pipeline.md`（注册表口径 + 清单）、`design/paper-discovery.md`
   （模型面空窗口径）、`architecture/code-map.md`、`architecture/database-shared-tables.md:348-350`
   模板清单、`design/main-line-curriculum.md:88`、`design/download-pipeline.md:213/243/363/365`。
7. 顺带修已查实漂移：`exploration-pipeline.md:109-110` 声称 `list_templates()` 供
   `/prompt-templates` 与 CLI `templates` 使用，**两个入口均已不在代码里**（QED-071 死码批清理时
   文档未跟）。本轮只把文档写实为「注册表代码 + 孤儿守护测试」，不恢复端点（属新契约面，另议）。

### W-8 交付记录

- **步骤 1 已交付（2026-09-29）**：`tests/test_prompt_template_ids.py` 追加注册表覆盖守护四条
  （孤儿编号检测 / 注册表清单钉死 / 豁免清单不得留失效条目 / 豁免条目必须注明去向），
  扫描面含 `src/**/*.py` 与 pipeline `*.yaml` 的 `template:` 值；豁免清单当前 9 条，逐条绑定步骤号。
  变异检验：注入未登记编号 → 红；注入已消失的豁免编号 → 红；移除后回到绿。
  证据：定向 `ruff check` clean，prompt 相关六测试文件 **74 passed**。
- **顺序偏差**：原步骤 1 的 `validate_for` 校验工厂推迟到步骤 3——本轮没有消费者，先加即空转抽象；
  守护测试独立先行即可把未登记面显式化。
- **步骤 2 已交付（2026-09-29）**：删 `book_advisor.assess`（`book-eval/assess@v1`）与
  `models.BookAssessment`，并摘除 `test_prompt_template_ids.py` 的 book-eval 断言与豁免条目。
  证据：`ruff check src tests` clean，`test_prompt_template_ids.py test_book_llm_advisor.py
  test_book_api.py test_db_models.py` **52 passed**。
- **步骤 3 已交付（2026-09-29）**：`PromptTemplate` 增可选 `system`（可为随 payload 生成的函数）、
  `validate_for` 与 `validator(payload)`（`validate`/`validate_for` 必居其一，`__post_init__` 兜底），
  `book-query/variants@v1`、`book-confirm/assess@v1`、`mainline-prefill/prefill@v1` 三条入册，
  `book_advisor.py`/`main_line/advisor.py` 瘦身为「组 payload → `template.messages/validator` → `_structured`」，
  `*_template_id` 类属性删除，豁免清单减三条、注册表钉死清单扩到六条。
  **等价性取证**：`httpx.MockTransport` 抓取三调用点实际外发消息体，迁移前后逐字节相同
  （`before == after` → `IDENTICAL`），文案零改动、版本号不动，历史留痕仍可比对。
  证据：`ruff check src tests scripts` clean，prompt/advisor/paper/CLI 定向 **117 passed**。
- **落点偏差（自主决定，此处显式登记）**：三条 prompt 未写进 `templates.py` 本体，而是新建
  `prompt_lab/advisor_templates.py` 注册进同一 `REGISTRY`（包 `__init__.py` 导入即注册）。
  原因：`tests/test_prompt_lab.py::test_templates_are_domain_neutral` 以**整份 `templates.py` 源文件**
  为扫描面断言不含学科绑定词，而 `mainline-prefill` 文案按设计含「顶尖大学数学课程」锚点——
  并入即需弱化该守护。守护强度优先于单文件聚合；代价是事实源由「一个文件」变「一个 REGISTRY
  + 两个族模块」，后续 068-2/QED-074 的 `paper-plan@v2` 建议同样落在 `advisor_templates.py`。
  残余风险：新族模块不受学科中立守护覆盖，靠注册表钉死清单与孤儿编号守护兜底。
- **步骤 4 已回退（2026-09-29）**：形态 A（删 `providers/bailian.py` + `tests/test_bailian_advisor.py`、
  `providers/__init__.py`/`cli.py._paper_service`/`papers.py` 提示语/三份测试同步）曾全量落地并通过
  `ruff check` 与 157 项定向测试，仅 `test_documentation.py::test_current_code_and_test_references_resolve`
  因四份文档仍引用已删路径而红；随后发现并行会话 16:38 新建的 QED-074 草案改判 D-7，经用户裁决
  **回退步骤 4**：两文件按 HEAD 复原，其余改动逐处反向替换，`llm_client.py`/`providers/__init__.py`/
  `test_paper_selection_cli.py` 回到无差异状态，豁免清单两条 paper-plan 去向改注 QED-074（守护断言
  相应允许 `QED-074` 前缀的去向句）。
- **文档同步推迟**：`code-map.md:38/54/55/153` 等留到步骤 6 一次做——`docs/architecture/code-map.md`
  现有并行会话未提交改动（QED-067 两行），2026-09-29 用户授权一并改并提交该文件。

### 影响面（评审时必须确认）

- ~~步骤 4 落地后 `papers recommend` 无模型面~~ **回退后不适用**：论文两条 prompt 留在原地，
  `papers recommend` 模型面全程可用；迁入注册表由 QED-074 W-2 承接，改造性质是「在册搬运」而非重建。
- 受影响测试面：`tests/test_bailian_advisor.py` 全部、`test_paper_application.py` 的 recommend
  用例、`test_prompt_template_ids.py` 的 paper 两用例；`test_cli_architecture.py` 的
  recommend 解析断言保留（CLI 命令面不删）。
- 论文链路不因此消失：`PaperService.search`/`get`、选择报告、`selections download` 与 PDF 落盘
  全部保持可用。

## 回滚

- 本计划只动代码与文档，不动数据根、不动库结构；逐提交回滚即可。
- 通路收敛采取「先禁用后删除」两步：W-4 第一步（配置层拒绝 direct）可单独回滚，
  删除分支为第二步，须 W-1~W-3 全绿后执行。
- 若 W-1/W-2 证明本地 9B 撑不住某条契约，该项按「降级须用户裁决，不得静默砍项」处理，
  本计划状态转 `Blocked` 并记录证据。

## 待裁项

| 编号 | 问题 | 选项与代价 |
| --- | --- | --- |
| Q72-a | 19000 从何而来：registry 现为 `context=16384`（`services/llm/registry.py:99`），`lms load -c 16384` | 改根 registry＝根侧改动（用户执行）；或本机 LM Studio GUI 手调（重启即失效） |
| Q72-b | 百炼代码删除节奏：一步删净 vs 先禁用 | **作废（2026-09-29 QED-074 改判：不删，双链路保留作备用与对比）** |
| Q72-c | `Bailian*` 类与文件名是否改名 | 改名牵动测试与文档同步面（AGENTS.md 同步义务）；不改名则「文档说百炼、代码走本地」长期裂口 |
| Q72-d | 27B（registry `context=8192`）在本地链路里的位置 | 不用＝少一个退路；用＝窗口反而更小，与 D-5 冲突 |
| Q72-e | `task/step` 留痕是否仍提根侧 REQ | 不提＝顺序只能靠 `prompt_template` + `id`；提＝根侧排期成本（067 已定 A 方案，本任务沿用） |
| Q72-f | ~~W-8 步骤 4 删论文模型面后的空窗形态~~ **已作废（2026-09-29 用户裁决回退步骤 4）**：论文模型面不删、空窗取消 | 原两选项（A 连 `BailianPaperAdvisor` 类与测试删净 / B 保留类只摘 prompt 文案）随 QED-074 W-2「迁入注册表」不再需要 |

## 关闭与归档

关闭时按 `qed-closeout`：todo 移 `completed.md`、本计划按 ADR 0009 做 Retain/Delete 判定
（预期 Retain，理由：预算表与本地模型能力口径是后续 `guides/` 文档的事实源）。
