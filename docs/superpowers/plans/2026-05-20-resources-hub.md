# Resources Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a shared resources hub for RSS articles, GitHub repositories, and curated links.

**Architecture:** Keep the existing `resources` table. Add focused repository helpers, a local management CLI, and a GitHub collector that stores repository metadata through `ResourceRepo`.

**Tech Stack:** Python 3.12, SQLAlchemy ORM, argparse, pytest, SQLite in-memory tests.

---

### Task 1: Resource Repository Helpers

**Files:**
- Modify: `app/repository/resource_repo.py`
- Create: `tests/test_resource_repo.py`

- [x] Write failing tests for `get_by_url`, `exists_by_url`, `search`, `list_favorites`, and `set_favorite`.
- [x] Run `python -m pytest tests/test_resource_repo.py -v` and confirm failures are missing-method failures. Environment blocked: WSL has no `python`; `python3` has no pytest.
- [x] Implement minimal query helpers in `ResourceRepo`.
- [ ] Re-run `python -m pytest tests/test_resource_repo.py -v`.

### Task 2: Resource CLI

**Files:**
- Create: `scripts/manage_resources.py`
- Modify: `tests/test_cli.py`

- [x] Add CLI parsing tests for `list`, `search`, `favorite`, and `export`.
- [x] Run targeted CLI parser tests and confirm import or parser failures. Environment blocked: WSL `python3` has no pytest.
- [x] Implement `parse_args`, list/search/favorite/export command handlers, and Markdown export formatting.
- [ ] Re-run targeted CLI tests.

### Task 3: GitHub Collector

**Files:**
- Create: `app/collectors/github_collector.py`
- Create: `scripts/hunt_github.py`
- Create: `tests/test_github_collector.py`
- Modify: `tests/test_cli.py`

- [x] Add tests with a fake downloader and SQLite session for inserting new repos and skipping duplicates.
- [x] Run targeted collector tests and confirm missing-module failure. Environment blocked: WSL `python3` has no pytest.
- [x] Implement `GitHubCollector.collect_repos`.
- [x] Add `scripts/hunt_github.py` CLI entry point and parser tests.
- [ ] Re-run targeted collector tests.

### Task 4: Documentation And Trackers

**Files:**
- Modify: `docs/design/README.md`
- Modify: `docs/trackers/todos.md`
- Modify: `docs/worklogs/2026-05-20.md`
- Modify: `README.md`

- [x] Add Resources Hub to the design map.
- [x] Update tracker status for T-204/T-205.
- [x] Record files changed and verification evidence in the worklog.
- [x] Run `rg` checks for new paths and stale references.

### Task 5: Verification

**Files:**
- No new files.

- [ ] Run `python -m pytest tests/test_resource_repo.py tests/test_cli.py tests/test_github_collector.py -v`.
- [ ] Run a broader relevant pytest selection if targeted tests pass.
- [x] Report exact verification output and any skipped tests.
