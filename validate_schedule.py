#!/usr/bin/env python3
"""
Independent schedule validator (TASKS.md 3.2).

Re-checks a generated schedule against ALL hard constraints using pure
Python only — never trusts the solver.

Usage:
    python validate_schedule.py schedule.json [--data data]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.data_loader import SchedulerData
from src.utils import slots_overlap

DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]


def entry_slots(entry) -> list:
    return list(range(entry["start_slot"], entry["end_slot"] + 1))


class ScheduleValidator:
    def __init__(self, data: SchedulerData, schedule: list, dropped: list | None = None):
        self.data = data
        self.schedule = schedule
        self.dropped_ids = {d["course_id"] for d in (dropped or [])}
        self.errors: list[str] = []

    def fail(self, check: str, msg: str):
        self.errors.append(f"[{check}] {msg}")

    def _overlapping_pairs(self, key_of) -> list:
        """Yield (entry, entry) pairs sharing key_of() and overlapping in time."""
        groups = {}
        for e in self.schedule:
            for key in key_of(e):
                groups.setdefault(key, []).append(e)

        pairs, seen = [], set()
        for key, entries in groups.items():
            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    e1, e2 = entries[i], entries[j]
                    if e1 is e2 or e1["day"] != e2["day"]:
                        continue
                    if slots_overlap(entry_slots(e1), entry_slots(e2)):
                        sig = tuple(sorted((e1["course_id"], e2["course_id"])))
                        if sig not in seen:
                            seen.add(sig)
                            pairs.append((key, e1, e2))
        return pairs

    @staticmethod
    def _entry_lecturers(e) -> list:
        # team teaching: check each co-lecturer; fall back to legacy string key
        return e.get("lecturer_ids") or [e["lecturer"]]

    def check_lecturer_conflicts(self) -> bool:
        """14.1: lecturer cannot teach two courses at overlapping times."""
        ok = True
        for name, e1, e2 in self._overlapping_pairs(self._entry_lecturers):
            self.fail("lecturer",
                      f"{name}: {e1['course_code']} and {e2['course_code']} "
                      f"overlap on {e1['day']}")
            ok = False
        return ok

    def check_room_conflicts(self) -> bool:
        """14.3: room cannot host two courses at the same time."""
        ok = True
        for room, e1, e2 in self._overlapping_pairs(lambda e: [e["room"]]):
            self.fail("room",
                      f"{room}: {e1['course_code']} and {e2['course_code']} "
                      f"overlap on {e1['day']}")
            ok = False
        return ok

    def check_student_conflicts(self) -> bool:
        """14.2: student group cannot attend two courses at once."""
        ok = True
        for group, e1, e2 in self._overlapping_pairs(
                lambda e: e["student_groups"]):
            self.fail("student",
                      f"{group}: {e1['course_code']} and {e2['course_code']} "
                      f"overlap on {e1['day']}")
            ok = False
        return ok

    def check_consecutive_credits(self) -> bool:
        """14.6/14.7: N SKS = N consecutive slots."""
        ok = True
        for e in self.schedule:
            course = self.data.course_dict[e["course_id"]]
            sl = entry_slots(e)
            if len(sl) != course.credits:
                self.fail("credits",
                          f"{e['course_code']}: {course.credits} SKS but "
                          f"{len(sl)} slots")
                ok = False
            if sl != list(range(sl[0], sl[0] + len(sl))):
                self.fail("consecutive",
                          f"{e['course_code']}: slots {sl} not consecutive")
                ok = False
        return ok

    def check_lecturer_availability(self) -> bool:
        """14.4: course must sit inside EVERY co-lecturer's availability."""
        ok = True
        for e in self.schedule:
            for lecturer_id in self.data.get_course_lecturers(e["course_id"]):
                availability = self.data.get_lecturer_availability(lecturer_id)
                if not availability:
                    continue  # unrestricted
                lecturer_name = self.data.lecturer_dict[lecturer_id].name
                if e["day"] not in availability:
                    self.fail("availability",
                              f"{e['course_code']}: {lecturer_name} unavailable "
                              f"on {e['day']}")
                    ok = False
                    continue
                free = set(availability[e["day"]])
                missing = set(entry_slots(e)) - free
                if missing:
                    self.fail("availability",
                              f"{e['course_code']}: {lecturer_name} unavailable "
                              f"slots {sorted(missing)}")
                    ok = False
        return ok

    def check_room_requirements(self) -> bool:
        """14.5: room capability must match course requirement."""
        ok = True
        room_by_name = {r.name: r for r in self.data.rooms}
        for e in self.schedule:
            course = self.data.course_dict[e["course_id"]]
            room = room_by_name.get(e["room"])
            if room is None:
                self.fail("room_type", f"{e['course_code']}: unknown room "
                                       f"{e['room']!r}")
                ok = False
            elif room.type != course.room_type_required:
                self.fail("room_type",
                          f"{e['course_code']} needs "
                          f"{course.room_type_required}, got {room.type} "
                          f"({e['room']})")
                ok = False
        return ok

    def check_all_courses_scheduled(self) -> bool:
        """Every course appears exactly once (except declared drops), valid day."""
        ok = True
        seen = [e["course_id"] for e in self.schedule]
        for course in self.data.courses:
            count = seen.count(course.id)
            if count == 0:
                if course.id not in self.dropped_ids:
                    self.fail("coverage", f"{course.code} not scheduled")
                    ok = False
            elif count > 1:
                self.fail("coverage", f"{course.code} scheduled {count} times")
                ok = False
        for e in self.schedule:
            if e["day"] not in DAYS:
                self.fail("day", f"{e['course_code']}: invalid day {e['day']}")
                ok = False
            if not (1 <= e["start_slot"] <= e["end_slot"] <= 9):
                self.fail("day",
                          f"{e['course_code']}: slots "
                          f"{e['start_slot']}-{e['end_slot']} out of 1-9")
                ok = False
        return ok

    def validate(self) -> bool:
        checks = [
            ("Checking lecturer conflicts...", self.check_lecturer_conflicts),
            ("Checking room conflicts...", self.check_room_conflicts),
            ("Checking student conflicts...", self.check_student_conflicts),
            ("Checking consecutive credits...", self.check_consecutive_credits),
            ("Checking lecturer availability...", self.check_lecturer_availability),
            ("Checking room requirements...", self.check_room_requirements),
            ("Checking all courses scheduled...", self.check_all_courses_scheduled),
        ]
        all_ok = True
        for label, fn in checks:
            ok = fn()
            print(f"{label} {'✓' if ok else '✗'}")
            all_ok = all_ok and ok
        return all_ok


def main(argv) -> int:
    if len(argv) < 2:
        print(__doc__.strip())
        return 2

    schedule_path = Path(argv[1])
    data_dir = "data"
    if "--data" in argv:
        data_dir = argv[argv.index("--data") + 1]

    if not schedule_path.exists():
        print(f"Schedule file not found: {schedule_path}")
        return 2

    data = SchedulerData(data_dir)
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))

    print(f"Validating {len(schedule)} entries against {len(data.courses)} "
          f"courses...\n")
    validator = ScheduleValidator(data, schedule)
    ok = validator.validate()

    if ok:
        print("\nSchedule is VALID.")
        return 0

    print("\nSchedule is INVALID:")
    for err in validator.errors:
        print(f"  - {err}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
