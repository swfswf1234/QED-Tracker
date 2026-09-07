# 服务生命周期脚本设计（service-lifecycle）

归档状态：已归档（2026-09-07 自 docs/design/ 移入 history/baselines/）
归档说明：
- 范围：启动/停止脚本契约、运行事实（logs/）、8900 接入契约、平台约束、验证。
- 失效原因：与 model-mode-config 同属服务运行面，按 ADR 0008 两文合并为
  [服务管理中心设计](../../design/service-management.md)，本文整篇并入后退役。
- 不可变锚点：正文以 2026-09-07 归档时点工作树状态冻结（本批文档含未提交修订，随本轮
  提交定稿；此后仅允许补 Historical 声明、反向关系或修复链接）。
- 当前事实入口：[服务管理中心设计](../../design/service-management.md)。
设计状态：Historical（2026-09-07 归档）
实现状态：Completed（承载内容已并入 service-management.md）
确认状态：已确认
最后更新：2026-09-07
需求方：QED-Engine（根仓库 REQ-017①「仓库内提供正式启动入口」；QED-037/REQ-043 扩展 `--mode`）
关联代码：`scripts/qed_tracker_service.py`、`src/qed_tracker/cli.py`（serve 命令）、`src/qed_tracker/config.py`、
`src/qed_tracker/llm_client.py`
关联测试：`tests/test_service_scripts.py`、`tests/test_llm_client.py`
关联 ADR：[ADR 0008](../../adr/0008-design-doc-scope-reshuffle.md)

## 背景与目的

QED-Tracker 以 8901 HTTP 服务运行，启动命令为 `qed-tracker serve`（等价 `python -m qed_tracker.cli
serve`）。根仓库 8900 控制中心此前直接 `Popen(["python", "-m", "qed_tracker.cli", "serve"])` 托管
本服务，启动/停止/重启的实现细节散落在根仓库 `service_manager.py` 的注册表与进程管理逻辑中，
本仓库自身没有正式、可复用的生命周期入口（REQ-017①）。

本设计在本仓库内提供**唯一、自含的生命周期脚本** `scripts/qed_tracker_service.py`：负责解释器
继承、后台拉起、PID 记录、优雅停止与强杀兜底、健康等待与状态探测。根仓库只需黑盒调用
`python scripts/qed_tracker_service.py start|stop|restart`，不再需要持有子进程句柄或复制进程
管理逻辑；端口探测与过渡窗口语义仍由 8900 负责，本脚本不重复实现。

## 脚本接口契约

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
- `--mode local|qed-engine`（QED-037）：模型模式——`local`=直连 dashscope qwen /
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
`.env` 查找、MySQL 迁移与双通道日志（stderr + `logs/qed-tracker.log`），脚本不再重定向应用日志，
两文件互不重复。模型模式经子进程 env 注入（见上 `--mode` 契约）。

## 与 8900 控制中心接入契约

根仓库 `service_manager.py` 的 `tracker` 单元改造为调用本脚本（根仓库侧实施，另行安排）：

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

## 平台约束

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

## 验证

- 定向测试 `tests/test_service_scripts.py`（30 用例）：tmp 目录 + monkeypatch 隔离 PID/日志/
  模式状态路径与系统调用，覆盖 parser（含 `--mode`）、start 幂等/spawn/PID 写入/`--mode`
  持久化与子进程 env 注入/默认模式/`--wait` 健康与超时、stop 无 PID/stale 清理/优雅/强杀兜底/
  SystemError 兜底/`_proc_alive` 真实判活/`_kill_tree` 失败可见/两腿失效退 1 不假 stopped/
  CTRL_BREAK 空放走强杀、restart 顺序与换模式、status 双路径与模式输出、退出码与
  `QED_TRACKER_PORT` 默认端口。
- 全量门禁：`pytest tests -q` + `ruff check src tests scripts` 全绿。