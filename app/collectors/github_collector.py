"""GitHub repository metadata collector."""

from sqlalchemy.orm import Session
from loguru import logger

from app.collectors import BaseCollector
from app.core.config import settings
from app.core.database import get_conn, init_tables
from app.models.resource import Resource
from app.repository.resource_repo import ResourceRepo
from app.tools.github_downloader import GitHubDownloader


class GitHubCollector(BaseCollector):
    source = "github"

    def __init__(
        self,
        db: Session | None = None,
        downloader: GitHubDownloader | None = None,
        token: str | None = None,
    ):
        self.db = db
        self.downloader = downloader or GitHubDownloader(token=token if token is not None else settings.github_token)

    def collect_repos(self, repos: list[str], no_db: bool = False) -> int:
        """Collect repository metadata and store missing repos in resources."""
        if no_db:
            for repo in repos:
                info = self.downloader.get_repo_info(repo)
                if info:
                    print(f"[repo] {info.get('full_name', repo)}")
                    print(f"       {info.get('url', '')}")
            return 0

        owns_db = self.db is None
        db = self.db or get_conn()
        try:
            if owns_db:
                init_tables()
            repo_store = ResourceRepo(db)
            imported = 0
            for repo in repos:
                info = self.downloader.get_repo_info(repo)
                if not info or not info.get("url"):
                    logger.warning(f"跳过 GitHub 仓库: {repo}")
                    continue
                if repo_store.exists_by_url(info["url"]):
                    logger.info(f"已存在: {info['url']}")
                    continue
                repo_store.create(self._to_resource(info))
                imported += 1
            return imported
        finally:
            if owns_db:
                db.close()

    def _to_resource(self, info: dict) -> Resource:
        notes = self._format_notes(info)
        return Resource(
            id=None,
            resource_type="repo",
            title=info.get("full_name", ""),
            url=info.get("url", ""),
            description=info.get("description", ""),
            course_tags=info.get("topics", []),
            author="",
            platform="GitHub",
            notes=notes,
        )

    def _format_notes(self, info: dict) -> str:
        topics = ",".join(info.get("topics", []))
        return "\n".join(
            part for part in [
                f"stars={info.get('stars', 0)}",
                f"language={info.get('language', '')}",
                f"license={info.get('license', '')}",
                f"topics={topics}",
            ]
            if part and not part.endswith("=")
        )
