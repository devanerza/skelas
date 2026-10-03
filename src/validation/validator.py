import json
from pathlib import Path
from typing import List, Dict, Tuple
from ..models import (
    Course, StudentGroup, Lecturer, Room, TimeSlot,
    CourseEnrollment, TeachingAssignment, LecturerAvailability
)


class DataValidator:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.errors = []
        self.warnings = []
    
    def load_json(self, filename: str):
        try:
            with open(self.data_dir / filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.errors.append(f"Failed to load {filename}: {e}")
            return None
    
    def validate_all(self) -> Tuple[bool, List[str], List[str]]:
        self.errors = []
        self.warnings = []
        
        time_slots_data = self.load_json('time_slots.json')
        courses_data = self.load_json('courses.json')
        student_groups_data = self.load_json('student_groups.json')
        course_enrollments_data = self.load_json('course_enrollments.json')
        lecturers_data = self.load_json('lecturers.json')
        teaching_assignments_data = self.load_json('teaching_assignments.json')
        rooms_data = self.load_json('rooms.json')
        lecturer_availability_data = self.load_json('lecturer_availability.json')
        
        if None in [time_slots_data, courses_data, student_groups_data, 
                    course_enrollments_data, lecturers_data, 
                    teaching_assignments_data, rooms_data, lecturer_availability_data]:
            return False, self.errors, self.warnings
        
        time_slots = [TimeSlot(**ts) for ts in time_slots_data]
        courses = [Course(**c) for c in courses_data]
        student_groups = [StudentGroup(**sg) for sg in student_groups_data]
        course_enrollments = [CourseEnrollment(**ce) for ce in course_enrollments_data]
        lecturers = [Lecturer(**l) for l in lecturers_data]
        teaching_assignments = [TeachingAssignment(**ta) for ta in teaching_assignments_data]
        rooms = [Room(**r) for r in rooms_data]
        lecturer_availability = [LecturerAvailability(**la) for la in lecturer_availability_data]
        
        self._validate_time_slots(time_slots)
        self._validate_courses(courses)
        self._validate_student_groups(student_groups)
        self._validate_course_enrollments(course_enrollments, courses, student_groups)
        self._validate_lecturers(lecturers)
        self._validate_teaching_assignments(teaching_assignments, courses, lecturers)
        self._validate_rooms(rooms)
        self._validate_lecturer_availability(lecturer_availability, lecturers, time_slots)
        
        return len(self.errors) == 0, self.errors, self.warnings
    
    def _validate_time_slots(self, time_slots: List[TimeSlot]):
        if not time_slots:
            self.errors.append("No time slots defined")
            return
        
        slots = [ts.slot for ts in time_slots]
        if len(slots) != len(set(slots)):
            self.errors.append("Duplicate slot numbers found")
        
        for ts in time_slots:
            if ts.slot < 1 or ts.slot > 9:
                self.errors.append(f"Invalid slot number: {ts.slot}. Must be 1-9")
    
    def _validate_courses(self, courses: List[Course]):
        if not courses:
            self.errors.append("No courses defined")
            return
        
        course_ids = [c.id for c in courses]
        if len(course_ids) != len(set(course_ids)):
            self.errors.append("Duplicate course IDs found")
        
        valid_room_types = ["CLASSROOM", "COMPUTER_LAB", "LOGISTICS_LAB"]
        
        for course in courses:
            if course.credits < 2 or course.credits > 4:
                self.errors.append(f"Course {course.id} has invalid credits: {course.credits}. Must be 2-4")
            
            if course.room_type_required not in valid_room_types:
                self.errors.append(f"Course {course.id} has invalid room type: {course.room_type_required}")
    
    def _validate_student_groups(self, student_groups: List[StudentGroup]):
        if not student_groups:
            self.errors.append("No student groups defined")
            return
        
        group_ids = [sg.id for sg in student_groups]
        if len(group_ids) != len(set(group_ids)):
            self.errors.append("Duplicate student group IDs found")
    
    def _validate_course_enrollments(self, enrollments: List[CourseEnrollment], 
                                     courses: List[Course], student_groups: List[StudentGroup]):
        course_ids = {c.id for c in courses}
        group_ids = {sg.id for sg in student_groups}
        enrolled_courses = set()
        
        for enrollment in enrollments:
            if enrollment.course_id not in course_ids:
                self.errors.append(f"Enrollment references non-existent course: {enrollment.course_id}")
            
            enrolled_courses.add(enrollment.course_id)
            
            for group in enrollment.student_groups:
                if group not in group_ids:
                    self.errors.append(f"Enrollment references non-existent student group: {group}")
        
        unenrolled = course_ids - enrolled_courses
        if unenrolled:
            self.warnings.append(f"Courses without enrollments: {', '.join(unenrolled)}")
    
    def _validate_lecturers(self, lecturers: List[Lecturer]):
        if not lecturers:
            self.errors.append("No lecturers defined")
            return
        
        lecturer_ids = [l.id for l in lecturers]
        if len(lecturer_ids) != len(set(lecturer_ids)):
            self.errors.append("Duplicate lecturer IDs found")
    
    def _validate_teaching_assignments(self, assignments: List[TeachingAssignment],
                                       courses: List[Course], lecturers: List[Lecturer]):
        course_ids = {c.id for c in courses}
        lecturer_ids = {l.id for l in lecturers}
        assigned_courses = set()
        
        for assignment in assignments:
            if assignment.course_id not in course_ids:
                self.errors.append(f"Assignment references non-existent course: {assignment.course_id}")
            
            if assignment.lecturer_id not in lecturer_ids:
                self.errors.append(f"Assignment references non-existent lecturer: {assignment.lecturer_id}")
            
            assigned_courses.add(assignment.course_id)
        
        unassigned = course_ids - assigned_courses
        if unassigned:
            self.errors.append(f"Courses without lecturer assignment: {', '.join(unassigned)}")
    
    def _validate_rooms(self, rooms: List[Room]):
        if not rooms:
            self.errors.append("No rooms defined")
            return
        
        room_ids = [r.id for r in rooms]
        if len(room_ids) != len(set(room_ids)):
            self.errors.append("Duplicate room IDs found")
    
    def _validate_lecturer_availability(self, availabilities: List[LecturerAvailability],
                                        lecturers: List[Lecturer], time_slots: List[TimeSlot]):
        lecturer_ids = {l.id for l in lecturers}
        valid_slots = {ts.slot for ts in time_slots}
        valid_days = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]
        
        for avail in availabilities:
            if avail.lecturer_id not in lecturer_ids:
                self.errors.append(f"Availability references non-existent lecturer: {avail.lecturer_id}")
            
            for day, slots in avail.availability.items():
                if day not in valid_days:
                    self.errors.append(f"Invalid day in availability: {day}")
                
                for slot in slots:
                    if slot not in valid_slots:
                        self.errors.append(f"Invalid slot {slot} in availability for lecturer {avail.lecturer_id}")
