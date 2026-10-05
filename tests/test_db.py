"""
Phase 4: SQLite data layer tests (TASKS.md 4.1 + 4.2).

Gate: data/ loads identically from JSON and SQL, so the engine suite passes
against BOTH backends.

Run: python tests/test_db.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import db
from src.data_loader import SchedulerData

COMPARE_LISTS = (
    "time_slots", "courses", "student_groups", "lecturers", "rooms",
    "course_enrollments", "teaching_assignments", "lecturer_availability",
)


def make_conn() -> "sqlite3.Connection":
    tmp = Path(tempfile.mkdtemp(prefix="skelas_test_")) / "test.db"
    conn = db.connect(tmp)
    db.seed_from_json(conn, str(ROOT / "data"))
    return conn


def load_json(name: str) -> list:
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


class TestSeed(unittest.TestCase):
    def setUp(self):
        self.conn = make_conn()

    def tearDown(self):
        self.conn.close()

    def test_row_counts_match_json(self):
        expected = {
            "courses": len(load_json("courses.json")),
            "student_groups": len(load_json("student_groups.json")),
            "lecturers": len(load_json("lecturers.json")),
            "rooms": len(load_json("rooms.json")),
            "time_slots": len(load_json("time_slots.json")),
            "course_enrollments": sum(
                max(1, len(e["student_groups"]))  # empty -> NULL marker row
                for e in load_json("course_enrollments.json")),
        }
        for table, n in expected.items():
            self.assertEqual(db._count(self.conn, table), n, table)

    def test_seed_is_idempotent(self):
        first = db._count(self.conn, "courses")
        db.seed_from_json(self.conn, str(ROOT / "data"))
        self.assertEqual(db._count(self.conn, "courses"), first)

    def test_invalid_data_rejected(self):
        empty = Path(tempfile.mkdtemp(prefix="skelas_empty_"))
        conn = db.connect(empty / "test.db")
        try:
            with self.assertRaises(ValueError):
                db.seed_from_json(conn, str(empty))
        finally:
            conn.close()


class TestJsonSqlParity(unittest.TestCase):
    """TASKS.md 4.2 gate: both backends produce identical SchedulerData."""

    @classmethod
    def setUpClass(cls):
        cls.json_data = SchedulerData(str(ROOT / "data"))
        cls.conn = make_conn()
        cls.sql_data = SchedulerData(conn=cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_lists_identical(self):
        for name in COMPARE_LISTS:
            want, got = getattr(self.json_data, name), getattr(self.sql_data, name)
            if name == "teaching_assignments":
                # JSON keeps legacy lecturer_id='D001'; SQL stores the
                # normalized form. Consumers only read all_lecturer_ids, so
                # compare through that property instead of raw fields.
                want = [(t.course_id, t.all_lecturer_ids, t.needs_review)
                        for t in want]
                got = [(t.course_id, t.all_lecturer_ids, t.needs_review)
                       for t in got]
            self.assertEqual(want, got, f"{name} differs between JSON and SQL")

    def test_lookup_maps_identical(self):
        self.assertEqual(self.json_data.course_dict, self.sql_data.course_dict)
        self.assertEqual(self.json_data.course_to_groups,
                         self.sql_data.course_to_groups)
        self.assertEqual(self.json_data.course_to_lecturer,
                         self.sql_data.course_to_lecturer)
        self.assertEqual(self.json_data.lecturer_to_availability,
                         self.sql_data.lecturer_to_availability)


class TestCrud(unittest.TestCase):
    def setUp(self):
        self.conn = make_conn()

    def tearDown(self):
        self.conn.close()

    def test_create_and_delete_lecturer(self):
        errs = db.create_entity(
            self.conn, "lecturers", {"id": "D999", "name": "Dr. Uji"})
        self.assertEqual(errs, [])
        self.assertIsNotNone(self.conn.execute(
            "SELECT 1 FROM lecturers WHERE id = 'D999'").fetchone())
        self.assertEqual(db.delete_entity(self.conn, "lecturers", "D999"), 1)
        self.assertEqual(db.delete_entity(self.conn, "lecturers", "D999"), 0)

    def test_create_validation_errors_in_bahasa(self):
        errs = db.create_entity(
            self.conn, "courses",
            {"id": "X1", "code": "X1", "name": "X", "credits": 9,
             "curriculum_semester": 3, "room_type_required": "CLASSROOM"})
        self.assertTrue(any("2-4" in e for e in errs), errs)
        errs = db.create_entity(
            self.conn, "courses", {"id": "X2", "code": "X2", "name": ""})
        self.assertTrue(any("wajib diisi" in e for e in errs), errs)

    def test_duplicate_pk_rejected(self):
        errs = db.create_entity(
            self.conn, "lecturers", {"id": "D001", "name": "Duplikat"})
        self.assertTrue(errs and "integritas" in errs[0])

    def test_assignment_requires_existing_fk(self):
        errs = db.add_assignment(self.conn, "COURSE-NOT-THERE", ["D001"])
        self.assertTrue(errs and "tidak ditemukan" in errs[0])


class TestSchedulePersistence(unittest.TestCase):
    def setUp(self):
        self.conn = make_conn()

    def tearDown(self):
        self.conn.close()

    def test_save_and_load_roundtrip(self):
        from src.scheduler import CourseScheduler

        result = CourseScheduler(SchedulerData(conn=self.conn)).schedule()
        run_id = db.save_run(self.conn, result)
        self.assertGreater(run_id, 0)

        latest = db.load_latest(self.conn)
        self.assertEqual(latest["id"], run_id)
        self.assertEqual(latest["status"], result.status)
        self.assertEqual(len(latest["schedule"]), len(result.schedule))
        self.assertEqual(len(latest["dropped"]), len(result.dropped or []))

        # entries decode back to the same shape the engine produced
        for got, want in zip(latest["schedule"], result.schedule):
            self.assertEqual(got["course_id"], want["course_id"])
            self.assertEqual(got["day"], want["day"])
            self.assertEqual(got["start_slot"], want["start_slot"])
            self.assertEqual(got["student_groups"], want.get("student_groups"))
            self.assertEqual(got["lecturer_ids"], want.get("lecturer_ids"))

    def test_load_latest_empty(self):
        self.assertIsNone(db.load_latest(self.conn))


if __name__ == "__main__":
    unittest.main(verbosity=2)
