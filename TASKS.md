# Development Tasks — Academic Course Scheduling System

Berdasarkan PRD dan development plan, berikut task execution untuk membangun scheduler engine.

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

**Goal**: Buat data jadwal dalam JSON/Python object, bukan database. Validasi struktur data sebelum masuk scheduler.

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

**Important**: Slot 1-5 consecutive, slot 6-9 consecutive, tetapi slot 5→6 NOT consecutive (lunch break).

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

**Rule**: `curriculum_semester` adalah metadata akademik, bukan penentu konflik.

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

**Critical**: Ini yang menentukan student conflict, bukan `curriculum_semester`.

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

Buat Python dataclass/pydantic models untuk setiap entity:
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
  [6,7,8,9]   # valid
  # [3,4,5,6] INVALID (crosses lunch break)
]
```

### 2.3 Create Decision Variables

For each course, scheduler determines:
- `day` (MONDAY - SATURDAY)
- `start_slot` (from valid consecutive blocks)
- `room` (from available rooms matching room_type_required)

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

If infeasible:
```json
{
  "status": "INFEASIBLE",
  "message": "No valid schedule found"
}
```

### 2.6 Create scheduler.py CLI

```bash
python scheduler.py
```

Output:
```
Loading data...
Courses: 50
Student groups: 15
Lecturers: 10
Rooms: 8

Building constraints...
Solving...

Status: FEASIBLE
Solve time: 2.31 seconds
```

---

## Phase 3 — Testing & Validation

**Goal**: Test scheduler correctness dengan unit test, integration test, dan schedule validator.

### 3.1 Unit Tests for Constraints

#### Test 1: Lecturer Conflict
```python
# 2 courses, 1 lecturer
# Expected: courses tidak overlap
```

#### Test 2: Room Conflict
```python
# 2 courses, 1 room
# Expected: courses tidak overlap
```

#### Test 3: Student Group Conflict
```python
# MK001 → IF-3
# MK002 → IF-3
# Expected: tidak overlap
```

#### Test 4: Different Student Groups
```python
# MK001 → IF-3
# MK002 → BD-3
# Expected: BOLEH overlap
```

#### Test 5: Cross-Semester Conflict
```python
# MK001 → IF-3, IF-5
# MK002 → IF-5
# Expected: tidak overlap (karena sama-sama attended by IF-5)
```

#### Test 6: Consecutive Slots for 4 SKS
```python
# Valid: [1,2,3,4] or [6,7,8,9]
# Invalid: [3,4,5,6] (crosses lunch break)
```

#### Test 7: Lecturer Availability
```python
# Lecturer A available Wednesday only
# Course assigned to Lecturer A
# Expected: harus scheduled on Wednesday
```

#### Test 8: Room Type Requirement
```python
# Course requires COMPUTER_LAB
# Expected: assigned to LAB01 (type=COMPUTER_LAB), not R501 (CLASSROOM)
```

### 3.2 Build Independent Schedule Validator (validate_schedule.py)

Setelah scheduler generate jadwal, validasi ulang secara independen:

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

Buat dataset realistis:
- 50 courses
- 10 lecturers
- 8 rooms
- 15 student groups
- 6 days
- 9 slots

Run scheduler dan catat:
- Solve time
- Status (FEASIBLE/INFEASIBLE)

### 3.4 Test Infeasible Scenario

Buat skenario yang sengaja tidak mungkin:
```
1 room
1 lecturer
10 courses × 4 SKS each
Only Monday-Friday, slot 1-4 available
```

Expected: `INFEASIBLE`

### 3.5 Benchmark Table

Hasil run nyata: `python tests/benchmark.py` (seed deterministik `SSEED = 20261003`,
validator independen meng-**VALID**ate setiap hasil FEASIBLE).
Solver timeout 120s. Dataset di-generate dengan load balancing
(lecturer/group paling ringan diprioritaskan) supaya tidak ada hotspot kapasitas.

| Courses | Lecturers | Rooms | Constraints | Solve Time | Status   | Valid  |
|---------|-----------|-------|-------------|------------|----------|--------|
| 10      | 5         | 4     | 8,248       | 0.69s      | FEASIBLE | VALID  |
| 25      | 8         | 6     | 91,749      | 8.66s      | FEASIBLE | VALID  |
| 50      | 12        | 8     | 488,612     | 131.30s    | FEASIBLE | VALID  |
| 80      | 16        | 8     | 1,397,302   | 165.08s    | UNKNOWN  | -      |

Catatan:
- 80 courses = **UNKNOWN** karena kena solver timeout 120s (1.4 juta constraint).
  Bukan INFEASIBLE — capacity check (`tests/diagnose_bench.py`) menunjukkan semua
  lecturer/group/room load masih di bawah batas. Naikkan `max_time_in_seconds`
  di `src/scheduler.py` bila perlu.
- Constraint count tumbuh ~kuadratik terhadap jumlah courses (room conflict
  pairwise).

---

## Phase 4 — Database & API (Future)

**Not started yet.** Akan dilakukan setelah Phase 1-3 stabil.

Goals:
- Migrate JSON data → PostgreSQL
- Build FastAPI endpoints
- Integrate scheduler engine dengan database

---

## Phase 5 — Dashboard/UI (Future)

**Not started yet.** Akan dilakukan setelah Phase 4 stabil.

Goals:
- React/Next.js dashboard
- CRUD untuk courses, lecturers, rooms, student groups
- Trigger scheduler via UI
- Visualize schedule output

---

## Current Status

**Phase**: Phase 1 (Setup)
**Next**: Create project structure and define JSON data files

---

## Notes

- **DO NOT** skip Phase 1-3 and jump to database/UI
- Scheduler engine harus berdiri sendiri dan testable tanpa database
- Fokus: correctness first, optimization later
- Soft constraints belum diimplementasikan (future work)
