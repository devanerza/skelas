"""
Course Scheduling Engine using OR-Tools CP-SAT
"""
from ortools.sat.python import cp_model
from typing import Dict, List, Tuple, Optional
import time

from .data_loader import SchedulerData
from .utils import generate_consecutive_blocks


DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]


class ScheduleResult:
    def __init__(self, status: str, solve_time: float, schedule: List[Dict] = None, message: str = ""):
        self.status = status
        self.solve_time = solve_time
        self.schedule = schedule or []
        self.message = message


class CourseScheduler:
    def __init__(self, data: SchedulerData):
        self.data = data
        self.model = cp_model.CpModel()
        self.vars = {}
        
    def schedule(self) -> ScheduleResult:
        """Main scheduling function"""
        start_time = time.time()
        
        print("Building decision variables...")
        self._create_variables()
        
        print("Adding constraints...")
        self._add_consecutive_slot_constraints()
        
        print("  - Lecturer conflict constraints...")
        self._add_lecturer_conflict_constraints()
        
        print("  - Student group conflict constraints...")
        self._add_student_group_conflict_constraints()
        
        print("  - Room conflict constraints...")
        self._add_room_conflict_constraints()
        
        print("  - Lecturer availability constraints...")
        self._add_lecturer_availability_constraints()
        
        print("  - Room requirement constraints...")
        self._add_room_requirement_constraints()
        
        print(f"Total constraints: {len(self.model.Proto().constraints)}")
        print("Solving...")
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 60.0
        status = solver.Solve(self.model)
        
        solve_time = time.time() - start_time
        
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            schedule = self._extract_solution(solver)
            return ScheduleResult(
                status="FEASIBLE",
                solve_time=solve_time,
                schedule=schedule
            )
        elif status == cp_model.INFEASIBLE:
            return ScheduleResult(
                status="INFEASIBLE",
                solve_time=solve_time,
                message="No valid schedule found"
            )
        else:
            return ScheduleResult(
                status="UNKNOWN",
                solve_time=solve_time,
                message="Solver did not find a solution in time"
            )
    
    def _create_variables(self):
        """Create decision variables for each course"""
        for course in self.data.courses:
            course_id = course.id
            
            # Generate valid consecutive blocks for this course
            blocks = generate_consecutive_blocks(course.credits)
            
            # Get compatible rooms
            compatible_rooms = self.data.get_compatible_rooms(course.room_type_required)
            if not compatible_rooms:
                raise ValueError(f"No compatible rooms for course {course_id} requiring {course.room_type_required}")
            
            # Decision variables: day, start_slot_block_index, room
            self.vars[course_id] = {
                'day': self.model.NewIntVar(0, len(DAYS) - 1, f'{course_id}_day'),
                'block_idx': self.model.NewIntVar(0, len(blocks) - 1, f'{course_id}_block'),
                'room': self.model.NewIntVar(0, len(compatible_rooms) - 1, f'{course_id}_room'),
                'blocks': blocks,
                'rooms': compatible_rooms
            }
    
    def _add_consecutive_slot_constraints(self):
        """Consecutive slots are already enforced by block generation"""
        pass
    
    def _add_lecturer_conflict_constraints(self):
        """Lecturer cannot teach two courses at the same time"""
        # Group courses by lecturer
        lecturer_courses = {}
        for course in self.data.courses:
            lecturer_id = self.data.get_course_lecturer(course.id)
            if lecturer_id:
                if lecturer_id not in lecturer_courses:
                    lecturer_courses[lecturer_id] = []
                lecturer_courses[lecturer_id].append(course.id)
        
        # For each lecturer with multiple courses, ensure no conflicts
        for lecturer_id, course_ids in lecturer_courses.items():
            if len(course_ids) < 2:
                continue
            
            for i in range(len(course_ids)):
                for j in range(i + 1, len(course_ids)):
                    c1, c2 = course_ids[i], course_ids[j]
                    self._add_no_overlap_constraint(c1, c2)
    
    def _add_student_group_conflict_constraints(self):
        """Student group cannot attend two courses at the same time"""
        # Group courses by student group
        group_courses = {}
        for course in self.data.courses:
            groups = self.data.get_course_student_groups(course.id)
            for group in groups:
                if group not in group_courses:
                    group_courses[group] = []
                group_courses[group].append(course.id)
        
        # For each group with multiple courses, ensure no conflicts
        for group, course_ids in group_courses.items():
            if len(course_ids) < 2:
                continue
            
            for i in range(len(course_ids)):
                for j in range(i + 1, len(course_ids)):
                    c1, c2 = course_ids[i], course_ids[j]
                    self._add_no_overlap_constraint(c1, c2)
    
    def _add_room_conflict_constraints(self):
        """Room cannot host two courses at the same time"""
        # For each room, for each pair of courses that can use it:
        # If both assigned to this room AND same day -> blocks must not overlap
        
        room_courses = {}
        for course in self.data.courses:
            compatible_rooms = self.vars[course.id]['rooms']
            for room in compatible_rooms:
                room_id = room.id
                if room_id not in room_courses:
                    room_courses[room_id] = []
                room_courses[room_id].append(course.id)
        
        for room_id, course_ids in room_courses.items():
            if len(course_ids) < 2:
                continue
            
            for i in range(len(course_ids)):
                for j in range(i + 1, len(course_ids)):
                    c1, c2 = course_ids[i], course_ids[j]
                    
                    # Get room indices for this room
                    rooms1 = self.vars[c1]['rooms']
                    rooms2 = self.vars[c2]['rooms']
                    
                    idx1 = next(k for k, r in enumerate(rooms1) if r.id == room_id)
                    idx2 = next(k for k, r in enumerate(rooms2) if r.id == room_id)
                    
                    # c1 uses this room
                    c1_uses = self.model.NewBoolVar(f'{c1}_uses_{room_id}')
                    self.model.Add(self.vars[c1]['room'] == idx1).OnlyEnforceIf(c1_uses)
                    self.model.Add(self.vars[c1]['room'] != idx1).OnlyEnforceIf(c1_uses.Not())
                    
                    # c2 uses this room
                    c2_uses = self.model.NewBoolVar(f'{c2}_uses_{room_id}')
                    self.model.Add(self.vars[c2]['room'] == idx2).OnlyEnforceIf(c2_uses)
                    self.model.Add(self.vars[c2]['room'] != idx2).OnlyEnforceIf(c2_uses.Not())
                    
                    # Both use this room
                    both_use = self.model.NewBoolVar(f'{c1}_{c2}_both_{room_id}')
                    self.model.AddBoolAnd([c1_uses, c2_uses]).OnlyEnforceIf(both_use)
                    self.model.AddBoolOr([c1_uses.Not(), c2_uses.Not()]).OnlyEnforceIf(both_use.Not())
                    
                    # Same day
                    same_day = self.model.NewBoolVar(f'{c1}_{c2}_same_day_{room_id}')
                    self.model.Add(self.vars[c1]['day'] == self.vars[c2]['day']).OnlyEnforceIf(same_day)
                    self.model.Add(self.vars[c1]['day'] != self.vars[c2]['day']).OnlyEnforceIf(same_day.Not())
                    
                    # Blocks overlap
                    overlap = self.model.NewBoolVar(f'{c1}_{c2}_overlap_{room_id}')
                    self._add_overlap_check(c1, c2, overlap)
                    
                    # If both_use AND same_day -> NOT overlap
                    conflict = self.model.NewBoolVar(f'{c1}_{c2}_conflict_{room_id}')
                    self.model.AddBoolAnd([both_use, same_day, overlap]).OnlyEnforceIf(conflict)
                    self.model.Add(conflict == 0)  # Forbid conflict
    
    def _add_lecturer_availability_constraints(self):
        """Course can only be scheduled during lecturer's available time"""
        for course in self.data.courses:
            lecturer_id = self.data.get_course_lecturer(course.id)
            if not lecturer_id:
                continue
            
            availability = self.data.get_lecturer_availability(lecturer_id)
            if not availability:
                continue
            
            course_id = course.id
            blocks = self.vars[course_id]['blocks']
            
            # For each (day, block) combination, check if lecturer is available
            for day_idx, day_name in enumerate(DAYS):
                if day_name not in availability:
                    # Lecturer not available on this day
                    self.model.Add(self.vars[course_id]['day'] != day_idx)
                else:
                    available_slots = set(availability[day_name])
                    
                    # For each block, check if all slots are available
                    for block_idx, block in enumerate(blocks):
                        if not set(block).issubset(available_slots):
                            # This block not available on this day
                            is_this_day = self.model.NewBoolVar(f'{course_id}_day{day_idx}')
                            is_this_block = self.model.NewBoolVar(f'{course_id}_block{block_idx}')
                            
                            self.model.Add(self.vars[course_id]['day'] == day_idx).OnlyEnforceIf(is_this_day)
                            self.model.Add(self.vars[course_id]['block_idx'] == block_idx).OnlyEnforceIf(is_this_block)
                            
                            # Cannot be both this day and this block
                            self.model.AddBoolOr([is_this_day.Not(), is_this_block.Not()])
    
    def _add_room_requirement_constraints(self):
        """Course requiring specific room type gets compatible room"""
        # Already handled by filtering compatible rooms in _create_variables
        pass
    
    def _add_no_overlap_constraint(self, course1_id: str, course2_id: str):
        """Ensure two courses don't overlap in time (unconditional)"""
        # Different day OR different (non-overlapping) time blocks
        same_day = self.model.NewBoolVar(f'{course1_id}_{course2_id}_same_day')
        self.model.Add(self.vars[course1_id]['day'] == self.vars[course2_id]['day']).OnlyEnforceIf(same_day)
        self.model.Add(self.vars[course1_id]['day'] != self.vars[course2_id]['day']).OnlyEnforceIf(same_day.Not())
        
        # If same day, blocks must not overlap
        overlaps = self.model.NewBoolVar(f'{course1_id}_{course2_id}_overlap')
        self._add_overlap_check(course1_id, course2_id, overlaps)
        
        # If same_day, then NOT overlaps
        self.model.AddImplication(same_day, overlaps.Not())
    
    def _add_overlap_check(self, c1: str, c2: str, overlaps_var):
        """Check if two course blocks overlap"""
        blocks1 = self.vars[c1]['blocks']
        blocks2 = self.vars[c2]['blocks']
        
        # For each combination, check overlap
        overlap_cases = []
        for i, b1 in enumerate(blocks1):
            for j, b2 in enumerate(blocks2):
                if set(b1) & set(b2):  # Overlap exists
                    case = self.model.NewBoolVar(f'{c1}_b{i}_{c2}_b{j}_overlaps')
                    
                    is_b1 = self.model.NewBoolVar(f'{c1}_is_b{i}')
                    self.model.Add(self.vars[c1]['block_idx'] == i).OnlyEnforceIf(is_b1)
                    self.model.Add(self.vars[c1]['block_idx'] != i).OnlyEnforceIf(is_b1.Not())
                    
                    is_b2 = self.model.NewBoolVar(f'{c2}_is_b{j}')
                    self.model.Add(self.vars[c2]['block_idx'] == j).OnlyEnforceIf(is_b2)
                    self.model.Add(self.vars[c2]['block_idx'] != j).OnlyEnforceIf(is_b2.Not())
                    
                    self.model.AddBoolAnd([is_b1, is_b2]).OnlyEnforceIf(case)
                    self.model.AddBoolOr([is_b1.Not(), is_b2.Not()]).OnlyEnforceIf(case.Not())
                    overlap_cases.append(case)
        
        if overlap_cases:
            self.model.AddBoolOr(overlap_cases).OnlyEnforceIf(overlaps_var)
            self.model.AddBoolAnd([c.Not() for c in overlap_cases]).OnlyEnforceIf(overlaps_var.Not())
        else:
            self.model.Add(overlaps_var == 0)
    
    def _extract_solution(self, solver: cp_model.CpSolver) -> List[Dict]:
        """Extract schedule from solved model"""
        schedule = []
        
        for course in self.data.courses:
            course_id = course.id
            
            day_idx = solver.Value(self.vars[course_id]['day'])
            block_idx = solver.Value(self.vars[course_id]['block_idx'])
            room_idx = solver.Value(self.vars[course_id]['room'])
            
            day = DAYS[day_idx]
            block = self.vars[course_id]['blocks'][block_idx]
            room = self.vars[course_id]['rooms'][room_idx]
            
            lecturer_id = self.data.get_course_lecturer(course_id)
            lecturer_name = self.data.lecturer_dict[lecturer_id].name if lecturer_id else "Unknown"
            
            student_groups = self.data.get_course_student_groups(course_id)
            
            # Get time strings
            start_slot = self.data.time_slots[block[0] - 1]
            end_slot = self.data.time_slots[block[-1] - 1]
            
            schedule.append({
                'course_id': course_id,
                'course_code': course.code,
                'course_name': course.name,
                'lecturer': lecturer_name,
                'student_groups': student_groups,
                'room': room.name,
                'day': day,
                'start_slot': block[0],
                'end_slot': block[-1],
                'time': f"{start_slot.start}-{end_slot.end}"
            })
        
        return schedule
