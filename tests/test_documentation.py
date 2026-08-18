import re
import shlex
from pathlib import Path

from qed_tracker.cli import build_parser

ROOT = Path(__file__).parents[1]
REQUIRED_CURRENT_DOCS = {
    Path("README.md"),
    Path("AGENTS.md"),
    Path("docs/index.md"),
    Path("docs/trackers/roadmap.md"),
    Path("docs/architecture/index.md"),
    Path("docs/architecture/system-overview.md"),
    Path("docs/architecture/code-map.md"),
    Path("docs/architecture/project-status.md"),
    Path("docs/architecture/main-line.md"),
    Path("docs/design/index.md"),
    Path("docs/design/acquisition-and-inventory.md"),
    Path("docs/design/paper-discovery.md"),
    Path("docs/design/source-discovery.md"),
    Path("docs/design/review-round-dedup.md"),
    Path("docs/design/tracker-service.md"),
    Path("docs/design/database-schema.md"),
    Path("docs/design/database-schema-ownership.md"),
    Path("docs/design/governance-contract-alignment.md"),
    Path("docs/design/main-line-curriculum.md"),
    Path("docs/design/three-table-schema.md"),
    Path("docs/design/service-lifecycle.md"),
    Path("docs/design/service-lifecycle-encoding-fix.md"),
    Path("docs/standards/index.md"),
    Path("docs/standards/documentation.md"),
    Path("docs/standards/adr-governance.md"),
    Path("docs/adr/index.md"),
    Path("docs/adr/0001-tracker-service-architecture.md"),
    Path("docs/guides/index.md"),
    Path("docs/guides/operations.md"),
    Path("docs/guides/development.md"),
    Path("docs/plans/index.md"),
    Path("docs/plans/2026-08-main-line-curriculum.md"),
    Path("docs/plans/2026-08-three-table-refactor.md"),
    Path("docs/plans/2026-08-knowledge-schema-refactor.md"),
    Path("docs/plans/2026-08-service-lifecycle-scripts.md"),
    Path("docs/trackers/index.md"),
    Path("docs/trackers/todo.md"),
    Path("docs/trackers/completed.md"),
}
REQUIRED_HISTORY_DOCS = {
    Path("docs/history/index.md"),
    Path("docs/plans/index.md"),
    Path("docs/trackers/index.md"),
    Path("docs/history/baselines/pre-acquisition-cli.md"),
    Path("docs/history/baselines/math-qe-2026-05.md"),
    Path("docs/history/baselines/catalog-set-field.md"),
    Path("docs/history/baselines/2026-08-service-and-book-download.md"),
    Path("docs/history/qed-030-retire-qt_resources/index.md"),
}
INDEX_DOCS = {
    Path("docs/index.md"),
    Path("docs/architecture/index.md"),
    Path("docs/design/index.md"),
    Path("docs/standards/index.md"),
    Path("docs/adr/index.md"),
    Path("docs/guides/index.md"),
    Path("docs/history/index.md"),
}
DESIGN_DOCS = {
    Path("docs/architecture/system-overview.md"),
    Path("docs/architecture/main-line.md"),
    Path("docs/design/acquisition-and-inventory.md"),
    Path("docs/design/paper-discovery.md"),
    Path("docs/design/source-discovery.md"),
    Path("docs/design/review-round-dedup.md"),
    Path("docs/design/tracker-service.md"),
    Path("docs/design/database-schema.md"),
    Path("docs/design/database-schema-ownership.md"),
    Path("docs/design/governance-contract-alignment.md"),
    Path("docs/design/main-line-curriculum.md"),
    Path("docs/design/service-lifecycle.md"),
    Path("docs/design/service-lifecycle-encoding-fix.md"),
}
LINK_PATTERN = re.compile(r"\[[^]]+\]\(([^)]+)\)")
COMMAND_PATTERN = re.compile(r"^\s*(qed-tracker(?:\s+.+)?)\s*$", re.MULTILINE)
CODE_REFERENCE_PATTERN = re.compile(r"`((?:src|tests)/[^`]+)`")
LEGACY_PATTERNS = {
    "legacy application path": re.compile(r"(?:^|[`\s(])app/"),
    "legacy documentation path": re.compile(r"docs/(?:discuss|worklogs|knowledge_base)/"),
    "retired version": re.compile(r"\b0\.2\b"),
}


def _all_markdown() -> list[Path]:
    return [ROOT / "README.md", ROOT / "AGENTS.md", *sorted((ROOT / "docs").rglob("*.md"))]


def _current_markdown() -> list[Path]:
    return [path for path in _all_markdown() if "history" not in path.relative_to(ROOT).parts]


def _local_targets(document: Path):
    for target in LINK_PATTERN.findall(document.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        local = target.split("#", 1)[0]
        if local:
            yield target, (document.parent / local).resolve()


def test_documentation_entrypoints_are_intentional():
    all_docs = {path.relative_to(ROOT) for path in _all_markdown()}
    current = {path.relative_to(ROOT) for path in _current_markdown()}
    assert current == REQUIRED_CURRENT_DOCS
    assert all_docs == REQUIRED_CURRENT_DOCS | REQUIRED_HISTORY_DOCS
    assert INDEX_DOCS <= all_docs
    assert not list((ROOT / "docs").rglob("README.md"))
    assert not (ROOT / "docs/history/worklogs").exists()


def test_managed_documentation_has_required_metadata():
    violations = []
    for document in sorted((ROOT / "docs").rglob("*.md")):
        content = document.read_text(encoding="utf-8")
        for field in ("状态：", "最后更新："):
            if field not in content:
                violations.append(f"{document.relative_to(ROOT)}: missing {field}")
    for relative in DESIGN_DOCS:
        content = (ROOT / relative).read_text(encoding="utf-8")
        for field in ("实现状态：", "关联代码：", "关联测试："):
            if field not in content:
                violations.append(f"{relative}: missing {field}")
    assert not violations, "\n".join(violations)


def test_all_documentation_links_resolve():
    missing = []
    for document in _all_markdown():
        for target, resolved in _local_targets(document):
            if not resolved.exists():
                missing.append(f"{document.relative_to(ROOT)} -> {target}")
    assert not missing, "\n".join(missing)


def test_current_code_and_test_references_resolve():
    missing = []
    # docs/plans/ 描述未来文件与命令（计划语义），豁免反引号路径存在性检查
    for document in _current_markdown():
        if "plans" in document.relative_to(ROOT).parts:
            continue
        for target in CODE_REFERENCE_PATTERN.findall(document.read_text(encoding="utf-8")):
            if not (ROOT / target).exists():
                missing.append(f"{document.relative_to(ROOT)} -> {target}")
    assert not missing, "\n".join(missing)


def test_current_documentation_has_no_legacy_guidance():
    violations = []
    for document in _current_markdown():
        content = document.read_text(encoding="utf-8")
        for name, pattern in LEGACY_PATTERNS.items():
            if pattern.search(content):
                violations.append(f"{document.relative_to(ROOT)}: {name}")
    assert not violations, "\n".join(violations)


def test_operational_entrypoints_do_not_link_to_history():
    operational = [
        ROOT / "README.md",
        ROOT / "docs/guides/operations.md",
        ROOT / "docs/guides/development.md",
    ]
    history_root = (ROOT / "docs/history").resolve()
    violations = []
    for document in operational:
        for target, resolved in _local_targets(document):
            if resolved == history_root or history_root in resolved.parents:
                violations.append(f"{document.relative_to(ROOT)} -> {target}")
    assert not violations, "\n".join(violations)


def test_documented_cli_commands_match_the_parser():
    parser = build_parser()
    commands = []
    for document in _current_markdown():
        if "plans" in document.relative_to(ROOT).parts:
            continue  # 计划文档描述规划命令（未实现），豁免
        commands.extend(COMMAND_PATTERN.findall(document.read_text(encoding="utf-8")))
    assert commands
    for command in commands:
        argv = shlex.split(command)[1:]
        try:
            parser.parse_args(argv)
        except SystemExit as exc:
            assert exc.code == 0, command


def test_tracker_ids_and_active_plan_are_governed():
    todo = (ROOT / "docs/trackers/todo.md").read_text(encoding="utf-8")
    completed = (ROOT / "docs/trackers/completed.md").read_text(encoding="utf-8")
    todo_ids = re.findall(r"\| (QED-\d{3}) \|", todo)
    completed_ids = re.findall(r"\| (QED-\d{3}) \|", completed)
    assert todo_ids
    assert len(todo_ids) == len(set(todo_ids))
    assert not set(todo_ids) & set(completed_ids)
    for plan in (ROOT / "docs/plans").glob("*.md"):
        if plan.name != "index.md":
            assert f"../plans/{plan.name}" in todo
