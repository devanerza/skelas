"""
Data loader for scheduling system

Two interchangeable sources (TASKS.md 4.2):
    SchedulerData("data")          -> JSON files (default, test/seed source)
    SchedulerData(conn=<sqlite3>)  -> SQL tables via src.db
Engine and validators only ever read through the lookup maps below, so the
source swap leaves CourseScheduler untouched.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional


class SchedulerData:
    def __init__(self, data_dir: str = "data", conn=None):
        if conn is not None:
            from .db import load_scheduler_data
            d = load_scheduler_data(conn)
            self.time_slots = d["time_slots"]
            self.courses = d["courses"]
            self.student_groups = d["student_groups"]
            self.lecturers = d["lecturers"]
            self.rooms = d["rooms"]
            self.course_enrollments = d["course_enrollments"]
            self.teaching_assignments = d["teaching_assignments"]
            self.lecturer_availability = d["lecturer_availability"]
        else:
            self.data_dir = Path(data_dir)
            self.time_slots = self._load_time_slots()
            self.courses = self._load_courses()
            self.student_groups = self._load_student_groups()
            self.lecturers = self._load_lecturers()
            self.rooms = self._load_rooms()
            self.course_enrollments = self._load_course_enrollments()
            self.teaching_assignments = self._load_teaching_assignments()
            self.lecturer_availability = self._load_lecturer_availability()

        # Build lookup dicts
        self.course_dict = {c.id: c for c in self.courses}
        self.lecturer_dict = {l.id: l for l in self.lecturers}
        self.room_dict = {r.id: r for r in self.rooms}
        self.student_group_dict = {sg.id: sg for sg in self.student_groups}

        # Build enrollment and assignment maps
        self.course_to_groups = {ce.course_id: ce.student_groups for ce in self.course_enrollments}
        # course -> list of lecturer ids; repeated course_id rows merge into one list
        self.course_to_lecturer: Dict[str, List[str]] = {}
        for ta in self.teaching_assignments:
            self.course_to_lecturer.setdefault(ta.course_id, []).extend(ta.all_lecturer_ids)
        self.lecturer_to_availability = {la.lecturer_id: la.availability for la in self.lecturer_availability}

    def _load_json(self, filename: str) -> List[Dict]:
        with open(self.data_dir / filename, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _load_time_slots(self):
        from .models import TimeSlot
        return [TimeSlot(**ts) for ts in self._load_json('time_slots.json')]

    def _load_courses(self):
        from .models import Course
        return [Course(**c) for c in self._load_json('courses.json')]

    def _load_student_groups(self):
        from .models import StudentGroup
        return [StudentGroup(**sg) for sg in self._load_json('student_groups.json')]

    def _load_lecturers(self):
        from .models import Lecturer
        return [Lecturer(**l) for l in self._load_json('lecturers.json')]

    def _load_rooms(self):
        from .models import Room
        return [Room(**r) for r in self._load_json('rooms.json')]

    def _load_course_enrollments(self):
        from .models import CourseEnrollment
        return [CourseEnrollment(**ce) for ce in self._load_json('course_enrollments.json')]

    def _load_teaching_assignments(self):
        from .models import TeachingAssignment
        return [TeachingAssignment(**ta) for ta in self._load_json('teaching_assignments.json')]

    def _load_lecturer_availability(self):
        from .models import LecturerAvailability
        return [LecturerAvailability(**la) for la in self._load_json('lecturer_availability.json')]

    def get_course_student_groups(self, course_id: str) -> List[str]:
        return self.course_to_groups.get(course_id, [])

    def get_course_lecturer(self, course_id: str) -> Optional[str]:
        lecturers = self.get_course_lecturers(course_id)
        return lecturers[0] if lecturers else None

    def get_course_lecturers(self, course_id: str) -> List[str]:
        return self.course_to_lecturer.get(course_id, [])

    def get_lecturer_availability(self, lecturer_id: str) -> Dict[str, List[int]]:
        return self.lecturer_to_availability.get(lecturer_id, {})

    def get_compatible_rooms(self, room_type: str):
        return [r for r in self.rooms if r.type == room_type]
