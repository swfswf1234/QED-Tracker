"""WgetMirror — wget --mirror 全站镜像工具 (通过 WSL 调用)"""

import subprocess
import time
from pathlib import Path

from loguru import logger

from app.core.config import settings


class WgetMirror:
    WGET_ARGS = [
        "--mirror",
        "--convert-links",
        "--adjust-extension",
        "--page-requisites",
        "--no-parent",
        "--no-host-directories",
        "--wait=2",
        "--random-wait",
        "--limit-rate=1M",
        "--user-agent=Mozilla/5.0 (compatible; QED-Tracker/0.2)",
    ]

    def __init__(self, proxy: str = ""):
        self.proxy = proxy

    @staticmethod
    def _win_to_wsl_path(path: Path) -> str:
        drive = path.drive.lower().rstrip(":")
        rest = path.as_posix()[2:]
        return f"/mnt/{drive}{rest}"

    def mirror(self, name: str, url: str, output_dir: Path, timeout: int = 7200) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        wsl_out = self._win_to_wsl_path(output_dir.resolve())

        args = list(self.WGET_ARGS)
        if self.proxy:
            host = "host.docker.internal"
            args.extend([
                "-e", f"http_proxy=http://{host}:{self.proxy.split(':')[-1]}",
                "-e", f"https_proxy=http://{host}:{self.proxy.split(':')[-1]}",
            ])
        args.extend([f"--directory-prefix={wsl_out}", url])

        cmd = ["wsl.exe", "wget"] + args
        logger.info(f"镜像: {name} <- {url}")
        t0 = time.time()

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired:
            elapsed = int(time.time() - t0)
            logger.error(f"超时: {name} ({timeout}s)")
            return self._make_result(name, url, output_dir, 0, elapsed, "timeout")
        except FileNotFoundError:
            logger.error("wsl.exe 未找到，请确认 WSL 已安装并启用")
            return self._make_result(name, url, output_dir, 0, 0, "no_wsl")

        elapsed = int(time.time() - t0)
        file_count = self._count_files(output_dir)

        if result.returncode != 0:
            stderr_tail = (result.stderr or "")[:300]
            logger.warning(f"wget 返回码 {result.returncode}: {stderr_tail}")
            if file_count > 0:
                logger.info(f"部分完成: {name} — {file_count} 文件, {elapsed}s")
                return self._make_result(name, url, output_dir, file_count, elapsed, "partial")
            return self._make_result(name, url, output_dir, 0, elapsed, f"error_{result.returncode}")

        logger.info(f"完成: {name} — {file_count} 文件, {elapsed}s")
        return self._make_result(name, url, output_dir, file_count, elapsed, "ok")

    @staticmethod
    def _count_files(directory: Path) -> int:
        if not directory.exists():
            return 0
        return sum(1 for _ in directory.rglob("*") if _.is_file())

    @staticmethod
    def _make_result(name: str, url: str, output_dir: Path, file_count: int, elapsed: int, status: str) -> dict:
        try:
            local_path = str(output_dir.relative_to(settings.dataset_path).as_posix())
        except ValueError:
            local_path = str(output_dir)
        return {
            "name": name,
            "url": url,
            "local_path": local_path,
            "file_count": file_count,
            "elapsed_seconds": elapsed,
            "status": status,
        }
