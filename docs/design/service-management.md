# 服务管理中心设计（service-management）

设计状态：Accepted
实现状态：Implemented
确认状态：暂定
最后更新：2026-09-07
需求方：QED-Engine（根仓库 REQ-017①「仓库内提供正式启动入口」；QED-037/REQ-043「模型模式与密钥分置」扩展 `--mode`；ADR 0008 职责重划合并立项）
关联代码：`scripts/qed_tracker_service.py`、`src/qed_tracker/config.py`、`src/qed_tracker/llm_client.py`、
`src/qed_tracker/cli.py`（serve 命令）、`src/qed_tracker/api/main.py`（CORS）、自身 `.env`
关联测试：`tests/test_service_scripts.py`、`tests/test_llm_client.py`、
`tests/test_config_catalog_matching.py`（`.env` 优先级与密钥唯一变量）、`tests/test_bailian_advisor.py`、
`tests/test_main_line_advisor.py`（gateway 路由）
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)、[ADR 0008](../adr/0008-design-doc-scope-reshuffle.md)

> 本文档是**服务运行面唯一设计事实源**（ADR 0008）：由原 `service-lifecycle.md`（生命周期脚本）
> 与 `model-mode-config.md`（模型模式与密钥分置）合并，并新增多项目约定导航节。职责边界：
> 只管服务启停契约、运行事实、配置与模型模式、多项目约定导航；不管任何业务管线
> （取书见 [download-pipeline](download-pipeline.md)、录入见 [knowledge-import](knowledge-import.md)、
> 端点契约见 [架构 API](../architecture/api.md)）。

## 背景与目的

QED-Tracker 以 8901 HTTP 服务运行，启动命令为 `qed-tracker serve`（等价
`python -m qed_tracker.cli serve`）。本文档承载两条运行面主线：

1. **服务生命周期**：根仓库 8900 控制中心此前直接 `Popen` 托管本服务，进程管理细节散落在根仓库
   `service_manager.py`；本仓库提供**唯一、自含的生命周期脚本** `scripts/qed_tracker_service.py`
   （REQ-017①），8900 只需黑盒调用。
2. **配置与模型模式**：本仓库以自身 `.env` 承载非密钥私有配置，密钥统一为唯一变量 `API_KEY`
   （REQ-043/QED-037/038）；LLM 调用经兼容层双模式（`local` 直连 / `qed-engine` 经 8900 网关），
   启停脚本支持 `--mode` 切换。

多项目约定（端口、dataset 布局、共享表归属）按 [AGENTS.md](../../AGENTS.md) 原则
**只链接不复制**：跨项目契约以 QED-Engine 根仓库 `docs/` 为准，本文档仅登记本仓实现事实指针。

## 决策登记（QED-037/038 定案，2026-08-20 评审）

> 1. 本子项目只以 qwen 模型提供 API：`local` 模式 = 自身 `.env` 的 `API_KEY` 直连 dashscope；
> 2. 三处 advisor（bailian / book_advisor / main_line）`_complete` 统一经 llm_client 兼容层，
>    业务 API 不变；
> 3. local 调用记录 `qed_llm_calls` 取值 `service=qed_tracker`、`mode=api`、`provider=qwen`、
>    `endpoint=text`（direct 本质为云端 API key 调用，mode 记 api 与根仓库路由语义一致）；
> 4. config.py 的 `.env` 解析**不修改 os.environ**（合并视图，真实环境变量优先），
>    避免测试环境污染；service 脚本经子进程 env 注入 `QED_API_SELECT` 使模式生效；
> 5. QED-038（ARCH-017）：`llm_api_key()` 只读唯一密钥 `API_KEY`，无任何别名回退。

> **跨项目裁决同步（2026-08-20）**：根仓库裁决（ARCH-017）——逐厂商 key 别名**全部取消**
> （含 `QWEN_API_KEY` / `DASHSCOPE_API_KEY` / `DEEPSEEK_API_KEY` / `GLM_API_KEY`），统一
> `API_KEY` + `QED_API_PROVIDER`（厂商选择，当前 qwen）为准；**所有「旧变量降级为别名」
> 「兼容别名」表述均已按此修订，不保留任何别名回退**。契约以根仓库
> [configuration-and-secrets.md](../../../docs/design/configuration-and-secrets.md) 当前约定为准。

## 服务生命周期脚本契约

单文件纯标准库（无第三方依赖），子命令：

```text
python scripts/qed_tracker_service.py {start|stop|restart|status} [--port PORT] [--mode local|qed-engine]
```

- `start`：默认拉起进程后立即返回；`--wait [SECONDS]` 时轮询 `/api/v1/health` 直到就绪
  （默认超时 30s）。已运行（PID 存活或端口探测通过）时报 `already running`，幂等退出 0。
  成功输出 `pid: <n>` 与 `log: <path>`。
- `stop`：读取 PID 文件 → `CTRL_BREAK_EVENT` 优雅停止 → 5s 宽限（`_proc_alive` 判活）→
  未退出则 `taskkill /PID /T /F` 强杀整树再等 5s → 复核仍存活则报 `stop failed` 并退出 1
  （PID 文件保留现场供手动恢复）；确认终止后删除 PID 文件，强杀兜底生效时输出
  `stopped (forced)`。无 PID 或进程已死时清理残留并幂等退出 0。
- `restart`：先 stop 后 start，透传 `--wait` 与 `--mode`。
- `status`：PID 存活 / 端口探测（socket 预检 + HTTP 健康确认）双路径，输出
  `running (pid <n>, mode <mode>)` / `running (port probe <port>)` / `stopped`，信息型恒退出 0。
- `--port`：health 探测端口，默认取 `QED_TRACKER_PORT` 环境变量，无则 8901；`serve` 本身
  仍按配置（自身 `.env` 的 `QED_TRACKER_PORT`）监听。
- `--mode local|qed-engine`（QED-037）：模型模式——`local`=直连 dashscope /
  `qed-engine`=经 8900 网关 `/llm/text`。不传时默认读自身 `.env` 的 `QED_API_SELECT`
  （缺省 `local`）；模式持久化到 `logs/qed-tracker-mode`（重启可换模式，重启后生效）；
  子进程 env 注入 `QED_API_SELECT`（env 优先于 `.env`，config.py 读取生效）。

退出码：`0` 成功或幂等；`1` 运行失败（spawn 失败、`--wait` 健康超时、stop 无法终止）；`2` 参数错误（argparse）。

## 运行事实

```text
QED-Tracker/
├── scripts/qed_tracker_service.py   # 生命周期脚本
└── logs/                            # 已 gitignore，运行产物
    ├── qed-tracker.pid              # PID 文件（纯 PID 文本）
    ├── qed-tracker-mode             # 模型模式状态文件（QED-037，local / qed-engine）
    ├── qed-tracker-serve.log        # 子进程 stdout/stderr（uvicorn 访问与未捕获异常）
    └── qed-tracker.log              # 应用级日志（serve 双通道 FileHandler，不受脚本影响）
```

子进程命令 = `sys.executable -m qed_tracker.cli serve`，工作目录为仓库根；`serve` 自身完成
`.env` 查找、MySQL 模型自愈（`ensure_schema()`）与双通道日志（stderr + `logs/qed-tracker.log`），
脚本不再重定向应用日志，两文件互不重复。模型模式经子进程 env 注入（见上 `--mode` 契约）。

## 与 8900 控制中心接入契约

根仓库 `service_manager.py` 的 `tracker` 单元调用本脚本：

| 操作 | 根仓库调用 | 结果来源 |
| --- | --- | --- |
| start | `python scripts/qed_tracker_service.py start`（workdir=QED-Tracker） | stdout 首行 `pid: <n>` 或读 `logs/qed-tracker.pid` |
| stop | `python scripts/qed_tracker_service.py stop` | 脚本自含优雅停止 + 强杀兜底 + 复核，退出码 0 成功 / 1 终止失败 |
| restart | `python scripts/qed_tracker_service.py restart` | 同上 |
| 状态 | 8900 既有端口探测不变（socket + HTTP，不调用脚本） | — |

- 脚本**自含完整生命周期**（PID 文件 + 优雅停止 + 强杀兜底），8900 无需再持有 Popen 句柄；
  `_MANAGED` 的 PID 记录可改为启动后读脚本输出/PID 文件，仅用于前端展示。
- 8900 的启动/停止过渡窗口（15s）、端口探测、并发 409 语义均不变；停止未运行服务的幂等
  由 8900 现有探测先行判断（脚本侧 stop 对未运行也幂等退出 0）。
- 环境继承：8900 以自身进程环境调用脚本（根 `.env` 已注入），`serve` 的 `.env` 查找
  （config.py 自身 `.env` → 根 `.env` 兜底）覆盖独立启动场景；`--mode` 经子进程 env
  注入 `QED_API_SELECT`。

## 平台约束（Windows 实现细节）

- Windows 下 `os.kill(pid, 0)` 会直接 TerminateProcess（2026-08-17 实测），进程存在性检测：
  start/status 幂等路径用 `tasklist /FI "PID eq <pid>"`（其误判有端口探测兜底，无害）；
  stop 路径一律用 `_proc_alive`（ctypes kernel32 `OpenProcess` + `GetExitCodeProcess`，
  毫秒级、无 WMI/GBK 依赖）——tasklist 探测失败/超时曾被当作「进程已死」导致假 stopped
  （2026-09-04 根因修复，与根仓库脚本同构），`_proc_alive` 探测失败按存活处理（未知 ≠ 已死）。
- 优雅停止用 `signal.CTRL_BREAK_EVENT`（子进程以 `CREATE_NEW_PROCESS_GROUP` 拉起，uvicorn
  捕获 KeyboardInterrupt 优雅收尾），5s 宽限后 `taskkill /PID /T /F` 强杀兜底。无交互控制台
  环境（服务/管道调用）下 `os.kill(CTRL_BREAK)` 抛 SystemError（包裹 WinError 87，2026-08-17
  实测），conda run 等跨 console 语境还可能静默空放——脚本捕获 `(OSError, SystemError)` 走
  taskkill 强杀兜底并标注 `(forced)`，不崩溃；强杀后再以 `_proc_alive` 复核，仍存活报
  `stop failed` 并退出 1（绝不假 stopped，2026-09-04 修复）。
- `_kill_tree` 返回 bool 并打印 taskkill 失败输出（不再静默吞错），失败可见、可诊断。
- 非 Windows 平台回退：`NEW_PROCESS_GROUP = 0`、`CTRL_BREAK_EVENT = SIGTERM`，`_proc_alive`
  回退 `_pid_is_alive`；taskkill 在非 Windows 下失败返回 False 走 `stop failed`
  （Windows 专属部署）。

## 配置与密钥

### `.env` 读取优先级

`config.py` 读取优先级：**真实环境变量 → 自身 `.env` → 根 `.env`（向上走查兜底）→ 内置默认值**；
`.env` 解析**不修改 os.environ**（合并视图，避免测试环境污染）；值支持内联注释剥离
（` #` 前有空白才截断，避免误伤密码等真实值）。根 `.env` 由统一 CLI `qed` 启动服务时注入；
独立启动时 `config.py` 自动向当前目录上方查找根 `.env`（不覆盖已显式设置的环境变量），
无 `.env` 时降级运行（启动尾注提醒）。

### `.env` 变量表（自身 `.env` 常用键）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `QED_API_SELECT` | `local` | 模式：`api`（API key）/ `local`（direct 直连）/ `qed-engine`（经 8900 网关）。QED-Tracker 视角取 `local` / `qed-engine` 二值；**语义钉不可删**（两仓 local 语义不同：本仓=直连 dashscope，根仓=LM Studio 本地模型） |
| `API_KEY` | 空 | **唯一密钥变量**（逐厂商 key 别名已全部取消、无回退；根仓库 ARCH-017 收敛）；厂商由根仓库侧 `QED_API_PROVIDER` 决定（QED-Tracker 只以 qwen 提供 API，不感知该变量）；**独立运行底线键留守**（单独 clone 无根 `.env` 时保证 LLM 能力） |
| `QED_LLM_GATEWAY_URL` | `http://127.0.0.1:8900` | `qed-engine` 模式读取；`local`/`api` 模式忽略（REQ-063 下沉根 `.env`） |
| `QED_MODEL` | `qwen-plus` | 文字模型名（`llm_model`）；**本仓 `.env` 实际取值 `deepseek-v4-flash-0731`**（P15 探索纪律有意覆盖，2026-08-26 起，全链验证可用，回执注明偏差——有意不同于根仓库默认 qwen 系） |
| `QED_LLM_TIMEOUT` | `300` | LLM 上游调用超时秒数（REQ-061 同步：原 60s 硬编码默认曾致 courses@v3 长生成 ReadTimeout；REQ-063 下沉根 `.env`） |
| `QED_DB_HOST` | `127.0.0.1` | 见 `QED_DB_*` |
| `QED_DB_PORT` | `3306` | 见 `QED_DB_*`（REQ-063 下沉） |
| `QED_DB_NAME` | `qed` | 见 `QED_DB_*`（REQ-063 下沉） |
| `QED_DB_USER` | `root` | 见 `QED_DB_*`（REQ-063 下沉） |
| `QED_DB_PASSWORD` | 空 | MySQL 密钥，只经环境读取，不入 `Settings` repr；**独立运行底线键留守** |
| `QED_TRACKER_PORT` | `8901` | 服务端口 |

### 全量键清单（代码事实源 `config.py` `_ENV_MAP`，27 键）

`QED_MODEL`、`QED_AXIOM_URL`（默认 `http://127.0.0.1:8902`）、`QED_TRACKER_PORT`、
`QED_TRACKER_URL`、`QED_DATA_ROOT`（数据根，见下文「多项目约定导航」）、
`QED_DB_HOST` / `QED_DB_PORT` / `QED_DB_NAME` / `QED_DB_USER` / `QED_DB_PASSWORD`、
`QED_PROXY`（代理访问，绕开 archive.org/openlibrary.org 的 DNS 污染与限流）、
`QED_TIMEOUT_SECONDS`（30）、`QED_RETRIES`（3）、`QED_FETCH_ATTEMPT_TIMEOUT`
（旧键一版别名 → `QED_BOOK_CANDIDATE_BUDGET`，新键设置时被其覆盖）、
`QED_BOOK_CANDIDATE_BUDGET`（300，候选级预算秒）、`QED_BOOK_MIN_PAGES`（10）、
`QED_BOOK_MIN_SIZE_BYTES`（204800）、`QED_BOOK_SEARCH_LIMIT`（8）、
`QED_BOOK_QUERY_VARIANTS`（3）、`QED_BOOK_LLM_QUERY`（true）、`QED_BOOK_LLM_CONFIRM`（true）、
`QED_BOOK_LLM_BUDGET`（8）、`QED_TLS_VERIFY`（true）、`QED_LLM_BASE_URL`
（dashscope compatible-mode）、`QED_LLM_TIMEOUT`（300）、`QED_API_SELECT`、
`QED_LLM_GATEWAY_URL`。

- `QED_SOURCES`：特例处理（env 或文件，逗号分隔），默认
  `internet_archive, open_library, google_books, libgen_li`（libgen_li 为发现专用来源，
  metadata_only + 人工下载 links，无直链不落盘）。
- `API_KEY`：唯一密钥变量，经 `_ENV_KEYS` + `llm_api_key()` 读取（无别名回退）。
- `QED_BOOK_*` 七键与 `QED_FETCH_ATTEMPT_TIMEOUT` 的取书语义见
  [下载管线设计](download-pipeline.md)配置项清单。
- 无 `QED_DB_PASSWORD` 时数据库相关能力降级：服务与 CLI 正常启动，登记暂缓并输出提醒；
  不因缺库缺密阻塞下载主链路。

### LLM 兼容层双模式（`llm_client.py`）

| 模式 | 实现 | 行为 |
| --- | --- | --- |
| `local` | `direct` | 用自身 `.env` 的 `API_KEY` 直连 dashscope 文字模型，**不依赖 8900 在线**（独立性铁律） |
| `qed-engine` | `gateway` | HTTP 调 `QED_LLM_GATEWAY_URL` 的 `/llm/text` 网关（`{prompt, system?, prompt_template?, max_tokens?}` → `{reply, call_id}`），**不接触密钥**，密钥只存根仓库 |

- 三处 advisor（bailian / book_advisor / main_line）`_complete` 统一经兼容层，业务 API 不变；
  service 脚本 `--mode` 经子进程 env 注入 `QED_API_SELECT` 生效。
- local 调用记录由 `llm_client.py` 写 qed 库 `qed_llm_calls` 表
  （`service=qed_tracker` / `mode=api` / `provider=qwen` / `endpoint=text`）；`qed-engine` 模式下
  网关统一写表，本仓不重复写。**表结构契约**以根仓库
  [llm-gateway-and-model-management.md](../../../docs/design/llm-gateway-and-model-management.md)
  为准，本层用 SQLAlchemy engine（复用 `QED_DB_*`）INSERT，DB 不可达降级记日志不阻塞模型调用。
- 缺密钥/网关不可达时降级并明确报错，不阻塞启动（沿用现有降级约定）。

## 多项目约定导航

> 跨项目契约（端口、根 `.env` 变量、dataset 布局）以 QED-Engine 根仓库 `docs/` 为准
> （[AGENTS.md](../../AGENTS.md)）：本节只登记事实源链接与本仓实现事实指针，不复制契约正文。

| 约定域 | 唯一事实源 | 本仓实现事实指针 |
| --- | --- | --- |
| 端口 | 根仓库 [four-service-architecture.md](../../../docs/architecture/four-service-architecture.md)（8903 前端 / 8900 后端 / 8902 Axiom-Flow / 8901 本服务）；端口变量见根仓库 [configuration-and-secrets.md](../../../docs/design/configuration-and-secrets.md) | 本仓速查表复制于 [本地开发环境](../standards/local-dev.md)（端口表）；`QED_TRACKER_PORT`（默认 8901） |
| CORS | 根仓库 service-contracts.md 裁决：8903 前端只连 8900 网关，浏览器不直连 8901/8902；直连 8901 的 CORS 收窄为**可选后续（未执行）** | 现状 `src/qed_tracker/api/main.py`：`FRONTEND_ORIGINS` 允许 `http://127.0.0.1:8903` / `http://localhost:8903`（CORSMiddleware）——两口径并存的现状如实登记 |
| dataset 布局 | 根仓库 [dataset-conventions.md](../../../docs/design/dataset-conventions.md)（`raw/<domain>/<course>/` 唯一被外部读取、写入方本仓；tmp 按项目分桶；tmp→raw 原子落盘；`<slug>_<sha256前8>` 命名；raw 不可变）；`QED_DATA_ROOT` 定义见根仓库 configuration-and-secrets.md | `config.py` `state_dir` = `<QED_DATA_ROOT>/qed-tracker/meta`（ARCH-019）；`inventory.py`（`raw/<domain_id>/<course_id>/` 落盘、`tmp/qed-tracker/downloads` 下载临时区）；本仓 `.env` `QED_DATA_ROOT=D:\coding\QED-Engine\dataset` |
| 共享表归属 | 本仓 [数据库共享表设计](../architecture/database-shared-tables.md)（`qed_*` 共享 / `qt_*` 本仓私有 / `af_*` Axiom 私有；`qed_domain`/`qed_course` 写主体本仓、`qed_llm_calls` 三项目可写；8900 离线降级直写白名单例外；schema 变更先经根仓库 database-design.md 登记再由写权限方实施） | 私有表清单见 [数据库专用表设计](../architecture/database-private-tables.md)；模型即 schema 自愈 `ensure_schema()`（ADR 0006） |
| 服务对接 | 根仓库 [service-contracts.md](../../../docs/design/service-contracts.md)（服务职责与消费方向） | 8900 启停接入见上文契约节；Axiom-Flow 消费面见 [架构 API](../architecture/api.md) 外部接口节 |

## 验证

- 定向测试 `tests/test_service_scripts.py`（30 用例）：覆盖 parser（含 `--mode`）、start
  幂等/spawn/PID 写入/`--mode` 持久化与子进程 env 注入/默认模式/`--wait` 健康与超时、stop
  无 PID/stale 清理/优雅/强杀兜底/SystemError 兜底/`_proc_alive` 真实判活/`_kill_tree`
  失败可见/两腿失效退 1 不假 stopped/CTRL_BREAK 空放走强杀、restart 顺序与换模式、status
  双路径与模式输出、退出码与 `QED_TRACKER_PORT` 默认端口。
- `tests/test_config_catalog_matching.py` 覆盖 `.env` 来源优先级与密钥唯一变量（QED-038：
  `llm_api_key` 只读 `API_KEY`，无别名回退）；`tests/test_llm_client.py`（10 用例）覆盖
  `direct` / `gateway` 双模式与 `qed_llm_calls` 落库/降级（固定 fixture，不访问公网）；
  `tests/test_bailian_advisor.py`、`tests/test_main_line_advisor.py` 覆盖 gateway 路由
  （不接触密钥）。
- 真实冒烟：自身 `.env` 生效（`local` 直连可用，无 8900 也能评估）；`--mode qed-engine`
  重启后经 8900 `/llm/text` 调用成功且调用记录 `service=qed_tracker` 落库；`--mode local`
  调用记录落库同表；脚本 start/stop/restart/status 生命周期全链。
- 全量门禁按 [开发指南](../guides/development.md) 执行。

## 变更记录

| 日期 | 变更 | 说明 |
| --- | --- | --- |
| 2026-09-07 | 新建 | 由 service-lifecycle.md 与 model-mode-config.md 合并（ADR 0008），补 `_ENV_MAP` 全量键清单、`QED_MODEL` 实际取值修正、新增多项目约定导航节 |
