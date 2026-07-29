import re
from pathlib import Path

CURRENT_DOCS = (
    "README.md",
    "docs/agent_protocol.md",
    "docs/architecture.md",
    "docs/tests.md",
    "docs/design/README.md",
    "docs/design/download_sources.md",
    "docs/design/axiom_handoff.md",
    "docs/trackers/todos.md",
    "docs/trackers/resolved.md",
)


def test_current_documentation_links_resolve():
    root = Path(__file__).parents[1]
    missing = []
    for relative in CURRENT_DOCS:
        document = root / relative
        assert document.exists(), relative
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#")):
                continue
            local = target.split("#", 1)[0]
            if local and not (document.parent / local).resolve().exists():
                missing.append(f"{relative} -> {target}")
    assert not missing, "\n".join(missing)
