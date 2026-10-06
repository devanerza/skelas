#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.data_loader import SchedulerData
from src.scheduler import CourseScheduler


def main():
    print("=" * 60)
    print("Sistem Penjadwalan Mata Kuliah")
    print("=" * 60)
    print()
    
    print("Memuat data...")
    try:
        data = SchedulerData("data")
        print(f"✓ {len(data.courses)} mata kuliah")
        print(f"✓ {len(data.lecturers)} dosen")
        print(f"✓ {len(data.rooms)} ruangan")
        print(f"✓ {len(data.student_groups)} kelompok mahasiswa")
        print()
    except Exception as e:
        print(f"❌ Gagal memuat data: {e}")
        return 1
    
    print("Inisialisasi scheduler...")
    scheduler = CourseScheduler(data)

    flagged = [ta for ta in data.teaching_assignments if ta.needs_review]
    if flagged:
        print("\n⚠ Penugasan ditandai perlu ditinjau (edit data/teaching_assignments.json):")
        for ta in flagged:
            course = data.course_dict.get(ta.course_id)
            name = course.name if course else ta.course_id
            lecturers = ", ".join(
                data.lecturer_dict[l].name for l in ta.all_lecturer_ids
                if l in data.lecturer_dict)
            print(f"  - {ta.course_id} {name}: {lecturers or '(no lecturer)'}")
        print()
    
    print()
    result = scheduler.schedule()
    
    print()
    print("=" * 60)
    print(f"Status: {result.status}")
    print(f"Waktu penyelesaian: {result.solve_time:.2f} detik")
    print("=" * 60)
    print()
    
    if result.status in ("FEASIBLE", "PARTIAL"):
        if result.status == "PARTIAL":
            print(f"⚠ {result.message}\n")
        else:
            print("✅ Jadwal valid ditemukan!\n")
        
        # Ekspor untuk validasi independen: python validate_schedule.py schedule.json
        out_path = Path(__file__).parent / "schedule.json"
        out_path.write_text(
            json.dumps(result.schedule, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Diekspor: {out_path.name}")
        print("Validasi: python validate_schedule.py schedule.json\n")
        
        # Kelompokkan per hari
        by_day = {}
        for entry in result.schedule:
            day = entry['day']
            if day not in by_day:
                by_day[day] = []
            by_day[day].append(entry)
        
        # Cetak jadwal
        hari_id = {"MONDAY": "SENIN", "TUESDAY": "SELASA", "WEDNESDAY": "RABU",
                   "THURSDAY": "KAMIS", "FRIDAY": "JUMAT", "SATURDAY": "SABTU"}
        for day in ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]:
            if day not in by_day:
                continue
            
            print(f"\n{hari_id[day]}")
            print("-" * 60)
            
            # Urutkan per slot awal
            entries = sorted(by_day[day], key=lambda x: x['start_slot'])
            
            for entry in entries:
                print(f"{entry['time']:15} | {entry['room']:15} | {entry['course_code']} - {entry['course_name']}")
                print(f"{' ':15} | {' ':15} | Dosen: {entry['lecturer']}")
                print(f"{' ':15} | {' ':15} | Kelompok: {', '.join(entry['student_groups'])}")
                print()
        
        if result.dropped:
            print("\n" + "=" * 60)
            print(f"DILEWATI (tidak feasible): {len(result.dropped)} mata kuliah")
            print("=" * 60)
            for entry in result.dropped:
                meta = (f"{entry.get('credits', 0)} SKS · "
                        f"{entry.get('room_type_required', '')} · "
                        f"Ruang: {', '.join(entry.get('rooms', []))} · "
                        f"Dosen: {', '.join(entry.get('lecturers', []))} · "
                        f"Kelompok: {', '.join(entry.get('student_groups', []))}")
                print(f"  ✗ {entry['course_code']} - {entry['course_name']}")
                print(f"    {meta}")
                print(f"    Alasan: {entry['reason']}")
                if entry.get('suggestion'):
                    print(f"    Saran: {entry['suggestion']}")
                print()
            print("Diagnosis per mata kuliah (perbaiki file data, lalu jalankan ulang):")
            for i, e in enumerate(scheduler.diagnose_dropped(result.dropped), 1):
                print(f"{i}. {e['course_name']}: {e['reason']}")
                if e.get('suggestion'):
                    print(f"   Saran: {e['suggestion']}")
            print()
        
        return 0
    
    elif result.status == "INFEASIBLE":
        print(f"❌ {result.message}")
        print("\nDiagnosis (penyebab konkret dari data Anda):")
        for i, finding in enumerate(scheduler.diagnose(), 1):
            print(f"{i}. {finding}")
        return 1
    
    else:
        print(f"⚠ {result.message}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
