"""SQLite data layer (Phase 4).

Schema mirrors data/*.json (ARCHITECTURE.md §3.5). JSON files stay the seed
source: seed_from_json() runs DataValidator first, wipes the tables, then
inserts — array columns (student_groups, lecturer_ids, availability) are
split into join rows.
"""
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from .models import (
    Course, StudentGroup, Lecturer, Room, TimeSlot,
    CourseEnrollment, TeachingAssignment, LecturerAvailability
)

DEFAULT_DB = Path(__file__).resolve().parent.parent / "skelas.db"

VALID_ROOM_TYPES = ("CLASSROOM", "COMPUTER_LAB", "LOGISTICS_LAB")
VALID_DAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY")

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    curriculum_semester INTEGER NOT NULL,
    credits INTEGER NOT NULL CHECK (credits BETWEEN 2 AND 4),
    room_type_required TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS student_groups (
    id TEXT PRIMARY KEY,
    program TEXT NOT NULL,
    cohort INTEGER NOT NULL,
    semester INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS lecturers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rooms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    capacity INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS time_slots (
    slot INTEGER PRIMARY KEY CHECK (slot BETWEEN 1 AND 9),
    start TEXT NOT NULL,
    "end" TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS course_enrollments (
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    group_id TEXT REFERENCES student_groups(id) ON DELETE CASCADE,  -- NULL = course with no groups
    PRIMARY KEY (course_id, group_id)
);
CREATE TABLE IF NOT EXISTS teaching_assignments (
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    lecturer_id TEXT NOT NULL REFERENCES lecturers(id) ON DELETE CASCADE,
    needs_review INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (course_id, lecturer_id)
);
CREATE TABLE IF NOT EXISTS lecturer_availability (
    lecturer_id TEXT NOT NULL REFERENCES lecturers(id) ON DELETE CASCADE,
    day TEXT NOT NULL,
    slot INTEGER NOT NULL CHECK (slot BETWEEN 1 AND 9),
    PRIMARY KEY (lecturer_id, day, slot)
);
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL,
    solve_time REAL NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS schedule_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    course_code TEXT NOT NULL,
    course_name TEXT NOT NULL,
    lecturer TEXT NOT NULL DEFAULT '',
    lecturer_ids TEXT NOT NULL DEFAULT '[]',
    student_groups TEXT NOT NULL DEFAULT '[]',
    room TEXT NOT NULL,
    day TEXT NOT NULL,
    start_slot INTEGER NOT NULL,
    end_slot INTEGER NOT NULL,
    time TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS schedule_dropped (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    course_code TEXT NOT NULL,
    course_name TEXT NOT NULL,
    reason TEXT NOT NULL
);
"""

# table -> (columns, required fields, int fields)
ENTITY_SPECS = {
    "courses": (
        ("id", "code", "name", "curriculum_semester", "credits", "room_type_required"),
        ("id", "code", "name", "curriculum_semester", "credits", "room_type_required"),
        ("curriculum_semester", "credits"),
    ),
    "student_groups": (
        ("id", "program", "cohort", "semester"),
        ("id", "program", "cohort", "semester"),
        ("cohort", "semester"),
    ),
    "lecturers": (
        ("id", "name"),
        ("id", "name"),
        (),
    ),
    "rooms": (
        ("id", "name", "type", "capacity"),
        ("id", "name", "type", "capacity"),
        ("capacity",),
    ),
}


def connect(db_path=DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


# ---------------------------------------------------------------- migration

def seed_from_json(conn: sqlite3.Connection, data_dir="data") -> Dict[str, int]:
    """Wipe all tables and load data/*.json (validated first)."""
    from .validation.validator import DataValidator

    ok, errors, _ = DataValidator(str(data_dir)).validate_all()
    if not ok:
        raise ValueError("Data tidak valid:\n- " + "\n- ".join(errors))

    def load(name):
        return json.loads((Path(data_dir) / name).read_text(encoding="utf-8"))

    courses = load("courses.json")
    groups = load("student_groups.json")
    lecturers = load("lecturers.json")
    rooms = load("rooms.json")
    slots = load("time_slots.json")

    # One row per (course, group) in JSON order; JSON allows courses with an
    # empty student_groups list, so those become a (course, NULL) marker row
    # (plain JOINs ignore NULL, load_scheduler_data reads it as an empty list).
    enroll_rows = []
    for e in load("course_enrollments.json"):
        if not e["student_groups"]:
            enroll_rows.append((e["course_id"], None))
        for g in dict.fromkeys(e["student_groups"]):
            enroll_rows.append((e["course_id"], g))

    assign_rows = []
    for row in load("teaching_assignments.json"):
        ids = row.get("lecturer_ids") or (
            [row.get("lecturer_id")] if row.get("lecturer_id") else [])
        for lid in dict.fromkeys(ids):
            assign_rows.append(
                (row["course_id"], lid, 1 if row.get("needs_review") else 0))

    avail_rows = list(dict.fromkeys(
        (la["lecturer_id"], day, slot)
        for la in load("lecturer_availability.json")
        for day, slots in la["availability"].items()
        for slot in slots))

    with conn:
        for table in ("schedule_dropped", "schedule_entries", "schedules",
                      "course_enrollments", "teaching_assignments",
                      "lecturer_availability", "courses", "student_groups",
                      "lecturers", "rooms", "time_slots"):
            conn.execute(f"DELETE FROM {table}")

        conn.executemany(
            "INSERT INTO courses VALUES (:id, :code, :name, "
            ":curriculum_semester, :credits, :room_type_required)", courses)
        conn.executemany(
            "INSERT INTO student_groups VALUES (:id, :program, :cohort, :semester)",
            groups)
        conn.executemany("INSERT INTO lecturers VALUES (:id, :name)", lecturers)
        conn.executemany(
            "INSERT INTO rooms VALUES (:id, :name, :type, :capacity)", rooms)
        conn.executemany(
            "INSERT INTO time_slots VALUES (:slot, :start, :end)", slots)
        conn.executemany(
            "INSERT INTO course_enrollments VALUES (?, ?)", enroll_rows)
        conn.executemany(
            "INSERT INTO teaching_assignments VALUES (?, ?, ?)", assign_rows)
        conn.executemany(
            "INSERT INTO lecturer_availability VALUES (?, ?, ?)", avail_rows)

    # sanity: split rows survived intact
    counts = {t: _count(conn, t) for t in
              ("courses", "student_groups", "lecturers", "rooms", "time_slots",
               "course_enrollments", "teaching_assignments",
               "lecturer_availability")}
    expected = {
        "courses": len(courses), "student_groups": len(groups),
        "lecturers": len(lecturers), "rooms": len(rooms),
        "time_slots": len(slots), "course_enrollments": len(enroll_rows),
        "teaching_assignments": len(assign_rows),
        "lecturer_availability": len(avail_rows),
    }
    mismatch = {t: (expected[t], counts[t]) for t in expected
                if expected[t] != counts[t]}
    if mismatch:
        raise RuntimeError(f"Migrasi tidak konsisten (expected, actual): {mismatch}")
    return counts


def _count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ------------------------------------------------------------------ reading

def load_scheduler_data(conn: sqlite3.Connection) -> dict:
    """Rebuild the 8 dataclass lists from SQL (JSON order preserved via rowid)."""
    time_slots = [TimeSlot(slot=r["slot"], start=r["start"], end=r["end"])
                  for r in conn.execute("SELECT * FROM time_slots")]
    courses = [Course(id=r["id"], code=r["code"], name=r["name"],
                      curriculum_semester=r["curriculum_semester"],
                      credits=r["credits"],
                      room_type_required=r["room_type_required"])
               for r in conn.execute("SELECT * FROM courses")]
    groups = [StudentGroup(id=r["id"], program=r["program"],
                           cohort=r["cohort"], semester=r["semester"])
              for r in conn.execute("SELECT * FROM student_groups")]
    lecturers = [Lecturer(id=r["id"], name=r["name"])
                 for r in conn.execute("SELECT * FROM lecturers")]
    rooms = [Room(id=r["id"], name=r["name"], type=r["type"],
                  capacity=r["capacity"])
             for r in conn.execute("SELECT * FROM rooms")]

    enroll_map: Dict[str, List[str]] = {}
    for r in conn.execute("SELECT * FROM course_enrollments"):
        gids = enroll_map.setdefault(r["course_id"], [])
        if r["group_id"] is not None:  # NULL = explicitly empty list
            gids.append(r["group_id"])
    enrollments = [CourseEnrollment(course_id=cid, student_groups=gids)
                   for cid, gids in enroll_map.items()]

    assign_map: Dict[str, List[str]] = {}
    review_map: Dict[str, bool] = {}
    for r in conn.execute("SELECT * FROM teaching_assignments"):
        assign_map.setdefault(r["course_id"], []).append(r["lecturer_id"])
        if r["needs_review"]:
            review_map[r["course_id"]] = True
    assignments = [TeachingAssignment(course_id=cid, lecturer_ids=lids,
                                      needs_review=review_map.get(cid, False))
                   for cid, lids in assign_map.items()]

    avail_map: Dict[str, Dict[str, List[int]]] = {}
    for r in conn.execute("SELECT * FROM lecturer_availability"):
        avail_map.setdefault(r["lecturer_id"], {}).setdefault(
            r["day"], []).append(r["slot"])
    availability = [LecturerAvailability(lecturer_id=lid, availability=av)
                    for lid, av in avail_map.items()]

    return {
        "time_slots": time_slots, "courses": courses,
        "student_groups": groups, "lecturers": lecturers, "rooms": rooms,
        "course_enrollments": enrollments,
        "teaching_assignments": assignments,
        "lecturer_availability": availability,
    }


# -------------------------------------------------------------------- CRUD

def create_entity(conn, table: str, payload: dict) -> List[str]:
    """Insert one entity row. Returns error list ([] = success)."""
    if table not in ENTITY_SPECS:
        return [f"Unknown table: {table}"]
    cols, required, int_cols = ENTITY_SPECS[table]

    errors, values = [], {}
    for col in cols:
        val = payload.get(col)
        if col in required and val in (None, ""):
            errors.append(f"{col} wajib diisi")
            continue
        if col in int_cols and val not in (None, ""):
            try:
                val = int(val)
            except (TypeError, ValueError):
                errors.append(f"{col} harus angka")
                continue
        values[col] = val

    if table == "courses" and not errors:
        if not 2 <= values["credits"] <= 4:
            errors.append(f"credits harus 2-4, dapat {values['credits']}")
        if values["room_type_required"] not in VALID_ROOM_TYPES:
            errors.append(f"room_type_required salah: {values['room_type_required']}")
    if table == "rooms" and not errors and values["type"] not in VALID_ROOM_TYPES:
        errors.append(f"type salah: {values['type']}")
    if errors:
        return errors

    with conn:
        try:
            conn.execute(
                f"INSERT INTO {table} ({', '.join(cols)}) "
                f"VALUES ({', '.join('?' * len(cols))})",
                [values[c] for c in cols])
        except sqlite3.IntegrityError as e:
            return [f"Melanggar integritas data: {e}"]
    return []


def delete_entity(conn, table: str, pk: str) -> int:
    """Delete one entity row (join rows cascade). Returns rows deleted."""
    if table not in ENTITY_SPECS:
        return 0
    with conn:
        cur = conn.execute(f"DELETE FROM {table} WHERE id = ?", (pk,))
    return cur.rowcount


def list_entities(conn, table: str) -> List[dict]:
    if table not in ENTITY_SPECS:
        return []
    return [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]


# ------------------------------------------------------- relation writers

def add_enrollment(conn, course_id: str, group_ids: List[str]) -> List[str]:
    errors = _check_fk(conn, "courses", course_id, "mata kuliah")
    for gid in group_ids:
        errors += _check_fk(conn, "student_groups", gid, "kelompok")
    if errors:
        return errors
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO course_enrollments VALUES (?, ?)",
            [(course_id, g) for g in group_ids])
    return []


def add_assignment(conn, course_id: str, lecturer_ids: List[str],
                   needs_review: bool = False) -> List[str]:
    errors = _check_fk(conn, "courses", course_id, "mata kuliah")
    for lid in lecturer_ids:
        errors += _check_fk(conn, "lecturers", lid, "dosen")
    if errors:
        return errors
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO teaching_assignments VALUES (?, ?, ?)",
            [(course_id, lid, 1 if needs_review else 0)
             for lid in dict.fromkeys(lecturer_ids)])
    return []


def set_availability(conn, lecturer_id: str, availability: dict) -> List[str]:
    errors = _check_fk(conn, "lecturers", lecturer_id, "dosen")
    for day, slots in availability.items():
        if day not in VALID_DAYS:
            errors.append(f"Hari tidak valid: {day}")
        for slot in slots:
            if not isinstance(slot, int) or not 1 <= slot <= 9:
                errors.append(f"Slot tidak valid: {slot}")
    if errors:
        return errors
    rows = [(lecturer_id, day, slot)
            for day, slots in availability.items() for slot in slots]
    with conn:
        conn.execute("DELETE FROM lecturer_availability WHERE lecturer_id = ?",
                     (lecturer_id,))
        conn.executemany(
            "INSERT INTO lecturer_availability VALUES (?, ?, ?)", rows)
    return []


def _check_fk(conn, table: str, pk: str, label: str) -> List[str]:
    if conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (pk,)).fetchone():
        return []
    return [f"{label} tidak ditemukan: {pk}"]


# ------------------------------------------------------- schedule results

def save_run(conn, result) -> int:
    """Persist a ScheduleResult; returns the schedules.id."""
    with conn:
        cur = conn.execute(
            "INSERT INTO schedules (status, solve_time, message) VALUES (?, ?, ?)",
            (result.status, float(result.solve_time), result.message or ""))
        run_id = cur.lastrowid
        for e in result.schedule:
            conn.execute(
                "INSERT INTO schedule_entries (schedule_id, course_id, "
                "course_code, course_name, lecturer, lecturer_ids, "
                "student_groups, room, day, start_slot, end_slot, time) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, e.get("course_id", ""), e.get("course_code", ""),
                 e.get("course_name", ""), e.get("lecturer") or "",
                 json.dumps(e.get("lecturer_ids") or []),
                 json.dumps(e.get("student_groups") or []),
                 e.get("room", ""), e.get("day", ""),
                 e.get("start_slot"), e.get("end_slot"), e.get("time", "")))
        for d in (result.dropped or []):
            conn.execute(
                "INSERT INTO schedule_dropped (schedule_id, course_id, "
                "course_code, course_name, reason) VALUES (?, ?, ?, ?, ?)",
                (run_id, d.get("course_id", ""), d.get("course_code", ""),
                 d.get("course_name", ""), d.get("reason", "")))
    return run_id


def load_latest(conn) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM schedules ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return None

    entries = []
    for r in conn.execute(
            "SELECT * FROM schedule_entries WHERE schedule_id = ? "
            "ORDER BY id", (row["id"],)):
        e = dict(r)
        e["lecturer_ids"] = json.loads(e.pop("lecturer_ids"))
        e["student_groups"] = json.loads(e.pop("student_groups"))
        e.pop("id")
        e.pop("schedule_id")
        entries.append(e)

    dropped = [dict(r) for r in conn.execute(
        "SELECT course_id, course_code, course_name, reason "
        "FROM schedule_dropped WHERE schedule_id = ? ORDER BY id",
        (row["id"],))]

    return {
        "id": row["id"],
        "status": row["status"],
        "solve_time": row["solve_time"],
        "message": row["message"],
        "created_at": row["created_at"],
        "schedule": entries,
        "dropped": dropped,
    }
