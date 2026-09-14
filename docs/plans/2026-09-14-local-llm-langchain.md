# 本地 LLM 模型对接与 LangChain 编排（local-llm-langchain）

状态：Draft
任务类型：Plan
最后更新：2026-09-14
需求方：用户（学习优化本地小模型）
目标项目：QED-Tracker
评审方：用户
关联设计：[服务管理中心设计](../design/service-management.md)（模型模式与密钥分置）、[论文发现设计](../design/paper-discovery.md)（LLM 顾问边界）、[探索管线设计](../design/exploration-pipeline.md)（prompt 模板）
关联 Tracker：QED-067
归档判定：待关闭时按 [ADR 0009](../adr/0009-closed-plan-archival.md) 做 Retain/Delete 两态判定

## 目标与成功标准

v1.0 主线：QED-Tracker 以 **8900 网关（`qed-engine` 模式）** 接入 QED-Engine 本地文字模型
（qwen3.5 9B），并将 prompt 与 pipeline 逐步改为 **LangChain（LCEL）** 编排；后续扩展
MCP 与 skill。本任务是「学习优化本地小模型」的一环。

成功标准（待评审细化）：

1. `qed-engine` 模式经 8900 网关调用本地 qwen3.5 9B 成功，调用记录落 `qed_llm_calls`。
2. 至少一条现有管线（候选：book-confirm / course explore）以 LangChain LCEL 重写并通过门禁。
3. MCP / skill 扩展点有明确设计（不要求本轮实现）。
4. 模型文件、生命周期、网关归 QED-Engine；本仓只做接入与 prompt/pipeline 编排。

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

- 范围：本仓模型接入（`qed-engine` 网关口径）、prompt/pipeline 的 LangChain 编排抽象、
  MCP/skill 预留设计。
- 非目标：模型权重/训练/量化、模型文件与生命周期管理（归 QED-Engine）；不改动 `qed_llm_calls`
  表结构；不改变「模型不写资源事实」约束。

## 前置条件

- QED-Engine 本地 qwen3.5 9B 服务与 8900 网关可用（根仓库侧）。
- 根 `.env` 模式与模型名确认。

## 工作项（简要，待细化）

1. 端到端验证 `qed-engine` 模式调用本地模型（真实冒烟 + `qed_llm_calls` 落库）。
2. 引入 LangChain 依赖与适配层：PromptTemplate / Runnable（LCEL）/ OutputParser 包装现有
   `llm_client`（保持业务 API 不变）。
3. 选一条管线试点迁移（候选 book-confirm 或 course explore），TDD 先红后绿。
4. MCP / skill 扩展点设计（工具注册、调用边界、与「模型不写资源事实」约束的关系）。

## 验证与验收

- 默认测试不访问公网/本地模型；用假顾问或 `httpx.MockTransport`（见[测试门禁](../standards/testing.md)）。
- 真实冒烟记录（时间/模型/结果）按[操作指南](../guides/operations.md)要求登记。
- 全量门禁按[开发指南](../guides/development.md)执行。

## 回滚

LangChain 为新增适配层，保留原 `llm_client` 直调路径可回退。

## 关闭与归档

关闭时按 [ADR 0009](../adr/0009-closed-plan-archival.md) 做 Retain/Delete 两态判定；
设计确定后按 [ADR 0003](../adr/0003-pending-design-location.md) 迁入 `design/`。
