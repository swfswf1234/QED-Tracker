# 模型模式与密钥分置实现计划（model-mode-config）

状态：Current
最后更新：2026-08-20

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** QED-Tracker 模型调用改为双模式（`local` 直连 dashscope qwen / `qed-engine` 经 8900 网关），密钥统一为自身 `.env` 的 `API_KEY`，承接根仓库 REQ-043。

**Architecture:** 设计见 `docs/design/model-mode-config.md`（Accepted/Implemented）。新增 `src/qed_tracker/llm_client.py` 兼容层：`direct`（自身 `API_KEY` 直连 dashscope，**离线可用**，本子项目只以 qwen 模型提供 API）/ `gateway`（HTTP 调 8900 `POST /api/v1/llm/text`，不接触密钥）；三处 advisor（bailian.py / book_advisor.py / main_line/advisor.py）`_complete` 统一走兼容层，业务 API 不变；local 模式调用记录写 `qed_llm_calls`（`service=qed_tracker`、`mode=api`、`provider=qwen`、`endpoint=text`，2026-08-20 评审定案）。config.py 自实现 `.env` 解析（无 python-dotenv 依赖）。

**Tech Stack:** Python 3.12（QED_env）、pytest（TDD）、ruff。

**约束：** 优先级 = 真实环境变量 > 自身 `.env`（QED-Tracker 仓库根）> 根 `.env`（向上走查兜底）> 内置默认；`.env` 解析不修改 os.environ（合并视图，避免测试环境污染）；`API_KEY` 为唯一密钥变量（逐厂商 key 已取消，根仓库 configuration-and-secrets.md 2026-08-20 收敛），`DASHSCOPE_API_KEY` 为兼容别名；DB 不可达时 qed_llm_calls 写入降级记日志不阻塞；qed-engine 模式由网关写表，QED-Tracker 不重复写；白名单登记与 `llm_client.py` 创建同批提交（doc 测试 `test_current_code_and_test_references_resolve` 校验代码路径存在）。

---

## 任务 1：自身 `.env` + config.py 改读自身 `.env`（TDD）

**Files:**
- Create: `.env`（本地密钥，gitignore 已排除）
- Edit: `src/qed_tracker/config.py`
- Edit: `tests/test_config_catalog_matching.py`
- Edit: `tests/test_cli_architecture.py`、`tests/test_main_line_cli.py`（DB 门禁测试 chdir 隔离真实 .env）

- [x] **Step 1: 写失败测试** — `tests/test_config_catalog_matching.py`：自身 `.env` 生效（tmp 目录建 .env 后 load_settings 读到）；根 `.env` 兜底（自身 .env 缺失时向上走查）；真实环境变量优先；空值跳过留给兜底来源；`llm_api_key()` 只读唯一密钥变量 `API_KEY`（QED-038/ARCH-017：`QWEN_API_KEY`/`DASHSCOPE_API_KEY` 等别名全部取消、无回退）。
- [x] **Step 2: 运行确认失败**。
- [x] **Step 3: 实现** — `config.py`：`.env` 解析为合并视图（不修改 os.environ；真实环境变量 > 自身 `.env` > 根 `.env` 兜底 > 内置默认）；`Settings`/`_ENV_MAP` 增 `QED_API_SELECT → api_select`、`QED_LLM_GATEWAY_URL → llm_gateway_url`；`llm_api_key()` 唯一密钥变量；`degradation_notice` 文案同步统一 `API_KEY`。仓库根新建 `.env` 模板（注释齐全；密钥留空由根 `.env` 兜底）。
- [x] **Step 4: 验证通过** — `pytest tests/test_config_catalog_matching.py -q` 17 passed + DB 门禁测试适配后回归。

## 任务 2：llm_client.py 兼容层（TDD）

**Files:**
- Create: `src/qed_tracker/llm_client.py`
- Create: `tests/test_llm_client.py`

- [x] **Step 1: 写失败测试** — `tests/test_llm_client.py`（固定 fixture，不访问公网，10 用例）：`direct` 模式经 MockTransport 验证 dashscope `/chat/completions` 请求与响应解析；`gateway` 模式经 MockTransport 验证 `POST {QED_LLM_GATEWAY_URL}/api/v1/llm/text`（`{prompt, system?, prompt_template?, max_tokens?}` → `{reply, call_id}`，messages 映射 prompt/system，不接触密钥）；缺密钥报错文案含统一 `API_KEY`；DB 不可达时 qed_llm_calls 写入降级不抛；gateway 不写调用记录。
- [x] **Step 2: 运行确认失败**。
- [x] **Step 3: 实现** — `llm_client.py`：`LlmClient`（api_select/api_key/model/base_url/gateway_url/timeout/call_budget/max_tokens/client/engine 注入）；`complete(messages, *, prompt_template="")` 返回内容文本；`api_select` 取 local/api → direct，qed-engine → gateway；direct 走 OpenAI 兼容 `chat/completions`；gateway 走 8900 `/api/v1/llm/text`；direct 后 INSERT `qed_llm_calls`（SQLAlchemy engine，原生 SQL，`mode=api/provider=qwen/endpoint=text/service=qed_tracker`，`duration_ms/status/error`，DB 不可达降级）。
- [x] **Step 4: 验证通过** — 10 passed。

## 任务 3：三处 advisor 接入兼容层（TDD）

**Files:**
- Edit: `src/qed_tracker/providers/bailian.py`、`src/qed_tracker/providers/book_advisor.py`、`src/qed_tracker/main_line/advisor.py`
- Edit: `tests/test_bailian_advisor.py`、`tests/test_main_line_advisor.py`
- Edit: `src/qed_tracker/cli.py`（`_paper_service`/`_mainline_advisor` 构造 + `_llm_call_engine`）、`src/qed_tracker/api/main.py`（Application advisor 构造）

- [x] **Step 1: 写失败测试** — bailian / main_line advisor 各增 gateway 路由测试（api_select="qed-engine"、api_key=""，断言请求路径 `http://127.0.0.1:8900/api/v1/llm/text` 且无 Authorization 头）。
- [x] **Step 2: 运行确认失败**。
- [x] **Step 3: 实现** — 三处 `_complete` 改用 `self.llm_client.complete(messages)`（gateway 模式跳过密钥检查；错误文案保留原类型 BailianError/ValueError 但密钥缺失提示统一 `API_KEY`）；构造器 `api_key/base_url/client` 参数保留（向后兼容）但改经 `llm_client` 构造，新增 `api_select`/`gateway_url`/`engine` 可选参数；`calls`/`usages`/`response_sha256` metadata 契约不变。
- [x] **Step 4: 验证通过** — 既有 advisor 用例 + gateway 新用例全绿。

## 任务 4：service 脚本 --mode + 契约文档同步（TDD）

**Files:**
- Edit: `scripts/qed_tracker_service.py`
- Edit: `tests/test_service_scripts.py`
- Edit: `docs/design/service-lifecycle.md`、`docs/design/model-mode-config.md`（实现状态更新）、`docs/guides/operations.md`

- [x] **Step 1: 写失败测试** — `--mode local|qed-engine` 解析；start/restart 带 `--mode` 写入 `logs/qed-tracker-mode` 状态文件且子进程 env 注入 `QED_API_SELECT`；不传时默认读自身 `.env`（缺省 local）；重启可换模式；status 输出当前运行模式。
- [x] **Step 2: 运行确认失败**。
- [x] **Step 3: 实现** — `scripts/qed_tracker_service.py`：`--mode` 参数（start/restart，choices）；`MODE_FILE = LOG_DIR / "qed-tracker-mode"`；`default_mode()` 读自身 `.env` 的 QED_API_SELECT；spawn 时 `env = {**os.environ, "QED_API_SELECT": mode}`；status 输出 `running (pid N, mode X)`。
- [x] **Step 4: 文档同步** — service-lifecycle.md 补 `--mode` 契约（参数/状态文件/PID/日志/退出码）；operations.md 补 `--mode` 用法与自身 `.env` 模板；model-mode-config.md 实现状态更新 + 评审定案登记。
- [ ] **Step 5: 验证通过** + 全量门禁 `pytest tests -q` + `ruff check src tests scripts` + `git diff --check`。
- [x] **Step 6: 白名单同步** — `tests/test_documentation.py`：`REQUIRED_CURRENT_DOCS` += tutorial-naming.md、model-mode-config.md、2026-08-model-mode-config.md、2026-08-tutorial-naming.md；`DESIGN_DOCS` += 两份设计文档。
- [ ] **Step 7: 提交** — 显式路径 commit。

## 收尾

- [ ] 真实冒烟：8901 健康；无 8900 时 `local` 直连可用（QED_API_SELECT=local + API_KEY 生效）；`--mode qed-engine` 重启后经网关 `/api/v1/llm/text` 调用成功且调用记录 `service=qed_tracker` 落库；`--mode local` 调用记录落同表（`mode=api/provider=qwen`）。
- [ ] 整理 REQ-043 回执内容（提交号 + 测试输出）交付用户写入根仓库 REQ-043 行；根仓库侧联调验收。
