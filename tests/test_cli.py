"""测试：CLI 参数解析"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.hunt_papers import parse_args as parse_papers
from scripts.hunt_textbooks import parse_args as parse_textbooks
from scripts.hunt_docs import parse_args as parse_docs
from scripts.hunt_github import parse_args as parse_github
from scripts.manage_resources import parse_args as parse_resources


class TestHuntPapersCLI:
    def test_defaults(self):
        args = parse_papers(["--domain", "math.CA"])
        assert args.domain == "math.CA"
        assert args.max == 10
        assert not args.all_domains
        assert not args.no_db

    def test_all_domains(self):
        args = parse_papers(["--all-domains"])
        assert args.all_domains

    def test_max_results(self):
        args = parse_papers(["--domain", "math.FA", "--max", "20"])
        assert args.max == 20


class TestHuntTextbooksCLI:
    def test_defaults(self):
        args = parse_textbooks([])
        assert args.course is None
        assert not args.no_db

    def test_specific_course(self):
        args = parse_textbooks(["--course", "03"])
        assert args.course == "03"

    def test_no_db(self):
        args = parse_textbooks(["--no-db"])
        assert args.no_db


class TestHuntDocsCLI:
    def test_specific_doc(self):
        args = parse_docs(["--name", "pytorch"])
        assert args.name == "pytorch"
        assert not args.all

    def test_all_docs(self):
        args = parse_docs(["--all"])
        assert args.all

    def test_no_db(self):
        args = parse_docs(["--no-db"])
        assert args.no_db


class TestManageResourcesCLI:
    def test_list_resources(self):
        args = parse_resources(["list", "--type", "article", "--limit", "20"])
        assert args.command == "list"
        assert args.type == "article"
        assert args.limit == 20

    def test_search_resources(self):
        args = parse_resources(["search", "probability", "--type", "blog"])
        assert args.command == "search"
        assert args.keyword == "probability"
        assert args.type == "blog"

    def test_favorite_resource(self):
        args = parse_resources(["favorite", "abc123", "--unset"])
        assert args.command == "favorite"
        assert args.resource_id == "abc123"
        assert args.unset is True

    def test_export_resources(self):
        args = parse_resources(["export", "--format", "markdown", "--output", "resources.md"])
        assert args.command == "export"
        assert args.format == "markdown"
        assert args.output == "resources.md"


class TestHuntGitHubCLI:
    def test_repos_from_arguments(self):
        args = parse_github(["pytorch/pytorch", "vllm-project/vllm"])
        assert args.repos == ["pytorch/pytorch", "vllm-project/vllm"]
        assert args.file is None
        assert not args.no_db

    def test_repos_from_file(self):
        args = parse_github(["--file", "repos.txt", "--no-db"])
        assert args.file == "repos.txt"
        assert args.no_db
