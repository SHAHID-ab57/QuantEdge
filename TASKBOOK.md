# Task Book

## Purpose

This document serves as the single source of truth for tracking every milestone, epic,
task, and micro-task throughout the project lifecycle. It replaces reliance on chat
history, distributed notes, or informal checklists by providing a centralized,
structured, and version-controlled implementation backlog.

Task tracking is important because it ensures clear accountability, prevents scope
creep, provides visibility into project progress, and enforces disciplined execution
of the project plan. Every contributor should consult this document to understand what
is being worked on, what is pending, and what has been completed.

This document should be updated after every completed task. It will evolve alongside
the project as new epics are identified, priorities shift, and milestones are delivered.

---

## Task Status

| Status | Meaning |
|---|---|
| Planned | Task has been identified and described but is not yet ready to begin. |
| Ready | All prerequisites are met; work can commence. |
| In Progress | Development is actively underway. |
| Review | Implementation is complete and awaiting review. |
| Completed | Finished, reviewed, and approved. |
| Blocked | Cannot proceed due to an unresolved dependency or external blocker. |
| Deferred | Postponed to a future milestone; not currently scheduled. |

---

## Task ID Convention

Every task is identified by a hierarchical ID that encodes its position in the project
structure.

**Format:** `M{0}-E{1}-T{2}-MT{3}`

| Segment | Meaning | Example |
|---|---|---|
| `M0` | Milestone 0 | `M0` |
| `E1` | Epic 1 within the milestone | `E1` |
| `T3` | Task 3 within the epic | `T3` |
| `MT2` | Micro-task 2 within the task | `MT2` |

**Examples:**

- `M0-E1-T1-MT1` — Milestone 0, Epic 1, Task 1, Micro-task 1
- `M2-E3-T7-MT4` — Milestone 2, Epic 3, Task 7, Micro-task 4
- `M5-E1-T2-MT1` — Milestone 5, Epic 1, Task 2, Micro-task 1
- `M0-E1-T4-MT0` — Milestone 0, Epic 1, Task 4 (no micro-task breakdown)

When a task does not require micro-task decomposition, `MT0` is used.

---

## Priority Levels

| Priority | Usage |
|---|---|
| Critical | Blocks all other work; must be resolved immediately. |
| High | Essential for the current milestone; should be completed before non-essentials. |
| Medium | Important but can be deferred within the milestone if necessary. |
| Low | Nice-to-have; addressed only after all higher-priority tasks are complete. |

Priority is reassessed at the beginning of each milestone.

---

## Dependency Rules

- Tasks may depend on the completion of one or more previous tasks.
- Dependencies must never be skipped. A task cannot begin until all prerequisite tasks
  are marked Completed.
- Documentation tasks must be completed before implementation tasks for the same
  component.
- The dependency chain is recorded in the Dependencies column of the Progress Tracking
  table.

---

## Git Workflow

Every micro-task follows a consistent workflow:

1. **Prompt** — One focused OpenCode prompt that defines the scope of the micro-task.
2. **Commit** — One Git commit containing only the changes for that micro-task.
3. **Review** — The commit is reviewed before being merged.

This one-to-one-to-one mapping ensures a clean, auditable history where every commit
corresponds to a well-defined unit of work.

Larger tasks that span multiple micro-tasks produce one commit per micro-task and
one review per task.

---

## Progress Tracking

| ID | Milestone | Epic | Task | Status | Priority | Dependencies | Git Commit |
|---|---|---|---|---|---|---|---|
| M0-E1-T1-MT1 | M0: Foundation | E1: Documentation | T1: Project Charter | Ready | Critical | None | — |
| M0-E1-T1-MT2 | M0: Foundation | E1: Documentation | T1: Project Charter | Planned | Critical | M0-E1-T1-MT1 | — |
| M0-E1-T2-MT1 | M0: Foundation | E1: Documentation | T2: Architecture | Planned | Critical | M0-E1-T1-MT2 | — |
| M0-E2-T1-MT1 | M0: Foundation | E2: Scaffold | T1: Repository Setup | Planned | High | M0-E1-T2-MT1 | — |
| M0-E2-T2-MT1 | M0: Foundation | E2: Scaffold | T2: Build Config | Planned | High | M0-E2-T1-MT1 | — |
| M1-E1-T1-MT1 | M1: Data Layer | E1: Ingestion | T1: Data Sources | Planned | High | M0-E2-T2-MT1 | — |
| M1-E1-T2-MT1 | M1: Data Layer | E1: Ingestion | T2: Pipeline | Planned | High | M1-E1-T1-MT1 | — |
| M2-E1-T1-MT1 | M2: Features | E1: Engineering | T1: Feature API | Planned | Medium | M1-E1-T2-MT1 | — |
| M3-E1-T1-MT1 | M3: AI Training | E1: Workflow | T1: Research Env | Planned | Medium | M2-E1-T1-MT1 | — |
| M4-E1-T1-MT1 | M4: Prediction | E1: Engine | T1: Serving | Planned | Medium | M3-E1-T1-MT1 | — |

---

## Milestone Summary

| Milestone | Name | Progress | Status |
|---|---|---|---|
| M0 | Foundation | 0% | Planned |
| M1 | Data Layer | 0% | Planned |
| M2 | Feature Engineering | 0% | Planned |
| M3 | AI Research & Training | 0% | Planned |
| M4 | Prediction Engine | 0% | Planned |
| M5 | Backtesting | 0% | Planned |
| M6 | Paper Trading | 0% | Planned |
| M7 | Portfolio Analytics | 0% | Planned |
| M8 | Risk Management | 0% | Planned |
| M9 | Production Readiness | 0% | Planned |
| M10 | Monitoring & Observability | 0% | Planned |
| M11 | Community & Expansion | 0% | Planned |

---

## Working Rules

1. **One micro-task per prompt.** Each OpenCode prompt addresses exactly one micro-task
   from the backlog. No scope creep within a single prompt.

2. **One commit per micro-task.** Every completed micro-task produces exactly one Git
   commit with a descriptive message referencing the task ID.

3. **Never work on multiple milestones simultaneously.** Only one milestone may be in
   progress at any given time. All epics and tasks within that milestone must be
   completed before the next milestone begins.

4. **Complete reviews before marking tasks complete.** A task is not considered
   Completed until its implementation has been reviewed and approved.

5. **Update TASKBOOK.md after every completed task.** The Progress Tracking table must
   be updated to reflect the current status, and the Git Commit column must reference
   the commit hash.

6. **Keep documentation synchronized with implementation.** When a task changes the
   codebase, any affected documentation must be updated within the same micro-task
   commit.

7. **Do not change task IDs.** Once assigned, a task ID is permanent. Deferred or
   cancelled tasks retain their IDs for traceability.

---

## Future Expansion

The following sections are reserved for future use as the project matures:

### Sprint Planning

### Release Planning

### Risk Register

### Technical Debt Tracking

### Change Requests

### Architecture Review Log
