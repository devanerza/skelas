"""
Course Scheduling Engine using OR-Tools CP-SAT
"""
from ortools.sat.python import cp_model
from typing import Dict, List
import time

from .data_loader import SchedulerData
from .utils import generate_consecutive_blocks, slots_overlap


DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]
DAY_ID = {"MONDAY": "Senin", "TUESDAY": "Selasa", "WEDNESDAY": "Rabu",
          "THURSDAY": "Kamis", "FRIDAY": "Jumat", "SATURDAY": "Sabtu"}


class ScheduleResult:
    def __init__(self, status: str, solve_time: float, schedule: List[Dict] = None,
                 message: str = "", dropped: List[Dict] = None):
        self.status = status
        self.solve_time = solve_time
        self.schedule = schedule or []
        self.message = message
        self.dropped = dropped or []


class _ProgressCallback(cp_model.CpSolverSolutionCallback):
    """Prints each improving solution so long solves show life."""

    def __init__(self):
        super().__init__()
        self._n = 0

    def on_solution_callback(self):
        self._n += 1
        print(f"  solusi #{self._n} (objektif {self.ObjectiveValue():.0f})",
              flush=True)


class CourseScheduler:
    def __init__(self, data: SchedulerData):
        self.data = data
        self.model = cp_model.CpModel()
        self.vars = {}

    def schedule(self) -> ScheduleResult:
        """Build the reified model: every course gets a `sched` bool.
        Objective maximizes scheduled courses first — the solver itself
        decides which courses must be skipped when all cannot fit."""
        start_time = time.time()

        print("Membuat variabel keputusan...")
        self._create_variables()

        print("Menambahkan batasan...")
        print("  - Batasan konflik dosen...")
        self._add_lecturer_conflict_constraints()

        print("  - Batasan konflik kelompok mahasiswa...")
        self._add_student_group_conflict_constraints()

        print("  - Batasan konflik ruangan...")
        self._add_room_conflict_constraints()

        print("  - Batasan ketersediaan dosen...")
        self._add_lecturer_availability_constraints()

        print("  - Fungsi objektif (maksimalkan yang terjadwal, lalu padatkan)...")
        self._add_objective()

        print(f"Total batasan: {len(self.model.Proto().constraints)}", flush=True)
        print("Memecahkan (berbatas waktu, solusi terbaik tetap ditampilkan)...",
              flush=True)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 30.0
        status = solver.Solve(self.model, _ProgressCallback())

        solve_time = time.time() - start_time

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return self._build_result(solver, solve_time)
        return ScheduleResult(
            status="UNKNOWN",
            solve_time=solve_time,
            message="Solver tidak menemukan solusi dalam waktu yang tersedia"
        )

    def _build_result(self, solver: cp_model.CpSolver,
                      solve_time: float) -> ScheduleResult:
        """Map solved model onto FEASIBLE / PARTIAL / INFEASIBLE and
        explain every skipped course against the produced schedule."""
        scheduled_ids = [c.id for c in self.data.courses
                         if solver.Value(self.vars[c.id]['sched'])]
        dropped_ids = [c.id for c in self.data.courses
                       if c.id not in scheduled_ids]

        if not scheduled_ids:
            return ScheduleResult(
                status="INFEASIBLE",
                solve_time=solve_time,
                message="Tidak ada mata kuliah yang bisa dijadwalkan dengan batasan saat ini")

        schedule = self._extract_solution(solver, scheduled_ids)
        dropped = [self._drop_reason(course_id, schedule)
                   for course_id in dropped_ids]

        if dropped:
            message = (f"Jadwal parsial: {len(schedule)} dari "
                       f"{len(self.data.courses)} mata kuliah terjadwal, "
                       f"{len(dropped)} dilewati karena tidak feasible")
        else:
            message = "Jadwal valid ditemukan"
        return ScheduleResult(
            status="PARTIAL" if dropped else "FEASIBLE",
            solve_time=solve_time,
            schedule=schedule,
            message=message,
            dropped=dropped)

    @staticmethod
    def _slots_free(day: str, block: List[int], occupied: List[Dict]) -> bool:
        return not any(
            e['day'] == day and
            slots_overlap(list(range(block[0], block[-1] + 1)),
                          list(range(e['start_slot'], e['end_slot'] + 1)))
            for e in occupied)

    def _drop_reason(self, course_id: str, scheduled: List[Dict]) -> Dict:
        """Build a diagnosis card: metadata + aggregated blockers + suggestion.

        Structural failures (no room type, no valid block from availability)
        return early; every other blocker is COLLECTED so the card shows all
        of them, not just the first.
        """
        course = self.data.course_dict[course_id]
        blocks = generate_consecutive_blocks(course.credits)
        lecturers = self.data.get_course_lecturers(course_id)
        groups = self.data.get_course_student_groups(course_id)
        compatible = self.data.get_compatible_rooms(course.room_type_required)
        card = {
            'course_id': course_id,
            'course_code': course.code,
            'course_name': course.name,
            'credits': course.credits,
            'room_type_required': course.room_type_required,
            'rooms': [r.name for r in compatible],
            'lecturers': [self.data.lecturer_dict[l].name for l in lecturers
                          if l in self.data.lecturer_dict],
            'student_groups': groups,
        }

        if not compatible:
            card['reason'] = (f"Tidak ada ruangan bertipe "
                              f"{course.room_type_required}")
            card['suggestion'] = "Tambahkan ruangan di data/rooms.json"
            return card

        options = [
            (d, b) for d in DAYS for b in blocks
            if all(d not in (self.data.get_lecturer_availability(l) or {})
                   or set(b).issubset(
                       set(self.data.get_lecturer_availability(l)[d]))
                   for l in lecturers)]
        if not options:
            name = (self.data.lecturer_dict[lecturers[0]].name
                    if lecturers else "(tanpa dosen)")
            card['reason'] = (f"Ketersediaan {name} tidak menyisakan blok "
                              f"{course.credits} SKS")
            card['suggestion'] = (
                "Perluas data/lecturer_availability.json atau ganti dosen "
                "di data/teaching_assignments.json")
            return card

        blockers = []
        for lecturer_id in lecturers:
            occupied = [e for e in scheduled
                        if lecturer_id in e.get('lecturer_ids', [])]
            if occupied and not any(self._slots_free(d, b, occupied)
                                    for d, b in options):
                name = self.data.lecturer_dict[lecturer_id].name
                blockers.append((
                    f"Dosen {name} sudah penuh di semua slot valid",
                    "Alihkan satu mata kuliah di data/teaching_assignments.json "
                    "atau longgarkan data/lecturer_availability.json"))

        for group in groups:
            occupied = [e for e in scheduled
                        if group in e.get('student_groups', [])]
            if occupied and not any(self._slots_free(d, b, occupied)
                                    for d, b in options):
                blockers.append((
                    f"Kelompok {group} tidak punya jendela bebas "
                    f"{course.credits} SKS tersisa minggu ini",
                    "Pindahkan satu mata kuliah kelompok ini di "
                    "data/course_enrollments.json"))

        room_free = any(
            any(self._slots_free(d, b,
                                 [e for e in scheduled if e['room'] == r.name])
                for d, b in options)
            for r in compatible)
        if not room_free:
            blockers.append((
                f"Semua ruangan tipe {course.room_type_required} terblokir "
                "di setiap slot valid",
                "Tambah ruangan di data/rooms.json"))

        if blockers:
            card['reason'] = "Blokir: " + "; ".join(t for t, _ in blockers)
            card['suggestion'] = blockers[0][1]
        else:
            card['reason'] = (
                f"Setiap resource bebas di satu opsi, namun tidak pernah "
                f"bersamaan — hanya {len(options)} opsi (hari, blok) valid "
                "tersisa")
            card['suggestion'] = (
                "Alihkan satu tugas di data/teaching_assignments.json atau "
                "longgarkan ketersediaan di data/lecturer_availability.json")

        concrete = self._suggest(course_id, options, scheduled)
        if concrete:
            card['suggestion'] = concrete
        return card

    def _shares(self, entry: Dict, course_id: str) -> bool:
        """True if a scheduled entry shares lecturer/group/room with course."""
        course = self.data.course_dict[course_id]
        lecturers = set(self.data.get_course_lecturers(course_id))
        groups = set(self.data.get_course_student_groups(course_id))
        room_names = {r.name for r in
                      self.data.get_compatible_rooms(course.room_type_required)}
        return (bool(lecturers & set(entry.get('lecturer_ids', [])))
                or bool(groups & set(entry.get('student_groups', [])))
                or entry.get('room') in room_names)

    def _suggest(self, course_id: str, options: List,
                 scheduled: List[Dict]) -> str:
        """Counterfactual probe: smallest set of scheduled courses whose
        eviction frees one valid (day, block). Pure Python, no re-solve."""
        candidates = [e for e in scheduled
                      if e['course_id'] != course_id
                      and self._shares(e, course_id)]
        for day, block in options:
            needed = [e for e in candidates
                      if e['day'] == day and
                      slots_overlap(list(range(block[0], block[-1] + 1)),
                                    list(range(e['start_slot'],
                                               e['end_slot'] + 1)))]
            if needed and self._slots_free(
                    day, block,
                    [e for e in scheduled if e not in needed]):
                names = ", ".join(dict.fromkeys(
                    e['course_name'] for e in needed))
                return (f"Bebaskan {names} dari {DAY_ID[day]} slot "
                        f"{block[0]}–{block[-1]} (atau pindahkan salah satu "
                        "ke hari lain)")
        return ""

    def diagnose_dropped(self, dropped: List[Dict]) -> List[Dict]:
        """Diagnosis cards per skipped course (already structured)."""
        return dropped

    def diagnose(self) -> List[str]:
        """Temuan konkret berbasis data ketika model tidak feasible.

        Setiap temuan menyebut nama pelaku dan file yang perlu diedit,
        sehingga pengguna tidak perlu menebak penyebab umumnya.
        """
        findings = []
        week_slots = len(DAYS) * 9  # 9 slot per hari

        # 1. Mata kuliah yang ketersediaan dosen menyisakan blok tidak valid
        for course in self.data.courses:
            for lecturer_id in self.data.get_course_lecturers(course.id):
                availability = self.data.get_lecturer_availability(lecturer_id)
                if not availability:
                    continue
                lecturer_name = self.data.lecturer_dict[lecturer_id].name
                blocks = generate_consecutive_blocks(course.credits)
                options = sum(
                    1 for day_name in DAYS
                    if day_name in availability
                    for block in blocks
                    if set(block).issubset(set(availability[day_name])))
                if options == 0:
                    findings.append(
                        f"{course.name}: TIDAK ADA slot valid — ketersediaan dosen "
                        f"{lecturer_name} meniadakan semua blok {course.credits} SKS. "
                        "Perbaiki: perluas data/lecturer_availability.json atau "
                        "ganti dosen di data/teaching_assignments.json")
                elif options <= 4:
                    findings.append(
                        f"{course.name}: hanya {options} opsi (hari, blok) valid dari "
                        f"ketersediaan dosen {lecturer_name} — risiko bentrok tinggi. "
                        "Perbaiki: perluas data/lecturer_availability.json")

        # 2. Beban dosen vs ketersediaan (cek statis, lalu probe solver)
        lecturer_courses = {}
        for course in self.data.courses:
            for lecturer_id in self.data.get_course_lecturers(course.id):
                lecturer_courses.setdefault(lecturer_id, []).append(course)

        for lecturer_id, courses in sorted(lecturer_courses.items()):
            availability = self.data.get_lecturer_availability(lecturer_id) or {}
            if not availability or len(courses) < 2:
                continue
            lecturer_name = self.data.lecturer_dict[lecturer_id].name
            free_slots = sum(len(v) for v in availability.values())
            load = sum(c.credits for c in courses)
            if load > free_slots:
                findings.append(
                    f"Dosen {lecturer_name}: mengajar {load} SKS tapi hanya punya "
                    f"{free_slots} slot bebas ({len(availability)} hari) — mustahil "
                    "sudah sebelum ada bentrok. Perbaiki: perluas "
                    "data/lecturer_availability.json atau alihkan satu mata kuliah "
                    "di data/teaching_assignments.json")
            elif self._probe_lecturer_fit(courses, availability):
                findings.append(
                    f"Dosen {lecturer_name}: {load} SKS dalam {free_slots} slot bebas "
                    "tidak bisa disusun sebagai blok berturut-turut — terbukti tidak "
                    "feasible sendirian. Perbaiki: perluas "
                    "data/lecturer_availability.json atau alihkan satu mata kuliah "
                    "di data/teaching_assignments.json")

        # 3. Beban kelompok mahasiswa
        group_load = {}
        for course in self.data.courses:
            for group in self.data.get_course_student_groups(course.id):
                group_load[group] = group_load.get(group, 0) + course.credits
        for group, load in sorted(group_load.items()):
            if load > week_slots - 6:
                findings.append(
                    f"Kelompok {group}: {load} SKS dari {week_slots} slot mingguan — "
                    "sisa ruang sangat sempit untuk bentrok. Perbaiki: pindahkan satu "
                    "mata kuliah ke kelompok lain di data/course_enrollments.json")

        # 4. Kapasitas ruangan
        type_demand = {}
        for course in self.data.courses:
            type_demand[course.room_type_required] = \
                type_demand.get(course.room_type_required, 0) + course.credits
        for room_type, demand in sorted(type_demand.items()):
            rooms = [r for r in self.data.rooms if r.type == room_type]
            capacity = len(rooms) * week_slots
            if not rooms:
                findings.append(
                    f"Tidak ada ruangan bertipe {room_type}. "
                    "Perbaiki: tambahkan di data/rooms.json")
            elif demand > capacity:
                findings.append(
                    f"Ruangan [{room_type}]: permintaan {demand} SKS MELEBIHI "
                    f"kapasitas {capacity} slot ({len(rooms)} ruangan). Perbaiki: "
                    "tambah ruangan di data/rooms.json atau longgarkan "
                    "room_type_required di data/courses.json")
            elif demand > capacity * 0.9:
                findings.append(
                    f"Ruangan [{room_type}]: permintaan {demand} SKS vs kapasitas "
                    f"{capacity} slot ({len(rooms)} ruangan) — hampir penuh, "
                    "fragmentasi mudah membuatnya gagal. Perbaiki: tambah satu "
                    "ruangan di data/rooms.json")

        if not findings:
            findings.append(
                "Tidak ada dosen, kelompok, atau ruangan yang melanggar batasan "
                "sendirian — bentrok berasal dari kombinasinya. Uji satu per satu: "
                "longgarkan seluruh ketersediaan di data/lecturer_availability.json "
                "(atau kosongkan room_type_required di data/courses.json), jalankan "
                "ulang, dan lihat perubahan mana yang membuatnya feasible.")
        return findings

    def _probe_lecturer_fit(self, courses: List, availability: Dict) -> bool:
        """True only if this lecturer's courses provably cannot fit their
        availability (sub-model: courses + availability + no-overlap)."""
        model = cp_model.CpModel()
        intervals = []
        for course in courses:
            blocks = generate_consecutive_blocks(course.credits)
            day = model.NewIntVar(0, len(DAYS) - 1, f'{course.id}_pday')
            block_idx = model.NewIntVar(0, len(blocks) - 1, f'{course.id}_pblock')
            offsets = [b[0] - 1 for b in blocks]
            off = model.NewIntVar(0, 9, f'{course.id}_poff')
            model.AddElement(block_idx, offsets, off)
            start = model.NewIntVar(0, 10 * len(DAYS) - 1, f'{course.id}_pstart')
            model.Add(start == 10 * day + off)
            end = model.NewIntVar(0, 10 * len(DAYS) + 5, f'{course.id}_pend')
            model.Add(end == start + course.credits)
            intervals.append(
                model.NewIntervalVar(start, course.credits, end, f'{course.id}_piv'))

            for day_idx, day_name in enumerate(DAYS):
                if day_name not in availability:
                    model.Add(day != day_idx)
                else:
                    available = set(availability[day_name])
                    for k, block in enumerate(blocks):
                        if not set(block).issubset(available):
                            is_day = model.NewBoolVar(f'{course.id}_pd{day_idx}')
                            is_block = model.NewBoolVar(f'{course.id}_pb{day_idx}_{k}')
                            model.Add(day == day_idx).OnlyEnforceIf(is_day)
                            model.Add(day != day_idx).OnlyEnforceIf(is_day.Not())
                            model.Add(block_idx == k).OnlyEnforceIf(is_block)
                            model.Add(block_idx != k).OnlyEnforceIf(is_block.Not())
                            model.AddBoolOr([is_day.Not(), is_block.Not()])

        model.AddNoOverlap(intervals)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5.0
        return solver.Solve(model) == cp_model.INFEASIBLE

    def _create_variables(self):
        """Create decision variables + time intervals for each course.

        Timeline encoding (instead of pairwise block-comparison):
        absolute time T = day * 10 + offset(slot), where
        slot s -> offset s-1 (slots 1-9 -> 0..8)
        Course duration == credits, so each course becomes ONE interval
        on a shared 60-unit timeline (6 days x 10 units).

        Each course also gets a `sched` bool: 1 = include in schedule,
        0 = skipped (all its constraints are guarded by it).
        """
        for course in self.data.courses:
            course_id = course.id

            # Generate valid consecutive blocks for this course
            blocks = generate_consecutive_blocks(course.credits)

            # Get compatible rooms
            compatible_rooms = self.data.get_compatible_rooms(course.room_type_required)
            room_domain = compatible_rooms or self.data.rooms
            sched = self.model.NewBoolVar(f'{course_id}_sched')
            if not compatible_rooms:
                # Unplaceable by design: force skip, _drop_reason explains.
                self.model.Add(sched == 0)
            day = self.model.NewIntVar(0, len(DAYS) - 1, f'{course_id}_day')
            block_idx = self.model.NewIntVar(0, len(blocks) - 1, f'{course_id}_block')
            room = self.model.NewIntVar(0, len(room_domain) - 1, f'{course_id}_room')

            # Absolute start on shifted timeline
            offsets = [b[0] - 1 for b in blocks]
            off = self.model.NewIntVar(0, 9, f'{course_id}_off')
            self.model.AddElement(block_idx, offsets, off)
            day10 = self.model.NewIntVar(0, 10 * (len(DAYS) - 1), f'{course_id}_day10')
            self.model.Add(day10 == 10 * day)
            start = self.model.NewIntVar(0, 10 * len(DAYS) - 1, f'{course_id}_start')
            self.model.Add(start == day10 + off)
            end = self.model.NewIntVar(0, 10 * len(DAYS) + 5, f'{course_id}_end')
            self.model.Add(end == start + course.credits)

            # One OPTIONAL interval per course (presence = sched): skipped
            # courses never collide in lecturer/group NoOverlap.
            interval = self.model.NewOptionalIntervalVar(
                start, course.credits, end, sched, f'{course_id}_iv')

            # One OPTIONAL interval per compatible room (presence = both
            # scheduled AND assigned to this room)
            room_intervals = {}
            for idx, r in enumerate(room_domain):
                pres = self.model.NewBoolVar(f'{course_id}_uses_{r.id}')
                self.model.Add(pres <= sched)
                self.model.Add(room == idx).OnlyEnforceIf(pres)
                # When scheduled: pres <-> (room == idx). When skipped: free.
                self.model.Add(room != idx).OnlyEnforceIf([pres.Not(), sched])
                room_intervals[r.id] = self.model.NewOptionalIntervalVar(
                    start, course.credits, end, pres, f'{course_id}_iv_{r.id}')

            self.vars[course_id] = {
                'sched': sched,
                'day': day,
                'block_idx': block_idx,
                'room': room,
                'blocks': blocks,
                'rooms': room_domain,
                'interval': interval,
                'room_intervals': room_intervals,
            }

    def _add_lecturer_conflict_constraints(self):
        """Lecturer cannot teach two courses at the same time (AddNoOverlap).

        Team teaching: every lecturer of a course gets that course's optional
        interval, so all co-lecturers are conflict-checked against their
        other courses. Skipped courses (sched=0) drop out of the NoOverlap.
        """
        lecturer_courses = {}
        for course in self.data.courses:
            for lecturer_id in self.data.get_course_lecturers(course.id):
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
        """Course can only be scheduled during ALL its lecturers' available time"""
        for course in self.data.courses:
            for lecturer_id in self.data.get_course_lecturers(course.id):
                self._add_availability_for_lecturer(course, lecturer_id)

    def _add_availability_for_lecturer(self, course, lecturer_id: str):
        availability = self.data.get_lecturer_availability(lecturer_id)
        if not availability:
            return

        course_id = course.id
        sched = self.vars[course_id]['sched']
        blocks = self.vars[course_id]['blocks']
        suffix = f'_{lecturer_id}'

        # For each (day, block) combination, check if lecturer is available
        for day_idx, day_name in enumerate(DAYS):
            if day_name not in availability:
                # Lecturer not available on this day (only when scheduled)
                self.model.Add(self.vars[course_id]['day'] != day_idx) \
                    .OnlyEnforceIf(sched)
            else:
                available_slots = set(availability[day_name])

                # For each block, check if all slots are available
                for block_idx, block in enumerate(blocks):
                    if not set(block).issubset(available_slots):
                        # This block not available on this day
                        is_this_day = self.model.NewBoolVar(f'{course_id}_day{day_idx}{suffix}')
                        is_this_block = self.model.NewBoolVar(f'{course_id}_block{block_idx}{suffix}')

                        # Deactivated entirely when the course is skipped
                        self.model.Add(self.vars[course_id]['day'] == day_idx) \
                            .OnlyEnforceIf([is_this_day, sched])
                        self.model.Add(self.vars[course_id]['day'] != day_idx) \
                            .OnlyEnforceIf([is_this_day.Not(), sched])
                        self.model.Add(self.vars[course_id]['block_idx'] == block_idx) \
                            .OnlyEnforceIf([is_this_block, sched])
                        self.model.Add(self.vars[course_id]['block_idx'] != block_idx) \
                            .OnlyEnforceIf([is_this_block.Not(), sched])

                        # Cannot be both this day and this block
                        self.model.AddBoolOr([is_this_day.Not(), is_this_block.Not()]) \
                            .OnlyEnforceIf(sched)

    def _add_objective(self):
        """
        1. Maximize the number of scheduled courses (dominant term)
        2. Minimize schedule span: distinct days used, earlier days/slots
        """
        course_ids = list(self.vars.keys())
        sched_vars = [self.vars[c]['sched'] for c in course_ids]

        # Day used: day_used[d] = 1 if any scheduled course uses day d
        day_used = []
        for d in range(len(DAYS)):
            is_used = self.model.NewBoolVar(f'day_{d}_used')
            course_on_day = []
            for c in course_ids:
                on_day = self.model.NewBoolVar(f'{c}_on_day_{d}')
                self.model.Add(self.vars[c]['day'] == d).OnlyEnforceIf(
                    [on_day, self.vars[c]['sched']])
                self.model.Add(self.vars[c]['day'] != d).OnlyEnforceIf(
                    [on_day.Not(), self.vars[c]['sched']])
                course_on_day.append(on_day)

            self.model.AddBoolOr(course_on_day).OnlyEnforceIf(is_used)
            self.model.AddBoolAnd([c.Not() for c in course_on_day]) \
                .OnlyEnforceIf(is_used.Not())
            day_used.append(is_used)

        # Earlier starts: block_idx already ordered morning-first (idx 0 = slot 1)
        start_cost = [self.vars[c]['block_idx'] for c in course_ids]

        # Earlier days tie-break: prefer Monday over Friday
        day_cost = [self.vars[c]['day'] for c in course_ids]

        # Weight: scheduled count dominates, then days, earlier days, slots
        self.model.Maximize(
            1_000_000 * sum(sched_vars)
            - 100 * sum(day_used) - 10 * sum(day_cost) - sum(start_cost))

    def _extract_solution(self, solver: cp_model.CpSolver,
                          scheduled_ids: List[str]) -> List[Dict]:
        """Extract schedule from solved model (scheduled courses only)"""
        schedule = []

        for course in self.data.courses:
            if course.id not in scheduled_ids:
                continue
            course_id = course.id

            day_idx = solver.Value(self.vars[course_id]['day'])
            block_idx = solver.Value(self.vars[course_id]['block_idx'])
            room_idx = solver.Value(self.vars[course_id]['room'])

            day = DAYS[day_idx]
            block = self.vars[course_id]['blocks'][block_idx]
            room = self.vars[course_id]['rooms'][room_idx]

            lecturer_ids = self.data.get_course_lecturers(course_id)
            lecturer_name = " / ".join(
                self.data.lecturer_dict[l].name for l in lecturer_ids
            ) if lecturer_ids else "Unknown"

            student_groups = self.data.get_course_student_groups(course_id)

            # Get time strings
            start_slot = self.data.time_slots[block[0] - 1]
            end_slot = self.data.time_slots[block[-1] - 1]

            schedule.append({
                'course_id': course_id,
                'course_code': course.code,
                'course_name': course.name,
                'lecturer': lecturer_name,
                'lecturer_ids': lecturer_ids,
                'student_groups': student_groups,
                'room': room.name,
                'day': day,
                'start_slot': block[0],
                'end_slot': block[-1],
                'time': f"{start_slot.start}-{end_slot.end}"
            })

        return schedule
