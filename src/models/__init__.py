from dataclasses import dataclass
from typing import List, Dict


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
    lecturer_id: str


@dataclass
class LecturerAvailability:
    lecturer_id: str
    availability: Dict[str, List[int]]
