#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.data_loader import SchedulerData
from src.scheduler import CourseScheduler


def main():
    print("=" * 60)
    print("Academic Course Scheduling System")
    print("=" * 60)
    print()
    
    print("Loading data...")
    try:
        data = SchedulerData("data")
        print(f"✓ Loaded {len(data.courses)} courses")
        print(f"✓ Loaded {len(data.lecturers)} lecturers")
        print(f"✓ Loaded {len(data.rooms)} rooms")
        print(f"✓ Loaded {len(data.student_groups)} student groups")
        print()
    except Exception as e:
        print(f"❌ Failed to load data: {e}")
        return 1
    
    print("Initializing scheduler...")
    scheduler = CourseScheduler(data)
    
    print()
    result = scheduler.schedule()
    
    print()
    print("=" * 60)
    print(f"Status: {result.status}")
    print(f"Solve time: {result.solve_time:.2f}s")
    print("=" * 60)
    print()
    
    if result.status == "FEASIBLE":
        print("✅ Valid schedule found!\n")
        
        # Export for independent validation: python validate_schedule.py schedule.json
        out_path = Path(__file__).parent / "schedule.json"
        out_path.write_text(
            json.dumps(result.schedule, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Exported: {out_path.name}")
        print("Validate: python validate_schedule.py schedule.json\n")
        
        # Group by day
        by_day = {}
        for entry in result.schedule:
            day = entry['day']
            if day not in by_day:
                by_day[day] = []
            by_day[day].append(entry)
        
        # Print schedule
        for day in ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]:
            if day not in by_day:
                continue
            
            print(f"\n{day}")
            print("-" * 60)
            
            # Sort by start slot
            entries = sorted(by_day[day], key=lambda x: x['start_slot'])
            
            for entry in entries:
                print(f"{entry['time']:15} | {entry['room']:15} | {entry['course_code']} - {entry['course_name']}")
                print(f"{' ':15} | {' ':15} | Lecturer: {entry['lecturer']}")
                print(f"{' ':15} | {' ':15} | Groups: {', '.join(entry['student_groups'])}")
                print()
        
        return 0
    
    elif result.status == "INFEASIBLE":
        print(f"❌ {result.message}")
        print("\nPossible causes:")
        print("- Conflicting lecturer availability")
        print("- Insufficient rooms")
        print("- Over-constrained student groups")
        print("\nSuggestions:")
        print("- Check lecturer_availability.json")
        print("- Add more rooms or relax room requirements")
        print("- Review course enrollments for conflicts")
        return 1
    
    else:
        print(f"⚠ {result.message}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
