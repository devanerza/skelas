from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class TimeSlot:
    slot: int
    start: str
    end: str


@dataclass
class Course:
    id: str
    code: str
    name: str
    curriculum_semester: int
    credits: int
    room_type_required: str


@dataclass
class StudentGroup:
    id: str
    program: str
    cohort: int
    semester: int


@dataclass
class Lecturer:
    id: str
    name: str


@dataclass
class Room:
    id: str
    name: str
    type: str
    capacity: int


@dataclass
class CourseEnrollment:
    course_id: str
    student_groups: List[str]


@dataclass
class TeachingAssignment:
    course_id: str
    lecturer_id: str = ""  # legacy single-lecturer field
    lecturer_ids: Optional[List[str]] = None  # team teaching: 1..N lecturers
    needs_review: bool = False  # flag: assignment not confirmed by user yet

    @property
    def all_lecturer_ids(self) -> List[str]:
        if self.lecturer_ids:
            return self.lecturer_ids
        return [self.lecturer_id] if self.lecturer_id else []


@dataclass
class LecturerAvailability:
    lecturer_id: str
    availability: Dict[str, List[int]]
