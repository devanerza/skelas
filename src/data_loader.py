"""
Data loader for scheduling system
"""
import json
from pathlib import Path
from typing import Dict, List
from .models import (
    Course, StudentGroup, Lecturer, Room, TimeSlot,
    CourseEnrollment, TeachingAssignment, LecturerAvailability
)


class SchedulerData:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        
        # Load all data
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
        self.course_to_lecturer = {ta.course_id: ta.lecturer_id for ta in self.teaching_assignments}
        self.lecturer_to_availability = {la.lecturer_id: la.availability for la in self.lecturer_availability}
    
    def _load_json(self, filename: str) -> List[Dict]:
        with open(self.data_dir / filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _load_time_slots(self) -> List[TimeSlot]:
        data = self._load_json('time_slots.json')
        return [TimeSlot(**ts) for ts in data]
    
    def _load_courses(self) -> List[Course]:
        data = self._load_json('courses.json')
        return [Course(**c) for c in data]
    
    def _load_student_groups(self) -> List[StudentGroup]:
        data = self._load_json('student_groups.json')
        return [StudentGroup(**sg) for sg in data]
    
    def _load_lecturers(self) -> List[Lecturer]:
        data = self._load_json('lecturers.json')
        return [Lecturer(**l) for l in data]
    
    def _load_rooms(self) -> List[Room]:
        data = self._load_json('rooms.json')
        return [Room(**r) for r in data]
    
    def _load_course_enrollments(self) -> List[CourseEnrollment]:
        data = self._load_json('course_enrollments.json')
        return [CourseEnrollment(**ce) for ce in data]
    
    def _load_teaching_assignments(self) -> List[TeachingAssignment]:
        data = self._load_json('teaching_assignments.json')
        return [TeachingAssignment(**ta) for ta in data]
    
    def _load_lecturer_availability(self) -> List[LecturerAvailability]:
        data = self._load_json('lecturer_availability.json')
        return [LecturerAvailability(**la) for la in data]
    
    def get_course_student_groups(self, course_id: str) -> List[str]:
        return self.course_to_groups.get(course_id, [])
    
    def get_course_lecturer(self, course_id: str) -> str:
        return self.course_to_lecturer.get(course_id)
    
    def get_lecturer_availability(self, lecturer_id: str) -> Dict[str, List[int]]:
        return self.lecturer_to_availability.get(lecturer_id, {})
    
    def get_compatible_rooms(self, room_type: str) -> List[Room]:
        return [r for r in self.rooms if r.type == room_type]
