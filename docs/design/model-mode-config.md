# 模型模式与密钥分置设计（model-mode-config）

设计状态：Proposed
实现状态：Not Started
最后更新：2026-08-20
需求方：QED-Engine（根仓库 REQ-043「QED-Tracker 模型模式与密钥分置改造」，设计依据根仓库
[llm-gateway-and-model-management.md](../../../docs/design/llm-gateway-and-model-management.md)
「QED-Tracker（请求方：QED-Tracker 仓库，REQ-043）」一节）
关联代码：`src/qed_tracker/config.py`（`.env` 读取与密钥别名）、
`src/qed_tracker/llm_client.py`（新增，兼容层）、`scripts/qed_tracker_service.py`（`--mode`）、
根 `.env` / 自身 `.env`（新建）
关联测试：`tests/test_config_catalog_matching.py`（`.env`/密钥别名用例挂接位置）、
`tests/test_service_scripts.py`（`--mode` 生命周期用例挂接位置）、
`tests/test_llm_client.py`（新增，兼容层双模式用例）
关联 ADR：无新增（沿用 [ADR 0001](../adr/0001-tracker-service-architecture.md)）

> **状态说明**：本设计为**未来实现方案**，尚未评审、未开工。跨项目契约（变量命名、网关端点、
> `qed_llm_calls` 表结构、密钥约定）以根仓库
> [llm-gateway-and-model-management.md](../../../docs/design/llm-gateway-and-model-management.md)
> 为准，本仓库只链接不复制。

> **跨项目裁决同步（2026-08-20）**：根仓库裁决（ARCH-017）——逐厂商 key 别名**全部取消**
> （含 `QWEN_API_KEY` / `DASHSCOPE_API_KEY` / `DEEPSEEK_API_KEY` / `GLM_API_KEY`），统一
> `API_KEY` + `QED_API_PROVIDER`（厂商选择，当前 qwen）为准；**本设计内所有「旧变量降级为
> 别名」「兼容别名」表述均已按此修订，不保留任何别名回退**。契约以根仓库
> [configuration-and-secrets.md](../../../docs/design/configuration-and-secrets.md) 当前约定为准。

## 背景与目的

当前 QED-Tracker 无自身 `.env`，`config.py` 直读根 `.env` 的 `QED_*` 变量，密钥只认
`QWEN_API_KEY`。根仓库 LLM 网关与模型管理改造轮（P3，REQ-043）要求 QED-Tracker：

1. 新建自身 `.env`，密钥统一为 `API_KEY`（唯一密钥变量，无别名回退），非密钥私有配置归自身 `.env`；
2. `config.py` 改读自身 `.env`（根 `.env` 兜底，保持独立性铁律）；
3. 新增 `llm_client.py` 兼容层：`local`（direct，直连）/ `qed-engine`（gateway，经 8900 网关，
   不接触密钥）；
4. `scripts/qed_tracker_service.py` 增加 `--mode local|qed-engine`，重启可换模式，状态持久化；
5. local 模式调用记录写根仓库 `qed_llm_calls` 表（`service=qed_tracker`）。

## 自身 `.env` 变量表（新建，建议模板进 README/operations）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `QED_API_SELECT` | `local` | 模式：`api`（API key）/ `local`（direct 直连）/ `qed-engine`（经 8900 网关）。QED-Tracker 视角取 `local` / `qed-engine` 二值 |
| `API_KEY` | 空 | **唯一密钥变量**（逐厂商 key 别名已全部取消、无回退；根仓库 ARCH-017 收敛）；厂商由根仓库侧 `QED_API_PROVIDER` 决定（QED-Tracker 只以 qwen 提供 API，不感知该变量） |
| `QED_LLM_GATEWAY_URL` | `http://127.0.0.1:8900` | `qed-engine` 模式读取；`local`/`api` 模式忽略 |
| `QED_MODEL` | `qwen-plus` | 文字模型名（`llm_model`） |
| `QED_DB_HOST` | `127.0.0.1` | 见 `QED_DB_*` |
| `QED_DB_PORT` | `3306` | 见 `QED_DB_*` |
| `QED_DB_NAME` | `qed` | 见 `QED_DB_*` |
| `QED_DB_USER` | `root` | 见 `QED_DB_*` |
| `QED_DB_PASSWORD` | 空 | MySQL 密钥，只经环境读取，不入 `Settings` repr |
| `QED_TRACKER_PORT` | `8901` | 服务端口 |

- `QED_DB_*` 五变量：`QED_DB_HOST` / `QED_DB_PORT` / `QED_DB_NAME` / `QED_DB_USER` /
  `QED_DB_PASSWORD`，承载 qed 库连接（调用记录写 `qed_llm_calls` 复用）。
- 既有非密钥私有配置（`QED_AXIOM_URL`、`QED_TRACKER_URL`、`QED_PROXY`、`QED_TIMEOUT_SECONDS`、
  `QED_RETRIES`、`QED_TLS_VERIFY`、`QED_SOURCES` 等）继续由自身 `.env` 承载，行为不变。

## 改动范围

### 1. `config.py` 改读自身 `.env`

- 新增自身 `.env` 读取（仓库根 `.env`），读取优先级：真实环境变量 → 自身 `.env` → 根 `.env`
  （向上走查兜底）→ 内置默认值；`.env` 解析**不修改 os.environ**（合并视图，避免测试环境污染）。
- `_ENV_MAP` 新增 `QED_API_SELECT → api_select`、`QED_LLM_GATEWAY_URL → llm_gateway_url`；
  根 `.env` 直读逻辑保留为兜底。
- `llm_api_key()` 只读唯一密钥变量 `API_KEY`（**无 `QWEN_API_KEY` / `DASHSCOPE_API_KEY` 等
  任何别名回退**，根仓库 ARCH-017 裁决）；`llm_configured` 相应判断。
- `degradation_notice` 提示文案同步统一 `API_KEY`。

### 2. 新增 `src/qed_tracker/llm_client.py` 兼容层

对外提供统一调用接口，业务调用方代码不变；内部按 `QED_API_SELECT` 切换：

| 模式 | 实现 | 行为 |
| --- | --- | --- |
| `local` | `direct` | 用自身 `.env` 的 `API_KEY` 直连 dashscope 文字模型（qwen-plus），**不依赖 8900 在线**（独立性铁律） |
| `qed-engine` | `gateway` | HTTP 调 `QED_LLM_GATEWAY_URL` 的 `/llm/text` 网关，**不接触密钥**，密钥只存根仓库 |

- `direct` 复用现有 dashscope 调用语义（OpenAI 兼容），`gateway` 按根仓库端点契约
  `POST /llm/text`（`{prompt, system?, prompt_template?, max_tokens?}` → `{reply, call_id}`）。
- 缺密钥/网关不可达时降级并明确报错，不阻塞启动（沿用现有降级约定）。

### 3. `scripts/qed_tracker_service.py` 增加 `--mode`

- `start` / `restart` 支持 `--mode local|qed-engine`；不传时默认读自身 `.env` 的 `QED_API_SELECT`。
- 模式持久化到 `logs/` 状态文件（与 PID/日志契约同目录）；重启可改模式（重启换模式生效）。
- `status` 输出当前运行模式。PID 文件 / 优雅停止 / 强杀兜底 / `--wait` 健康等待沿用现有契约。

### 4. local 模式调用记录写 `qed_llm_calls`

- `direct`（local/api 模式）调用后由 `llm_client.py` 自行写入 qed 库 `qed_llm_calls` 表，
  `service=qed_tracker`、`mode=api`、`provider=qwen`、`endpoint=text`（2026-08-20 评审定案：
  direct 本质为云端 API key 调用，mode 记 api 与根仓库路由语义一致）。
- `qed-engine` 模式下网关统一写表，QED-Tracker 不重复写。
- **表结构契约**：以根仓库
  [llm-gateway-and-model-management.md](../../../docs/design/llm-gateway-and-model-management.md)
  「调用记录表 `qed_llm_calls`」一节为准（根仓库 Alembic 迁移落地，qed 库），本仓库不另行定义；
  本层用 SQLAlchemy engine（复用 `QED_DB_*`）INSERT，DB 不可达降级记日志不阻塞模型调用。

## 验证与回执

- 定向测试：`tests/test_config_catalog_matching.py` 覆盖 `.env` 来源优先级与密钥唯一变量/别名
  回退；`tests/test_llm_client.py`（新增 10 用例）覆盖 `direct` / `gateway` 双模式与
  `qed_llm_calls` 落库/降级（固定 fixture，不访问公网）；`tests/test_service_scripts.py`
  （26 用例）覆盖 `--mode` 生命周期与状态持久化；`tests/test_bailian_advisor.py`、
  `tests/test_main_line_advisor.py` 覆盖 gateway 路由（不接触密钥）。
- 真实冒烟：自身 `.env` 生效（`local` 直连可用，无 8900 也能评估）；`--mode qed-engine` 重启后
  经 8900 `/llm/text` 调用成功且调用记录 `service=qed_tracker` 落库；`--mode local` 调用记录
  落库同表。
- 全量门禁按 [开发指南](../guides/development.md) 执行；**文档白名单同步**已登记
  （`tests/test_documentation.py` 的 `REQUIRED_CURRENT_DOCS` 与 `DESIGN_DOCS` 含本设计文档）。
- 回执根仓库 REQ-043（提交号 + 测试输出），根仓库侧联调验收。
