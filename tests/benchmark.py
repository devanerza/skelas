"""
Phase 3: benchmark scheduler on generated realistic datasets (TASKS.md 3.3/3.5).

Deterministic (fixed seed). Generates N courses across IF/BD/TL groups,
runs the scheduler, then re-validates every result with the independent
validator.

Run: python tests/benchmark.py
"""
import io
import json
import random
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data_loader import SchedulerData
from src.scheduler import CourseScheduler, DAYS
from validate_schedule import ScheduleValidator

PROGRAMS = ["IF", "BD", "TL"]
SEMESTERS = [1, 3, 5, 7]
SLOTS = [
    {"slot": 1, "start": "08:15", "end": "09:00"},
    {"slot": 2, "start": "09:00", "end": "09:45"},
    {"slot": 3, "start": "09:45", "end": "10:30"},
    {"slot": 4, "start": "10:30", "end": "11:15"},
    {"slot": 5, "start": "11:15", "end": "12:00"},
    {"slot": 6, "start": "13:00", "end": "13:45"},
    {"slot": 7, "start": "13:45", "end": "14:30"},
    {"slot": 8, "start": "14:30", "end": "15:15"},
    {"slot": 9, "start": "15:15", "end": "16:00"},
]
SSEED = 20261003


def generate_dataset(n_courses: int, n_lecturers: int, n_rooms: int):
    """Deterministic realistic dataset in a temp dir."""
    rng = random.Random(SSEED + n_courses)
    tmp = Path(tempfile.mkdtemp(prefix=f"bench_{n_courses}_"))

    groups = [{"id": f"{p}-{s}", "program": p, "cohort": 2026 - s, "semester": s}
              for p in PROGRAMS for s in SEMESTERS]

    # Always include both lab types; rest are classrooms
    room_types = ["CLASSROOM"] * max(1, n_rooms - 2) + ["COMPUTER_LAB", "LOGISTICS_LAB"]
    rooms = [{"id": f"R{i}", "name": f"Ruang {i}", "type": t, "capacity": 40}
             for i, t in enumerate(room_types[:n_rooms])]

    lecturers = [{"id": f"D{i:03d}", "name": f"Lecturer {i}"}
                 for i in range(n_lecturers)]
    # Every lecturer: >=2 full days (so 4-SKS always possible) + extra
    # morning-only / afternoon-only days (realistic, non-trivial)
    availability = []
    for lec in lecturers:
        days = rng.sample(DAYS, k=rng.randint(4, 6))
        full_days = days[:2]
        extra_days = days[2:]
        avail = {d: list(range(1, 10)) for d in full_days}
        for day in extra_days:
            avail[day] = (list(range(1, 6)) if rng.random() < 0.5
                          else list(range(6, 10)))
        availability.append({"lecturer_id": lec["id"], "availability": avail})

    courses, enrollments, assignments = [], [], []
    lab_courses = max(1, n_courses // 10)
    # Greedy load balancing so no lecturer / group gets overloaded
    # (random assignment created hotspots exceeding the 54-slot capacity)
    group_load = {g["id"]: 0 for g in groups}
    lec_load = {l["id"]: 0 for l in lecturers}
    for i in range(n_courses):
        cid = f"MK{i:03d}"
        room_type = "COMPUTER_LAB" if i < lab_courses else "CLASSROOM"
        credits = rng.choice([2, 3, 3, 4])
        courses.append({
            "id": cid, "code": f"X{100 + i}", "name": f"Course {i}",
            "curriculum_semester": rng.choice(SEMESTERS),
            "credits": credits,
            "room_type_required": room_type,
        })
        # 1-3 groups, always the least-loaded ones
        n_g = rng.randint(1, 3)
        picks = sorted(groups, key=lambda g: group_load[g["id"]])[:n_g]
        for g in picks:
            group_load[g["id"]] += credits
        enrollments.append({"course_id": cid,
                            "student_groups": [g["id"] for g in picks]})
        lec = min(lecturers, key=lambda l: lec_load[l["id"]])
        lec_load[lec["id"]] += credits
        assignments.append({"course_id": cid, "lecturer_id": lec["id"]})

    files = {
        "time_slots.json": SLOTS,
        "courses.json": courses,
        "student_groups.json": groups,
        "lecturers.json": lecturers,
        "rooms.json": rooms,
        "course_enrollments.json": enrollments,
        "teaching_assignments.json": assignments,
        "lecturer_availability.json": availability,
    }
    for name, content in files.items():
        (tmp / name).write_text(json.dumps(content), encoding="utf-8")
    return tmp


def run_bench(n_courses, n_lecturers, n_rooms):
    data_dir = generate_dataset(n_courses, n_lecturers, n_rooms)
    data = SchedulerData(str(data_dir))

    out = io.StringIO()
    with redirect_stdout(out):
        result = CourseScheduler(data).schedule()

    m = re.search(r"Total constraints: (\d+)", out.getvalue())
    n_constraints = int(m.group(1)) if m else 0

    valid = "-"
    if result.status == "FEASIBLE":
        with redirect_stdout(io.StringIO()):
            ok = ScheduleValidator(data, result.schedule).validate()
        valid = "VALID" if ok else "INVALID"

    return result, valid, n_constraints


def main():
    print(f"{'Courses':>8} {'Lect':>5} {'Rooms':>5} {'Constr':>7} {'Time':>8} "
          f"{'Status':>11} {'Valid':>7}")
    print("-" * 60)

    scenarios = [
        (10, 5, 4),
        (25, 8, 6),
        (50, 12, 8),
        (80, 16, 8),
    ]
    rows = []
    for n_c, n_l, n_r in scenarios:
        result, valid, n_constr = run_bench(n_c, n_l, n_r)
        print(f"{n_c:>8} {n_l:>5} {n_r:>5} {n_constr:>7} {result.solve_time:>7.2f}s "
              f"{result.status:>11} {valid:>7}")
        rows.append((n_c, n_l, n_r, n_constr, result, valid))
        if result.status not in ("FEASIBLE", "INFEASIBLE"):
            print(f"  !! {result.message}")

    return rows


if __name__ == "__main__":
    main()
