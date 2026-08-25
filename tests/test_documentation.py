"""QED-Tracker 文档治理守护契约测试。

守护面清单（裁剪自根仓库七类，适配本仓库五层文档体系）：
  - architecture：架构文档完整性（入口集合、元数据、链接）
  - design：设计文档完整性（元数据、链接、DesignRef 引用）
  - standards：工程规范合规（文档规范、ADR 治理）
  - guides：操作入口可用性（CLI 命令一致性、不链历史）
  - trackers：任务治理（ID 唯一性、活跃计划关联）

编写约定（承接根仓库 governance-contract.md 范本）：
  - 纯标准库（re, shlex, pathlib），无第三方依赖
  - 自包含（不依赖外部服务或数据库）
  - 零网络访问
"""
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
    Path("docs/trackers/project-status.md"),
    Path("docs/architecture/index.md"),
    Path("docs/architecture/system-overview.md"),
    Path("docs/architecture/code-map.md"),
    Path("docs/architecture/main-line.md"),
    Path("docs/architecture/api.md"),
    Path("docs/architecture/database-schema.md"),
    Path("docs/design/index.md"),
    Path("docs/design/acquisition-and-inventory.md"),
    Path("docs/design/docs-restructure-alignment.md"),
    Path("docs/design/paper-discovery.md"),
    Path("docs/design/source-discovery.md"),
    Path("docs/design/review-round-dedup.md"),
    Path("docs/design/tracker-service.md"),
    Path("docs/design/governance-contract-alignment.md"),
    Path("docs/design/main-line-curriculum.md"),
    Path("docs/design/service-lifecycle.md"),
    Path("docs/design/service-lifecycle-encoding-fix.md"),
    Path("docs/design/tutorial-naming.md"),
    Path("docs/design/model-mode-config.md"),
    Path("docs/standards/index.md"),
    Path("docs/standards/documentation.md"),
    Path("docs/standards/adr-governance.md"),
    Path("docs/standards/version-cleanup.md"),
    Path("docs/adr/index.md"),
    Path("docs/adr/0001-tracker-service-architecture.md"),
    Path("docs/adr/0002-version-cleanup-governance.md"),
    Path("docs/adr/0003-pending-design-location.md"),
    Path("docs/guides/index.md"),
    Path("docs/guides/operations.md"),
    Path("docs/guides/development.md"),
    Path("docs/plans/index.md"),
    Path("docs/plans/2026-08-main-line-curriculum.md"),
    Path("docs/plans/2026-08-docs-restructure-alignment.md"),
    Path("docs/plans/2026-08-prompt-explore-baseline.md"),
    Path("docs/plans/2026-08-prompt-optimization.md"),
    Path("docs/plans/2026-08-prompt-explore-baseline.md"),
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
    Path("docs/history/qed-036-tutorial-naming/index.md"),
    Path("docs/history/three-table-schema.md"),
    Path("docs/history/database-schema-ownership.md"),
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
    Path("docs/architecture/database-schema.md"),
    Path("docs/design/acquisition-and-inventory.md"),
    Path("docs/design/paper-discovery.md"),
    Path("docs/design/source-discovery.md"),
    Path("docs/design/review-round-dedup.md"),
    Path("docs/design/tracker-service.md"),
    Path("docs/design/governance-contract-alignment.md"),
    Path("docs/design/main-line-curriculum.md"),
    Path("docs/design/service-lifecycle.md"),
    Path("docs/design/service-lifecycle-encoding-fix.md"),
    Path("docs/design/tutorial-naming.md"),
    Path("docs/design/model-mode-config.md"),
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
    """守护：文档入口集合完整性。

    模块职责：确保当前文档与历史文档的集合严格匹配预定义白名单，
    防止未授权文件混入或必要文件被意外移除。

    设计关联（DesignRef）：docs/standards/documentation.md「文档分类与事实边界」
    实现状态：Implemented
    被测代码：docs/ 全目录 Markdown 文件集合
    守护面：architecture + design（文档结构完整性）
    失效后果：文档入口失控——新增文档未登记、必要文档被删除或历史文档混入当前层，
    导致 Agent 进场导航失效或过期信息误导决策。
    """
    all_docs = {path.relative_to(ROOT) for path in _all_markdown()}
    current = {path.relative_to(ROOT) for path in _current_markdown()}
    assert current == REQUIRED_CURRENT_DOCS
    assert all_docs == REQUIRED_CURRENT_DOCS | REQUIRED_HISTORY_DOCS
    assert INDEX_DOCS <= all_docs
    assert not list((ROOT / "docs").rglob("README.md"))
    assert not (ROOT / "docs/history/worklogs").exists()


def test_managed_documentation_has_required_metadata():
    """守护：文档元数据完整性。

    模块职责：确保所有管理文档包含强制元数据字段（状态、最后更新），
    设计与架构文档额外包含实现状态、关联代码、关联测试。

    设计关联（DesignRef）：docs/standards/documentation.md「元数据」
    实现状态：Implemented
    被测代码：docs/ 全目录 Markdown 文件（架构/设计/标准/指南/索引/ADR）
    守护面：design + architecture（文档元数据规范）
    失效后果：文档缺少元数据导致 Agent 无法判断文档时效性与关联性，
    可能依据过期设计做出错误实现决策。
    """
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
    """守护：文档内链接有效性。

    模块职责：确保当前文档中所有本地相对链接指向真实存在的文件，
    防止断链导致 Agent 导航失败。（历史文件豁免：只读留档相对路径可能因文件移动失效）

    设计关联（DesignRef）：docs/standards/documentation.md「内部链接显式指向文件」
    实现状态：Implemented
    被测代码：docs/ 全目录 Markdown 文件（history/ 豁免）
    守护面：architecture + design（文档链接完整性）
    失效后果：断链导致 Agent 无法导航到关联文档，可能跳过关键设计约束或实现指南。
    """
    missing = []
    for document in _all_markdown():
        # 历史文件为只读留档，相对链接可能因文件移动而失效，豁免检查
        if "history" in document.relative_to(ROOT).parts:
            continue
        for target, resolved in _local_targets(document):
            if not resolved.exists():
                missing.append(f"{document.relative_to(ROOT)} -> {target}")
    assert not missing, "\n".join(missing)


def test_current_code_and_test_references_resolve():
    """守护：文档中代码/测试路径引用有效性。

    模块职责：确保当前文档中反引号引用的 src/ 和 tests/ 路径指向真实文件，
    防止文档描述的代码路径不存在。（plans/ 豁免：计划文档描述未来文件）

    设计关联（DesignRef）：docs/standards/documentation.md「代码与测试引用」
    实现状态：Implemented
    被测代码：docs/ 当前文档中 `src/...` 和 `tests/...` 反引号引用
    守护面：code（文档与代码对齐）
    失效后果：文档引用不存在的代码路径，Agent 按文档指引找不到对应实现，
    可能误判功能缺失或定位错误模块。
    """
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
    """守护：当前文档无过期指导。

    模块职责：确保当前文档不包含旧版本路径（app/、docs/discuss/）、
    退役版本号（0.2）等过期内容，防止 Agent 执行已废弃操作。

    设计关联（DesignRef）：docs/standards/documentation.md「归档与删除」
    实现状态：Implemented
    被测代码：docs/ 当前文档（history/ 豁免）
    守护面：standards（文档时效性）
    失效后果：过期指导残留在当前文档中，Agent 可能执行已废弃的命令或
    引用已不存在的路径，导致操作失败或数据损坏。
    """
    violations = []
    for document in _current_markdown():
        content = document.read_text(encoding="utf-8")
        for name, pattern in LEGACY_PATTERNS.items():
            if pattern.search(content):
                violations.append(f"{document.relative_to(ROOT)}: {name}")
    assert not violations, "\n".join(violations)


def test_operational_entrypoints_do_not_link_to_history():
    """守护：操作入口不链历史。

    模块职责：确保 README.md 和操作指南（operations.md、development.md）
    中的本地链接不指向 docs/history/ 目录，防止用户执行历史操作。

    设计关联（DesignRef）：docs/standards/documentation.md「失效指南默认删除」
    实现状态：Implemented
    被测代码：README.md、docs/guides/operations.md、docs/guides/development.md
    守护面：guides（操作入口纯净性）
    失效后果：操作入口链向历史文档，用户可能按照过期指南执行操作，
    导致配置错误或功能异常。
    """
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
    """守护：文档 CLI 命令与 parser 一致。

    模块职责：确保当前文档中记录的 qed-tracker 命令行用法
    能被 CLI parser 正确解析，防止文档描述的命令不可用。

    设计关联（DesignRef）：docs/standards/documentation.md「CLI 命令一致性」
    实现状态：Implemented
    被测代码：src/qed_tracker/cli.py（build_parser）
    守护面：guides（CLI 可用性）
    失效后果：文档描述的命令无法被 parser 解析，用户执行时报错，
    降低文档可信度并阻碍操作流程。
    """
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
    """守护：Tracker ID 与活跃计划治理。

    模块职责：确保待办列表中 QED-ID 唯一、不与完成台账重复，
    且 docs/plans/ 中的每个计划文件在 todo 中有对应引用。

    设计关联（DesignRef）：docs/trackers/todo.md「任务 ID 治理规则」
    实现状态：Implemented
    被测代码：docs/trackers/todo.md、docs/trackers/completed.md、docs/plans/
    守护面：trackers（任务治理完整性）
    失效后果：Tracker ID 重复或计划无引用，导致任务追踪混乱，
    Agent 可能重复执行已完成任务或遗漏活跃计划。
    """
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
