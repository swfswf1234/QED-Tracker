"""QED-Tracker 8901 服务生命周期管理：start / stop / restart / status。

子进程 = `python -m qed_tracker.cli serve`（继承当前解释器，天然落在 QED_env）；
PID 文件 logs/qed-tracker.pid，子进程 stdout/stderr 落 logs/qed-tracker-serve.log，
应用级日志仍由 serve 双通道写 logs/qed-tracker.log（两文件不重复）。
接口契约（含 8900 控制中心接入方式）见 docs/design/service-lifecycle.md。

退出码：0 成功/幂等；1 运行失败（spawn 失败、health 超时）；2 参数错误（argparse）。
Windows 注意：os.kill(pid, 0) 会直接 TerminateProcess，进程存在性检测用 tasklist。
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
PID_FILE = LOG_DIR / "qed-tracker.pid"
SERVE_LOG = LOG_DIR / "qed-tracker-serve.log"

NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
CTRL_BREAK_EVENT = getattr(signal, "CTRL_BREAK_EVENT", signal.SIGTERM)

STOP_GRACE_SECONDS = 5.0
STOP_POLL_INTERVAL = 0.2
HEALTH_TIMEOUT_SECONDS = 30.0
HEALTH_INTERVAL_SECONDS = 0.5


def default_port() -> int:
    """health 探测端口：QED_TRACKER_PORT 环境变量，默认 8901。"""
    return int(os.getenv("QED_TRACKER_PORT", "8901"))


def serve_command() -> list[str]:
    """子进程命令：当前解释器 + CLI serve（config.py 直读根 .env 的 QED_*）。"""
    return [sys.executable, "-m", "qed_tracker.cli", "serve"]


def _pid_is_alive(pid: int) -> bool:
    """Windows 进程存在性检测：tasklist（os.kill(pid, 0) 会直接 TerminateProcess）。"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return str(pid) in result.stdout


def read_pid() -> int | None:
    if not PID_FILE.is_file():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _health_ok(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=1.0) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _spawn() -> int:
    """拉起服务进程并写 PID 文件；返回退出码。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = open(SERVE_LOG, "ab")  # noqa: SIM115 - 子进程继承句柄，随其生命周期
    try:
        proc = subprocess.Popen(
            serve_command(),
            cwd=str(ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=NEW_PROCESS_GROUP,
            env=os.environ.copy(),
        )
    except Exception as exc:
        log_file.close()
        print(f"spawn failed: {exc}")
        return 1
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    print(f"pid: {proc.pid}")
    print(f"log: {SERVE_LOG}")
    return 0


def _wait_healthy(port: int, timeout: float) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _health_ok(port):
            print(f"healthy: http://127.0.0.1:{port}/api/v1/health")
            return 0
        time.sleep(HEALTH_INTERVAL_SECONDS)
    print(f"health not OK within {timeout:g}s")
    return 1


def cmd_start(args: argparse.Namespace) -> int:
    port = args.port
    pid = read_pid()
    if pid is not None and _pid_is_alive(pid):
        print(f"already running (pid {pid})")
        return 0
    if _port_open(port):
        print(f"already running (port {port})")
        return 0
    if _spawn() != 0:
        return 1
    if args.wait and args.wait > 0:
        return _wait_healthy(port, args.wait)
    return 0


def _kill_tree(pid: int) -> None:
    """taskkill 强杀进程树（优雅停止超时后的兜底）。"""
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def cmd_stop(args: argparse.Namespace) -> int:
    pid = read_pid()
    if pid is None:
        print("not running (no pid file)")
        return 0
    if not _pid_is_alive(pid):
        PID_FILE.unlink(missing_ok=True)
        print("not running (stale pid file)")
        return 0
    forced = False
    try:
        os.kill(pid, CTRL_BREAK_EVENT)
    except (OSError, SystemError):
        # 无交互控制台环境（服务/管道）下 GenerateConsoleCtrlEvent 抛 WinError 87，
        # CPython 包装为 SystemError；一律走 taskkill 强杀兜底，不崩溃。
        _kill_tree(pid)
        forced = True
    deadline = time.monotonic() + STOP_GRACE_SECONDS
    while time.monotonic() < deadline and _pid_is_alive(pid):
        time.sleep(STOP_POLL_INTERVAL)
    if _pid_is_alive(pid):
        _kill_tree(pid)
        forced = True
    PID_FILE.unlink(missing_ok=True)
    print("stopped" + (" (forced)" if forced else ""))
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    cmd_stop(args)
    return cmd_start(args)


def cmd_status(args: argparse.Namespace) -> int:
    pid = read_pid()
    if pid is not None and _pid_is_alive(pid):
        print(f"running (pid {pid})")
        return 0
    if pid is not None:
        PID_FILE.unlink(missing_ok=True)
    if _port_open(args.port) and _health_ok(args.port):
        print(f"running (port probe {args.port})")
        return 0
    print("stopped")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qed_tracker_service",
        description="QED-Tracker 8901 服务生命周期管理（start/stop/restart/status）。",
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="health 探测端口（默认 QED_TRACKER_PORT 或 8901）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="启动服务（默认立即返回，--wait 可选等待健康就绪）")
    start.add_argument(
        "--wait", nargs="?", const=HEALTH_TIMEOUT_SECONDS, type=float, default=0.0,
        help=f"等待 /api/v1/health 就绪，默认 {HEALTH_TIMEOUT_SECONDS:g}s",
    )
    start.set_defaults(func=cmd_start)

    stop = subparsers.add_parser("stop", help="停止服务（优雅 + 强杀兜底）")
    stop.set_defaults(func=cmd_stop)

    restart = subparsers.add_parser("restart", help="重启服务")
    restart.add_argument(
        "--wait", nargs="?", const=HEALTH_TIMEOUT_SECONDS, type=float, default=0.0,
        help=f"等待 /api/v1/health 就绪，默认 {HEALTH_TIMEOUT_SECONDS:g}s",
    )
    restart.set_defaults(func=cmd_restart)

    status = subparsers.add_parser("status", help="查询服务状态")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.port is None:
        args.port = default_port()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())