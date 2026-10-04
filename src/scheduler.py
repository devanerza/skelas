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
        
        print("  - Optimization objective (compact schedule)...")
        self._add_objective()
        
        print(f"Total constraints: {len(self.model.Proto().constraints)}")
        print("Solving...")
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 120.0
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
        """Create decision variables + time intervals for each course.

        Timeline encoding (instead of pairwise block-comparison):
        absolute time T = day * 10 + offset(slot), where
        - morning slot s -> offset s-1 (slots 1-5 -> 0..4)
        - afternoon slot s -> offset s   (slots 6-9 -> 6..9)
        - offset 5 = lunch, never occupied by any block
        Course duration == credits, so each course becomes ONE interval
        on a shared 60-unit timeline (6 days x 10 units).
        """
        for course in self.data.courses:
            course_id = course.id

            # Generate valid consecutive blocks for this course
            blocks = generate_consecutive_blocks(course.credits)

            # Get compatible rooms
            compatible_rooms = self.data.get_compatible_rooms(course.room_type_required)
            if not compatible_rooms:
                raise ValueError(f"No compatible rooms for course {course_id} requiring {course.room_type_required}")

            day = self.model.NewIntVar(0, len(DAYS) - 1, f'{course_id}_day')
            block_idx = self.model.NewIntVar(0, len(blocks) - 1, f'{course_id}_block')
            room = self.model.NewIntVar(0, len(compatible_rooms) - 1, f'{course_id}_room')

            # Absolute start on shifted timeline
            offsets = [b[0] - 1 if b[0] <= 5 else b[0] for b in blocks]
            off = self.model.NewIntVar(0, 9, f'{course_id}_off')
            self.model.AddElement(block_idx, offsets, off)
            day10 = self.model.NewIntVar(0, 10 * (len(DAYS) - 1), f'{course_id}_day10')
            self.model.Add(day10 == 10 * day)
            start = self.model.NewIntVar(0, 10 * len(DAYS) - 1, f'{course_id}_start')
            self.model.Add(start == day10 + off)
            end = self.model.NewIntVar(0, 10 * len(DAYS) + 5, f'{course_id}_end')
            self.model.Add(end == start + course.credits)

            # One interval per course (for lecturer / student group NoOverlap)
            interval = self.model.NewIntervalVar(
                start, course.credits, end, f'{course_id}_iv')

            # One OPTIONAL interval per compatible room (presence = room assignment)
            room_intervals = {}
            for idx, r in enumerate(compatible_rooms):
                pres = self.model.NewBoolVar(f'{course_id}_uses_{r.id}')
                self.model.Add(room == idx).OnlyEnforceIf(pres)
                self.model.Add(room != idx).OnlyEnforceIf(pres.Not())
                room_intervals[r.id] = self.model.NewOptionalIntervalVar(
                    start, course.credits, end, pres, f'{course_id}_iv_{r.id}')

            self.vars[course_id] = {
                'day': day,
                'block_idx': block_idx,
                'room': room,
                'blocks': blocks,
                'rooms': compatible_rooms,
                'interval': interval,
                'room_intervals': room_intervals,
            }
    
    def _add_consecutive_slot_constraints(self):
        """Consecutive slots are already enforced by block generation"""
        pass
    
    def _add_lecturer_conflict_constraints(self):
        """Lecturer cannot teach two courses at the same time (AddNoOverlap)"""
        lecturer_courses = {}
        for course in self.data.courses:
            lecturer_id = self.data.get_course_lecturer(course.id)
            if lecturer_id:
                lecturer_courses.setdefault(lecturer_id, []).append(course.id)

        for lecturer_id, course_ids in lecturer_courses.items():
            if len(course_ids) < 2:
                continue
            self.model.AddNoOverlap(
                [self.vars[c]['interval'] for c in course_ids])

    def _add_student_group_conflict_constraints(self):
        """Student group cannot attend two courses at the same time (AddNoOverlap)"""
        group_courses = {}
        for course in self.data.courses:
            for group in self.data.get_course_student_groups(course.id):
                group_courses.setdefault(group, []).append(course.id)

        for group, course_ids in group_courses.items():
            if len(course_ids) < 2:
                continue
            self.model.AddNoOverlap(
                [self.vars[c]['interval'] for c in course_ids])

    def _add_room_conflict_constraints(self):
        """Room cannot host two courses at the same time (AddNoOverlap on
        optional intervals — presence ties interval to room assignment)"""
        room_courses = {}
        for course in self.data.courses:
            for room in self.vars[course.id]['rooms']:
                room_courses.setdefault(room.id, []).append(course.id)

        for room_id, course_ids in room_courses.items():
            if len(course_ids) < 2:
                continue
            self.model.AddNoOverlap(
                [self.vars[c]['room_intervals'][room_id] for c in course_ids])
    
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
                            self.model.Add(self.vars[course_id]['day'] != day_idx).OnlyEnforceIf(is_this_day.Not())
                            self.model.Add(self.vars[course_id]['block_idx'] == block_idx).OnlyEnforceIf(is_this_block)
                            self.model.Add(self.vars[course_id]['block_idx'] != block_idx).OnlyEnforceIf(is_this_block.Not())
                            
                            # Cannot be both this day and this block
                            self.model.AddBoolOr([is_this_day.Not(), is_this_block.Not()])
    
    def _add_objective(self):
        """
        Minimize schedule span:
        1. Number of distinct days used (fewer days = more compact week)
        2. Total start slot index (earlier starts within used days)
        """
        # Day used: day_used[d] = 1 if any course scheduled on day d
        course_ids = [c.id for c in self.data.courses]
        day_used = []
        for d in range(len(DAYS)):
            is_used = self.model.NewBoolVar(f'day_{d}_used')
            # is_used == 1 iff at least one course uses day d
            course_on_day = []
            for c in course_ids:
                on_day = self.model.NewBoolVar(f'{c}_on_day_{d}')
                self.model.Add(self.vars[c]['day'] == d).OnlyEnforceIf(on_day)
                self.model.Add(self.vars[c]['day'] != d).OnlyEnforceIf(on_day.Not())
                course_on_day.append(on_day)
            
            self.model.AddBoolOr(course_on_day).OnlyEnforceIf(is_used)
            self.model.AddBoolAnd([c.Not() for c in course_on_day]).OnlyEnforceIf(is_used.Not())
            day_used.append(is_used)
        
        # Earlier starts: block_idx already ordered morning-first (idx 0 = slot 1)
        start_cost = [self.vars[c]['block_idx'] for c in course_ids]
        
        # Earlier days tie-break: prefer Monday over Friday
        day_cost = [self.vars[c]['day'] for c in course_ids]
        
        # Weight: days dominate, then earlier days, then earlier slots
        self.model.Minimize(100 * sum(day_used) + 10 * sum(day_cost) + sum(start_cost))

    def _add_room_requirement_constraints(self):
        """Course requiring specific room type gets compatible room"""
        # Already handled by filtering compatible rooms in _create_variables
        pass

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
