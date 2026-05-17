"""测试：CLI 参数解析"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.hunt_papers import parse_args as parse_papers
from scripts.hunt_textbooks import parse_args as parse_textbooks
from scripts.hunt_docs import parse_args as parse_docs


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
