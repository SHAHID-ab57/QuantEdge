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

| Status      | Meaning                                                               |
| ----------- | --------------------------------------------------------------------- |
| Planned     | Task has been identified and described but is not yet ready to begin. |
| Ready       | All prerequisites are met; work can commence.                         |
| In Progress | Development is actively underway.                                     |
| Review      | Implementation is complete and awaiting review.                       |
| Completed   | Finished, reviewed, and approved.                                     |
| Blocked     | Cannot proceed due to an unresolved dependency or external blocker.   |
| Deferred    | Postponed to a future milestone; not currently scheduled.             |

---

## Task ID Convention

Every task is identified by a hierarchical ID that encodes its position in the project
structure.

**Format:** `M{0}-E{1}-T{2}-MT{3}`

| Segment | Meaning                      | Example |
| ------- | ---------------------------- | ------- |
| `M0`    | Milestone 0                  | `M0`    |
| `E1`    | Epic 1 within the milestone  | `E1`    |
| `T3`    | Task 3 within the epic       | `T3`    |
| `MT2`   | Micro-task 2 within the task | `MT2`   |

**Examples:**

- `M0-E1-T1-MT1` — Milestone 0, Epic 1, Task 1, Micro-task 1
- `M2-E3-T7-MT4` — Milestone 2, Epic 3, Task 7, Micro-task 4
- `M5-E1-T2-MT1` — Milestone 5, Epic 1, Task 2, Micro-task 1
- `M0-E1-T4-MT0` — Milestone 0, Epic 1, Task 4 (no micro-task breakdown)

When a task does not require micro-task decomposition, `MT0` is used.

---

## Priority Levels

| Priority | Usage                                                                           |
| -------- | ------------------------------------------------------------------------------- |
| Critical | Blocks all other work; must be resolved immediately.                            |
| High     | Essential for the current milestone; should be completed before non-essentials. |
| Medium   | Important but can be deferred within the milestone if necessary.                |
| Low      | Nice-to-have; addressed only after all higher-priority tasks are complete.      |

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

1. **Prompt** — One focused Claude Code prompt that defines the scope of the micro-task.
2. **Commit** — One Git commit containing only the changes for that micro-task.
3. **Review** — The commit is reviewed before being merged.

This one-to-one-to-one mapping ensures a clean, auditable history where every commit
corresponds to a well-defined unit of work.

Larger tasks that span multiple micro-tasks produce one commit per micro-task and
one review per task.

---

## Progress Tracking

The milestone numbering below was replaced wholesale (see `ROADMAP.md`) once
it became clear the old M0–M11 breakdown didn't map onto what had actually
been built — see `CLAUDE.md`'s own note on this. The rows below are real,
not illustrative: each one names an actually-completed capability, verified
against the Definition of Done stated in `ROADMAP.md`'s own Purpose section
(real code, a passing test, and it's actually wired in), with the commit
that introduced it where the work has been committed.

| ID       | Milestone                        | Epic                         | Task                                                                                                                               | Status    | Priority | Dependencies | Git Commit           |
| -------- | -------------------------------- | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | --------- | -------- | ------------ | -------------------- |
| M1-E1-T1 | M1: Research & Training Platform | E1: Data Layer               | Market data ingestion, validation, event bus                                                                                       | Completed | Critical | None         | `ee8c890`            |
| M1-E2-T1 | M1: Research & Training Platform | E2: Feature Engineering      | Feature Engineering Engine                                                                                                         | Completed | High     | M1-E1-T1     | `11d03a9`            |
| M1-E3-T1 | M1: Research & Training Platform | E3: Dataset Validation       | Dataset Validation & Quality Engine                                                                                                | Completed | High     | M1-E2-T1     | `d53cbde`            |
| M1-E4-T1 | M1: Research & Training Platform | E4: ML Dataset Builder       | ML Dataset Builder                                                                                                                 | Completed | High     | M1-E2-T1     | `345341d`            |
| M1-E5-T1 | M1: Research & Training Platform | E5: Experiment Management    | Experiment Management System                                                                                                       | Completed | High     | M1-E4-T1     | `00d6d52`            |
| M1-E6-T1 | M1: Research & Training Platform | E6: Training Framework       | ML Training Framework + Baseline Model Framework                                                                                   | Completed | Critical | M1-E5-T1     | `c57a19d`, `3bd31a8` |
| M1-E6-T2 | M1: Research & Training Platform | E6: Training Framework       | Per-column feature normalization                                                                                                   | Completed | High     | M1-E6-T1     | `4376586`            |
| M1-E7-T1 | M1: Research & Training Platform | E7: Model Evaluation         | Model Evaluation & Benchmarking Engine                                                                                             | Completed | High     | M1-E6-T1     | `3a411c1`            |
| M1-E8-T1 | M1: Research & Training Platform | E8: Experiment Config Editor | In-app `feature_set`/`target_config`/`split_config` editor                                                                         | Completed | Medium   | M1-E5-T1     | `346f708`            |
| M2-E1-T1 | M2: Prediction & Backtesting     | E1: Live Prediction          | Live Prediction Service (`app/prediction/`, `/ml/predict`)                                                                         | Completed | Critical | M1-E6-T1     | `9871c1c`            |
| M2-E1-T2 | M2: Prediction & Backtesting     | E1: Live Prediction          | Non-blocking `/training-jobs/{id}/run` (background `asyncio.Task`, own DB session, duplicate-run rejection, shutdown cancellation) | Completed | High     | M1-E6-T1     | `8bb20f5`            |
| M2-E1-T3 | M2: Prediction & Backtesting     | E1: Live Prediction          | Prediction Grading (`app/prediction/grading.py`, `PredictionGradingScheduler`, `scripts/grade_predictions.py`)                     | Completed | High     | M2-E1-T1     | `92c4425`            |
| M2-E2-T1 | M2: Prediction & Backtesting     | E2: Backtesting              | Backtesting Engine (`app/backtest/`, `/ml/backtest`) — reuses live prediction + grading unmodified, verified no-look-ahead         | Completed | High     | M2-E1-T3     | pending commit       |

---

## Milestone Summary

| Milestone | Name                                         | Status      |
| --------- | -------------------------------------------- | ----------- |
| M1        | Research & Training Platform                 | COMPLETE    |
| M2        | Prediction & Backtesting                     | COMPLETE    |
| M3        | Paper Trading & Risk                         | NOT STARTED |
| M4        | Data Breadth                                 | NOT STARTED |
| M5        | Production Hardening                         | NOT STARTED |
| M6        | Live Trading (gated on extensive validation) | NOT STARTED |

M2 is now closed: the Live Prediction Service, making training-job
execution non-blocking (the async seam the Backtesting Engine's own runs
now share, rather than a second mechanism), Prediction Grading, and the
Backtesting Engine itself (reuses the live prediction and grading code
completely unmodified, verified adversarially to have no look-ahead bias)
are all real, tested, and wired into the running API and dashboard. See
`ROADMAP.md` for what each milestone actually covers.

---

## Working Rules

1. **One micro-task per prompt.** Each Claude Code prompt addresses exactly one micro-task
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
