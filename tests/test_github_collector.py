"""Tests for GitHubCollector."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.collectors.github_collector import GitHubCollector
from app.repository.resource_repo import ResourceRepo


class FakeGitHubDownloader:
    def __init__(self):
        self.calls = []

    def get_repo_info(self, repo: str) -> dict:
        self.calls.append(repo)
        if repo == "missing/repo":
            return {}
        return {
            "full_name": repo,
            "description": f"{repo} description",
            "url": f"https://github.com/{repo}",
            "stars": 100,
            "language": "Python",
            "topics": ["llm", "inference"],
            "license": "Apache-2.0",
        }


class TestGitHubCollector:
    def test_collect_repos_inserts_github_resources(self, db_session):
        collector = GitHubCollector(db=db_session, downloader=FakeGitHubDownloader())

        imported = collector.collect_repos(["vllm-project/vllm", "missing/repo"])

        repo = ResourceRepo(db_session)
        saved = repo.get_by_url("https://github.com/vllm-project/vllm")
        assert imported == 1
        assert saved is not None
        assert saved.resource_type == "repo"
        assert saved.title == "vllm-project/vllm"
        assert saved.platform == "GitHub"
        assert "stars=100" in saved.notes
        assert "license=Apache-2.0" in saved.notes

    def test_collect_repos_skips_existing_urls(self, db_session):
        downloader = FakeGitHubDownloader()
        collector = GitHubCollector(db=db_session, downloader=downloader)

        first = collector.collect_repos(["pytorch/pytorch"])
        second = collector.collect_repos(["pytorch/pytorch"])

        repo = ResourceRepo(db_session)
        assert first == 1
        assert second == 0
        assert len(repo.get_by_type("repo")) == 1
