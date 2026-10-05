# ARCHITECTURE — Skelas (Academic Course Scheduling System)

Whole-system architecture: application layer → data layer (JSON "database") →
CP-SAT engine logic → validation → output. Derived from current code
(`src/`, `data/`, entry scripts), not aspirational.

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Entry Points                                               │
│  run_scheduler.py   validate.py   validate_schedule.py      │
│  main.py (FastAPI stub, unused)  tests/*                    │
└────────────┬────────────────────────────────────────────────┘
             │
┌────────────▼────────────┐   ┌──────────────────────────────┐
│  src/data_loader.py     │◄──│  data/*.json  (source of     │
│  SchedulerData          │   │  truth, flat file "DB")      │
└────────────┬────────────┘   └──────────────────────────────┘
             │ SchedulerData (models + lookup maps)
┌────────────▼────────────┐
│  src/scheduler.py       │  OR-Tools CP-SAT constraint solver
│  CourseScheduler        │  → ScheduleResult (status/schedule/dropped)
└────────────┬────────────┘
             │ schedule.json (export)
┌────────────▼────────────┐
│  validate_schedule.py   │  independent pure-Python re-check
└─────────────────────────┘
```

Pipeline: **load JSON → build dataclass models + lookup maps → build CP-SAT
model → solve (30s cap) → extract result → export schedule.json → independent
validation**.

Phase 4 (SQLite/FastAPI) from [TASKS.md](TASKS.md) is implemented —
`main.py` exposes the FastAPI app over `skelas.db`. This repo is API-only;
the dashboard is a separate duplicate repo consuming this API, so no UI
layer exists in this architecture.

---

## 2. Application Layer

### 2.1 Entry points

| Script | Role |
|---|---|
| `run_scheduler.py` | Main CLI. Loads `data/`, runs solver, prints schedule (Bahasa Indonesia), exports `schedule.json`, prints diagnosis on INFEASIBLE/PARTIAL. |
| `validate.py` | Runs `DataValidator` on raw JSON (structural integrity before solve). |
| `validate_schedule.py` | Re-checks `schedule.json` against all hard constraints with pure Python — never trusts the solver. |
| `tests/test_scheduler.py`, `tests/benchmark.py` | Unit tests per constraint + benchmark table (seed `SSEED = 20261003`). |
| `main.py` | FastAPI stub (`GET /`), not wired to the engine yet. |

### 2.2 Module responsibilities

| Module | Responsibility |
|---|---|
| [src/models/__init__.py](src/models/__init__.py) | 8 dataclasses mirroring the 8 JSON files. Plain dataclasses, no validation logic. |
| [src/data_loader.py](src/data_loader.py) | `SchedulerData`: loads all JSON once, builds lookup dicts (`course_dict`, `lecturer_dict`, ...) and relation maps (`course_to_groups`, `course_to_lecturer`, `lecturer_to_availability`). Provides query methods used by engine. |
| [src/utils.py](src/utils.py) | `generate_consecutive_blocks(credits)` → all valid N-slot windows within slots 1–9; `slots_overlap(a, b)` → set intersection. |
| [src/validation/validator.py](src/validation/validator.py) | `DataValidator`: structural checks (unique IDs, FK integrity, credits 2–4, valid room types, valid availability slots, orphan enrollment/assignment detection). |
| [src/scheduler.py](src/scheduler.py) | `CourseScheduler`: model construction, constraint encoding, solve, result building, drop-reason + infeasibility diagnosis. |

### 2.3 Data flow inside `SchedulerData`

Constructed once per run:

- Entity lists: `courses`, `lecturers`, `rooms`, `student_groups`, `time_slots`
- Relation lists: `course_enrollments`, `teaching_assignments`, `lecturer_availability`
- Lookup maps:
  - `course_dict / lecturer_dict / room_dict / student_group_dict` — id → entity
  - `course_to_groups`: `course_id → [group_id]` (from `course_enrollments.json`)
  - `course_to_lecturer`: `course_id → [lecturer_id]` (merged; repeated rows and
    `lecturer_ids` arrays both supported → team teaching)
  - `lecturer_to_availability`: `lecturer_id → {DAY: [slot, ...]}`

Engine only ever reads through these maps — no direct file access in
`scheduler.py`.

---

## 3. Data Layer — JSON "Database Schema"

Flat JSON files in `data/` act as tables. Each file is a JSON array of row
objects; `id` (or a natural key) is the primary key; cross-file references are
foreign keys validated by `DataValidator`.

### 3.1 Entity–Relation diagram

```
time_slots (static calendar config)

courses ──< course_enrollments >── student_groups
   │
   ├──< teaching_assignments >── lecturers ──< lecturer_availability
   │
   └── room_type_required ──► rooms.type        (type match, not FK)

schedule.json (output) references: course_id, lecturer_ids,
                                    student_groups, room name, day, slots
```

### 3.2 Table definitions

#### `time_slots.json` — calendar grid (static config)

| Column | Type | Key/Constraint |
|---|---|---|
| `slot` | int | PK, 1–9 (unique) |
| `start` | string | "HH:MM" |
| `end` | string | "HH:MM" |

9 slots/day, 6 days (`MONDAY`–`SATURDAY`) → 54 slot-units/week. No forced
lunch break — slots 5→6 flow consecutively.

#### `courses.json`

| Column | Type | Key/Constraint |
|---|---|---|
| `id` | string | PK (`MK001`, ...) |
| `code` | string | display code (non-unique in real data, e.g. shared by course group) |
| `name` | string | |
| `curriculum_semester` | int | academic metadata only — **never** used for conflicts |
| `credits` | int | 2–4; determines block length (N SKS = N consecutive slots) |
| `room_type_required` | string | enum `CLASSROOM` \| `COMPUTER_LAB` \| `LOGISTICS_LAB`; soft-FK → `rooms.type` |

#### `student_groups.json`

| Column | Type | Key/Constraint |
|---|---|---|
| `id` | string | PK (`IF-5`, `BD-3`, ...) = `{program}-{cohort semester}` |
| `program` | string | `IF` \| `BD` \| `TL` |
| `cohort` | int | enrollment year |
| `semester` | int | current semester — metadata, **not** a conflict determinant |

#### `course_enrollments.json` — join table (drives student conflicts)

| Column | Type | Key/Constraint |
|---|---|---|
| `course_id` | string | FK → `courses.id` |
| `student_groups` | string[] | FKs → `student_groups.id` |

One row per course; array form = denormalized M:N. **This file, not
`curriculum_semester`, decides which groups clash.** A group appearing in two
courses → those courses cannot overlap (even cross-semester).

#### `lecturers.json`

| Column | Type | Key/Constraint |
|---|---|---|
| `id` | string | PK (`D001`, ...) |
| `name` | string | |

#### `teaching_assignments.json` — join table (course ↔ lecturer)

| Column | Type | Key/Constraint |
|---|---|---|
| `course_id` | string | FK → `courses.id`; every course must have ≥1 assignment (else error) |
| `lecturer_id` | string | legacy single-lecturer FK → `lecturers.id` |
| `lecturer_ids` | string[] | team-teaching FKs; takes precedence over `lecturer_id` |
| `needs_review` | bool | flag: assignment unconfirmed → warning in validator + CLI banner |

Engine normalizes both forms via `TeachingAssignment.all_lecturer_ids`.
Multiple rows with same `course_id` merge into one lecturer list.

#### `lecturer_availability.json`

| Column | Type | Key/Constraint |
|---|---|---|
| `lecturer_id` | string | PK/FK → `lecturers.id` (one row per lecturer) |
| `availability` | object | `{DAY: [slot ints]}`; DAY ∈ MONDAY..SATURDAY, slots ∈ 1–9; absent lecturer = unrestricted |

#### `rooms.json`

| Column | Type | Key/Constraint |
|---|---|---|
| `id` | string | PK (`R501`, `LAB01`, ...) |
| `name` | string | unique in practice (output references rooms by name) |
| `type` | string | `CLASSROOM` \| `COMPUTER_LAB` \| `LOGISTICS_LAB` |
| `capacity` | int | stored, currently not enforced by engine |

### 3.3 Lookup / derivation (not stored)

Built at load time, never persisted:

- `course → [lecturer_ids]` ← `teaching_assignments` (merged rows)
- `course → [group_ids]` ← `course_enrollments`
- `lecturer → availability` ← `lecturer_availability`
- `room_type → [rooms]` ← filter `rooms` by `type`

### 3.4 Output schema — `schedule.json`

Flat array (written by `run_scheduler.py`, read by `validate_schedule.py`):

```json
{
  "course_id": "MK001",
  "course_code": "ARI-24-IF",
  "course_name": "Enterprise Resource Planning",
  "lecturer": "Ari Widianto, S.Kom., M.Kom / ...",
  "lecturer_ids": ["D001", "D008"],
  "student_groups": ["IF-5", "BD-5", "TL-5"],
  "room": "Kelas 501",
  "day": "MONDAY",
  "start_slot": 1,
  "end_slot": 3,
  "time": "08:15-10:30"
}
```

`ScheduleResult` envelope (in-memory): `status`, `solve_time`, `schedule[]`,
`message`, `dropped[]` (each: `course_id`, `course_code`, `course_name`,
`reason`).

Status contract:
- `FEASIBLE` — all courses scheduled
- `PARTIAL` — some scheduled, `dropped[]` explains each skip
- `INFEASIBLE` — 0 scheduled (diagnosis printed)
- `UNKNOWN` — no solution within 30s cap

### 3.5 Relational mapping (Phase 4, implemented — SQLite)

JSON files map 1:1 onto tables in `src/db.py` (`skelas.db`, stdlib
`sqlite3`, no extra dependency):

| JSON file | Table | Keys |
|---|---|---|
| `courses.json` | `courses` | PK `id` |
| `student_groups.json` | `student_groups` | PK `id` |
| `lecturers.json` | `lecturers` | PK `id` |
| `rooms.json` | `rooms` | PK `id` |
| `time_slots.json` | `time_slots` | PK `slot` |
| `course_enrollments.json` | `course_enrollments` | composite PK `(course_id, group_id)` — split array to rows; `group_id NULL` marks a course with an empty array |
| `teaching_assignments.json` | `teaching_assignments` | composite PK `(course_id, lecturer_id)` — split `lecturer_ids`; keep `needs_review` |
| `lecturer_availability.json` | `lecturer_availability` | composite PK `(lecturer_id, day, slot)` — split the availability dict |
| `schedule.json` | `schedules` + `schedule_entries` + `schedule_dropped` | entries FK → `courses`; arrays stored as JSON text |

Seeding (`seed_from_json`) runs `DataValidator` first, wipes + inserts in one
transaction, then sanity-checks row counts. `SchedulerData(conn=...)` reads
the same lookup maps as the JSON path, so `CourseScheduler` is untouched.

---

## 4. Engine Logic (`src/scheduler.py`)

### 4.1 Pre-solve: block generation

`generate_consecutive_blocks(credits)` enumerates every contiguous run of
`credits` slots inside 1–9. Example for 4 SKS: `[1,2,3,4] … [6,7,8,9]`.
Consecutiveness and same-day placement are enforced **by construction** —
the solver only picks which valid block, never assembles slots.

### 4.2 Timeline encoding (one interval per course)

Instead of pairwise slot comparison:

```
absolute time T = day * 10 + offset(slot)      slot s → offset s-1
start = T_start,  end = start + credits        duration = credits
```

6 days × 10 units = 60-unit timeline (unit 9 per day always empty →
intervals never wrap across days). Each course becomes **one interval** on
this shared timeline; overlap detection becomes native `AddNoOverlap`.

(Historical: pairwise encoding needed ~1.4M constraints at 80 courses →
`UNKNOWN`; NoOverlap encoding needs ~5.6k → `FEASIBLE`.)

### 4.3 Decision variables (per course)

| Var | Domain | Meaning |
|---|---|---|
| `sched` | bool | 1 = included in schedule, 0 = skipped (reified) |
| `day` | 0..5 | MONDAY..SATURDAY |
| `block_idx` | 0..N-1 | index into valid blocks for this course's credits |
| `room` | 0..K-1 | index into compatible rooms (`rooms` matching `room_type_required`; raises if none) |
| `off / day10 / start / end` | derived | `off = offsets[block_idx]` (element), `start = 10*day + off`, `end = start + credits` |
| `interval` | optional interval `(start, credits, end)` present iff `sched` | conflict interval |
| `room_intervals[r]` | optional interval per compatible room, presence `pres` iff `sched && room==r` | room occupancy interval |
| `uses_r` (`pres`) | bool | `pres ≤ sched`; `pres ↔ (room == idx)` when scheduled |

### 4.4 Hard constraints

All conflicts encoded as `AddNoOverlap` on absolute-time intervals;
all constraints guarded by `sched` so skipped courses drop out cleanly.

1. **Lecturer conflict** — group courses by lecturer (team teaching: each
   co-lecturer gets the course's interval) → one `AddNoOverlap` per lecturer
   with ≥2 courses.
2. **Student group conflict** — group courses by enrolled group
   (`course_enrollments`, NOT `curriculum_semester`) → `AddNoOverlap` per
   group. Cross-semester sharing (e.g. IF-5 in MK001+MK002) clashes correctly.
3. **Room conflict** — per room, `AddNoOverlap` over that room's
   `room_intervals` (presence tied to room assignment + `sched`).
4. **Lecturer availability** — for each (course, co-lecturer):
   - lecturer absent on a day → `day != idx` (only if `sched`)
   - block not fully ⊆ available slots on a day → reified pair of bools
     (`is_this_day`, `is_this_block`) with `AddBoolOr(¬day, ¬block)`,
     all `OnlyEnforceIf(sched)`.
   - lecturer with **no** availability record = unrestricted (constraint
     skipped).
5. **Room requirement** — structural: `room` domain only spans
   `get_compatible_rooms(room_type_required)`; no invalid assignment possible.
6. **Consecutive slots / same-day** — by block generation + single interval.

No soft constraints yet (future work).

### 4.5 Objective (lexicographic-by-weight)

```python
Maximize( 1_000_000 * sum(sched)            # schedule as many courses as possible
        - 100 * sum(day_used)               # compact: fewer distinct days
        - 10  * sum(day_cost)               # earlier days (Mon > Fri)
        - 1 * sum(start_cost))              # earlier slots (morning-first)
```

Weight gaps guarantee term 1 dominates all others. Solver decides *which*
courses to skip in a single solve (no probe loop).

### 4.6 Solve & result building

- `CpSolver`, `max_time_in_seconds = 30`, `_ProgressCallback` prints each
  improving solution (long runs never look hung).
- On `OPTIMAL`/`FEASIBLE`: read `sched` for every course →
  - 0 scheduled → `INFEASIBLE`
  - all → `FEASIBLE`
  - some → `PARTIAL` + `dropped[]` where `_drop_reason()` re-derives WHY
    (no compatible room → availability leaves no block → lecturer slot-full →
    group no free window → all rooms blocked → combination clash), each
    message naming the JSON file to edit.
- `_extract_solution()` maps var values back to the output schema
  (day name, block → start/end slot, room name, time string from
  `time_slots.json`).

### 4.7 Diagnosis (`diagnose()` / `diagnose_dropped()`)

When infeasible, static + probe analysis produces actionable findings:

1. per course×lecturer: zero (day, block) options, or ≤4 options (risk)
2. per lecturer: load SKS > free slots (provably impossible) or
   `_probe_lecturer_fit()` — sub-model (5s) proving blocks can't fit
   availability alone
3. per group: SKS load vs 54 weekly slots (warn > 48)
4. per room type: demand SKS vs `rooms × 54` capacity (error >100%, warn >90%)
5. fallback: no single violator → suggests one-at-a-time data experiments

Each finding names the responsible entity **and the file to edit**.

---

## 5. Validation Architecture (two independent layers)

### Layer 1 — Input: `DataValidator` (pre-solve)

| Check | Level |
|---|---|
| JSON files loadable, non-empty entities | error |
| Unique ids (courses, groups, lecturers, rooms, slots) | error |
| `credits` ∈ 2–4; `room_type_required` ∈ enum | error |
| FK integrity: enrollment → course/group, assignment → course/lecturer, availability → lecturer | error |
| Course without lecturer assignment | error |
| Availability day/slot values valid | error |
| Course without enrollment; `needs_review` assignment | warning |

### Layer 2 — Output: `ScheduleValidator` (post-solve, no solver trust)

Pure Python, re-derives everything from `schedule.json` + `data/`:

| Check | Rule |
|---|---|
| lecturer conflicts | same `lecturer_id` in two overlapping same-day entries → fail |
| room conflicts | same room name overlapping → fail |
| student conflicts | shared group overlapping → fail |
| consecutive credits | slot count == credits AND slots contiguous |
| availability | every co-lecturer covers all occupied slots |
| room requirements | `room.type == course.room_type_required` |
| coverage | each course exactly once, day ∈ enum, slots ⊆ 1–9 |

Exit code 0 = VALID, 1 = INVALID with per-check failure list.

---

## 6. Testing

- `tests/test_scheduler.py` — one unit test per constraint (lecturer/room/
  student conflict, cross-semester conflict, block generation, availability,
  room type, infeasible → partial-with-reasons).
- `tests/benchmark.py` — deterministic seed, sizes 10–80 courses; every
  FEASIBLE/PARTIAL result re-validated by the independent validator; counts
  model constraints (NoOverlap refactor: 8,248 → 743 at 10 courses).
