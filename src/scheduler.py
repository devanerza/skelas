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
        self._add_lecturer_conflict_constraints()
        self._add_student_group_conflict_constraints()
        self._add_room_conflict_constraints()
        self._add_lecturer_availability_constraints()
        self._add_room_requirement_constraints()
        
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
        # For all course pairs, if they can use the same room, add conflict
        courses = self.data.courses
        for i in range(len(courses)):
            for j in range(i + 1, len(courses)):
                c1, c2 = courses[i].id, courses[j].id
                
                # Check if courses share compatible rooms
                rooms1 = set(r.id for r in self.vars[c1]['rooms'])
                rooms2 = set(r.id for r in self.vars[c2]['rooms'])
                
                if rooms1 & rooms2:  # If they share rooms
                    # If same day and overlapping slots and same room -> conflict
                    same_day = self.model.NewBoolVar(f'{c1}_{c2}_same_day')
                    self.model.Add(self.vars[c1]['day'] == self.vars[c2]['day']).OnlyEnforceIf(same_day)
                    self.model.Add(self.vars[c1]['day'] != self.vars[c2]['day']).OnlyEnforceIf(same_day.Not())
                    
                    # If same day, check overlap and room
                    # Simplified: if same day and potentially same room, ensure different blocks
                    overlaps = self.model.NewBoolVar(f'{c1}_{c2}_overlap')
                    self._add_overlap_check(c1, c2, overlaps)
                    
                    same_room = self.model.NewBoolVar(f'{c1}_{c2}_same_room')
                    self._add_same_room_check(c1, c2, same_room)
                    
                    # If same_day AND overlaps AND same_room -> INVALID
                    conflict = self.model.NewBoolVar(f'{c1}_{c2}_conflict')
                    self.model.AddBoolAnd([same_day, overlaps, same_room]).OnlyEnforceIf(conflict)
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
        """Ensure two courses don't overlap in time"""
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
                if set(b1) & set(b2):  # Overlap
                    case = self.model.NewBoolVar(f'{c1}_b{i}_{c2}_b{j}_overlaps')
                    
                    is_b1 = self.model.NewBoolVar(f'{c1}_is_b{i}')
                    is_b2 = self.model.NewBoolVar(f'{c2}_is_b{j}')
                    
                    self.model.Add(self.vars[c1]['block_idx'] == i).OnlyEnforceIf(is_b1)
                    self.model.Add(self.vars[c2]['block_idx'] == j).OnlyEnforceIf(is_b2)
                    
                    self.model.AddBoolAnd([is_b1, is_b2]).OnlyEnforceIf(case)
                    overlap_cases.append(case)
        
        if overlap_cases:
            self.model.AddBoolOr(overlap_cases).OnlyEnforceIf(overlaps_var)
            self.model.AddBoolAnd([c.Not() for c in overlap_cases]).OnlyEnforceIf(overlaps_var.Not())
        else:
            self.model.Add(overlaps_var == 0)
    
    def _add_same_room_check(self, c1: str, c2: str, same_room_var):
        """Check if two courses assigned to same room"""
        rooms1 = self.vars[c1]['rooms']
        rooms2 = self.vars[c2]['rooms']
        
        # Find common rooms
        common_room_ids = set(r.id for r in rooms1) & set(r.id for r in rooms2)
        
        if not common_room_ids:
            self.model.Add(same_room_var == 0)
            return
        
        # Check if both courses assigned to same room
        same_cases = []
        for room_id in common_room_ids:
            idx1 = next(i for i, r in enumerate(rooms1) if r.id == room_id)
            idx2 = next(i for i, r in enumerate(rooms2) if r.id == room_id)
            
            case = self.model.NewBoolVar(f'{c1}_{c2}_room_{room_id}')
            
            is_r1 = self.model.NewBoolVar(f'{c1}_room{idx1}')
            is_r2 = self.model.NewBoolVar(f'{c2}_room{idx2}')
            
            self.model.Add(self.vars[c1]['room'] == idx1).OnlyEnforceIf(is_r1)
            self.model.Add(self.vars[c2]['room'] == idx2).OnlyEnforceIf(is_r2)
            
            self.model.AddBoolAnd([is_r1, is_r2]).OnlyEnforceIf(case)
            same_cases.append(case)
        
        if same_cases:
            self.model.AddBoolOr(same_cases).OnlyEnforceIf(same_room_var)
            self.model.AddBoolAnd([c.Not() for c in same_cases]).OnlyEnforceIf(same_room_var.Not())
    
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
