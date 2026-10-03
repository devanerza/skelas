"""Quick capacity diagnostic for benchmark datasets (not committed logic)."""
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.benchmark import generate_dataset
from src.data_loader import SchedulerData
from src.scheduler import DAYS
from src.utils import generate_consecutive_blocks

for n_c, n_l, n_r in [(50, 12, 8), (80, 16, 8)]:
    d = SchedulerData(str(generate_dataset(n_c, n_l, n_r)))
    print(f"=== {n_c} courses / {n_l} lecturers / {n_r} rooms ===")

    # Lecturer load vs capacity
    load = {}
    for c in d.courses:
        lid = d.get_course_lecturer(c.id)
        load[lid] = load.get(lid, 0) + c.credits
    for lid, need in sorted(load.items(), key=lambda x: -x[1])[:3]:
        avail = d.get_lecturer_availability(lid)
        cap = sum(len(v) for v in avail.values())
        # real capacity = slots per day considering blocks, rough: total free slots
        print(f"  lecturer {lid}: needs {need} slots, free {cap} slots")

    # Group load vs capacity (6 days x 9 = 54)
    gload = {}
    for c in d.courses:
        for g in d.get_course_student_groups(c.id):
            gload[g] = gload.get(g, 0) + c.credits
    for g, need in sorted(gload.items(), key=lambda x: -x[1])[:3]:
        print(f"  group {g}: needs {need} slots, max 54")

    # Room type load vs capacity
    rload = {}
    for c in d.courses:
        rload[c.room_type_required] = rload.get(c.room_type_required, 0) + c.credits
    for t, need in rload.items():
        rooms = [r for r in d.rooms if r.type == t]
        print(f"  {t}: needs {need} slots in {len(rooms)} rooms "
              f"(cap {len(rooms) * 6 * 9})")
