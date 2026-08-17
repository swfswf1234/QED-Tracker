# 服务生命周期脚本设计（service-lifecycle）

设计状态：Accepted
实现状态：Implemented
最后更新：2026-08-17
需求方：QED-Engine（根仓库 REQ-017①「仓库内提供正式启动入口」）
关联代码：`scripts/qed_tracker_service.py`、`src/qed_tracker/cli.py`（serve 命令）、`src/qed_tracker/config.py`
关联测试：`tests/test_service_scripts.py`

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
python scripts/qed_tracker_service.py {start|stop|restart|status} [--port PORT]
```

- `start`：默认拉起进程后立即返回；`--wait [SECONDS]` 时轮询 `/api/v1/health` 直到就绪
  （默认超时 30s）。已运行（PID 存活或端口探测通过）时报 `already running`，幂等退出 0。
  成功输出 `pid: <n>` 与 `log: <path>`。
- `stop`：读取 PID 文件 → `CTRL_BREAK_EVENT` 优雅停止 → 5s 宽限 → `taskkill /PID /T /F` 强杀
  兜底 → 删除 PID 文件。无 PID 或进程已死时清理残留并幂等退出 0。
- `restart`：先 stop 后 start，透传 `--wait`。
- `status`：PID 存活 / 端口探测（socket 预检 + HTTP 健康确认）双路径，输出
  `running (pid <n>)` / `running (port probe <port>)` / `stopped`，信息型恒退出 0。
- `--port`：health 探测端口，默认取 `QED_TRACKER_PORT` 环境变量，无则 8901；`serve` 本身
  仍按配置（根 `.env` 的 `QED_TRACKER_PORT`）监听。

退出码：`0` 成功或幂等；`1` 运行失败（spawn 失败、`--wait` 健康超时）；`2` 参数错误（argparse）。

## 运行事实

```text
QED-Tracker/
├── scripts/qed_tracker_service.py   # 生命周期脚本
└── logs/                            # 已 gitignore，运行产物
    ├── qed-tracker.pid              # PID 文件（纯 PID 文本）
    ├── qed-tracker-serve.log        # 子进程 stdout/stderr（uvicorn 访问与未捕获异常）
    └── qed-tracker.log              # 应用级日志（serve 双通道 FileHandler，不受脚本影响）
```

子进程命令 = `sys.executable -m qed_tracker.cli serve`，工作目录为仓库根；`serve` 自身完成根
`.env` 查找、MySQL 迁移与双通道日志（stderr + `logs/qed-tracker.log`），脚本不再重定向应用日志，
两文件互不重复。

## 与 8900 控制中心接入契约

根仓库 `service_manager.py` 的 `tracker` 单元改造为调用本脚本（根仓库侧实施，另行安排）：

| 操作 | 根仓库调用 | 结果来源 |
| --- | --- | --- |
| start | `python scripts/qed_tracker_service.py start`（workdir=QED-Tracker） | stdout 首行 `pid: <n>` 或读 `logs/qed-tracker.pid` |
| stop | `python scripts/qed_tracker_service.py stop` | 脚本自含优雅停止 + 强杀兜底，退出码 0 |
| restart | `python scripts/qed_tracker_service.py restart` | 同上 |
| 状态 | 8900 既有端口探测不变（socket + HTTP，不调用脚本） | — |

- 脚本**自含完整生命周期**（PID 文件 + 优雅停止 + 强杀兜底），8900 无需再持有 Popen 句柄；
  `_MANAGED` 的 PID 记录可改为启动后读脚本输出/PID 文件，仅用于前端展示。
- 8900 的启动/停止过渡窗口（15s）、端口探测、并发 409 语义均不变；停止未运行服务的幂等
  由 8900 现有探测先行判断（脚本侧 stop 对未运行也幂等退出 0）。
- 环境继承：8900 以自身进程环境调用脚本（根 `.env` 已注入），`serve` 的 `_load_root_env`
  兜底独立启动场景。

## 平台约束

- Windows 下 `os.kill(pid, 0)` 会直接 TerminateProcess（2026-08-17 实测），进程存在性检测
  一律用 `tasklist /FI "PID eq <pid>"`。
- 优雅停止用 `signal.CTRL_BREAK_EVENT`（子进程以 `CREATE_NEW_PROCESS_GROUP` 拉起，uvicorn
  捕获 KeyboardInterrupt 优雅收尾），5s 宽限后 `taskkill /PID /T /F` 强杀兜底。
- 非 Windows 平台回退：`NEW_PROCESS_GROUP = 0`、`CTRL_BREAK_EVENT = SIGTERM`，强杀回退
  SIGKILL 语义由 `_kill_tree` 的 taskkill 调用在非 Windows 下直接失败吞掉（Windows 专属部署）。

## 验证

- 定向测试 `tests/test_service_scripts.py`（18 用例）：tmp 目录 + monkeypatch 隔离 PID/日志路径
  与系统调用，覆盖 parser、start 幂等/spawn/PID 写入/`--wait` 健康与超时、stop 无 PID/stale
  清理/优雅/强杀兜底、restart 顺序、status 双路径、退出码与 `QED_TRACKER_PORT` 默认端口。
- 全量门禁：`pytest tests -q` + `ruff check src tests scripts` 全绿。