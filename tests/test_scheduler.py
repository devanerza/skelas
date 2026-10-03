"""
Phase 3: Unit tests for scheduler hard constraints (TASKS.md 3.1 + 3.4).

Run: python tests/test_scheduler.py
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data_loader import SchedulerData
from src.scheduler import CourseScheduler
from src.utils import generate_consecutive_blocks, slots_overlap

# Default 9 daily slots (matches data/time_slots.json)
DEFAULT_SLOTS = [
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


def course(cid: str, credits: int = 2, room_type: str = "CLASSROOM") -> dict:
    return {
        "id": cid,
        "code": cid,
        "name": f"Course {cid}",
        "curriculum_semester": 3,
        "credits": credits,
        "room_type_required": room_type,
    }


def make_data(courses, enrollments, assignments, availability,
              groups=None, rooms=None, lecturers=None) -> SchedulerData:
    """Write a fixture dataset to a temp dir and load it through the real loader."""
    tmp = tempfile.mkdtemp(prefix="sched_test_")
    files = {
        "time_slots.json": DEFAULT_SLOTS,
        "courses.json": courses,
        "student_groups": groups if groups is not None else [
            {"id": "IF-3", "program": "IF", "cohort": 2023, "semester": 3},
            {"id": "IF-5", "program": "IF", "cohort": 2022, "semester": 5},
            {"id": "BD-3", "program": "BD", "cohort": 2023, "semester": 3},
        ],
        "lecturers.json": lecturers if lecturers is not None else [
            {"id": "D001", "name": "Dr. A"},
            {"id": "D002", "name": "Dr. B"},
            {"id": "D003", "name": "Dr. C"},
        ],
        "rooms.json": rooms if rooms is not None else [
            {"id": "R1", "name": "Ruang 1", "type": "CLASSROOM", "capacity": 40},
            {"id": "R2", "name": "Ruang 2", "type": "CLASSROOM", "capacity": 40},
        ],
        "course_enrollments.json": enrollments,
        "teaching_assignments.json": assignments,
        "lecturer_availability.json": availability,
    }
    # student_groups key needs .json extension
    files["student_groups.json"] = files.pop("student_groups")
    for name, content in files.items():
        (Path(tmp) / name).write_text(json.dumps(content), encoding="utf-8")
    return SchedulerData(tmp)


def run_scheduler(data: SchedulerData):
    with redirect_stdout(io.StringIO()):
        return CourseScheduler(data).schedule()


def entry(schedule, cid: str) -> dict:
    return next(e for e in schedule if e["course_id"] == cid)


def slots(e: dict) -> list:
    return list(range(e["start_slot"], e["end_slot"] + 1))


def overlap(schedule, c1: str, c2: str) -> bool:
    e1, e2 = entry(schedule, c1), entry(schedule, c2)
    if e1["day"] != e2["day"]:
        return False
    return slots_overlap(slots(e1), slots(e2))


# Tight fixture: both lecturers available MONDAY slots 1-3 ONLY.
# 2-SKS courses then have only blocks [1,2] / [2,3] -> any two of them
# MUST overlap in time. So if a conflict constraint is missing, the solver
# happily returns FEASIBLE-with-overlap; tests below catch exactly that.
MON_SLOTS_1_3 = {"MONDAY": [1, 2, 3]}


class TestLecturerConflict(unittest.TestCase):
    """14.1: one lecturer cannot teach two overlapping courses."""

    def test_same_lecturer_courses_do_not_overlap(self):
        data = make_data(
            courses=[course("C1"), course("C2")],
            enrollments=[
                {"course_id": "C1", "student_groups": ["IF-3"]},
                {"course_id": "C2", "student_groups": ["BD-3"]},
            ],
            assignments=[
                {"course_id": "C1", "lecturer_id": "D001"},
                {"course_id": "C2", "lecturer_id": "D001"},
            ],
            availability=[{"lecturer_id": "D001", "availability": MON_SLOTS_1_3}],
        )
        result = run_scheduler(data)
        # Tight window: impossible to fit 2+2 slots without overlap -> INFEASIBLE
        # with the constraint, FEASIBLE+overlap without it. Never allow the latter.
        if result.status == "FEASIBLE":
            self.assertFalse(overlap(result.schedule, "C1", "C2"),
                             "Lecturer taught two overlapping courses")


class TestRoomConflict(unittest.TestCase):
    """14.3: one room cannot host two courses at the same time."""

    def test_single_room_courses_do_not_overlap(self):
        data = make_data(
            courses=[course("C1"), course("C2")],
            enrollments=[
                {"course_id": "C1", "student_groups": ["IF-3"]},
                {"course_id": "C2", "student_groups": ["BD-3"]},
            ],
            assignments=[
                {"course_id": "C1", "lecturer_id": "D001"},
                {"course_id": "C2", "lecturer_id": "D002"},
            ],
            availability=[
                {"lecturer_id": "D001", "availability": MON_SLOTS_1_3},
                {"lecturer_id": "D002", "availability": MON_SLOTS_1_3},
            ],
            rooms=[{"id": "R1", "name": "Ruang 1", "type": "CLASSROOM", "capacity": 40}],
        )
        result = run_scheduler(data)
        if result.status == "FEASIBLE":
            self.assertFalse(overlap(result.schedule, "C1", "C2"),
                             "Two courses hosted in the same room at once")


class TestStudentGroupConflict(unittest.TestCase):
    """14.2: a shared student group forbids overlap."""

    def test_same_group_courses_do_not_overlap(self):
        data = make_data(
            courses=[course("C1"), course("C2")],
            enrollments=[
                {"course_id": "C1", "student_groups": ["IF-3"]},
                {"course_id": "C2", "student_groups": ["IF-3"]},
            ],
            assignments=[
                {"course_id": "C1", "lecturer_id": "D001"},
                {"course_id": "C2", "lecturer_id": "D002"},
            ],
            availability=[
                {"lecturer_id": "D001", "availability": MON_SLOTS_1_3},
                {"lecturer_id": "D002", "availability": MON_SLOTS_1_3},
            ],
        )
        result = run_scheduler(data)
        if result.status == "FEASIBLE":
            self.assertFalse(overlap(result.schedule, "C1", "C2"),
                             "Shared student group attended two overlapping courses")


class TestDifferentGroupsAllowed(unittest.TestCase):
    """Different groups: overlap MUST be allowed (TASKS Test 4)."""

    def test_different_groups_may_overlap(self):
        data = make_data(
            courses=[course("C1"), course("C2")],
            enrollments=[
                {"course_id": "C1", "student_groups": ["IF-3"]},
                {"course_id": "C2", "student_groups": ["BD-3"]},
            ],
            assignments=[
                {"course_id": "C1", "lecturer_id": "D001"},
                {"course_id": "C2", "lecturer_id": "D002"},
            ],
            availability=[
                {"lecturer_id": "D001", "availability": MON_SLOTS_1_3},
                {"lecturer_id": "D002", "availability": MON_SLOTS_1_3},
            ],
        )
        result = run_scheduler(data)
        self.assertEqual(result.status, "FEASIBLE")
        # Tight window forces overlap -> proves student conflict is NOT applied
        # across disjoint groups
        self.assertTrue(overlap(result.schedule, "C1", "C2"),
                        "Different groups were wrongly forbidden from overlapping")


class TestCrossSemesterConflict(unittest.TestCase):
    """14.2: conflict decided by enrolled groups, never curriculum semester."""

    def test_shared_group_across_different_semesters_conflicts(self):
        data = make_data(
            courses=[course("C1"), course("C2")],
            enrollments=[
                # C1 spans semester 3+5 cohorts, C2 only semester 5
                {"course_id": "C1", "student_groups": ["IF-3", "IF-5"]},
                {"course_id": "C2", "student_groups": ["IF-5"]},
            ],
            assignments=[
                {"course_id": "C1", "lecturer_id": "D001"},
                {"course_id": "C2", "lecturer_id": "D002"},
            ],
            availability=[
                {"lecturer_id": "D001", "availability": MON_SLOTS_1_3},
                {"lecturer_id": "D002", "availability": MON_SLOTS_1_3},
            ],
        )
        result = run_scheduler(data)
        if result.status == "FEASIBLE":
            self.assertFalse(overlap(result.schedule, "C1", "C2"),
                             "IF-5 attended two overlapping courses")


class TestConsecutiveSlots(unittest.TestCase):
    """14.6/14.7: N SKS = N consecutive slots, no lunch-break crossing."""

    def test_four_sks_blocks(self):
        self.assertEqual(
            generate_consecutive_blocks(4),
            [[1, 2, 3, 4], [2, 3, 4, 5], [6, 7, 8, 9]],
        )

    def test_no_block_crosses_lunch_break(self):
        for credits in (2, 3, 4):
            for block in generate_consecutive_blocks(credits):
                self.assertFalse({5, 6}.issubset(block),
                                 f"Block {block} crosses lunch break")
                self.assertEqual(block, list(range(block[0], block[0] + credits)),
                                 f"Block {block} not consecutive")

    def test_course_duration_equals_credits(self):
        data = make_data(
            courses=[course("C1", credits=4)],
            enrollments=[{"course_id": "C1", "student_groups": ["IF-3"]}],
            assignments=[{"course_id": "C1", "lecturer_id": "D001"}],
            availability=[{"lecturer_id": "D001",
                           "availability": {"MONDAY": [1, 2, 3, 4, 5]}}],
        )
        result = run_scheduler(data)
        self.assertEqual(result.status, "FEASIBLE")
        e = entry(result.schedule, "C1")
        self.assertEqual(len(slots(e)), 4, "4-SKS course must occupy 4 slots")


class TestLecturerAvailability(unittest.TestCase):
    """14.4: course cannot leave lecturer's availability window."""

    def test_course_scheduled_on_available_day_only(self):
        data = make_data(
            courses=[course("C1")],
            enrollments=[{"course_id": "C1", "student_groups": ["IF-3"]}],
            assignments=[{"course_id": "C1", "lecturer_id": "D003"}],
            availability=[{"lecturer_id": "D003",
                           "availability": {"WEDNESDAY": [1, 2, 3, 4, 5, 6, 7, 8, 9]}}],
        )
        result = run_scheduler(data)
        self.assertEqual(result.status, "FEASIBLE")
        self.assertEqual(entry(result.schedule, "C1")["day"], "WEDNESDAY",
                         "Course scheduled outside lecturer availability")

    def test_lunch_gap_not_available_even_if_lecturer_free(self):
        # Lecturer free only slot 5 + slot 6 -> no valid 2-SKS block exists
        data = make_data(
            courses=[course("C1")],
            enrollments=[{"course_id": "C1", "student_groups": ["IF-3"]}],
            assignments=[{"course_id": "C1", "lecturer_id": "D003"}],
            availability=[{"lecturer_id": "D003",
                           "availability": {"MONDAY": [5, 6]}}],
        )
        result = run_scheduler(data)
        self.assertEqual(result.status, "INFEASIBLE",
                         "5+6 are not consecutive, no valid block exists")


class TestRoomRequirement(unittest.TestCase):
    """14.5: course requiring a lab gets a lab room."""

    def test_lab_course_assigned_to_lab_room(self):
        data = make_data(
            courses=[course("C1", room_type="COMPUTER_LAB")],
            enrollments=[{"course_id": "C1", "student_groups": ["IF-3"]}],
            assignments=[{"course_id": "C1", "lecturer_id": "D001"}],
            availability=[{"lecturer_id": "D001",
                           "availability": {"MONDAY": [1, 2, 3, 4, 5, 6, 7, 8, 9]}}],
            rooms=[
                {"id": "R1", "name": "Ruang 1", "type": "CLASSROOM", "capacity": 40},
                {"id": "LAB01", "name": "Lab Komputer", "type": "COMPUTER_LAB", "capacity": 30},
            ],
        )
        result = run_scheduler(data)
        self.assertEqual(result.status, "FEASIBLE")
        room_name = entry(result.schedule, "C1")["room"]
        assigned = next(r for r in data.rooms if r.name == room_name)
        self.assertEqual(assigned.type, "COMPUTER_LAB",
                         "LAB-required course landed in a non-lab room")


class TestInfeasibleScenario(unittest.TestCase):
    """3.4: deliberately impossible dataset -> INFEASIBLE, not a crash."""

    def test_overloaded_lecturer_single_room_is_infeasible(self):
        # 10 courses x 4 SKS = 40 slots needed,
        # capacity = 1 room x (Mon-Fri, slots 1-4 -> one valid block/day) = 5
        courses = [course(f"C{i:02d}", credits=4) for i in range(10)]
        enrollments = [{"course_id": c["id"], "student_groups": ["IF-3"]}
                       for c in courses]
        assignments = [{"course_id": c["id"], "lecturer_id": "D001"}
                       for c in courses]
        availability = [{"lecturer_id": "D001",
                         "availability": {
                             d: [1, 2, 3, 4]
                             for d in ("MONDAY", "TUESDAY", "WEDNESDAY",
                                       "THURSDAY", "FRIDAY")}}]
        data = make_data(
            courses=courses,
            enrollments=enrollments,
            assignments=assignments,
            availability=availability,
            rooms=[{"id": "R1", "name": "Ruang 1",
                    "type": "CLASSROOM", "capacity": 40}],
        )
        result = run_scheduler(data)
        self.assertEqual(result.status, "INFEASIBLE",
                         "Expected no feasible schedule for this scenario")


if __name__ == "__main__":
    unittest.main(verbosity=2)
