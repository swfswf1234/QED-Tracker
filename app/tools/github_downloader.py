"""GitHub 项目文档/Release 跟踪工具

用法:
    from app.tools.github_downloader import GitHubDownloader
    dl = GitHubDownloader(token="ghp_xxx")
    info = dl.get_repo_info("pytorch/pytorch")
    paths = dl.download_latest_release("pytorch/pytorch", save_dir)
"""

import httpx
import re
from pathlib import Path
from typing import Optional

from loguru import logger


class GitHubDownloader:
    """GitHub 项目跟踪工具"""

    API_BASE = "https://api.github.com"

    def __init__(self, token: str = ""):
        self.token = token
        self._headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    def _request(self, url: str) -> dict | list | None:
        try:
            resp = httpx.get(url, headers=self._headers, follow_redirects=True, timeout=30.0)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"GitHub API 请求失败: {url[:60]} — {e}")
            return None

    def get_repo_info(self, repo: str) -> dict:
        """获取仓库基本信息"""
        data = self._request(f"{self.API_BASE}/repos/{repo}")
        if not data:
            return {}
        return {
            "full_name": data.get("full_name", ""),
            "description": data.get("description", ""),
            "url": data.get("html_url", ""),
            "stars": data.get("stargazers_count", 0),
            "language": data.get("language", ""),
            "topics": data.get("topics", []),
            "default_branch": data.get("default_branch", "main"),
            "license": data.get("license", {}).get("spdx_id", "") if data.get("license") else "",
        }

    def download_latest_release(self, repo: str, save_dir: Path) -> list[Path]:
        """下载最新 Release 资产"""
        data = self._request(f"{self.API_BASE}/repos/{repo}/releases/latest")
        if not data:
            logger.warning(f"无 Release: {repo}")
            return []

        tag = data.get("tag_name", "latest")
        save_dir = save_dir / repo.replace("/", "_") / tag
        save_dir.mkdir(parents=True, exist_ok=True)

        downloaded = []
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            url = asset.get("browser_download_url", "")
            if not name or not url:
                continue
            filepath = save_dir / name
            if filepath.exists():
                logger.info(f"已存在: {name}")
                downloaded.append(filepath)
                continue
            try:
                resp = httpx.get(url, follow_redirects=True, timeout=120.0)
                resp.raise_for_status()
                filepath.write_bytes(resp.content)
                logger.info(f"下载: {name} ({len(resp.content) / 1024:.0f} KB)")
                downloaded.append(filepath)
            except Exception as e:
                logger.error(f"下载失败 {name}: {e}")
        return downloaded

    def clone_docs(self, repo: str, subdir: str, save_dir: Path) -> Optional[Path]:
        """浅克隆仓库的文档目录"""
        target = save_dir / repo.replace("/", "_") / subdir
        if target.exists():
            logger.info(f"文档目录已存在: {target}")
            return target
        url = f"https://github.com/{repo}.git"
        try:
            import subprocess as sp
            tmp_dir = save_dir / f"_{repo.replace('/', '_')}_clone"
            if tmp_dir.exists():
                import shutil
                shutil.rmtree(tmp_dir)
            sp.run(
                ["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", url, str(tmp_dir)],
                capture_output=True, text=True, timeout=120,
            )
            sp.run(
                ["git", "-C", str(tmp_dir), "sparse-checkout", "set", subdir],
                capture_output=True, text=True, timeout=30,
            )
            src = tmp_dir / subdir
            if src.exists():
                import shutil
                shutil.copytree(src, target, dirs_exist_ok=True)
                import shutil
                shutil.rmtree(tmp_dir)
                logger.info(f"文档已克隆: {target}")
                return target
            import shutil
            shutil.rmtree(tmp_dir)
        except Exception as e:
            logger.error(f"克隆失败 {repo}/{subdir}: {e}")
        return None

    def get_readme(self, repo: str) -> str:
        """获取仓库 README 内容"""
        data = self._request(f"{self.API_BASE}/repos/{repo}/readme")
        if not data:
            return ""
        content = data.get("content", "")
        import base64
        try:
            decoded = base64.b64decode(content).decode("utf-8")
            return decoded[:5000]
        except Exception:
            return ""
