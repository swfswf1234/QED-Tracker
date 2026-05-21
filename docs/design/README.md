# Design Documents

`docs/design/` stores accepted design records for QED-Tracker. These documents explain how a feature, workflow, or domain area should work after a decision has been made.

Open proposals and unresolved alternatives belong in `docs/discuss/`. Task status belongs in `docs/trackers/`. Durable resource facts belong in `docs/knowledge_base/`.

## Design Map

### Domain Designs

Documents that define what QED-Tracker tracks and how domain-specific collection should behave.

| Document | Scope | Status |
| --- | --- | --- |
| `math_qe_curriculum.md` | Math QE resource collection, confidence levels, collector flow, and dataset layout. | Active |
| `book_hunter_sources.md` | Textbook source strategy, LibGen and Anna's Archive download flow, and confidence matching. | Active |
| `frontier_tracking.md` | Frontier math and algorithm feeds, curated source list, and RSS collection strategy. | Active |
| `resources_hub.md` | Shared resources table, CLI, repository helpers, and GitHub metadata collection. | Active |
| `llm_research_plan.md` | LLM research direction, tool readiness, and unresolved target-list decisions. | Reserved |
| `cs_llm_sprint.md` | CS LLM sprint: DS+Algo → ML → DL → LLM algorithm → LLM application. | Draft |

### Workflow Guides

Documents that describe repeatable local operations or tool workflows.

| Document | Scope | Status |
| --- | --- | --- |
| `doc_viewer_guide.md` | Local HTTP viewer for mirrored official documentation. | Active |
| `pytorch_docs_guide.md` | PyTorch documentation mirroring and local viewing workflow. | Active |

## System-Level Designs

These are kept at `docs/` root because they describe the whole application rather than one design subarea.

| Document | Scope |
| --- | --- |
| `../architecture.md` | System architecture, module ownership, and data flow. |
| `../database.md` | Database abstraction, table schemas, repository rules, and engine selection. |
| `../tests.md` | Test strategy, commands, and current test coverage. |

## Writing Rules

Use design documents to record decisions that future agents and maintainers can act on.

- Start with scope, status, and the decision or design intent.
- Prefer diagrams, tables, schemas, command examples, and explicit data flow over long prose.
- Include file paths for the code modules that implement the design.
- Separate stable decisions from open questions. Open questions should link to `docs/discuss/` when they are still unresolved.
- Keep operational status out of design docs unless it affects the design. Put task progress in `docs/trackers/todos.md` or `docs/trackers/resolved.md`.
- When a design changes, update the relevant document in the same change as the code or workflow update.

## When To Add A New Design Document

Create a new file in `docs/design/` when the change introduces one of these:

- A new collector, tool, repository, data flow, or CLI workflow.
- A new domain resource strategy such as textbooks, papers, official docs, RSS feeds, or LLM research targets.
- A durable workflow that future agents must repeat.
- A resolved proposal from `docs/discuss/`.

Do not create a design document for one-off execution notes, temporary errors, or simple task progress.

## Naming

Use lowercase snake_case file names:

```text
<domain_or_tool>_<purpose>.md
```

Examples:

- `book_hunter_sources.md`
- `frontier_tracking.md`
- `resources_hub.md`
- `doc_viewer_guide.md`

If a document is primarily an unresolved proposal, keep it in `docs/discuss/` until the decision is accepted.
