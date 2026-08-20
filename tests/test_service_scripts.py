"""scripts/qed_tracker_service.py 生命周期脚本契约测试。

脚本是 8901 服务的启停封装（承接根仓库 REQ-017①，设计见
docs/design/service-lifecycle.md）。测试用 tmp 目录与 monkeypatch 隔离
PID/日志路径与系统调用，不访问公网、不读写真实数据根。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "qed_tracker_service.py"


class FakeProc:
    """最小 Popen 替身：持有 pid，poll 恒未退出。"""

    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid

    def poll(self) -> None:
        return None


@pytest.fixture
def module():
    spec = importlib.util.spec_from_file_location("qed_tracker_service", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def isolated(module, monkeypatch, tmp_path):
    """把 PID/日志/模式状态路径全部隔离到 tmp 目录。"""
    monkeypatch.setattr(module, "LOG_DIR", tmp_path)
    monkeypatch.setattr(module, "PID_FILE", tmp_path / "qed-tracker.pid")
    monkeypatch.setattr(module, "MODE_FILE", tmp_path / "qed-tracker-mode")
    monkeypatch.setattr(module, "SERVE_LOG", tmp_path / "serve.log")
    return tmp_path


def test_parser_has_subcommands(module):
    parser = module.build_parser()
    for name in ("start", "stop", "restart", "status"):
        assert parser.parse_args([name]).command == name


def test_parser_mode_option(module):
    """QED-037：start/restart 支持 --mode local|qed-engine。"""
    for sub in ("start", "restart"):
        args = module.build_parser().parse_args([sub, "--mode", "qed-engine"])
        assert args.mode == "qed-engine"
        assert module.build_parser().parse_args([sub, "--mode", "local"]).mode == "local"
    assert module.build_parser().parse_args(["start"]).mode is None


def test_default_mode_from_own_env_or_local(module, monkeypatch, tmp_path):
    """不传 --mode 时默认读自身 .env 的 QED_API_SELECT，缺省 local。"""
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / ".env").write_text("QED_API_SELECT=qed-engine\n", encoding="utf-8")
    assert module.default_mode() == "qed-engine"
    (tmp_path / ".env").write_text("QED_MODEL=qwen-plus\n", encoding="utf-8")
    assert module.default_mode() == "local"
    (tmp_path / ".env").unlink()
    assert module.default_mode() == "local"


def test_parser_port_and_wait_options(module):
    args = module.build_parser().parse_args(["--port", "8911", "start", "--wait"])
    assert args.port == 8911
    assert args.command == "start"
    assert args.wait == module.HEALTH_TIMEOUT_SECONDS


def test_default_port_from_env(module, monkeypatch):
    monkeypatch.setenv("QED_TRACKER_PORT", "8905")
    assert module.default_port() == 8905
    monkeypatch.delenv("QED_TRACKER_PORT")
    assert module.default_port() == 8901


def test_start_writes_pid_and_spawns_serve(module, isolated, monkeypatch):
    calls: dict = {}

    def fake_popen(cmd, **kwargs):
        calls["cmd"] = cmd
        calls["kwargs"] = kwargs
        return FakeProc(pid=4242)

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(module, "_port_open", lambda port: False)
    monkeypatch.setattr(module, "_pid_is_alive", lambda pid: False)
    args = module.build_parser().parse_args(["start"])
    assert module.cmd_start(args) == 0
    assert calls["cmd"][0] == sys.executable
    assert calls["cmd"][1:] == ["-m", "qed_tracker.cli", "serve"]
    assert (isolated / "qed-tracker.pid").read_text(encoding="utf-8") == "4242"


def test_start_with_mode_persists_and_injects_env(module, isolated, monkeypatch):
    """QED-037：--mode 持久化到 logs/ 状态文件，且子进程 env 注入 QED_API_SELECT。"""
    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["env"] = dict(kwargs.get("env") or {})
        return FakeProc(pid=4242)

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(module, "_port_open", lambda port: False)
    monkeypatch.setattr(module, "_pid_is_alive", lambda pid: False)
    args = module.build_parser().parse_args(["start", "--mode", "qed-engine"])
    assert module.cmd_start(args) == 0
    assert (isolated / "qed-tracker-mode").read_text(encoding="utf-8") == "qed-engine"
    assert captured["env"].get("QED_API_SELECT") == "qed-engine"


def test_start_without_mode_uses_default(module, isolated, monkeypatch):
    """不传 --mode 时按默认模式启动并持久化。"""
    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["env"] = dict(kwargs.get("env") or {})
        return FakeProc(pid=4242)

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(module, "_port_open", lambda port: False)
    monkeypatch.setattr(module, "_pid_is_alive", lambda pid: False)
    monkeypatch.setattr(module, "default_mode", lambda: "local")
    args = module.build_parser().parse_args(["start"])
    assert module.cmd_start(args) == 0
    assert captured["env"].get("QED_API_SELECT") == "local"
    assert (isolated / "qed-tracker-mode").read_text(encoding="utf-8") == "local"


def test_restart_can_switch_mode(module, monkeypatch):
    """QED-037：restart 可换模式（重启后生效）。"""
    started = []

    def record_start(args):
        started.append(args.mode)
        return 0

    monkeypatch.setattr(module, "cmd_stop", lambda args: 0)
    monkeypatch.setattr(module, "cmd_start", record_start)
    args = module.build_parser().parse_args(["restart", "--mode", "qed-engine"])
    assert module.cmd_restart(args) == 0
    assert started == ["qed-engine"]


def test_status_reports_running_mode(module, isolated, monkeypatch, capsys):
    """QED-037：status 输出当前运行模式。"""
    (isolated / "qed-tracker.pid").write_text("4242", encoding="utf-8")
    (isolated / "qed-tracker-mode").write_text("qed-engine", encoding="utf-8")
    monkeypatch.setattr(module, "_pid_is_alive", lambda pid: True)
    assert module.cmd_status(module.build_parser().parse_args(["status"])) == 0
    assert "mode qed-engine" in capsys.readouterr().out


def test_start_already_running_by_pid(module, isolated, monkeypatch):
    (isolated / "qed-tracker.pid").write_text("4242", encoding="utf-8")
    monkeypatch.setattr(module, "_pid_is_alive", lambda pid: True)
    monkeypatch.setattr(
        module.subprocess, "Popen", lambda *a, **kw: pytest.fail("不应重复 spawn")
    )
    args = module.build_parser().parse_args(["start"])
    assert module.cmd_start(args) == 0


def test_start_already_running_by_port(module, isolated, monkeypatch):
    monkeypatch.setattr(module, "_pid_is_alive", lambda pid: False)
    monkeypatch.setattr(module, "_port_open", lambda port: True)
    monkeypatch.setattr(
        module.subprocess, "Popen", lambda *a, **kw: pytest.fail("不应重复 spawn")
    )
    args = module.build_parser().parse_args(["start"])
    assert module.cmd_start(args) == 0


def test_start_spawn_failure_returns_1(module, isolated, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("python not found")

    monkeypatch.setattr(module.subprocess, "Popen", boom)
    monkeypatch.setattr(module, "_port_open", lambda port: False)
    monkeypatch.setattr(module, "_pid_is_alive", lambda pid: False)
    args = module.build_parser().parse_args(["start"])
    assert module.cmd_start(args) == 1
    assert not (isolated / "qed-tracker.pid").exists()


def test_start_wait_reports_healthy(module, isolated, monkeypatch):
    monkeypatch.setattr(module.subprocess, "Popen", lambda cmd, **kw: FakeProc(pid=7))
    monkeypatch.setattr(module, "_port_open", lambda port: False)
    monkeypatch.setattr(module, "_pid_is_alive", lambda pid: False)
    monkeypatch.setattr(module, "_health_ok", lambda port: True)
    args = module.build_parser().parse_args(["start", "--wait"])
    assert module.cmd_start(args) == 0


def test_start_wait_timeout_returns_1(module, isolated, monkeypatch):
    monkeypatch.setattr(module.subprocess, "Popen", lambda cmd, **kw: FakeProc(pid=7))
    monkeypatch.setattr(module, "_port_open", lambda port: False)
    monkeypatch.setattr(module, "_pid_is_alive", lambda pid: False)
    monkeypatch.setattr(module, "_health_ok", lambda port: False)
    args = module.build_parser().parse_args(["start", "--wait", "0.05"])
    assert module.cmd_start(args) == 1


def test_stop_no_pid_file(module, isolated, monkeypatch):
    args = module.build_parser().parse_args(["stop"])
    assert module.cmd_stop(args) == 0


def test_stop_stale_pid_file_cleaned(module, isolated, monkeypatch):
    (isolated / "qed-tracker.pid").write_text("4242", encoding="utf-8")
    monkeypatch.setattr(module, "_pid_is_alive", lambda pid: False)
    args = module.build_parser().parse_args(["stop"])
    assert module.cmd_stop(args) == 0
    assert not (isolated / "qed-tracker.pid").exists()


def test_stop_graceful_no_force(module, isolated, monkeypatch):
    (isolated / "qed-tracker.pid").write_text("4242", encoding="utf-8")
    monkeypatch.setattr(module, "STOP_GRACE_SECONDS", 0.05)
    monkeypatch.setattr(module.time, "sleep", lambda s: None)
    alive_calls = {"n": 0}

    def fake_alive(pid):
        alive_calls["n"] += 1
        return alive_calls["n"] == 1  # os.kill 前存活，之后立即消失

    monkeypatch.setattr(module, "_pid_is_alive", fake_alive)
    break_sent = []
    monkeypatch.setattr(module.os, "kill", lambda pid, sig: break_sent.append(pid))
    tree_calls = []
    monkeypatch.setattr(module, "_kill_tree", lambda pid: tree_calls.append(pid))
    args = module.build_parser().parse_args(["stop"])
    assert module.cmd_stop(args) == 0
    assert break_sent == [4242]
    assert tree_calls == []
    assert not (isolated / "qed-tracker.pid").exists()


def test_stop_force_kill_fallback(module, isolated, monkeypatch):
    (isolated / "qed-tracker.pid").write_text("4242", encoding="utf-8")
    monkeypatch.setattr(module, "STOP_GRACE_SECONDS", 0.05)
    monkeypatch.setattr(module.time, "sleep", lambda s: None)
    monkeypatch.setattr(module, "_pid_is_alive", lambda pid: True)  # 永不退出
    break_sent = []
    monkeypatch.setattr(module.os, "kill", lambda pid, sig: break_sent.append(pid))
    tree_calls = []
    monkeypatch.setattr(module, "_kill_tree", lambda pid: tree_calls.append(pid))
    args = module.build_parser().parse_args(["stop"])
    assert module.cmd_stop(args) == 0
    assert break_sent == [4242]
    assert tree_calls == [4242]
    assert not (isolated / "qed-tracker.pid").exists()


def test_stop_systemerror_from_kill_falls_back_to_force(module, isolated, monkeypatch):
    """无交互控制台环境下 os.kill(CTRL_BREAK) 抛 SystemError（包裹 WinError 87），
    必须兜底强杀而不是崩溃。"""
    (isolated / "qed-tracker.pid").write_text("4242", encoding="utf-8")
    monkeypatch.setattr(module, "STOP_GRACE_SECONDS", 0.05)
    monkeypatch.setattr(module.time, "sleep", lambda s: None)

    def broken_kill(pid, sig):
        raise SystemError("<built-in function kill> returned a result with an exception set")

    monkeypatch.setattr(module.os, "kill", broken_kill)
    alive_state = {"n": 0}

    def fake_alive(pid):
        alive_state["n"] += 1
        return alive_state["n"] == 1  # os.kill 前存活，之后视为已退出

    monkeypatch.setattr(module, "_pid_is_alive", fake_alive)
    tree_calls = []
    monkeypatch.setattr(module, "_kill_tree", lambda pid: tree_calls.append(pid))
    args = module.build_parser().parse_args(["stop"])
    assert module.cmd_stop(args) == 0
    assert tree_calls == [4242]
    assert not (isolated / "qed-tracker.pid").exists()


def test_restart_stops_then_starts(module, monkeypatch):
    calls = []

    def record_stop(args):
        calls.append("stop")
        return 0

    def record_start(args):
        calls.append("start")
        return 0

    monkeypatch.setattr(module, "cmd_stop", record_stop)
    monkeypatch.setattr(module, "cmd_start", record_start)
    args = module.build_parser().parse_args(["restart"])
    assert module.cmd_restart(args) == 0
    assert calls == ["stop", "start"]


def test_status_running_by_pid(module, isolated, monkeypatch):
    (isolated / "qed-tracker.pid").write_text("4242", encoding="utf-8")
    monkeypatch.setattr(module, "_pid_is_alive", lambda pid: True)
    args = module.build_parser().parse_args(["status"])
    assert module.cmd_status(args) == 0


def test_status_running_by_port(module, isolated, monkeypatch):
    monkeypatch.setattr(module, "_pid_is_alive", lambda pid: False)
    monkeypatch.setattr(module, "_port_open", lambda port: True)
    monkeypatch.setattr(module, "_health_ok", lambda port: True)
    args = module.build_parser().parse_args(["status"])
    assert module.cmd_status(args) == 0


def test_status_stopped_and_stale_pid_cleaned(module, isolated, monkeypatch):
    (isolated / "qed-tracker.pid").write_text("4242", encoding="utf-8")
    monkeypatch.setattr(module, "_pid_is_alive", lambda pid: False)
    monkeypatch.setattr(module, "_port_open", lambda port: False)
    monkeypatch.setattr(module, "_health_ok", lambda port: False)
    args = module.build_parser().parse_args(["status"])
    assert module.cmd_status(args) == 0
    assert not (isolated / "qed-tracker.pid").exists()


def test_main_runs_subcommand(module, monkeypatch):
    monkeypatch.setattr(module, "cmd_status", lambda args: 7)
    assert module.main(["status"]) == 7


def test_pid_is_alive_tolerates_non_utf8_stdout(module, monkeypatch):
    """中文 Windows 下 tasklist 输出 GBK（Python utf-8 解码失败 → stdout=None）时，
    _pid_is_alive 不得抛 TypeError，应返回 False（进程状态未知，走端口探测兜底）。"""
    captured: dict = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return type("R", (), {"returncode": 0, "stdout": None})()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    assert module._pid_is_alive(9999) is False, "stdout=None 时应返回 False 而非抛 TypeError"
    assert captured.get("errors") == "replace", "subprocess.run 应带 errors='replace' 容忍 GBK 输出"

    def fake_run_ok(*args, **kwargs):
        return type("R", (), {
            "returncode": 0,
            "stdout": "\nImage Name                     PID Session Name\n... 9999 ...\n",
        })()

    monkeypatch.setattr(module.subprocess, "run", fake_run_ok)
    assert module._pid_is_alive(9999) is True