# Project Context — Academic Course Scheduling System

## 1. Project Overview

Build a backend scheduling engine for generating university course schedules automatically based on multiple constraints.

The problem is an academic timetabling / constraint satisfaction problem (CSP). The system should find a valid combination of:

- course
- lecturer
- student group
- day
- consecutive time slots
- room

while satisfying hard constraints and, later, potentially optimizing soft constraints.

The project is intended to solve a real university scheduling problem, not merely generate random timetable data.

---

# 2. Academic Context

The current scheduling context consists of:

- 3 study programs:
  - Informatics (IF)
  - Digital Business (BD)
  - Logistics Engineering (TL)

- Multiple student cohorts/semesters, currently including:
  - Semester 1
  - Semester 3
  - Semester 5
  - Semester 7

The reference timetable contains classrooms and laboratories such as:

- Kelas 501
- Kelas 502
- Kelas 503
- Kelas 504
- Kelas 505
- Kelas 506
- Lab Komputer
- Lab Logistik

The reference timetable has 9 daily time slots:

1. 08:15–09:00
2. 09:00–09:45
3. 09:45–10:30
4. 10:30–11:15
5. 11:15–12:00
6. 13:00–13:45
7. 13:45–14:30
8. 14:30–15:15
9. 15:15–16:00

Days:

- Monday
- Tuesday
- Wednesday
- Thursday
- Friday
- Saturday

---

# 3. Important Distinction: Course Semester vs Student Semester

The number shown next to a course in the existing timetable (e.g. 1, 3, 5, 7) represents the COURSE'S CURRICULUM SEMESTER, not the number of credits.

For example:

    Artificial Intelligence
    curriculum semester = 5

does NOT mean:

    credits = 5

Credits are a separate property of a course.

A course normally has 2–4 SKS/credits.

Important:

A course belonging to semester 5 may be taken by a semester 3 student.

A course belonging to semester 7 may be taken by a semester 5 student.

Therefore, the scheduler MUST NOT determine timetable conflicts simply by comparing course semester values.

The actual student groups/cohorts affected by a course determine whether two courses conflict.

Example:

    Course A
    curriculum semester = 3
    student groups = IF-3

    Course B
    curriculum semester = 5
    student groups = IF-3, IF-5

Course A and Course B conflict because both are attended by IF-3, even though their curriculum semesters differ.

---

# 4. Credits / SKS Rule

Credits determine the duration of a course.

Rule:

    1 SKS = 1 timetable slot

Therefore:

    2 SKS = 2 consecutive slots
    3 SKS = 3 consecutive slots
    4 SKS = 4 consecutive slots

A course's slots MUST be consecutive.

Example for a 4-SKS course:

    08:15–09:00
    09:00–09:45
    09:45–10:30
    10:30–11:15

Valid.

This is NOT valid:

    08:15–09:00
    09:00–09:45
    09:45–10:30
    13:00–13:45

because the slots are not consecutive.

A course also cannot be split across different days.

Therefore, a course is treated by the scheduler as one continuous block of N consecutive slots.

---

# 5. Course Data

Each course should conceptually contain:

- course ID
- course code
- course name
- curriculum semester
- credits/SKS
- assigned lecturer(s)
- target student groups
- room requirements/capability requirements

Example:

    Course:
        Sistem Basis Data

    curriculum_semester:
        3

    credits:
        3

    student_groups:
        IF-3
        BD-3

The curriculum semester is informational/academic metadata.

The student groups are what matter for timetable conflict detection.

---

# 6. Student Groups

Student groups/cohorts should be modeled independently.

A student group may be identified by:

- study program
- cohort/semester

Examples:

    IF-3
    IF-5
    BD-3
    BD-5
    TL-5
    TL-7

A course may target:

- one student group
- multiple groups from the same program
- multiple programs
- all programs
- groups from different semesters

---

# 7. Cross-Program Courses

The system MUST support courses attended by multiple study programs.

Examples:

    Course X
    → IF-5
    → BD-5

or:

    Course Y
    → IF-5
    → BD-5
    → TL-5

This means the course is one scheduling block, but multiple student groups must be considered when checking conflicts.

---

# 8. All-Program Courses

The system MUST support courses intended for all programs.

For example:

    Pancasila
    → IF
    → BD
    → TL

or another university-wide course.

The scheduler should treat all relevant student groups as participants in the same course block.

---

# 9. Cross-Semester / Additional-Credit Courses

The system MUST support students taking courses outside their normal curriculum semester.

Example:

    Course:
        Artificial Intelligence

    curriculum semester:
        5

    enrolled/target groups:
        IF-3
        IF-5

The scheduler must therefore use actual course-to-student-group relationships rather than assuming:

    curriculum semester == student semester

---

# 10. Lecturer Data

Each lecturer should contain:

- lecturer ID
- name
- availability

Availability must support restrictions such as:

    Lecturer A → Wednesday only
    Lecturer B → Tuesday only
    Lecturer C → Monday–Thursday

Preferably availability should be granular enough to support time ranges, e.g.:

    Wednesday:
        08:15–12:00

rather than only storing a list of allowed days.

---

# 11. Room Data

Each room should contain:

- room ID
- room name
- room type/capability
- capacity (if needed)
- availability (if applicable)

Examples:

    Kelas 501
    Kelas 502
    ...
    Lab Komputer
    Lab Logistik

Room capability matters because certain courses may require a specific type of room.

Example:

    Programming course
    → requires computer lab

    Logistics practical course
    → requires logistics lab

---

# 12. Time Slot Data

Time should be represented as discrete slots, not arbitrary datetime values.

Each slot should conceptually contain:

- slot ID
- day
- slot number
- start time
- end time

The scheduler uses:

    day + start_slot + course_duration

to generate a candidate timetable block.

For a 3-SKS course:

    Monday + slot 2
    →
    slots 2, 3, 4

For a 4-SKS course:

    Monday + slot 2
    →
    slots 2, 3, 4, 5

---

# 13. Teaching Assignment

Do not assume that a course permanently belongs to exactly one lecturer.

The system should conceptually support a teaching assignment relationship:

    Course
        ↓
    Lecturer
        ↓
    Student Groups

This allows cases where:

- different lecturers teach different groups
- a course has multiple classes
- teaching assignments change between semesters

---

# 14. Hard Constraints

Hard constraints MUST NEVER be violated in a valid generated schedule.

Initial hard constraints:

### 14.1 Lecturer conflict

A lecturer cannot teach two courses at overlapping times.

    Lecturer A
    Monday 08:15–10:30
    Course X

Therefore:

    Lecturer A
    Monday 08:15–10:30
    Course Y

is invalid.

### 14.2 Student group conflict

A student group cannot have two courses at overlapping times.

Example:

    IF-3
    Monday 08:15–10:30
    Course A

Therefore another course attended by IF-3 cannot occupy those slots.

This applies even if the two courses have different curriculum semesters.

### 14.3 Room conflict

A room cannot host two courses at the same time.

### 14.4 Lecturer availability

A course cannot be scheduled outside its lecturer's availability.

Example:

    Lecturer A → Wednesday only

Course taught by Lecturer A:

    Tuesday → invalid
    Wednesday → potentially valid

### 14.5 Room requirement

A course requiring a particular room type/capability must be assigned to a compatible room.

### 14.6 Course duration

A course must occupy exactly N consecutive slots where:

    N = course credits

### 14.7 Same-day continuity

A course cannot be split across multiple days.

---

# 14A. Constraint Encoding (CP-SAT Implementation)

Hard constraints 14.1-14.3 (lecturer, student group, room conflict) MUST be
encoded using CP-SAT native `AddNoOverlap` on interval variables, NOT pairwise
bool-clause encoding.

### Timeline model

Absolute time:

    T = day * 10 + offset(slot)

Where:

    slot s (1-9) -> offset s-1   (0..8)
    no reserved lunch-break unit (classes/lecturers handle break times)

One day = 10 timeline units, one week = 60 units. A course with N credits
becomes ONE interval `[start, start + N)` on this shared timeline.

### Encoding per constraint

- **Lecturer conflict (14.1)**: one interval per course, grouped by lecturer
  → `AddNoOverlap([...])`
- **Student group conflict (14.2)**: same interval, grouped by student group
  → `AddNoOverlap([...])`
- **Room conflict (14.3)**: one OPTIONAL interval per (course, compatible room),
  presence bool linked to the course's room assignment variable
  → `AddNoOverlap([...])` per room

### Why not pairwise

Pairwise encoding (compare every course pair's day + block + room through
bool clauses) explodes: O(n²) pairs × several clauses each. Measured on the
benchmark (see TASKS.md section 3.5): 80 courses → 1,397,302 constraints
pairwise vs 5,648 with `AddNoOverlap`. The pairwise version timed out
(UNKNOWN); the native version returns FEASIBLE + VALID.

`AddNoOverlap` is handled by CP-SAT's dedicated interval propagator — stronger
propagation and far fewer clauses than hand-built bool encoding.

---

# 15. Soft Constraints

Soft constraints are preferences rather than absolute restrictions.

They may be introduced after the basic scheduler works.

Potential examples:

- lecturer preferred days
- lecturer preferred time ranges
- minimize large gaps between courses for a student group
- avoid excessive teaching load in one day
- avoid undesirable time slots
- distribute courses more evenly across the week

Soft constraints should NOT make a schedule invalid.

Instead, they can contribute penalties/costs to candidate schedules.

Example:

    Schedule A:
        hard violations = 0
        soft penalty = 5

    Schedule B:
        hard violations = 0
        soft penalty = 15

Schedule A would be preferable from an optimization perspective, without declaring B invalid.

---

# 16. No-Solution / Edge Case Handling

The scheduler MUST NOT assume that a valid schedule always exists.

There may be cases where constraints make scheduling impossible.

Example:

    Lecturer A
    → available only Wednesday

    Lecturer A teaches:
    Course A = 4 slots
    Course B = 4 slots

    Wednesday available capacity:
    6 slots

No feasible schedule exists.

**Implemented behavior — partial scheduling**: instead of returning nothing,
the system ALWAYS produces and shows a schedule by skipping the specific
infeasible courses. Every course has a reified `sched` boolean; the objective
maximizes `sum(sched)` first, so the solver itself selects the smallest set
of courses to skip:

- all courses scheduled → status `FEASIBLE`
- some scheduled → status `PARTIAL` — schedule is shown, then a skipped
  section listing each dropped course with a concrete reason (which
  lecturer/group/room is saturated, or missing room type / too-tight
  availability), naming lecturers and courses by NAME
- none scheduled → status `INFEASIBLE` with a diagnosis

Per-course diagnosis is computed statically from the data: valid
(day, block) options vs. occupied slots of the scheduled entries, room-type
availability, lecturer free-slot load. Full-model diagnosis (`diagnose()`)
covers lecturer load vs availability (with a solver probe), student-group
load vs weekly slots, and room capacity vs demand — each finding names the
offending entity and the data file to edit.

Example:

    Jadwal parsial: 54 dari 58 mata kuliah terjadwal, 4 dilewati

    DILEWATI (tidak feasible):
      Penjaminan Mutu Perangkat Lunak
        Alasan: Dosen X sudah penuh di semua slot tersedia oleh mata
        kuliah yang terjadwal

---

# 17. Constraint Relaxation

A future version may support relaxing soft or configurable constraints when no solution exists.

Example:

    Level 1:
    all hard constraints + all preferences

    ↓ no solution

    Level 2:
    relax lecturer preference

    ↓ no solution

    Level 3:
    allow alternative room

    ↓ solution found

The system should clearly tell the user which constraint/preference was relaxed.

Hard constraints such as student conflicts, lecturer conflicts, and room conflicts should remain protected unless the system explicitly supports an administrator override.

---

# 18. Scheduling Problem Classification

This project should be treated as:

    Constraint Satisfaction / Constraint Optimization Problem

The problem is:

- deterministic
- observable
- discrete
- combinatorial
- constrained by many interdependent variables

The system does NOT require machine learning or an LLM.

The relevant AI/computational approach is search/optimization/constraint programming.

Potential approaches include:

- Constraint Programming
- CP-SAT
- heuristic search
- optimization techniques

Do NOT assume A*, Genetic Algorithm, or LLM is mandatory.

The implementation should choose an appropriate constraint-solving approach based on the actual requirements.

---

# 19. Scheduler Input

At minimum, the scheduling engine needs:

    Courses
    Lecturers
    Lecturer availability
    Student groups
    Course → student group relationships
    Teaching assignments
    Rooms
    Room capabilities
    Room availability (if needed)
    Time slots
    Hard constraints
    Soft constraints (optional initially)

---

# 20. Scheduler Output

A generated schedule entry should conceptually contain:

    course
    lecturer
    student groups
    room
    day
    start slot
    end slot

Example:

    Course:
        Sistem Basis Data

    Lecturer:
        Lecturer A

    Student Groups:
        IF-3, BD-3

    Room:
        Lab Komputer

    Day:
        Wednesday

    Slots:
        1–3

    Time:
        08:15–10:30

Top-level result:

    status:  FEASIBLE | PARTIAL | INFEASIBLE | UNKNOWN
    solve_time
    schedule: [entry ...]
    dropped:  [ {course_id, course_code, course_name, reason} ... ]
             (only non-empty for PARTIAL — the skipped courses)

---

# 21. Recommended Development Strategy

Do NOT start by building the complete dashboard/application.

Start with the scheduling engine and a small deterministic dataset.

Phase 1:

- define data structures
- create sample courses
- create sample student groups
- create lecturers + availability
- create rooms
- create time slots
- implement hard constraints
- generate valid schedules
- detect conflicts
- return infeasible result when no solution exists

Phase 2:

- cross-program courses
- all-program courses
- cross-semester courses
- multiple teaching assignments
- room capabilities
- more realistic dataset

Phase 3:

- soft constraints
- optimization
- conflict explanation
- constraint relaxation
- import/export
- API
- dashboard/UI

The scheduler engine should remain independent from the UI.

---

# 22. Important Design Principle

The most important conceptual rule is:

    Course curriculum semester
        ≠
    Student semester
        ≠
    Course credits

And:

    Course credits
        → determines duration

    Student groups
        → determine student conflict

    Lecturer
        → determines lecturer conflict/availability

    Room
        → determines room conflict/capability

    Day + start slot
        → determines the candidate timetable position

This separation should be preserved throughout the database design, backend logic, and scheduling algorithm.