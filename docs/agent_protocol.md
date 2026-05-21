# QED-Tracker Agent Protocol

> Version: 1.1
> Status: Active
> Purpose: give agents a stable entry point for reading context, making changes, validating work, and keeping the documentation system coherent.

## 1. Reading Order

Before changing code or documentation, read context in this order:

1. `README.md` for product scope, runtime assumptions, and user-facing commands.
2. `docs/trackers/todos.md` for active work and known gaps.
3. The relevant design documents:
   - `docs/architecture.md` for system boundaries and data flow.
   - `docs/database.md` for schema and persistence rules.
   - `docs/design/README.md` for the design-document map.
   - Specific files under `docs/design/` for the feature or workflow being changed.
4. `docs/knowledge_base/` when the task touches textbook inventory, learning dependencies, or resource status.
5. Recent `docs/worklogs/YYYY-MM-DD.md` entries when the task continues previous work.

Do not rely on memory when a repository document already records the decision.

## 2. Work Loop

Every non-trivial task should follow the P-E-V-L loop.

### 2.1 Plan

- State the current understanding, intended edits, and risk areas before changing files.
- For multi-step work, keep a visible task list and update it as the work progresses.
- If an operation is destructive or hard to reverse, ask for human confirmation first.

### 2.2 Execute

- Keep edits scoped to the requested task and the affected documentation or code paths.
- Follow existing repository patterns before introducing a new abstraction.
- Python code should remain modular and compatible with the existing FastAPI, repository, and collector layout.
- Mathematical notation in docs and comments must use standard LaTeX syntax: `$...$` or `$$...$$`.

### 2.3 Verify

- Run the most relevant tests, scripts, or static checks for the changed area.
- If verification cannot run because of missing services, dependencies, credentials, or network access, record that limitation explicitly.
- For documentation-only changes, verify links, paths, and terminology with repository search.

### 2.4 Log

- Update `docs/trackers/todos.md` when task status changes.
- Update the relevant design document when architecture, workflow, schema, or module ownership changes.
- Add a dated worklog entry in `docs/worklogs/` for substantial changes, including changed files and verification evidence.

## 3. Documentation System

Use each documentation area for one job only.

| Location | Responsibility |
| --- | --- |
| `README.md` | Public project entry point, quick start, and high-level map. |
| `docs/agent_protocol.md` | Agent operating protocol and documentation maintenance rules. |
| `docs/architecture.md` | Current system architecture and module boundaries. |
| `docs/database.md` | Current database design, schema, and persistence rules. |
| `docs/tests.md` | Test strategy, commands, and coverage notes. |
| `docs/design/` | Accepted designs, module designs, domain designs, and workflow guides. |
| `docs/discuss/` | Open proposals and unresolved technical discussion. Move resolved decisions into `docs/design/` or trackers. |
| `docs/trackers/` | Active and resolved task status only. Do not store detailed designs here. |
| `docs/worklogs/` | Dated execution records. File names must use `YYYY-MM-DD.md`. |
| `docs/knowledge_base/` | Resource inventory, learning dependencies, and durable domain facts. |

See `docs/design/README.md` for the detailed design-document taxonomy.

## 4. Knowledge Core Rules

For textbook digitization, RAG preparation, and mathematical resources:

- Preserve logical hierarchy from source material: titles, chapters, theorems, proofs, exercises, references, and captions.
- Preserve source cross-references such as "see Theorem 2.1" instead of normalizing them away.
- Mark uncertain OCR or formula recognition as `[CHECK_REQUIRED]`; do not silently rewrite mathematical meaning.
- Treat `docs/knowledge_base/inventory.md` as the durable inventory record for textbook status.

## 5. Runtime Environment

- Conda environment: `QED_env`
- Python version: 3.12
- Dependency install: `pip install -r requirements.txt`
- Runtime configuration: copy `setting.example.ini` to `setting.ini`, then configure database and proxy values.
- Proxy configuration: use the `[Proxy]` section in `setting.ini`.
- Python commands should run inside `QED_env` unless the user explicitly chooses another environment.

## 6. Git And Change Hygiene

- Branch policy: keep `main` stable; use `dev` for daily work and `feat/*` for larger changes.
- Commit prefixes: `feat:`, `fix:`, `docs:`, `refactor:`.
- Before committing, check whether the change requires updates to:
  - `docs/design/`
  - `docs/trackers/`
  - `docs/worklogs/YYYY-MM-DD.md`
  - `README.md`
- Never revert unrelated user changes. If existing dirty files affect the task, work with them and call out any constraint.
