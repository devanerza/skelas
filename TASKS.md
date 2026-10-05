# Development Tasks — Academic Course Scheduling System

Based on the PRD and development plan, here is the task execution for building the scheduler engine.

---

## Git Commit Rule (STRICT)

**MANDATORY**: Commit after completing each logical feature/fix, not per file, not all at once.

**Commit granularity**:
- ✓ After completing 1 feature (e.g., "Add time slot validation")
- ✓ After fixing 1 bug (e.g., "Fix lecturer conflict detection")
- ✓ After completing 1 constraint implementation (e.g., "Implement student group conflict constraint")
- ✗ NOT after each file
- ✗ NOT after entire phase

**Commit message format**:
```
<type>: <short description>

<optional detailed explanation>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

**Examples**:
- `feat: add data validation for courses and student groups`
- `feat: implement consecutive slot block generator`
- `feat: add lecturer conflict constraint`
- `fix: correct cross-semester enrollment conflict detection`
- `test: add unit tests for room requirement constraint`

**Enforcement**: Each task section below MUST end with a commit command.

---

## Phase 1 — Data Modeling & Input Validation

**Goal**: Store scheduling data as JSON/Python objects, not a database. Validate data structure before it reaches the scheduler.

### 1.1 Setup Project Structure

```
scheduler/
├── data/
│   ├── courses.json
│   ├── student_groups.json
│   ├── lecturers.json
│   ├── rooms.json
│   ├── time_slots.json
│   ├── course_enrollments.json
│   ├── teaching_assignments.json
│   └── lecturer_availability.json
├── src/
│   ├── models/
│   │   ├── __init__.py
│   │   ├── course.py
│   │   ├── student_group.py
│   │   ├── lecturer.py
│   │   ├── room.py
│   │   └── time_slot.py
│   ├── validation/
│   │   ├── __init__.py
│   │   └── validator.py
│   └── main.py
└── tests/
    └── test_validation.py
```

### 1.2 Define Time Slots (data/time_slots.json)

```json
[
  {"slot": 1, "start": "08:15", "end": "09:00"},
  {"slot": 2, "start": "09:00", "end": "09:45"},
  {"slot": 3, "start": "09:45", "end": "10:30"},
  {"slot": 4, "start": "10:30", "end": "11:15"},
  {"slot": 5, "start": "11:15", "end": "12:00"},
  {"slot": 6, "start": "13:00", "end": "13:45"},
  {"slot": 7, "start": "13:45", "end": "14:30"},
  {"slot": 8, "start": "14:30", "end": "15:15"},
  {"slot": 9, "start": "15:15", "end": "16:00"}
]
```

**Important**: Slots 1-9 are one consecutive range; no forced lunch break (classes/lecturers arrange their own break).

### 1.3 Define Courses (data/courses.json)

```json
[
  {
    "id": "MK001",
    "code": "IF101",
    "name": "Algoritma dan Pemrograman Dasar",
    "curriculum_semester": 1,
    "credits": 3,
    "room_type_required": "CLASSROOM"
  },
  {
    "id": "MK002",
    "code": "IF301",
    "name": "Sistem Basis Data",
    "curriculum_semester": 3,
    "credits": 3,
    "room_type_required": "LAB"
  }
]
```

**Rule**: `curriculum_semester` is academic metadata, not a conflict determinant.

### 1.4 Define Student Groups (data/student_groups.json)

```json
[
  {"id": "IF-1", "program": "IF", "cohort": 2024, "semester": 1},
  {"id": "IF-3", "program": "IF", "cohort": 2023, "semester": 3},
  {"id": "IF-5", "program": "IF", "cohort": 2022, "semester": 5},
  {"id": "BD-3", "program": "BD", "cohort": 2023, "semester": 3},
  {"id": "TL-5", "program": "TL", "cohort": 2022, "semester": 5}
]
```

### 1.5 Define Course Enrollments (data/course_enrollments.json)

```json
[
  {"course_id": "MK001", "student_groups": ["IF-1"]},
  {"course_id": "MK002", "student_groups": ["IF-3", "BD-3"]},
  {"course_id": "MK003", "student_groups": ["IF-3", "IF-5"]}
]
```

**Critical**: This is what determines student conflict, not `curriculum_semester`.

### 1.6 Define Lecturers (data/lecturers.json)

```json
[
  {"id": "D001", "name": "Dr. Ahmad"},
  {"id": "D002", "name": "Dr. Budi"},
  {"id": "D003", "name": "Dr. Citra"}
]
```

### 1.7 Define Teaching Assignments (data/teaching_assignments.json)

```json
[
  {"course_id": "MK001", "lecturer_id": "D001"},
  {"course_id": "MK002", "lecturer_id": "D002"}
]
```

### 1.8 Define Lecturer Availability (data/lecturer_availability.json)

```json
[
  {
    "lecturer_id": "D001",
    "availability": {
      "MONDAY": [1,2,3,4,5],
      "TUESDAY": [1,2,3],
      "WEDNESDAY": [6,7,8,9]
    }
  }
]
```

### 1.9 Define Rooms (data/rooms.json)

```json
[
  {"id": "R501", "name": "Kelas 501", "type": "CLASSROOM", "capacity": 40},
  {"id": "R502", "name": "Kelas 502", "type": "CLASSROOM", "capacity": 40},
  {"id": "LAB01", "name": "Lab Komputer", "type": "COMPUTER_LAB", "capacity": 30},
  {"id": "LAB02", "name": "Lab Logistik", "type": "LOGISTICS_LAB", "capacity": 25}
]
```

### 1.10 Build Data Models (src/models/)

Build Python dataclass/pydantic models for each entity:
- `Course`
- `StudentGroup`
- `Lecturer`
- `Room`
- `TimeSlot`
- `CourseEnrollment`
- `TeachingAssignment`
- `LecturerAvailability`

### 1.11 Build Validator (src/validation/validator.py)

Validation rules:
- Credits must be 2-4
- Course IDs unique
- Student group references valid
- Lecturer availability slots valid (1-9)
- Room types valid
- No orphan course enrollments
- No orphan teaching assignments

### 1.12 Create validate.py Script

```bash
python validate.py
```

Output:
```
✓ Time slots valid
✓ Courses valid
✓ Student groups valid
✓ Course enrollments valid
✓ Lecturers valid
✓ Teaching assignments valid
✓ Rooms valid

Data validation passed.
```

---

## Phase 2 — Scheduling Engine (Constraint Solver)

**Goal**: Implement constraint-based scheduler using OR-Tools CP-SAT.

### 2.1 Install OR-Tools

```bash
pip install ortools
```

Update `requirements.txt`:
```
fastapi
uvicorn[standard]
ortools
```

### 2.2 Generate Valid Consecutive Slot Blocks

Function: `generate_consecutive_blocks(credits: int) -> List[List[int]]`

Example for 4 SKS:
```python
[
  [1,2,3,4],  # valid
  [2,3,4,5],  # valid
  [3,4,5,6],  # valid (slot 5→6 is not treated as a break)
  [4,5,6,7],  # valid
  [5,6,7,8],  # valid
  [6,7,8,9]   # valid
]
```

### 2.3 Create Decision Variables

For each course, scheduler determines:
- `day` (MONDAY - SATURDAY)
- `start_slot` (from valid consecutive blocks)
- `room` (from available rooms matching room_type_required)
- `sched` (reified bool: course is scheduled at all — see 2.8)

### 2.4 Implement Hard Constraints

#### 2.4.1 Lecturer Conflict Constraint
Lecturer cannot teach 2 courses at overlapping time.

#### 2.4.2 Student Group Conflict Constraint
Student group cannot attend 2 courses at overlapping time.

**Critical**: Check actual enrolled groups, not curriculum_semester.

#### 2.4.3 Room Conflict Constraint
Room cannot host 2 courses at same time.

#### 2.4.4 Lecturer Availability Constraint
Course can only be scheduled during lecturer's available slots.

#### 2.4.5 Room Requirement Constraint
Course requiring LAB must be assigned to LAB room type.

#### 2.4.6 Consecutive Slots Constraint
Course with N credits occupies exactly N consecutive slots (already enforced by valid block generation).

#### 2.4.7 Same-Day Constraint
Course cannot split across multiple days (already enforced by design).

### 2.5 Build Scheduler (src/scheduler.py)

Main function: `schedule(data) -> ScheduleResult`

Input: All JSON data loaded
Output:
```json
{
  "status": "FEASIBLE",
  "solve_time": 2.31,
  "schedule": [
    {
      "course_id": "MK001",
      "course_name": "Algoritma dan Pemrograman Dasar",
      "lecturer": "Dr. Ahmad",
      "student_groups": ["IF-1"],
      "room": "Kelas 501",
      "day": "MONDAY",
      "start_slot": 1,
      "end_slot": 3,
      "time": "08:15-10:30"
    }
  ]
}
```

If nothing can be scheduled:
```json
{
  "status": "INFEASIBLE",
  "message": "No course can be scheduled under current constraints"
}
```

### 2.6 Create run_scheduler.py CLI

```bash
python run_scheduler.py
```

Output (console messages in Bahasa Indonesia, status values in English):
```
Memuat data...
Mata kuliah: 50
Kelompok mahasiswa: 15
Dosen: 10
Ruangan: 8

Membuat variabel keputusan...
Menambahkan batasan...
Memecahkan (berbatas waktu, solusi terbaik tetap ditampilkan)...

Status: FEASIBLE
Waktu penyelesaian: 2.31 detik
```

### 2.7 (Done) Add independent schedule validator

`validate_schedule.py` re-runs all hard constraints on `schedule.json` without trusting the solver.

### 2.8 Partial Scheduling — always return a schedule

Every course gets a reified `sched` bool; all of its constraints are guarded
by it and the objective maximizes `1_000_000 * sum(sched)` first, so CP-SAT
picks which courses to skip in ONE solve (the old single-drop probe loop
never isolated multi-course conflicts → status UNKNOWN).

Status contract:
- 0 scheduled → `INFEASIBLE`
- all scheduled → `FEASIBLE`
- some scheduled → `PARTIAL` + `dropped` list with a per-course reason

Solve is capped at 30s with a live progress callback so long runs never look
hung; the best solution found is always returned.

---

## Phase 3 — Testing & Validation

**Goal**: Test scheduler correctness with unit tests, integration tests, and the schedule validator.

### 3.1 Unit Tests for Constraints

#### Test 1: Lecturer Conflict
```python
# 2 courses, 1 lecturer
# Expected: courses do not overlap
```

#### Test 2: Room Conflict
```python
# 2 courses, 1 room
# Expected: courses do not overlap
```

#### Test 3: Student Group Conflict
```python
# MK001 → IF-3
# MK002 → IF-3
# Expected: no overlap
```

#### Test 4: Different Student Groups
```python
# MK001 → IF-3
# MK002 → BD-3
# Expected: overlap ALLOWED
```

#### Test 5: Cross-Semester Conflict
```python
# MK001 → IF-3, IF-5
# MK002 → IF-5
# Expected: no overlap (both attended by IF-5)
```

#### Test 6: Consecutive Slots for 4 SKS
```python
# Valid: [1,2,3,4] .. [6,7,8,9] (all consecutive ranges within 1-9)
```

#### Test 7: Lecturer Availability
```python
# Lecturer A available Wednesday only
# Course assigned to Lecturer A
# Expected: scheduled on Wednesday
```

#### Test 8: Room Type Requirement
```python
# Course requires COMPUTER_LAB
# Expected: assigned to LAB01 (type=COMPUTER_LAB), not R501 (CLASSROOM)
```

#### Test 9: Infeasible Scenario → partial schedule
```python
# 10 courses × 4 SKS, 1 room, 1 lecturer
# Expected: PARTIAL or INFEASIBLE with a shown schedule and a reason
# for every skipped course (never a crash / UNKNOWN)
```

### 3.2 Build Independent Schedule Validator (validate_schedule.py)

After the scheduler generates a schedule, validate it independently:

```bash
python validate_schedule.py schedule.json
```

Output:
```
Checking lecturer conflicts... ✓
Checking room conflicts... ✓
Checking student conflicts... ✓
Checking consecutive credits... ✓
Checking lecturer availability... ✓
Checking room requirements... ✓
Checking all courses scheduled... ✓

Schedule is VALID.
```

### 3.3 Test Real Dataset

Use the realistic dataset:
- 58 courses
- 20 lecturers
- 5 rooms
- 15 student groups
- 6 days
- 9 slots

Run the scheduler and record:
- Solve time
- Status (FEASIBLE/PARTIAL)

### 3.4 Test Infeasible Scenario

Build a deliberately impossible scenario:
```
1 room
1 lecturer
10 courses × 4 SKS each
Only Monday-Friday, slot 1-4 available
```

Expected: `PARTIAL` (some courses scheduled, rest listed with reasons) or `INFEASIBLE`.

### 3.5 Benchmark Table

Real run: `python tests/benchmark.py` (deterministic seed `SSEED = 20261003`,
independent validator **validates** every FEASIBLE/PARTIAL result).
Solver time cap 30s. Dataset generated with load balancing (lightest
lecturer/group prioritized) so no capacity hotspot exists.

Encoding: conflicts are encoded as `AddNoOverlap` on absolute time intervals
(not pairwise block comparison). See "Constraint Encoding" in PRD.md.

| Courses | Lecturers | Rooms | Constraints | Solve Time | Status         | Valid |
|---------|-----------|-------|-------------|------------|----------------|-------|
| 10      | 5         | 4     | 743         | 0.18s      | FEASIBLE       | VALID |
| 25      | 8         | 6     | 1,586       | 3.84s      | FEASIBLE       | VALID |
| 50      | 12        | 8     | 3,513       | 30s cap    | FEASIBLE/PARTIAL | VALID |
| 80      | 16        | 8     | 5,648       | 30s cap    | FEASIBLE/PARTIAL | VALID |

Historical comparison before the pairwise → `AddNoOverlap` refactor (commit `d44e353`):

| Courses | Constraints (pairwise) | Constraints (NoOverlap) | Status before | Status after |
|---------|------------------------|-------------------------|---------------|--------------|
| 10      | 8,248                  | 743                     | FEASIBLE      | FEASIBLE     |
| 25      | 91,749                 | 1,586                   | FEASIBLE      | FEASIBLE     |
| 50      | 488,612                | 3,513                   | FEASIBLE      | FEASIBLE     |
| 80      | 1,397,302              | 5,648                   | UNKNOWN       | FEASIBLE     |

Notes:
- The benchmark rows above were captured before the 120s → 30s cap change;
  at the 30s cap 50/80 may end `PARTIAL` (solver keeps optimizing, the best
  solution is still returned). Raise `max_time_in_seconds` in
  `src/scheduler.py` if more courses/optimality are needed.
- Before the refactor, 80 courses = **UNKNOWN** (timeout). After: **FEASIBLE**.
- Constraints grow ~quadratically with course count, but the constant is far
  smaller because the solver processes `AddNoOverlap` as a native structure,
  not hundreds of thousands of bool clauses.

---

## Phase 4 — Database & API (Complete)

**Done.** SQLite (stdlib `sqlite3`, no extra dependency) instead of
PostgreSQL; schema mirrors `data/*.json` per [ARCHITECTURE.md §3.5](ARCHITECTURE.md).
Key invariant held: `CourseScheduler` reads only through `SchedulerData`,
so the loader swap left the engine untouched — all 15 engine tests pass
against BOTH backends (JSON + SQL, gated by `tests/test_db.py`).

Goals:
- Migrate JSON data → PostgreSQL
- Build FastAPI endpoints
- Integrate scheduler engine with the database

### 4.1 Schema Migration (JSON → PostgreSQL)

Create tables mirroring the JSON files (PKs/FKs per ARCHITECTURE.md §3.2):

```sql
courses            (id PK, code, name, curriculum_semester, credits CHECK 2-4, room_type_required)
student_groups     (id PK, program, cohort, semester)
lecturers          (id PK, name)
rooms              (id PK, name UNIQUE, type, capacity)
time_slots         (slot PK CHECK 1-9, start, end)
course_enrollments (course_id FK→courses, group_id FK→student_groups,
                    PK (course_id, group_id))          -- split student_groups[] to rows
teaching_assignments (course_id FK→courses, lecturer_id FK→lecturers,
                    needs_review, PK (course_id, lecturer_id)) -- split lecturer_id/lecturer_ids[]
lecturer_availability (lecturer_id FK→lecturers, day, slot, PK (lecturer_id, day, slot))
-- alternative: single row per lecturer with JSONB availability column
```

- `room_type_required` stays a soft link (enum/CHECK against
  `rooms.type`), not FK — matches current data model.
- Migrate script: read each `data/*.json`, split array columns
  (`student_groups`, `lecturer_ids`) into join rows, insert.
- Sanity check: row counts after split == sum of array lengths before.

### 4.2 Data Access Layer — swap loader behind `SchedulerData`

- Refactor `SchedulerData.__init__` to accept a source
  (`data_dir` JSON vs `db_session` SQL); all `_load_*` methods return the
  same dataclass lists.
- Rebuild the same lookup maps (`course_dict`, `course_to_groups`,
  `course_to_lecturer`, `lecturer_to_availability`) from query results —
  engine and validators must be byte-identical in behavior.
- Keep `data/` JSON as fallback + seed source for tests.
- Gate: `python tests/test_scheduler.py` passes against BOTH backends.

### 4.3 FastAPI Endpoints

Extend [main.py](main.py) (currently a stub):

```
GET    /courses, /lecturers, /rooms, /student-groups        # list
POST   /courses ... (CRUD per entity)
POST   /schedule/run            # run CourseScheduler, persist result
GET    /schedule/latest         # status + schedule[] + dropped[]
POST   /schedule/validate       # run ScheduleValidator on latest run
GET    /diagnose                # CourseScheduler.diagnose() findings
```

- `POST /schedule/run` wraps `run_scheduler.py` logic: load → solve
  (30s cap, run in background task if slow) → return `ScheduleResult`
  envelope (`status`, `solve_time`, `schedule`, `dropped`).
- Status contract unchanged: `FEASIBLE` / `PARTIAL` / `INFEASIBLE` /
  `UNKNOWN` (code and tests depend on these values).

### 4.4 Persist Schedule Output

- `schedules` table (id, status, solve_time, message, created_at) +
  `schedule_entries` (schedule_id FK, course_id FK, room_id FK, day,
  start_slot, end_slot, lecturer text, ...) — replaces the `schedule.json`
  file drop for API consumers; keep file export as dev convenience.
- `dropped` reasons stored alongside (course_id, reason) so `/schedule/latest`
  explains partial runs without re-solving.

### 4.5 Validation Integration

- Input: run `DataValidator` before every migration insert and behind
  `POST /courses` etc. (reject invalid rows with its `errors` list).
- Output: expose `ScheduleValidator` checks via `POST /schedule/validate`
  so the API never trusts the solver — same rule as the CLI.

---

**Commit points** (per Git Commit Rule above):
- `feat: add PostgreSQL schema mirroring data/ JSON files`
- `feat: add JSON-to-PostgreSQL migration script`
- `feat: add db-backed source to SchedulerData with JSON fallback`
- `feat: add FastAPI CRUD endpoints for scheduling entities`
- `feat: add /schedule/run endpoint integrating CP-SAT engine`
- `feat: persist schedule results and dropped reasons to database`
- `feat: expose input and schedule validation via API`

---

## Phase 5 — Dashboard/UI (Out of Scope — Separate Repo)

**Not part of this repository.** The dashboard/test GUI is developed in a
separate duplicate repo consuming this project's REST API. Only API-side
work happens here. Do not add frontend code to this repo.

---

## Current Status

**Phase**: Phase 1-4 complete (data modeling, CP-SAT engine, testing,
database & API). Project scope is API-only.
**Next**: Dashboard/UI lives in a separate duplicate repo — API-side work
continues here (soft constraints, relaxation, endpoint coverage).

---

## Notes

- **DO NOT** skip Phase 1-3 and jump to database work
- Scheduler engine must stand alone and be testable without a database
- Focus: correctness first, optimization later
- Soft constraints not implemented yet (future work)
- **API-only repo**: no dashboard/GUI code here — built in a separate
  duplicate repo against this API
- Console output is Bahasa Indonesia; status values (`FEASIBLE`/`PARTIAL`/
  `INFEASIBLE`) stay English because code and tests depend on them
